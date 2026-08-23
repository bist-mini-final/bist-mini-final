# 클린 아키텍처 계약

이 문서는 frontend, backend, worker Job, Kubernetes가 같은 설계 원칙을 따르도록
의존 방향과 객체 소유권을 정의한다. 구현 편의를 위한 우회 경로는 제품 경로로
승격하지 않는다.

## 계층과 의존 방향

```text
frontend view → feature hook → domain → API adapter → HTTP
                                               ↓
FastAPI router → application service → domain/module port
                         ↓                    ↑
                 infrastructure adapter ─────┘
                         ↓
              PostgreSQL queue → Kubernetes worker
                                      ↓
                              module DAG executor
```

허용되는 의존은 바깥 계층에서 안쪽 계약을 향한다.

| 계층 | 소유하는 것 | 의존하면 안 되는 것 |
| --- | --- | --- |
| `modules/` | 계산 DTO, 순수 계산, module port | FastAPI, Kubernetes, 화면 상태, client 생성 |
| `jobs/` | immutable DAG/worker 정의, queue, worker policy | DB 연결, HTTP, 실행 객체 |
| `backend/features/` | 유스케이스, 도메인 서비스, repository port | `backend/api/` |
| `backend/api/` | HTTP DTO 변환, status/header, 공통 오류 envelope | 공급자 생성, 계산 구현 |
| `backend/storage/`, `backend/providers/` | port 구현, bounded I/O | FastAPI route, React 계약 |
| `backend/bootstrap/` | 프로세스별 object graph와 자원 수명 | 도메인 계산 |
| `frontend/domain/` | 순수 상태 전이와 계산 | React, ky, browser I/O |
| `frontend/adapters/` | HTTP/React Flow 등 외부 형식 변환 | 화면별 중복 transport |

## 프로세스 객체 그래프

- `ApplicationContainer`가 API 프로세스의 유일한 composition root다.
- `RuntimeContainer`가 API와 one-shot worker가 공유하는 module graph를 만든다.
- module과 feature는 `OpenAIProvider`, `OpenAIResponsesClient`,
  `PgVectorStore`를 직접 생성하지 않고 생성자 port로 받는다.
- 한 프로세스의 Responses와 Embeddings는 하나의 `OpenAIProvider`와 keep-alive
  `httpx.Client`를 공유한다.
- PostgreSQL pool은 정규화한 database URL별로 하나만 만들고, 다른 URL의 pool을
  암묵적으로 닫지 않는다.
- container를 만든 프로세스가 provider와 pool의 종료를 책임진다. one-shot worker도
  빈 큐와 실패를 포함한 모든 종료 경로에서 container를 닫는다.

## Job과 Kubernetes의 단일 소스

- `jobs.ALL_JOBS`가 제품 Job 목록의 유일한 소스다.
- module DAG는 `DagJobDefinition`, 전용 queue consumer는
  `WorkerJobDefinition`으로 표현한다.
- queue 이름, worker entrypoint, KEDA pending SQL, deadline, volume policy는
  Job 정의가 소유한다.
- `jobs.kubernetes.kubernetes_worker_specs()`가 Job 정의를 배포 스펙으로 투영하고,
  하나의 `deploy/kubernetes/manifests/scaledjob.yaml`이 모든 ScaledJob을 렌더링한다.
- feature 디렉터리의 개별 Kubernetes YAML과 렌더 스크립트의 queue 하드코딩은
  허용하지 않는다.

## Kubernetes/KEDA 실행 계약

- PostgreSQL queue와 KEDA ScaledJob이 제품 Job 실행의 유일한 오케스트레이션 경로다.
- API는 queue 제출까지만 책임지고 실제 계산은 일회성 Kubernetes Job이 수행한다.
- KEDA는 네 개의 event-driven queue backlog를 기준으로 worker를 0→N→0 확장한다.
- claim, lease heartbeat, stale lease recovery, cancel은 PostgreSQL 상태 전이로 보장한다.
- `workflow_runs`와 `node_execution_logs`가 실행 이력의 유일한 source of truth다. API와
  worker는 DB 저장이 성공한 뒤에만 process-local projection을 갱신하며, DB가 없으면
  production container가 시작되지 않는다.
- 별도 scheduler나 이중 실행 소유권을 추가하지 않는다.
- 실행 정책 변경은 `JobDefinition`과 Kubernetes 투영 계층에서만 수행한다.

## I/O 및 응답 성능 계약

- API는 queue write 후 `202`를 반환하며 module, OpenAI, Excel 분석을 실행하지 않는다.
- sync DB 작업은 FastAPI thread pool 또는 `anyio.to_thread` 경계에서 실행한다.
- 목록과 polling은 compact projection을 사용하고 vector, 원본 workbook, 전체 node
  payload를 읽지 않는다.
- 임베딩은 순서를 보존한 bounded batch 병렬 호출, pgvector 대량 쓰기는 binary COPY
  또는 batch insert를 사용한다.
- SDK와 DB의 재시도는 infrastructure adapter 한 곳에서 bounded budget으로 처리한다.
  route, module, worker가 중첩 재시도를 추가하지 않는다.
- 진행 이벤트는 변경된 node/run projection만 저장하며 전체 그래프를 다시 쓰지 않는다.
- `backend.core.state_stream.SharedStateStream`이 persisted run/job 관찰의 공통 코어다.
  같은 API 프로세스에서 동일 resource를 보는 SSE client는 DB observer 하나를 공유하고,
  느린 client에는 최신 projection만 전달한다. client 수만큼 polling query를 늘리지 않는다.
- 인덱스별 로그 조회는 `node_execution_logs.output.index_id` expression index로 직접
  찾으며 전체 run 목록을 스캔하지 않는다. 과거 누락 이력 복구는 read endpoint가
  아니라 명시적 `backend.cli.backfill_ingestion_run` 운영 명령에서만 수행한다.

## frontend 계약

- `src/shared/api/httpClient.ts`가 유일한 HTTP transport와 `ApiError` 해석을 소유한다.
- `src/shared/api/sse.ts`가 chunk/CRLF-safe SSE decoding을, `src/shared/workflows/`가
  WorkflowRun 타입·node event 병합·재연결을 소유한다. Playground와 Data Sources가
  별도의 streaming/polling 구현을 만들지 않는다.
- feature service는 endpoint와 DTO 변환만 담당하고 자체 `ky.create`나 오류 envelope를
  만들지 않는다.
- graph 탐색과 module 기본값은 `domain/`, React Flow 변환은 `adapters/`, React 상태와
  effect는 `hooks/`에 둔다.
- module category와 canonical workflow는 backend 응답에서 가져오며 누락된 새 category를
  화면에서 숨기지 않는다.
- BI 제품 화면은 `/api/bi/companies`와 published snapshot만 사용한다. fixture는
  `src/test/fixtures`에서 테스트에만 사용하고 제품 route에서 import하지 않는다.

## 자동 강제 규칙

`tests/modules/test_architecture_contracts.py`는 최소한 다음을 실패시킨다.

- feature → API 역방향 import
- module 내부 infrastructure client 생성
- Job registry와 Kubernetes worker spec 불일치
- feature-owned Kubernetes YAML

새 계층 규칙은 문서만 추가하지 않고 같은 변경에서 정적 architecture test를 추가한다.
