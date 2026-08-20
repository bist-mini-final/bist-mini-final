#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"
export PATH="${PROJECT_ROOT}/.tools/bin:${PATH}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "필수 명령을 찾을 수 없습니다: $1" >&2
    exit 1
  fi
}

require_command docker
require_command node
require_command npm

install_kubernetes_tools() {
  if command -v k3d >/dev/null 2>&1 \
    && command -v kubectl >/dev/null 2>&1 \
    && command -v helm >/dev/null 2>&1; then
    return
  fi
  require_command curl
  require_command tar
  local os_name machine_arch tool_arch tool_dir temporary_dir
  os_name="$(uname -s | tr '[:upper:]' '[:lower:]')"
  machine_arch="$(uname -m)"
  case "${machine_arch}" in
    x86_64|amd64) tool_arch="amd64" ;;
    arm64|aarch64) tool_arch="arm64" ;;
    *) echo "지원하지 않는 CPU 아키텍처입니다: ${machine_arch}" >&2; exit 1 ;;
  esac
  case "${os_name}" in
    linux|darwin) ;;
    *) echo "setup.sh가 지원하지 않는 OS입니다: ${os_name}" >&2; exit 1 ;;
  esac
  tool_dir="${PROJECT_ROOT}/.tools/bin"
  mkdir -p "${tool_dir}"
  temporary_dir="$(mktemp -d)"
  trap 'rm -r "${temporary_dir}"' EXIT

  if ! command -v k3d >/dev/null 2>&1; then
    curl -fsSL \
      "https://github.com/k3d-io/k3d/releases/download/v5.9.0/k3d-${os_name}-${tool_arch}" \
      -o "${tool_dir}/k3d"
    chmod +x "${tool_dir}/k3d"
  fi
  if ! command -v kubectl >/dev/null 2>&1; then
    curl -fsSL \
      "https://dl.k8s.io/release/v1.35.0/bin/${os_name}/${tool_arch}/kubectl" \
      -o "${tool_dir}/kubectl"
    chmod +x "${tool_dir}/kubectl"
  fi
  if ! command -v helm >/dev/null 2>&1; then
    curl -fsSL \
      "https://get.helm.sh/helm-v3.21.4-${os_name}-${tool_arch}.tar.gz" \
      -o "${temporary_dir}/helm.tar.gz"
    tar -xzf "${temporary_dir}/helm.tar.gz" -C "${temporary_dir}"
    cp "${temporary_dir}/${os_name}-${tool_arch}/helm" "${tool_dir}/helm"
    chmod +x "${tool_dir}/helm"
  fi
  rm -r "${temporary_dir}"
  trap - EXIT
}

install_kubernetes_tools

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon이 실행 중이 아닙니다." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo ".env.example을 .env로 복사했습니다. OPENAI_API_KEY를 설정하세요."
fi

if [[ ! -x .venv/bin/python ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.11 .venv
  elif command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv .venv
  else
    require_command python3
    python3 -m venv .venv
  fi
fi

if command -v uv >/dev/null 2>&1; then
  uv pip install --python .venv/bin/python -r requirements.txt
else
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

(
  cd frontend
  npm ci
)

./deploy/kubernetes/local.sh all

echo "설치 완료: k3d/KEDA 배치 클러스터가 준비되었습니다."
echo "상태 확인: ./deploy/kubernetes/local.sh status"
echo "API 실행: .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8765 --reload"
echo "Frontend 실행: cd frontend && npm run dev"
