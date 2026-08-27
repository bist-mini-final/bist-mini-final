#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/../.." && pwd)"
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PROJECT_ROOT}/.tools/bin:${PATH}"
if [[ -n "${APPDATA:-}" ]]; then
  export PATH="${APPDATA}/uv/bin:${PATH}"
fi
CLUSTER_NAME="${K3D_CLUSTER_NAME:-bist-local}"
NAMESPACE="bist-batch"
WORKER_IMAGE="${KUBERNETES_WORKER_IMAGE:-bist-workflow-worker:local}"
BACKEND_IMAGE="${KUBERNETES_BACKEND_IMAGE:-bist-backend:local}"
FRONTEND_IMAGE="${KUBERNETES_FRONTEND_IMAGE:-bist-frontend:local}"
IMPORT_IMAGES="${K3D_IMPORT_IMAGES:-true}"
KEDA_VERSION="${KEDA_VERSION:-2.20.2}"
ACTION="${1:-all}"

resolve_project_python() {
  local candidate appdata_path runtime_python
  for candidate in \
    "${PROJECT_ROOT}/.venv/bin/python" \
    "${PROJECT_ROOT}/.venv/Scripts/python.exe" \
    "${PROJECT_ROOT}/.venv/Scripts/python"; do
    if [[ -x "${candidate}" ]] \
      && "${candidate}" -c "import sys" >/dev/null 2>&1; then
      PROJECT_PYTHON="${candidate}"
      return 0
    fi
  done

  # Some managed Windows devices block direct execution from .venv. uv's
  # managed interpreter is normally allowed; adding the virtualenv packages
  # to PYTHONPATH retains the project's locked dependency set.
  if [[ -n "${APPDATA:-}" && -d "${PROJECT_ROOT}/.venv/Lib/site-packages" ]]; then
    appdata_path="${APPDATA}"
    if command -v cygpath >/dev/null 2>&1; then
      appdata_path="$(cygpath -u "${APPDATA}")"
    fi
    runtime_python="$(find "${appdata_path}/uv/python" -name python.exe -type f \
      2>/dev/null | sort | tail -n 1)"
    if [[ -n "${runtime_python}" ]] \
      && "${runtime_python}" -c "import sys" >/dev/null 2>&1; then
      PROJECT_PYTHON="${runtime_python}"
      export PYTHONPATH="${PROJECT_ROOT}/.venv/Lib/site-packages${PYTHONPATH:+:${PYTHONPATH}}"
      echo "ℹ️  Device Guard 환경: uv 관리 Python과 프로젝트 의존성을 사용합니다."
      return 0
    fi
  fi
  PROJECT_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
}

resolve_project_python

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
      echo "⚠️ Node.js 22+ 설치가 필요합니다. (예: nvm install 22)" >&2
    fi
  fi
}

ensure_python_venv() {
  if ! "${PROJECT_PYTHON}" -c "import dotenv" >/dev/null 2>&1; then
    echo "⚡ .venv 가 없습니다. uv sync --frozen 으로 가상환경을 생성합니다..."
    ensure_uv
    (cd "${PROJECT_ROOT}" && uv sync --frozen)
    resolve_project_python
  fi
  if ! "${PROJECT_PYTHON}" -c "import dotenv" >/dev/null 2>&1; then
    echo "❌ 프로젝트 가상환경 Python을 찾을 수 없습니다: ${PROJECT_PYTHON}" >&2
    exit 1
  fi
}

check_tools() {
  ensure_docker
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

database_url() {
  local configured_database_url kubernetes_database_url
  kubernetes_database_url="$(config_value KUBERNETES_DATABASE_URL '')"
  if [[ -n "${kubernetes_database_url}" ]]; then
    echo "${kubernetes_database_url}"
    return 0
  fi
  configured_database_url="$(config_value DATABASE_URL '')"
  if [[ -n "${configured_database_url}" ]]; then
    echo "${configured_database_url}"
    return 0
  fi
  config_value PGVECTOR_URL postgresql://postgres:postgres@localhost:5432/rag_flow
}

database_is_local() {
  local pg_url
  pg_url="$(database_url)"
  "${PROJECT_PYTHON}" - "${pg_url}" <<'PY'
import sys
from urllib.parse import urlsplit
host = (urlsplit(sys.argv[1]).hostname or "").lower()
raise SystemExit(0 if host in {"localhost", "127.0.0.1", "::1"} else 1)
PY
}

start_database() {
  local pg_url
  pg_url="$(database_url)"
  if database_is_local; then
    docker compose -f "${PROJECT_ROOT}/deploy/compose/docker-compose.yml" up -d --wait
  else
    # A remote PGVECTOR_URL makes the local container unnecessary. Preserve
    # its named volume so switching back to local does not lose data.
    docker compose -f "${PROJECT_ROOT}/deploy/compose/docker-compose.yml" down
  fi
  (
    cd "${PROJECT_ROOT}"
    DATABASE_URL="${pg_url}" "${PROJECT_PYTHON}" -m alembic upgrade head
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
      --port "8080:80@loadbalancer" \
      --port "8443:443@loadbalancer" \
      --volume "${PROJECT_ROOT}/data:/mnt/bist-data@server:0"
  fi
  kubectl config use-context "k3d-${CLUSTER_NAME}" >/dev/null
  if docker inspect bist-pgvector >/dev/null 2>&1 \
    && ! docker inspect bist-pgvector \
      --format '{{json .NetworkSettings.Networks}}' | grep -q "\"k3d-${CLUSTER_NAME}\""; then
    docker network connect "k3d-${CLUSTER_NAME}" bist-pgvector
  fi
}

warn_if_ingress_ports_are_unmapped() {
  local load_balancer http_mapping
  load_balancer="k3d-${CLUSTER_NAME}-serverlb"
  http_mapping="$(docker port "${load_balancer}" 80/tcp 2>/dev/null || true)"
  if [[ -z "${http_mapping}" ]]; then
    echo "⚠️  이 클러스터에는 host 8080 → ingress 80 포트 매핑이 없습니다."
    echo "   안전을 위해 기존 클러스터는 자동 삭제하지 않았습니다."
    echo "   로컬 Ingress 접근이 필요하면 '${0} recreate'를 실행하거나 kubectl port-forward를 사용하세요."
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

install_ingress_controller() {
  helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx \
    --force-update >/dev/null
  helm repo update ingress-nginx >/dev/null
  helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx \
    --create-namespace \
    --set controller.service.type=LoadBalancer \
    --wait \
    --timeout 5m
  kubectl wait --for=condition=Available deployment/ingress-nginx-controller \
    --namespace ingress-nginx --timeout=180s
}

import_image() {
  local image="$1"
  if [[ "${IMPORT_IMAGES}" == "true" ]]; then
    k3d image import "${image}" --cluster "${CLUSTER_NAME}"
  fi
}

build_worker() {
  DOCKER_BUILDKIT=1 docker build \
    --target runtime \
    -f "${PROJECT_ROOT}/deploy/docker/Dockerfile.worker" \
    -t "${WORKER_IMAGE}" \
    "${PROJECT_ROOT}"
  import_image "${WORKER_IMAGE}"
}

build_backend() {
  DOCKER_BUILDKIT=1 docker build \
    -f "${PROJECT_ROOT}/deploy/docker/Dockerfile.backend" \
    -t "${BACKEND_IMAGE}" \
    "${PROJECT_ROOT}"
  import_image "${BACKEND_IMAGE}"
}

build_frontend() {
  DOCKER_BUILDKIT=1 docker build \
    --target runtime \
    -f "${PROJECT_ROOT}/deploy/docker/Dockerfile.frontend" \
    -t "${FRONTEND_IMAGE}" \
    "${PROJECT_ROOT}"
  import_image "${FRONTEND_IMAGE}"
}

build_images() {
  build_backend
  build_worker
  build_frontend
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
  pg_url="$(database_url)"
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

run_schema_migration() {
  kubectl delete job bist-schema-migrate -n "${NAMESPACE}" --ignore-not-found
  kubectl apply -f "${DEPLOY_DIR}/manifests/05-migrations.yaml"
  kubectl set image job/bist-schema-migrate migrate="${BACKEND_IMAGE}" \
    -n "${NAMESPACE}"
  kubectl patch job bist-schema-migrate -n "${NAMESPACE}" --type merge \
    -p '{"spec":{"suspend":false}}'
  if ! kubectl wait --for=condition=complete job/bist-schema-migrate \
    -n "${NAMESPACE}" --timeout=180s; then
    kubectl logs job/bist-schema-migrate -n "${NAMESPACE}" --all-containers \
      --tail=200 || true
    return 1
  fi
}

apply_application() {
  kubectl apply -f "${DEPLOY_DIR}/manifests/01-backend-rbac.yaml"
  run_schema_migration
  kubectl apply -f "${DEPLOY_DIR}/manifests/02-backend.yaml"
  kubectl apply -f "${DEPLOY_DIR}/manifests/03-frontend.yaml"
  kubectl apply -f "${DEPLOY_DIR}/manifests/04-ingress.yaml"
  kubectl set image deployment/backend-api backend="${BACKEND_IMAGE}" \
    -n "${NAMESPACE}"
  kubectl set image deployment/frontend-ui frontend="${FRONTEND_IMAGE}" \
    -n "${NAMESPACE}"
  # Local images intentionally keep a stable :local tag. Restarting creates
  # a new Pod after k3d imports the freshly built image without relying on a
  # mutable-tag pull from a remote registry.
  kubectl rollout restart deployment/backend-api -n "${NAMESPACE}"
  kubectl rollout restart deployment/frontend-ui -n "${NAMESPACE}"
  kubectl rollout status deployment/backend-api -n "${NAMESPACE}" --timeout=240s
  kubectl rollout status deployment/frontend-ui -n "${NAMESPACE}" --timeout=180s
  kubectl exec deployment/backend-api -n "${NAMESPACE}" -- \
    curl --fail --silent --show-error http://127.0.0.1:8765/readyz >/dev/null
}

show_status() {
  kubectl config use-context "k3d-${CLUSTER_NAME}" >/dev/null 2>&1 || true
  "${PROJECT_PYTHON}" "${DEPLOY_DIR}/scripts/capacity.py" --details
  k3d cluster list
  kubectl get pods -n keda 2>/dev/null || true
  kubectl get deployments,services,ingress -n "${NAMESPACE}" 2>/dev/null || true
  kubectl get scaledjobs,jobs,pods -n "${NAMESPACE}" 2>/dev/null || true
  kubectl top nodes 2>/dev/null || true
  warn_if_ingress_ports_are_unmapped
  if docker port "k3d-${CLUSTER_NAME}-serverlb" 80/tcp 2>/dev/null | grep -q .; then
    echo "애플리케이션 URL: http://localhost:8080"
  fi
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
    install_ingress_controller
    ;;
  build)
    check_tools
    ensure_cluster
    build_images
    ;;
  deploy)
    check_tools
    start_database
    ensure_cluster
    install_control_plane
    install_ingress_controller
    apply_workload
    apply_application
    warn_if_ingress_ports_are_unmapped
    ;;
  all)
    check_tools
    start_database
    ensure_cluster
    install_control_plane
    install_ingress_controller
    build_images
    apply_workload
    apply_application
    show_status
    ;;
  recreate)
    check_tools
    k3d cluster delete "${CLUSTER_NAME}" || true
    start_database
    ensure_cluster
    install_control_plane
    install_ingress_controller
    build_images
    apply_workload
    apply_application
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
  logs-api)
    kubectl logs -n "${NAMESPACE}" deployment/backend-api \
      --all-containers --tail=200 --prefix=true
    ;;
  down)
    k3d cluster stop "${CLUSTER_NAME}" || true
    ;;
  destroy)
    k3d cluster delete "${CLUSTER_NAME}" || true
    ;;
  *)
    echo "사용법: $0 {setup-tools|check|cluster|build|deploy|all|recreate|restart|status|logs|logs-api|down|destroy}" >&2
    exit 2
    ;;
esac
