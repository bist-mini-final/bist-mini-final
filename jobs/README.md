# Standalone jobs

`jobs/`는 FastAPI와 공간·수명주기가 분리된 one-shot batch worker를 포함한다.

## Workflow worker

`workflow_worker`는 Kubernetes Job 하나당 PostgreSQL 큐 item 하나만 처리한다.

```bash
DOCKER_BUILDKIT=1 docker build \
  --target runtime \
  -f jobs/workflow_worker/Dockerfile \
  -t bist-workflow-worker:local .

k3d image import bist-workflow-worker:local --cluster bist-local
```

컨테이너에는 전체 웹 서버와 프론트가 아니라 ingestion registry에 필요한 backend 코드만
포함된다. 실행 entrypoint는 다음과 같다.

```bash
python -m jobs.workflow_worker.main --queue excel-ingestion
```

필수 환경변수는 `PGVECTOR_URL`이며 OpenAI 기반 VLM/embedding에는
`OPENAI_API_KEY`, `OPENAI_BASE_URL`이 필요하다. 로컬에서는
`deploy/kubernetes/local.sh`가 Secret과 데이터 mount를 구성한다.

기본 runtime은 빠른 build/import를 위해 Torch를 제외한다. BGE가 필요하면
`--target local-models`로 만들고 모델 캐시 mount 정책을 별도로 추가한다.
