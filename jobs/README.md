# Standalone jobs

`jobs/` contains Prefect flows that are deployed and scaled independently from
the FastAPI web backend. A flow may import reusable domain/runtime code from
`backend/`, but HTTP routers never execute its heavy workload in-process.

## Excel ingestion

팀 공용 로컬·운영 실행은 Prefect deployment를 사용합니다. Prefect가 저장된
Playground DAG를 읽고 모듈별 Task를 생성하며 Docker worker가 Flow Run마다
일회성 컨테이너를 만들고 완료 후 자동 삭제합니다.

```bash
./deploy/prefect/local.sh all
```

Build the Prefect Flow image from the repository root:

```bash
docker build -f jobs/excel_ingestion/Dockerfile \
  --target prefect-runtime \
  -t bist-excel-ingestion-prefect:local .
```

The Dockerfile uses BuildKit cache mounts for apt packages and pip wheels. If
`requirements.txt` is unchanged, the dependency layer is reused as-is; when it
changes, previously downloaded wheels are reused. Keep BuildKit enabled and do
not use `--no-cache` for normal builds.

For CI builders that do not share the local Docker cache, export it to the
image registry:

```bash
docker buildx build --load \
  --cache-from type=registry,ref="$IMAGE:buildcache" \
  --cache-to type=registry,ref="$IMAGE:buildcache",mode=max \
  -f jobs/excel_ingestion/Dockerfile \
  -t "$IMAGE:latest" .
```

The default image supports the project's default OpenAI VLM and embedding
models without shipping Torch. For a job configured with a local BGE model,
build the optional larger image:

```bash
docker build --target local-models \
  -f jobs/excel_ingestion/Dockerfile \
  -t bist-excel-ingestion-prefect:bge .
```

The Flow container exits after one run. PostgreSQL owns durable product state
and a session advisory lock prevents duplicate execution of the same `run_id`.
