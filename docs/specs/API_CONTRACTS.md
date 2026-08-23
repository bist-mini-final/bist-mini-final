# API 계약

## 비동기 run 실행

`POST /api/workflows/{workflow_id}/runs`

- 요청을 검증하고 run snapshot을 PostgreSQL에 저장한 뒤 `workflow-core` 큐에 넣는다.
- 성공은 `202 Accepted`이며 body는 compact `WorkflowRun`이다.
- 실행 가능한 DB 큐가 없으면 `503`; 로컬 실행 폴백은 없다.
- 같은 run ID에 대한 dispatcher submit은 이미 queued/running이면 no-op이다.

`POST /api/runs/{run_id}/resume`은 실패/paused 상태를 정리하고 동일 큐에 재제출한다. `POST /api/runs/{run_id}/cancel`은 cancellation flag를 영속화한다.

Workflow와 Run 응답의 `schema_version`은 `2`로 고정한다. v1 그래프, `default` workflow 별칭, run 상태 상속 필드는 지원하지 않는다.

## OpenAI Responses 공급자 계약

- endpoint: `POST /v1/responses`
- single-turn text/vision/structured requests: `store=false`
- function tool loop: `store=true`; 후속 호출은 `previous_response_id`와 현재
  `instructions`를 다시 전달해 서버 측 상태를 이어 간다.
- structured output: `text.format={type: "json_schema", name, schema, strict: true}`
- tool definition: top-level `{type: "function", name, description, parameters, strict: true}`
- tool result: `{type: "function_call_output", call_id, output}`와 `previous_response_id`
- usage projection: `input_tokens → prompt_tokens`, `output_tokens → completion_tokens`, cached/reasoning token detail을 보존한다.

## 조회와 스트리밍

`GET /api/runs/{run_id}`와 `GET /api/runs`는 polling-safe summary를 반환한다. summary에는 대형 node input/output 대신 상태와 허용된 작은 도메인 결과만 포함한다.

`GET /api/runs/{run_id}/stream`은 다음 이벤트를 제공한다.

| event | data |
| --- | --- |
| `run_started` | 최초 compact run 식별자와 크기 |
| `node_progress` | pending/running node 또는 진행률 변경 |
| `node_completed` | succeeded/skipped node snapshot |
| `node_failed` | failed node snapshot |
| `run_completed` | terminal compact snapshot |

SSE는 이미 제출된 작업을 관찰할 뿐 실행기를 호출하지 않는다. 클라이언트 disconnect나 네트워크 오류는 취소 의미가 아니다.

## 오류 envelope

FastAPI validation 오류를 제외한 도메인 오류는 다음 형태를 사용한다.

```json
{
  "detail": {
    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
    "message": "Kubernetes 실행 큐를 사용할 수 없습니다",
    "retryable": true,
    "context": {"workflow_id": "rag_query"}
  }
}
```

frontend는 `code`를 분기 조건으로 사용하고 한국어 `message`를 파싱하지 않는다.

## BI 비동기 실행

`POST /api/bi/materializations`는 요청과 queued job을 PostgreSQL에 한 트랜잭션으로 저장하고 `202`를 반환한다. API는 profiler, RAG 또는 snapshot builder를 실행하지 않는다. materialization 상태 및 dashboard 조회는 PostgreSQL projection만 사용하며 큐가 없으면 `503`을 반환한다.

벤치마크는 `POST /api/benchmarks/jobs`만 실행 진입점으로 제공하며 PostgreSQL `benchmark` 큐에 저장한 뒤 즉시 `202`와 job ID를 반환한다. 비교 조정·채점도 전용 Kubernetes worker가 수행하며 API 메모리 thread나 JSON 결과 파일에 의존하지 않는다. 동기 장기 실행 endpoint는 제공하지 않는다.
