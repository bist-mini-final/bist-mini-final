#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "필수 명령을 찾을 수 없습니다: $1" >&2
    exit 1
  fi
}

require_command docker
require_command node
require_command npm

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

./deploy/prefect/local.sh all

echo "설치 완료: Prefect UI http://127.0.0.1:4200"
echo "API 실행: .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8765 --reload"
echo "Frontend 실행: cd frontend && npm run dev"
