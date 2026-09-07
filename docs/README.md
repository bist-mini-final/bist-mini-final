# 프로젝트 문서

[프로젝트 소개](../README.md) · [설치·실행](guides/SETUP.md) · [완료 요약](PROJECT_SUMMARY.md) · [협업·품질 관리](guides/COLLABORATION.md)

기준일: **2026-09-07** · 최종 소스: **`main`**

루트 README는 프로젝트 소개와 기능 시연을 담당하고, 사용·개발 가이드, 설계 문서, 평가 기록은 이 문서에서 찾아갑니다.

## 문서 구조

```text
docs/
├── README.md                           문서 통합 목차
├── PROJECT_SUMMARY.md                  프로젝트 결과·평가 기준·한계
├── CURRENT_IMPLEMENTATION_BASELINE.md  현재 구현 기준선
├── guides/                             설치·협업·DB 변경 가이드
│   ├── SETUP.md
│   ├── COLLABORATION.md
│   └── MIGRATIONS.md
├── blueprints/                         시스템·데이터·API 등 20개 설계 문서
├── evaluation/                         서버 실측 보고·원본 데이터·화면 근거
└── assets/                             기능 시연 GIF·README 커버
```

[개발·운영 가이드](guides/README.md) · [설계 문서](blueprints/README.md) · [평가 기록](evaluation/README.md) · [시연 자료](assets/README.md)

## 목적에 따라 읽기

| 목적 | 문서 | 담고 있는 내용 |
| --- | --- | --- |
| 처음 실행하기 | [설치·실행·배포](guides/SETUP.md) | 환경 변수, 로컬 서버, 워커, k3d·Helm, 문제 해결 |
| 완성된 결과 확인 | [프로젝트 완료 요약](PROJECT_SUMMARY.md) | 3단계 MVP, 기능, 평가 기준, 지원 범위와 한계 |
| 협업 방식 이해 | [협업·컨벤션·품질 관리](guides/COLLABORATION.md) | PR, GitHub Actions, CodeRabbit, 코드 규칙, 테스트 |
| 현재 코드 확인 | [구현 기준선](CURRENT_IMPLEMENTATION_BASELINE.md) | 제품 경계, 모듈·API·DB, 책임 구조, 검증 기록 |
| 상세 구조 이해 | [청사진 해석 규칙](blueprints/README.md) | 유지할 설계 계약과 20개 BP의 읽는 방법 |
| DB 변경 적용 | [마이그레이션 안내](guides/MIGRATIONS.md) | Alembic 실행과 schema 변경 관리 |
| 실험 근거 확인 | [서버 평가 기록](evaluation/README.md) | 실행 조건을 보존한 자동평가·성능·보안 기록 |

## 문서 기준

- **현재 구현**은 기준선과 해당 소스 코드를 함께 확인합니다. API·DB 수치는 기준선에서 관리합니다.
- **청사진**은 구현 완료 후에도 유지해야 할 책임·입출력·의존 규칙입니다. `Contract State: Target Architecture`는 미완료 표시가 아니며, 개별 BP의 `Structure State`는 모두 `Complete`입니다.
- **평가 기록**의 날짜·브랜치·이미지·수치는 실행 당시 조건입니다. 최종 보고 수치와 과거 자동채점 기록은 [평가 해석 기준](PROJECT_SUMMARY.md#평가-결과를-읽는-방법)에 따라 구분합니다.
- **시연 자료**는 [assets](assets/)의 GIF를 사용합니다. 발표·보고서 초안과 개인 임시 파일은 구현 계약의 기준으로 삼지 않습니다.
- **배치 원칙**: 새 가이드는 `guides/`, 설계 계약은 `blueprints/`, 평가 보고와 해당 원본은 `evaluation/`에 함께 둡니다. 실행 코드·DB revision·CI 설정은 원래 코드 디렉터리에 유지하고 문서에서 상대 링크로 연결합니다.

## 상세 설계 문서

시스템 → 데이터 처리 → 파이프라인 → 제품 화면 → 인터페이스 → 프론트엔드 → 검증 순서로 구성했습니다. 특정 기능만 살펴볼 때는 해당 워크스페이스 문서에서 구현 링크를 따라가면 됩니다.

| 도메인 | 청사진 번호 & 문서명 | 핵심 기술 스펙 및 내용 |
| :--- | :--- | :--- |
| **01. System** | [`BP-101`](blueprints/01_system_blueprints/BP-101_system_architecture_blueprint.md) | durable job 토폴로지, PostgreSQL 영속 상태, Redis 신호 및 KEDA 런타임 |
| | [`BP-102`](blueprints/01_system_blueprints/BP-102_backend_layered_architecture.md) | 완성된 modular monolith 트리, application port 의존성 및 구조 hard gate |
| | [`BP-103`](blueprints/01_system_blueprints/BP-103_concurrency_and_locking_model.md) | 3-Level 분산 락, 하트비트 Lease & 장애 복구 런북 |
| | [`BP-104`](blueprints/01_system_blueprints/BP-104_deployment_and_infra_topology.md) | Helm·Kubernetes KEDA ScaledJob, TriggerAuthentication 및 `/api/v1/jobs` |
| **02. Data Engine** | [`BP-201`](blueprints/02_data_engine_blueprints/BP-201_spreadsheet_coordinate_parser.md) | OpenPyXL 병합 해제 및 2D 직교 좌표계 정규화 |
| | [`BP-202`](blueprints/02_data_engine_blueprints/BP-202_luna_vlm_vision_detector.md) | 외부 OpenAI vision 기반 시트 구조 감지 및 결과 검증 |
| | [`BP-203`](blueprints/02_data_engine_blueprints/BP-203_binary_copy_vector_pipeline.md) | PostgreSQL Native `Binary COPY` 3072d 고속 벌크 주입 |
| **03. Pipeline** | [`BP-301`](blueprints/03_pipeline_module_blueprints/BP-301_dag_execution_engine.md) | Kahn 위상정렬 DAG, durable queue 실행 및 FSM |
| | [`BP-302`](blueprints/03_pipeline_module_blueprints/BP-302_module_pinout_catalog.md) | `ModuleRegistry` 기준 17개 원자적 파이프라인 모듈 계약 |
| | [`BP-303`](blueprints/03_pipeline_module_blueprints/BP-303_hybrid_retrieval_and_fusion.md) | Dense(3072d) + PostgreSQL FTS + RRF($k=60$) 융합 검색 |
| **04. Workspaces** | [`BP-401`](blueprints/04_workspace_blueprints/BP-401_ws_pipeline_playground.md) | 모듈 카탈로그, DAG 실행 및 SSE 상태 스트림 |
| | [`BP-402`](blueprints/04_workspace_blueprints/BP-402_ws_data_sources_management.md) | 스프레드시트 미리보기 및 영속 ingestion job 관리 |
| | [`BP-403`](blueprints/04_workspace_blueprints/BP-403_ws_financial_bi_analytics.md) | 21개 근거 기반 BI 지표와 재무 분석 화면 |
| | [`BP-404`](blueprints/04_workspace_blueprints/BP-404_ws_ai_financial_chatbot.md) | RAG 실행 작업, 상태 조회 및 대화형 챗봇 |
| | [`BP-405`](blueprints/04_workspace_blueprints/BP-405_ws_company_comparison.md) | 검증된 BI 원천 기반 버전형 기업 비교 스냅샷과 재무 순위·선택 비교 |
| **05. Interface** | [`BP-501`](blueprints/05_interface_blueprints/BP-501_rest_api_specification.md) | FastAPI REST API 엔드포인트 & 표준 에러 엔벨로프 |
| | [`BP-502`](blueprints/05_interface_blueprints/BP-502_sse_streaming_protocol.md) | Server-Sent Events(SSE) 실시간 스트리밍 프로토콜 |
| | [`BP-503`](blueprints/05_interface_blueprints/BP-503_database_erd_and_ddl.md) | Alembic 관리 PostgreSQL·pgvector·버전형 도메인 스냅샷 ERD & DDL |
| **06. Frontend** | [`BP-601`](blueprints/06_frontend_blueprints/BP-601_frontend_component_wiring.md) | React 18 SPA 컴포넌트 배선도, 모바일 상단 앱바·drawer 및 a11y 표준 |
| **07. Validation** | [`BP-701`](blueprints/07_validation_blueprints/BP-701_contract_testing_and_benchmarks.md) | AST 아키텍처 계약 검증 & 정량 벤치마크 하네스 |
