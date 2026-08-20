#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/../.." && pwd)"
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.yml"
FLOW_IMAGE="${PREFECT_FLOW_IMAGE:-bist-excel-ingestion-prefect:local}"
PREFECT_API_URL="${PREFECT_API_URL:-http://127.0.0.1:4200/api}"
ACTION="${1:-all}"

compose() {
  docker compose -p bist-prefect -f "${COMPOSE_FILE}" "$@"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "필수 명령을 찾을 수 없습니다: $1" >&2
    exit 1
  fi
}

check_tools() {
  require_command docker
  require_command curl
  if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon이 실행 중이 아닙니다." >&2
    exit 1
  fi
  if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    echo ".venv가 없습니다. 먼저 uv pip install --python .venv/bin/python -r requirements.txt 를 실행하세요." >&2
    exit 1
  fi
  "${PROJECT_ROOT}/.venv/bin/python" -c "import prefect, prefect_docker" >/dev/null
}

start_database() {
  docker compose -f "${PROJECT_ROOT}/docker-compose.db.yml" up -d --wait
}

build_images() {
  DOCKER_BUILDKIT=1 docker build \
    --target prefect-runtime \
    -f "${PROJECT_ROOT}/jobs/excel_ingestion/Dockerfile" \
    -t "${FLOW_IMAGE}" \
    "${PROJECT_ROOT}"
  DOCKER_BUILDKIT=1 compose build prefect-worker
}

start_control_plane() {
  compose up -d --wait prefect-db prefect-server
  for _attempt in $(seq 1 30); do
    if curl --silent --fail "${PREFECT_API_URL}/health" >/dev/null; then
      return
    fi
    sleep 1
  done
  echo "Prefect API가 준비되지 않았습니다." >&2
  exit 1
}

register_deployment() {
  PREFECT_API_URL="${PREFECT_API_URL}" \
    PREFECT_WORK_POOL_NAME="bist-docker" \
    PREFECT_FLOW_IMAGE="${FLOW_IMAGE}" \
    "${PROJECT_ROOT}/.venv/bin/python" "${DEPLOY_DIR}/bootstrap.py"
}

start_worker() {
  compose up -d --wait prefect-worker
  for _attempt in $(seq 1 30); do
    if PREFECT_API_URL="${PREFECT_API_URL}" \
      "${PROJECT_ROOT}/.venv/bin/prefect" work-pool inspect bist-docker \
      2>/dev/null | grep -q "READY"; then
      return
    fi
    sleep 1
  done
  echo "Docker work pool이 READY가 되지 않았습니다." >&2
  compose logs --tail=100 prefect-worker >&2
  exit 1
}

show_status() {
  compose ps
  echo "Flow containers:"
  docker ps -a \
    --filter "label=io.prefect.flow-run-id" \
    --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
  echo "Prefect UI: http://127.0.0.1:4200"
  echo "API deployment: PREFECT_DEPLOYMENT_NAME=excel-ingestion/docker"
}

case "${ACTION}" in
  check)
    check_tools
    ;;
  server)
    check_tools
    start_database
    start_control_plane
    ;;
  build)
    check_tools
    build_images
    ;;
  deploy)
    check_tools
    start_database
    start_control_plane
    register_deployment
    start_worker
    show_status
    ;;
  status)
    show_status
    ;;
  logs)
    compose logs --tail=200
    ;;
  all)
    check_tools
    start_database
    build_images
    start_control_plane
    register_deployment
    start_worker
    show_status
    ;;
  down)
    compose down
    ;;
  *)
    echo "사용법: $0 {check|server|build|deploy|status|logs|all|down}" >&2
    exit 2
    ;;
esac
