# 기능 요구사항

## 공통 모듈 및 워크플로

- **MOD-001**: 서버는 registry의 모듈 정의와 Pydantic JSON schema를 조회 가능하게 제공한다.
- **JOB-001**: 서버는 `jobs/`의 표준 DAG를 유효한 Workflow 문서로 제공한다.
- **JOB-002**: 저장 전과 실행 전 모두 노드 ID, module type, 포트 호환성, 엣지 참조, 순환을 검증한다.
- **JOB-003**: 표준 ID는 `rag_query`, `excel_ingestion`이며 canonical Job은 읽기 전용이다. 편집은 복제한 custom workflow에서만 허용한다.
- **RUN-001**: run 생성은 immutable graph snapshot과 runtime input/config override를 저장하고 즉시 Kubernetes 큐에 제출한다.
- **RUN-002**: 동일 run의 중복 제출은 멱등적이어야 한다.
- **RUN-003**: 실패/중지 run은 성공 노드를 재사용하고 실패/미실행 노드만 재개한다.
- **RUN-004**: 명시적 취소는 DB 플래그로 전달되며 worker는 다음 안전 지점에서 실행을 멈춘다.
- **RUN-005**: SSE 연결 종료는 run을 취소하지 않는다.
- **RUN-006**: Workflow/Run 문서는 schema version 2만 허용하며 이전 형식의 자동 변환이나 상태 상속을 수행하지 않는다.
- **RUN-007**: 모든 노드가 terminal이어도 성공한 sink가 하나도 없으면 run은 실패다.

## OpenAI 추론

- **AI-001**: 텍스트, structured output, function calling, vision은 모두 `POST /v1/responses`를 사용한다.
- **AI-002**: structured output은 `text.format.type=json_schema`와 `strict=true`를 사용한다.
- **AI-003**: tool continuation은 stateful Responses(`store=true`), `previous_response_id`, `function_call_output.call_id`를 사용하며 전체 대화를 재전송하지 않는다. 단발 호출은 `store=false`이다.
- **AI-004**: 기본 모델은 비용/처리량 최적화 모델 `gpt-5.6-luna`이고 일반 텍스트/tool 호출의 reasoning effort는 `none`이다.
- **AI-005**: 하나의 keep-alive HTTP connection pool, 제한된 재시도 예산, normalized usage/cost telemetry를 모든 Responses 호출이 공유한다.

## Excel 수집

- **ING-001**: `.xlsx` 업로드는 파일 메타데이터를 저장한 뒤 표준 `excel_ingestion` Job을 생성·제출한다.
- **ING-002**: selector → Luna 구조 감지 → 대칭 cell text 직렬화 → batch embedding → pgvector writer 순서를 보장한다.
- **ING-003**: 구조 감지 결과와 index 결과를 sheet metadata persistence에 각각 명시적 포트로 전달한다.
- **ING-004**: 동일 문서의 dense HNSW와 PostgreSQL FTS 입력을 한 writer 경계에서 원자적으로 관리한다.
- **ING-005**: 완료 후 source file, sheet, company/index summary를 Data Sources에서 조회할 수 있다.

## 하이브리드 RAG

- **RAG-001**: query context는 router와 decomposer에 전달되고 원 질문의 lineage를 유지한다.
- **RAG-002**: collection loader 결과는 query embedder, dense, keyword 검색에 동일하게 전달되며 query embedding은 선택한 index의 model과 dimension을 강제로 사용한다.
- **RAG-003**: dense와 PostgreSQL native keyword 결과를 RRF로 융합한다.
- **RAG-004**: semantic scope를 두 검색 경로에 동일 적용하고 0건이면 전역 검색으로 완화한다.
- **RAG-005**: context expander가 근거 셀/표 컨텍스트를 구성한 뒤 reader가 답과 근거를 반환한다.

## BI 및 벤치마크

- **BI-001**: BI 프로파일링/materialization과 질문 처리는 각각 전용 PostgreSQL 큐와 KEDA ScaledJob에서 수행한다.
- **BI-002**: BI 검색도 RAG-001~005와 동일한 하이브리드 검색 계약을 재사용한다.
- **BI-003**: 기업, materialization 상태, 스냅샷과 provenance는 PostgreSQL에 저장하며 부분 실패가 다른 기업의 처리를 막지 않는다.
- **BEN-001**: 벤치마크 API는 PostgreSQL `benchmark` 큐에 요청만 저장하고 전용 KEDA worker가 비교 대상별 run을 `workflow-core` 큐에 제출한다.
- **BEN-002**: 진행률, 중간 결과, active run과 최종 비교 결과를 PostgreSQL에 저장해 API/worker 재시작 후에도 재개한다.
- **BEN-003**: 비교 결과에는 실행시간, 비용/usage, 정확성 평가와 실패 원인이 포함된다.

## frontend

- **FE-001**: Playground palette와 node renderer는 `/modules` 응답의 현재 module type만 사용한다.
- **FE-002**: 초기/표준 그래프는 `/workflows`에서 가져오고 frontend 상수로 복제하지 않는다.
- **FE-003**: 실행 UI는 비동기 제출 후 SSE를 사용하고, 연결 실패 시 summary polling으로만 전환한다.
- **FE-004**: Data Sources는 표준 Excel Job만 제출하며 폐기된 exhaustive 변형을 노출하지 않는다.
- **FE-005**: benchmark 대상은 서버 workflow 목록에서 선택하며 존재하지 않는 ID를 하드코딩하지 않는다.
- **FE-006**: frontend는 schema version 2 그래프와 BI layout version 3만 읽으며 이전 저장 형식을 자동 보정하지 않는다.
- **FE-007**: canonical Job은 편집 컨트롤을 비활성화하고 복제 후 편집 경로를 제공한다.

## 공통 실패 계약

- 잘못된 사용자 입력/그래프는 `422`와 구조화된 오류를 반환한다.
- 존재하지 않는 리소스는 `404`, 현재 상태와 충돌하는 동작은 `409`를 반환한다.
- PostgreSQL/큐를 사용할 수 없어 실행을 보장할 수 없으면 `503`을 반환하며 API 내부 실행으로 폴백하지 않는다.
- 외부 공급자 오류는 node failure로 영속화하고 run summary/SSE에서 관찰 가능해야 한다.
