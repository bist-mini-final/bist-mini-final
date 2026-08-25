#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/../.." && pwd)"
PROJECT_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PROJECT_ROOT}/.tools/bin:${PATH}"
CLUSTER_NAME="${K3D_CLUSTER_NAME:-bist-local}"
NAMESPACE="bist-batch"
WORKER_IMAGE="${KUBERNETES_WORKER_IMAGE:-bist-workflow-worker:local}"
KEDA_VERSION="${KEDA_VERSION:-2.20.2}"
ACTION="${1:-all}"

has_command() {
  command -v "$1" >/dev/null 2>&1
}

ensure_docker() {
  if ! has_command docker; then
    if [[ "$(uname -s)" == "Darwin" ]] && has_command brew; then
      echo "⚡ Docker Desktop을 설치합니다..."
      brew install --cask docker
    else
      echo "❌ Docker가 설치되어 있지 않습니다. Docker Desktop 또는 Docker Engine을 먼저 설치해주세요." >&2
      exit 1
    fi
  fi

  if ! docker info >/dev/null 2>&1; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      echo "⏳ Docker 데몬이 실행 중이지 않습니다. Docker 데스크톱 앱을 시작합니다..."
      open -g -a Docker || open -g -a OrbStack || true
      for i in {1..30}; do
        if docker info >/dev/null 2>&1; then
          echo "✅ Docker 데몬 준비 완료."
          return 0
        fi
        sleep 2
      done
    fi
    echo "❌ Docker daemon이 실행 중이 아닙니다. Docker를 실행한 후 다시 시도하세요." >&2
    exit 1
  fi
}

ensure_uv() {
  if ! has_command uv; then
    echo "⚡ uv 가 설치되어 있지 않아 자동으로 설치합니다..."
    if has_command brew; then
      brew install uv
    else
      curl -LsSf https://astral.sh/uv/install.sh | sh
      export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
    fi
  fi
}

ensure_k3d() {
  if ! has_command k3d; then
    echo "⚡ k3d 가 설치되어 있지 않아 자동으로 설치합니다..."
    if has_command brew; then
      brew install k3d
    else
      curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
    fi
  fi
}

ensure_kubectl() {
  if ! has_command kubectl; then
    echo "⚡ kubectl 이 설치되어 있지 않아 자동으로 설치합니다..."
    if has_command brew; then
      brew install kubectl
    else
      local arch="$(uname -m)"
      [[ "$arch" == "x86_64" ]] && arch="amd64"
      [[ "$arch" == "aarch64" ]] && arch="arm64"
      local os="$(uname -s | tr '[:upper:]' '[:lower:]')"
      mkdir -p "${PROJECT_ROOT}/.tools/bin"
      curl -sLO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/${os}/${arch}/kubectl"
      chmod +x kubectl
      mv kubectl "${PROJECT_ROOT}/.tools/bin/kubectl"
    fi
  fi
}

ensure_helm() {
  if ! has_command helm; then
    echo "⚡ helm 이 설치되어 있지 않아 자동으로 설치합니다..."
    if has_command brew; then
      brew install helm
    else
      curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
      chmod 700 get_helm.sh
      ./get_helm.sh --no-sudo || true
      rm -f get_helm.sh
    fi
  fi
}

ensure_node() {
  if ! has_command node || ! has_command npm; then
    echo "⚡ Node.js / npm 이 설치되어 있지 않습니다..."
    if has_command brew; then
      brew install node
    else
      echo "⚠️ Node.js 18+ 설치가 필요합니다. (예: nvm install 20)" >&2
    fi
  fi
}

ensure_python_venv() {
  if [[ ! -x "${PROJECT_PYTHON}" ]]; then
    echo "⚡ .venv 가 없습니다. uv sync --frozen 으로 가상환경을 생성합니다..."
    ensure_uv
    (cd "${PROJECT_ROOT}" && uv sync --frozen)
  fi
}

check_tools() {
  ensure_docker
  ensure_uv
  ensure_k3d
  ensure_kubectl
  ensure_helm
  ensure_node
  ensure_python_venv
}

env_value() {
  "${PROJECT_PYTHON}" - "$PROJECT_ROOT" "$1" <<'PY'
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

database_is_local() {
  local pg_url
  pg_url="$(config_value PGVECTOR_URL postgresql://postgres:postgres@localhost:5432/rag_flow)"
  "${PROJECT_PYTHON}" - "${pg_url}" <<'PY'
import sys
from urllib.parse import urlsplit
host = (urlsplit(sys.argv[1]).hostname or "").lower()
raise SystemExit(0 if host in {"localhost", "127.0.0.1", "::1"} else 1)
PY
}

start_database() {
  if database_is_local; then
    docker compose -f "${PROJECT_ROOT}/deploy/compose/docker-compose.yml" up -d --wait
  else
    # A remote PGVECTOR_URL makes the local container unnecessary. Preserve
    # its named volume so switching back to local does not lose data.
    docker compose -f "${PROJECT_ROOT}/deploy/compose/docker-compose.yml" down
  fi
  (
    cd "${PROJECT_ROOT}"
    "${PROJECT_PYTHON}" -c \
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
    -f "${PROJECT_ROOT}/deploy/docker/Dockerfile.worker" \
    -t "${WORKER_IMAGE}" \
    "${PROJECT_ROOT}"
  k3d image import "${WORKER_IMAGE}" --cluster "${CLUSTER_NAME}"
}

cluster_database_url() {
  local source_url="$1"
  "${PROJECT_PYTHON}" - "$source_url" <<'PY'
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
  connection_hash="$("${PROJECT_PYTHON}" - "${cluster_pg_url}" <<'PY'
import hashlib
import sys
print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest())
PY
)"
  scaledjob_existed="false"
  previous_connection_hash=""
  if kubectl get scaledjob workflow-worker -n "${NAMESPACE}" >/dev/null 2>&1; then
    scaledjob_existed="true"
    previous_connection_hash="$(kubectl get scaledjob workflow-worker \
      -n "${NAMESPACE}" \
      -o jsonpath='{.metadata.annotations.bist\.ai/connection-hash}')"
  fi
  configured_max_jobs="$(env_value KUBERNETES_MAX_JOBS)"
  max_jobs="${KUBERNETES_MAX_JOBS:-${configured_max_jobs:-$("${PROJECT_PYTHON}" "${DEPLOY_DIR}/scripts/capacity.py")}}"

  kubectl apply -f "${DEPLOY_DIR}/manifests/00-namespace.yaml"
  if database_is_local; then
    database_endpoint="$(docker inspect bist-pgvector \
      --format "{{(index .NetworkSettings.Networks \"k3d-${CLUSTER_NAME}\").IPAddress}}")"
    "${PROJECT_PYTHON}" "${DEPLOY_DIR}/scripts/render_database.py" \
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
  "${PROJECT_PYTHON}" "${DEPLOY_DIR}/scripts/render.py" \
    --max-replicas "${max_jobs}" \
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
  "${PROJECT_PYTHON}" "${DEPLOY_DIR}/scripts/capacity.py" --details
  k3d cluster list
  kubectl get pods -n keda 2>/dev/null || true
  kubectl get scaledjobs,jobs,pods -n "${NAMESPACE}" 2>/dev/null || true
  kubectl top nodes 2>/dev/null || true
}

case "${ACTION}" in
  setup-tools|check)
    check_tools
    ;;
  cluster)
    check_tools
    start_database
    ensure_cluster
    install_control_plane
    ;;
  build)
    check_tools
    ensure_cluster
    build_worker
    ;;
  deploy)
    check_tools
    start_database
    ensure_cluster
    install_control_plane
    apply_workload
    ;;
  all)
    check_tools
    start_database
    ensure_cluster
    install_control_plane
    build_worker
    apply_workload
    show_status
    ;;
  restart)
    check_tools
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
    echo "사용법: $0 {setup-tools|check|cluster|build|deploy|all|restart|status|logs|down|destroy}" >&2
    exit 2
    ;;
esac
