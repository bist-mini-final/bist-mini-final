#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/../.." && pwd)"
export PATH="${PROJECT_ROOT}/.tools/bin:${PATH}"
CLUSTER_NAME="${K3D_CLUSTER_NAME:-bist-local}"
NAMESPACE="bist-batch"
QUEUE_NAME="${KUBERNETES_INGESTION_QUEUE:-excel-ingestion}"
WORKER_IMAGE="${KUBERNETES_WORKER_IMAGE:-bist-workflow-worker:local}"
KEDA_VERSION="${KEDA_VERSION:-2.20.2}"
ACTION="${1:-all}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "필수 명령을 찾을 수 없습니다: $1" >&2
    exit 1
  fi
}

check_tools() {
  require_command docker
  require_command k3d
  require_command kubectl
  require_command helm
  require_command python3
  if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon이 실행 중이 아닙니다." >&2
    exit 1
  fi
  if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    echo ".venv가 없습니다. 먼저 ./setup.sh를 실행하세요." >&2
    exit 1
  fi
}

env_value() {
  "${PROJECT_ROOT}/.venv/bin/python" - "$PROJECT_ROOT" "$1" <<'PY'
import sys
from pathlib import Path
import dotenv
root, key = Path(sys.argv[1]), sys.argv[2]
values = dotenv.dotenv_values(root / ".env")
print(values.get(key) or "")
PY
}

config_value() {
  local key="$1" default_value="$2" configured_value current_value
  current_value="${!key:-}"
  configured_value="$(env_value "${key}")"
  echo "${current_value:-${configured_value:-${default_value}}}"
}

load_configuration() {
  QUEUE_NAME="$(config_value KUBERNETES_INGESTION_QUEUE excel-ingestion)"
}

database_is_local() {
  local pg_url
  pg_url="$(config_value PGVECTOR_URL postgresql://postgres:postgres@localhost:5432/rag_flow)"
  "${PROJECT_ROOT}/.venv/bin/python" - "${pg_url}" <<'PY'
import sys
from urllib.parse import urlsplit
host = (urlsplit(sys.argv[1]).hostname or "").lower()
raise SystemExit(0 if host in {"localhost", "127.0.0.1", "::1"} else 1)
PY
}

start_database() {
  if database_is_local; then
    docker compose -f "${PROJECT_ROOT}/deploy/db/docker-compose.yml" up -d --wait
  else
    # A remote PGVECTOR_URL makes the local container unnecessary. Preserve
    # its named volume so switching back to local does not lose data.
    docker compose -f "${PROJECT_ROOT}/deploy/db/docker-compose.yml" down
  fi
  (
    cd "${PROJECT_ROOT}"
    .venv/bin/python -c \
      "from backend.storage.db_manager import DatabaseManager; assert DatabaseManager().ensure_schema()"
  )
}

ensure_cluster() {
  if k3d cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -qx "${CLUSTER_NAME}"; then
    if [[ "$(k3d cluster list --no-headers | awk -v name="${CLUSTER_NAME}" '$1 == name {print $2}')" != "1/1" ]]; then
      k3d cluster start "${CLUSTER_NAME}" >/dev/null
    fi
  else
    k3d cluster create "${CLUSTER_NAME}" \
      --servers 1 \
      --agents 0 \
      --wait \
      --k3s-arg "--disable=traefik@server:0" \
      --volume "${PROJECT_ROOT}/data:/mnt/bist-data@server:0"
  fi
  kubectl config use-context "k3d-${CLUSTER_NAME}" >/dev/null
  if docker inspect bist-pgvector >/dev/null 2>&1 \
    && ! docker inspect bist-pgvector \
      --format '{{json .NetworkSettings.Networks}}' | grep -q "\"k3d-${CLUSTER_NAME}\""; then
    docker network connect "k3d-${CLUSTER_NAME}" bist-pgvector
  fi
}

install_control_plane() {
  helm repo add kedacore https://kedacore.github.io/charts --force-update >/dev/null
  helm repo update kedacore >/dev/null
  helm upgrade --install keda kedacore/keda \
    --version "${KEDA_VERSION}" \
    --namespace keda \
    --create-namespace \
    --hide-notes \
    --wait \
    --timeout 5m
  if ! kubectl -n kube-system get deployment metrics-server >/dev/null 2>&1; then
    echo "k3s Metrics Server가 없어 공식 Helm chart로 설치합니다."
    helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ --force-update >/dev/null
    helm repo update metrics-server >/dev/null
    helm upgrade --install metrics-server metrics-server/metrics-server \
      --namespace kube-system \
      --set 'args[0]=--kubelet-insecure-tls' \
      --wait \
      --timeout 5m
  fi
  kubectl wait --for=condition=Available deployment/keda-operator \
    --namespace keda --timeout=180s
  kubectl wait --for=condition=Available deployment/metrics-server \
    --namespace kube-system --timeout=180s
}

build_worker() {
  DOCKER_BUILDKIT=1 docker build \
    --target runtime \
    -f "${PROJECT_ROOT}/jobs/workflow_worker/Dockerfile" \
    -t "${WORKER_IMAGE}" \
    "${PROJECT_ROOT}"
  k3d image import "${WORKER_IMAGE}" --cluster "${CLUSTER_NAME}"
}

cluster_database_url() {
  local source_url="$1"
  "${PROJECT_ROOT}/.venv/bin/python" - "$source_url" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit
parts = urlsplit(sys.argv[1])
host = parts.hostname or "localhost"
if host not in {"localhost", "127.0.0.1", "::1"}:
    print(sys.argv[1])
    raise SystemExit
userinfo = ""
if parts.username is not None:
    userinfo = parts.username
    if parts.password is not None:
        userinfo += ":" + parts.password
    userinfo += "@"
print(urlunsplit((parts.scheme, f"{userinfo}bist-pgvector.bist-batch.svc.cluster.local:5432", parts.path, parts.query, parts.fragment)))
PY
}

apply_workload() {
  local pg_url openai_key openai_base cluster_pg_url connection_hash previous_connection_hash scaledjob_existed max_jobs configured_max_jobs database_endpoint
  pg_url="$(config_value PGVECTOR_URL postgresql://postgres:postgres@localhost:5432/rag_flow)"
  openai_key="$(config_value OPENAI_API_KEY '')"
  openai_base="$(config_value OPENAI_BASE_URL https://api.openai.com/v1)"
  cluster_pg_url="$(cluster_database_url "${pg_url}")"
  connection_hash="$("${PROJECT_ROOT}/.venv/bin/python" - "${cluster_pg_url}" <<'PY'
import hashlib
import sys
print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest())
PY
)"
  scaledjob_existed="false"
  previous_connection_hash=""
  if kubectl get scaledjob excel-ingestion -n "${NAMESPACE}" >/dev/null 2>&1; then
    scaledjob_existed="true"
    previous_connection_hash="$(kubectl get scaledjob excel-ingestion \
      -n "${NAMESPACE}" \
      -o jsonpath='{.metadata.annotations.bist\.ai/connection-hash}')"
  fi
  configured_max_jobs="$(env_value KUBERNETES_MAX_JOBS)"
  max_jobs="${KUBERNETES_MAX_JOBS:-${configured_max_jobs:-$(python3 "${DEPLOY_DIR}/capacity.py")}}"

  kubectl apply -f "${DEPLOY_DIR}/templates/namespace.yaml"
  if database_is_local; then
    database_endpoint="$(docker inspect bist-pgvector \
      --format "{{(index .NetworkSettings.Networks \"k3d-${CLUSTER_NAME}\").IPAddress}}")"
    python3 "${DEPLOY_DIR}/render_database.py" \
      --endpoint "${database_endpoint}" | kubectl apply -f -
  else
    kubectl delete service bist-pgvector -n "${NAMESPACE}" --ignore-not-found
    kubectl delete endpointslice bist-pgvector-local \
      -n "${NAMESPACE}" --ignore-not-found
  fi
  kubectl -n "${NAMESPACE}" create secret generic bist-batch-env \
    --from-literal=PGVECTOR_URL="${cluster_pg_url}" \
    --from-literal=OPENAI_API_KEY="${openai_key}" \
    --from-literal=OPENAI_BASE_URL="${openai_base}" \
    --dry-run=client -o yaml | kubectl apply -f -
  python3 "${DEPLOY_DIR}/render.py" \
    --max-replicas "${max_jobs}" \
    --queue "${QUEUE_NAME}" \
    --image "${WORKER_IMAGE}" \
    --connection-hash "${connection_hash}" \
    --cpu-request "$(config_value KUBERNETES_JOB_CPU_REQUEST 1000m)" \
    --memory-request "$(config_value KUBERNETES_JOB_MEMORY_REQUEST 2Gi)" \
    --cpu-limit "$(config_value KUBERNETES_JOB_CPU_LIMIT 2)" \
    --memory-limit "$(config_value KUBERNETES_JOB_MEMORY_LIMIT 3Gi)" \
    | kubectl apply -f -
  if [[ "${scaledjob_existed}" == "true" \
    && "${previous_connection_hash}" != "${connection_hash}" ]]; then
    # KEDA's PostgreSQL scaler pools its DB connection. Restart only when the
    # connection secret changed so it never keeps querying the previous DB.
    kubectl rollout restart deployment/keda-operator -n keda
    kubectl rollout status deployment/keda-operator -n keda --timeout=180s
  fi
  echo "Docker 자원 기준 최대 병렬 Job: ${max_jobs}"
}

show_status() {
  kubectl config use-context "k3d-${CLUSTER_NAME}" >/dev/null 2>&1 || true
  python3 "${DEPLOY_DIR}/capacity.py" --details
  k3d cluster list
  kubectl get pods -n keda 2>/dev/null || true
  kubectl get scaledjobs,jobs,pods -n "${NAMESPACE}" 2>/dev/null || true
  kubectl top nodes 2>/dev/null || true
}

case "${ACTION}" in
  check)
    check_tools
    load_configuration
    ;;
  cluster)
    check_tools
    load_configuration
    start_database
    ensure_cluster
    install_control_plane
    ;;
  build)
    check_tools
    load_configuration
    ensure_cluster
    build_worker
    ;;
  deploy)
    check_tools
    load_configuration
    start_database
    ensure_cluster
    install_control_plane
    apply_workload
    ;;
  all)
    check_tools
    load_configuration
    start_database
    ensure_cluster
    install_control_plane
    build_worker
    apply_workload
    show_status
    ;;
  restart)
    check_tools
    load_configuration
    k3d cluster stop "${CLUSTER_NAME}" || true
    k3d cluster start "${CLUSTER_NAME}"
    kubectl config use-context "k3d-${CLUSTER_NAME}" >/dev/null
    show_status
    ;;
  status)
    show_status
    ;;
  logs)
    if [[ -z "$(kubectl get pods -n "${NAMESPACE}" \
      -l app.kubernetes.io/name=workflow-worker -o name 2>/dev/null)" ]]; then
      echo "실행 중이거나 보존된 workflow worker Pod가 없습니다."
    else
      kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/name=workflow-worker \
        --all-containers --tail=200 --prefix=true
    fi
    ;;
  down)
    k3d cluster stop "${CLUSTER_NAME}" || true
    ;;
  destroy)
    k3d cluster delete "${CLUSTER_NAME}" || true
    ;;
  *)
    echo "사용법: $0 {check|cluster|build|deploy|all|restart|status|logs|down|destroy}" >&2
    exit 2
    ;;
esac
