# Architecture & Design Documentation

이 디렉토리는 시스템 아키텍처 결정 기록(ADR) 및 파이프라인 설계 문서를 관리합니다.

---

## Architecture Decision Records (ADRs)

| ADR ID | 제목 | 상태 | 날짜 |
| :--- | :--- | :--- | :--- |
| [ADR-001](adr/0001-hybrid-indexing-and-streaming-ingestion-strategy.md) | **Hybrid Indexing (Dense HNSW + Sparse GIN FTS) and Streaming Ingestion Strategy** | `Accepted` | 2026-08-21 |
| [ADR-002](adr/0002-semantic-query-data-scope-routing-and-prefiltering.md) | **Semantic Query Data Scope Routing & SQL Metadata Pre-filtering (Company & Sheet Scoping)** | `Accepted` | 2026-08-21 |
| [ADR-003](adr/0003-entity-to-intent-mapping-and-symmetric-serialization.md) | **Entity-to-Intent Mapping & Symmetric `Company: ...` Serialization Architecture** | `Accepted` | 2026-08-21 |
| [ADR-004](adr/0004-module-architecture-and-pydantic-structured-output-standard.md) | **Module Architecture Simplification & Pydantic Structured Output Standard** | `Accepted` | 2026-08-22 |

---

## 개발 표준 & 가이드 (Standards & Guidelines)
- [**제품 및 기능 명세**](specs/README.md): Kubernetes 실행 경계, 기능 요구사항, API 계약, SLO와 검증 기준의 단일 진입점.
- [**클린 아키텍처 계약**](specs/ARCHITECTURE_CONTRACT.md): frontend/backend/worker/Kubernetes의 의존 방향과 객체 수명, KEDA 실행 계약.
- [**현재 모듈 런타임 아키텍처**](MODULE_HIERARCHY_ARCHITECTURE.md): `BaseModule`, `BaseLLMModule`, `BaseEmbeddingModule` 계층과 Responses·I/O 계약.
- [**RAG Pipeline Coding Standards & Module Patterns**](CODING_STANDARDS.md): 모듈 표준 레이아웃, Pydantic Structured Output 규칙, 대칭 직렬화 및 단일 소스 원칙 명세.

---

## 핵심 요약
- **하이브리드 인덱싱 (ADR-001)**: 단일 PostgreSQL 16 + `pgvector` 저장소 내에서 **HNSW 벡터 인덱스**와 **GIN FTS 전문검색 인덱스**를 동시 구축하고 **RRF Fusion**으로 결합.
- **스트리밍 수집 (ADR-001)**: `BaseEmbeddingModule` 및 `CellTextEmbedder`의 `storage_sink` 콜백을 통해 $O(\text{batch\_size})$ 수준으로 피크 메모리를 엄격히 제한.
- **데이터 스코프 라우팅 & 사전 필터링 (ADR-002)**: `(company_name, sheet_name)` 복합 스코프를 추론하여 DB 레벨에서 SQL 사전 필터링 푸시다운을 수행하고, 결과 0건 시 전역 검색으로 자동 릴랙스 폴백하여 재현율 100% 보장.
- **개체-인텐트 매핑 & 대칭 직렬화 (ADR-003)**: 복합 질의에서 기업별 요구 지표(`company_scopes`)를 격리 분해하고, 수집기와 질의기 모두 `Company: {company} | Sheet: {sheet} | ...` 포맷을 적용하여 교차 오염을 100% 차단.
- **모듈 단일화 및 Pydantic 구조화 (ADR-004)**: 중복 디렉토리/모듈을 단일화하고, 비정형 문자열 파싱 대신 Pydantic `model_validate_json()`을 통해 안전하고 견고한 데이터 파이프라인 구축.
- **Kubernetes 실행 단일화**: API는 계약 검증, PostgreSQL 큐 제출, 상태 조회와 SSE 전달만 수행한다. 실제 모듈 실행은 KEDA가 확장하는 일회성 Kubernetes Job에서만 수행한다.
