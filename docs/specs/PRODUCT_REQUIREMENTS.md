# 제품 요구사항

## 목표

재무 스프레드시트 적재, 하이브리드 RAG 질의, BI 스냅샷 생성과 벤치마크를 하나의 모듈 계약과 Kubernetes 실행 모델로 제공한다. 사용자는 HTTP 요청 수명이나 특정 API 인스턴스에 종속되지 않고 작업을 제출하고 진행 상태를 관찰하며 결과를 재조회할 수 있어야 한다.

## 시스템 경계

| 영역 | 반드시 수행하는 책임 | 금지되는 책임 |
| --- | --- | --- |
| `modules/` | Pydantic 입력·설정·출력, 핵심 계산 | HTTP, 화면 상태, DAG 하드코딩 |
| `jobs/` | 노드·포트·엣지·큐가 포함된 표준 DAG | DB 연결, 모듈 실행, API 호출 |
| backend API | 인증/계약 검증, run 생성, 큐 제출, 조회, SSE | 요청 프로세스에서 핵심 모듈 실행 |
| Kubernetes worker | 큐 claim, DAG 실행, 재시도/타임아웃, 상태 저장 | 사용자 HTTP 세션 보유 |
| PostgreSQL | run/lease/상태, pgvector/FTS, BI 데이터 | 프로세스 로컬 상태에 의존 |
| frontend | 서버 메타데이터 기반 편집·제출·관찰 | 표준 DAG/폐기 모듈의 독자 정의 |

## 비기능 요구사항

- **NFR-EXEC-001**: 제품의 모든 핵심 모듈 실행은 PostgreSQL 큐를 claim한 Kubernetes Job에서만 일어난다.
- **NFR-DUR-001**: API, SSE 연결 또는 브라우저가 종료되어도 제출된 run은 계속 실행되고 다시 조회할 수 있다.
- **NFR-ONCE-001**: Workflow lease/advisory lock과 BI worker generation ID로 한 세대의 작업은 하나의 worker만 결과를 확정한다. heartbeat가 끊긴 stale claim만 회수한다.
- **NFR-IO-001**: 상태 폴링은 대형 입력·중간 산출물·벡터 배열을 읽지 않는 summary projection을 사용한다.
- **NFR-IO-002**: 진행률 저장은 해당 노드 로그와 run 메타데이터만 갱신한다. 매 progress 이벤트마다 전체 DAG JSON을 다시 쓰지 않는다.
- **NFR-IO-003**: 수집과 임베딩은 배치 스트리밍을 사용하고, 요청/응답에 대형 바이너리 또는 벡터 배열을 포함하지 않는다.
- **NFR-SCALE-001**: 큐별 KEDA ScaledJob은 대기 작업 수에 따라 0에서 설정된 최대 동시성까지 확장한다.
- **NFR-OBS-001**: 모든 run과 node는 식별자, 상태, 시간, 오류, 시도 횟수와 외부 worker 식별자를 제공한다.

## 응답 SLO

개발 및 운영 환경의 인프라 지연을 분리하기 위해 API control-plane 시간과 worker 처리 시간을 별도로 측정한다.

| 지표 | 목표 |
| --- | --- |
| run 제출 API p95 | 250 ms 이하(외부 모델 호출 제외) |
| run summary 조회 p95 | 150 ms 이하 |
| SSE 상태 반영 지연 p95 | DB 갱신 후 1초 이하 |
| worker queue claim | Pod Ready 후 2초 이하 |
| 진행률 DB 쓰기 | 노드당 초당 최대 1회로 병합 |
| 중복 실행 | 정상 및 lease 회수 시험에서 0건 |

SLO 측정은 동일 리전의 warm PostgreSQL 기준이며, LLM·embedding 공급자의 응답 시간은 별도 span으로 기록한다.
