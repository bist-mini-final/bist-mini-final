# [BP-701] 아키텍처 불변식 계약 테스트 & 벤치마크
> **Document Code:** `BP-701` | **Category:** Validation & Benchmark Blueprint | **Status:** Implemented & Operational
> **Source Files:** [`tests/modules/test_architecture_contracts.py`](file:///c:/Repos/bist-mini-final/tests/modules/test_architecture_contracts.py), [`tests/modules/test_workflow_http_queue_sse_integration.py`](file:///c:/Repos/bist-mini-final/tests/modules/test_workflow_http_queue_sse_integration.py), [`tests/modules/test_redis_state_stream_integration.py`](file:///c:/Repos/bist-mini-final/tests/modules/test_redis_state_stream_integration.py), [`.github/workflows/ci.yml`](file:///c:/Repos/bist-mini-final/.github/workflows/ci.yml)

---

## 1. 아키텍처 불변식 계약 테스트 (Executable Architecture Contracts)

리팩토링 시 개발자의 실수로 계층 간 의존성 규칙이 깨지거나, 하위 모듈이 상위 API/인프라 클래스를 직접 인스턴스화하는 안티패턴을 원천 차단하기 위해 **Python AST(Abstract Syntax Tree) 기반 정적 계약 검증 테스트**를 실행합니다.

```mermaid
flowchart TD
    PYTEST["Pytest Runner (pytest tests/modules/)"] --> AST_PARSE["AST Parser (ast.walk on all .py files)"]
    
    subgraph Rules ["3대 불변식 아키텍처 헌법 (Architecture Invariants)"]
        R1["규칙 1: Feature -> API 역방향 참조 금지 (features never imports backend.api)"]
        R2["규칙 2: Modules 내 인프라 직접 생성 금지 (modules never constructs DatabaseManager, PgVectorStore...)"]
        R3["규칙 3: Kubernetes Worker Spec 불변식 검증 (Jobs <-> K8s Manifest Sync)"]
    end

    AST_PARSE --> Rules
    Rules --> PASS["✅ CI 파이프라인 통과 (Zero Architecture Drift)"]
    Rules --> FAIL["❌ Violations Raised (빌드 즉시 차단)"]
```

---

## 2. AST 계약 검증 테스트 구현 원리 (`test_architecture_contracts.py`)

### 1. `features` -> `api` 역방향 의존성 차단
```python
def test_features_never_import_http_api_layer() -> None:
    violations: list[str] = []
    for path in _python_files("backend/features"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("backend.api"):
                violations.append(str(path.relative_to(PROJECT_ROOT)))
    assert not violations, f"feature -> API layer inversion: {sorted(set(violations))}"
```

### 2. `modules`의 DI 의존성 주입 준수 (인프라 직접 생성 금지)
- 모듈 내부에서 `DatabaseManager()`, `PgVectorStore()`, `OpenAIProvider()`를 직접 `__init__`에서 생성하는 행위를 금지하고, 반드시 레지스트리나 팩토리로부터 주입받도록 강제합니다.

---

## 3. 정량적 벤치마크 평가 파이프라인 (`BenchmarkService`)

실제 재무 Q&A 정답지(Ground-Truth QA Dataset)를 기반으로 RAG 파이프라인의 검색 정확도와 답변 일치도를 정량 측정합니다:

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Evaluator
    participant BM as BenchmarkService
    participant QP as QuestionPipeline (Hybrid RAG)
    participant GT as Ground Truth Dataset
    participant Metric as Evaluation Metrics Engine

    Dev->>BM: run_benchmark(dataset_id, pipeline_config)
    BM->>GT: load_test_cases()
    loop 각 테스트 케이스
        BM->>QP: execute_question(test_case.query)
        QP-->>BM: generated_answer, cited_cells, latency_ms
        BM->>Metric: evaluate(ground_truth, generated_answer, cited_cells)
    end
    Metric-->>BM: BenchmarkReport (Accuracy, Precision@K, Recall@K, Latency P95)
    BM-->>Dev: JSON Evaluation Report & Visualization
```

### 4대 벤치마크 평가 메트릭 (Evaluation Metrics)
1. **Exact Match (EM)**: 수치 및 단위가 완벽히 일치하는 비율 (목표: > 95%)
2. **Cell Recall@5**: 실제 정답 셀이 상위 5개 검색 후보에 포함된 비율 (목표: > 98%)
3. **P95 Latency**: 전체 파이프라인 처리 시간의 95백분위수 (목표: < 500ms for Fast RAG)
4. **Hallucination Rate**: 잘못된 수식을 사용하거나 허위 숫자를 인용한 비율 (목표: 0.0%)

---

## 4. 리팩토링 및 CI 회귀 방지 가이드 (Refactoring Safety Workflow)

```bash
# 1. 아키텍처 계약 검증 (레이어 침범 여부 즉시 검사)
uv run pytest tests/modules/test_architecture_contracts.py

# 2. 전체 모듈 단위 및 통합 테스트 실행
uv run pytest tests/

# 3. 린팅 및 정적 타입 무결성 검사
uv run ruff check .
uv run pyright
```

### 현재 CI 통합 범위

GitHub Actions의 backend job은 PostgreSQL/pgvector와 Redis 서비스를 함께 기동하고 Alembic migration 후 전체 pytest를 실행합니다. 이 과정에는 다음 실사용 경로가 포함됩니다.

1. HTTP 워크플로 저장·큐 등록 → one-shot worker 처리 → `/api/v1/runs/{run_id}/stream` 종료 이벤트까지의 PostgreSQL 통합 계약
2. 서로 다른 `SharedStateStream` 인스턴스가 Redis Pub/Sub 알림을 받고, 60초 polling을 기다리지 않고 저장 상태를 다시 읽는 멀티 API Pod 시뮬레이션
3. Kubernetes ScaledJob renderer가 네 개의 유효한 `ScaledJob` 문서를 생성하는지 확인

---

## 5. 리팩토링 타깃 (Refactoring Targets)

1. **신규 기능 및 모듈 추가 시 단위 테스트 동반 확장 (Test Suite Co-Evolution)**:
   - **원칙**: 향후 신규 파이프라인 모듈(예: `DocumentProfilerModule`, `FinancialCalculatorModule`)이나 신규 비즈니스 기능(AI 챗봇 세션, 다중 기업 비교, 벡터 양자화 등) 추가 시, 반드시 **모듈별 독립 단위 테스트(`tests/modules/test_*.py`)와 입출력 Pydantic 핀아웃 계약 검증 테스트를 의무적으로 동반 추가**합니다.
   - **AST 아키텍처 규칙 확장**: 신규 레이어나 컴포넌트가 추가될 때마다 `test_architecture_contracts.py`에 불변식(Layer Inversion 차단 규칙)을 즉시 갱신하여 아키텍처 드리프트를 0%로 유지합니다.
   - **벤치마크 데이터셋 동기화**: 신규 도메인 수식 및 시나리오에 대한 Ground-Truth 정답 Q&A 데이터셋을 확충하여 릴리즈 전 회귀(Regression) 여부를 정량 검증합니다.
2. **구현됨 — 비동기 핵심 흐름 통합 테스트**:
   - FastAPI HTTP 호출 → PostgreSQL durable queue → one-shot worker → SSE terminal event와 Redis 멀티 Pod 상태 알림을 자동 검증합니다.
   - 실제 PostgreSQL을 사용하는 `AsyncConnectionPool` 재사용·쿼리·반환과 `TaskGroup` 병렬 상태 병합을 검증합니다. Native async leaf가 sync `execute()`를 우회하는 실행기 계약, Decomposer/Router/Reader의 async Responses, Query Embedder의 async embedding, data scope·dense/keyword Retriever·context expansion·Reader 셀 조회 도구의 async port 호출도 각각 회귀 검사합니다.
   - 파일 업로드부터 실제 OpenAI 임베딩과 Binary COPY까지의 전체 연결은 외부 API 비용·키가 필요하므로 현재 CI의 결정론적 기본 경로에는 넣지 않았습니다. 별도 통합 환경에서 확장할 대상입니다.
3. **구현됨 — GitHub Actions CI**:
   - `dev`, `main`의 push/PR에서 migration, pytest, Ruff, Pyright, ScaledJob render, 프론트엔드 typecheck·Vitest·build를 자동 실행합니다.
