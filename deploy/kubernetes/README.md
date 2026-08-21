# Local k3d + KEDA batch cluster

이 디렉터리는 팀 공용 로컬 배치 실행 환경을 재현한다.

```bash
./deploy/kubernetes/local.sh all
```

설치되는 항목:

- `PGVECTOR_URL`이 localhost일 때 제품 PostgreSQL + pgvector Docker container
- 단일 server k3d/k3s cluster (`bist-local`)
- KEDA Helm chart 2.20.2
- k3s 기본 Metrics Server 또는 누락 시 공식 chart
- `bist-workflow-worker:local` image
- `bist-batch/excel-ingestion` ScaledJob

실행 요청이 없으면 Job/Pod는 0개다. 기본 동시성은 Docker CPU/메모리에서 계산되며
현재 값은 `local.sh status`로 확인한다.

```bash
./deploy/kubernetes/local.sh status
./deploy/kubernetes/local.sh logs
./deploy/kubernetes/local.sh build
./deploy/kubernetes/local.sh deploy
./deploy/kubernetes/local.sh restart
./deploy/kubernetes/local.sh down
./deploy/kubernetes/local.sh destroy
```

`build`는 application source 변경 후 worker image만 다시 만들고 import한다. `deploy`는
`.env`의 Secret, 자동 capacity, resource request/limit, ScaledJob을 갱신한다.

`down`은 cluster container를 정지하고 `destroy`는 cluster를 삭제한다. 둘 다 제품
pgvector Docker volume과 저장소 `data/`는 보존한다.
