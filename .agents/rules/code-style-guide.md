---
trigger: always_on
glob: "**/*.py"
description: Project coding standards, LangChain/Pydantic library standards, module layout, and global exception guidelines
---

# RAG Pipeline Coding Standards & Module Patterns

본 문서는 `bist-mini-final` 프로젝트의 파이프라인 모듈 아키텍처, 코드 배치 표준, LangChain / Pydantic 라이브러리 표준 상속 규칙 및 전역 예외 처리 가이드라인을 정의합니다.

---

## 1. 핵심 아키텍처 및 라이브러리 표준 원칙

### 1.1 단일 소스 원칙 (Single Source of Truth)
- 모든 RAG 파이프라인 모듈은 **`modules/` 디렉토리 아래에서만 관리**합니다.
- 중복 래퍼 모듈, 분신 디렉토리(`backend/pipeline/` 등) 생성을 엄격히 금지합니다.
- 백엔드 런타임(`backend/engine/runtime/registry.py`)은 오직 `modules.*`에서 모듈을 직접 import하여 등록합니다.

### 1.2 하드코딩 정적 사전 및 캐시 배제 (Zero Hardcoded Thesaurus)
- 수백 줄에 달하는 하드코딩 정적 동의어 사전, thesaurus 테이블, 과거 질의 캐시 등의 불투명한 임시 패치는 금지합니다.
- 모든 자연어 쿼리 분석 및 원자적 서브쿼리 확장은 **최신 LLM 프롬프트와 Pydantic 모델**을 통해 결정론적으로 수행합니다.

### 1.3 `BaseLLMModule` / `BaseEmbedderModule` 기반 부모-자식 계층 분리 및 호출 단일화
- LLM 호출, Pydantic JSON 파싱, 멀티턴 도구 호출 루프(Tool Calling Loop), 토큰 사용량 집계, OpenAI 비용 계산, 지연 시간 측정을 자식 모듈마다 수십 줄씩 반복 작성하지 않습니다.
- **부모 클래스(`BaseLLMModule`, `BaseEmbedderModule`)의 책임**:
  - `self.complete_structured(...)` : 1-shot 구조화 생성, Pydantic 파싱, 토큰/비용/지연 집계
  - `self.complete_text(...)` : 1-shot 텍스트 생성, 토큰/비용/지연 집계
  - `self.complete_agentic(...)` : LangChain BaseTool 멀티턴 에이전틱 도구 루프, 도구 자동 invoke, 에러 피드백, 턴 누적 토큰/비용/지연 일괄 집계
  - `self.encode_texts(...)` / `self.encode_batches_streaming(...)` : 배치 임베딩, 차원 검증, 스트리밍 진행 보고
- **자식 모듈의 책임**:
  - 오직 자신만의 고유한 Pydantic DTO 선언, 프롬프트 템플릿, 도메인 Tool 정의 및 부모 메서드 1줄 호출만 수행합니다.

### 1.4 LangChain 표준 클래스 상속 및 도구 정의 규칙
- **에이전트 도구 (Tools)**:
  - 수동 JSON 딕셔너리 스키마나 어색한 클로저 팩토리 함수 대신, **LangChain 공식 `langchain_core.tools.BaseTool` 클래스를 직접 상속**하여 구현합니다.
  - 입력 계약은 반드시 `args_schema: Optional[ArgsSchema] = YourInputPydanticModel`로 명시하고, 실행은 `_run(self, ...)` 메서드를 구현합니다.
  - 외부 의존성(DB 스토어, 워크북 해시 등)은 도구 클래스의 필드로 주입합니다.
- **임베딩 인코더 (Embeddings)**:
  - 모든 임베딩 인코더는 **`langchain_core.embeddings.Embeddings`를 직접 상속**받아 `embed_documents(self, texts)` 및 `embed_query(self, text)`를 표준 구현합니다.
- **문서 및 벡터 저장소**:
  - 문서는 `langchain_core.documents.Document(page_content=..., metadata=...)` 표준 모델을 사용하며, `langchain_postgres.PGVector` 스키마와 100% 호환되도록 구성합니다.

---

## 2. 표준 모듈 배치 레이아웃 (Standard Module Layout)

모든 모듈 파일은 아래의 일관된 **5단계 배치 순서**를 준수합니다:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Imports & Logger Setup                                   │
│    - __future__, 표준 라이브러리, typing, Pydantic           │
│    - LangChain Core 표준 클래스 (BaseTool, Embeddings 등)    │
│    - modules.common (BaseModule, BaseLLMModule 등)          │
│    - logger = logging.getLogger(__name__) (모든 모듈 통일)   │
├─────────────────────────────────────────────────────────────┤
│ 2. Prompts & Presets (LLM 모듈인 경우)                      │
│    - MODULE_SYSTEM_PROMPT                                   │
│    - MODULE_USER_TEMPLATE                                   │
│    - MODULE_PRESETS (딕셔너리)                               │
├─────────────────────────────────────────────────────────────┤
│ 3. DTOs & Item Models                                       │
│    - Domain Pydantic Models (입력/출력/아이템 스키마)         │
│    - ModuleInputDTO (ModuleInputDTO 상속)                   │
│    - ModuleConfigDTO (ModuleConfigDTO 상속)                 │
│    - ModuleOutputDTO (ModuleDTO 상속)                       │
├─────────────────────────────────────────────────────────────┤
│ 4. Module Implementation                                    │
│    - class XModule(BaseLLMModule 또는 BaseModule):          │
│        * definition: ModuleDefinition                       │
│        * input_model, config_model, output_model 바인딩      │
│        * __init__()                                         │
│        * execute()                                          │
├─────────────────────────────────────────────────────────────┤
│ 5. Exports (__all__)                                        │
│    - 알파벳순 정렬된 공개 심볼 리스트                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Pydantic Structured Output & 금지 안티패턴

### 3.1 LLM 구조화 생성 표준 패턴
`BaseLLMModule`을 상속하여 1줄로 처리합니다:

```python
# ✅ 권장: BaseLLMModule 기반 1-line 구조화 생성
class DecomposerModule(BaseLLMModule):
    input_model = DecomposerInputDTO
    config_model = DecomposerConfigDTO
    output_model = SubqueriesDTO

    def execute(self, input_data: DecomposerInputDTO, config: Optional[DecomposerConfigDTO] = None) -> Dict[str, Any]:
        cfg = config or DecomposerConfigDTO()
        
        parsed_res, usage, cost_usd, latency_sec = self.complete_structured(
            messages_or_prompt=f"User Query: {input_data.query_context.question_text}",
            response_model=DecomposedSubqueriesResponse,
            model=cfg.model,
            system_prompt=LUNA_SYSTEM_PROMPT,
        )
        return {
            "query_context": input_data.query_context.model_dump(mode="json"),
            "subqueries": [item.to_serialized_query() for item in parsed_res.items],
        }
```

### 3.2 엄격한 금지 안티패턴 (Strict Anti-Patterns)
- ❌ **마크다운 백틱 자르기 금지**: `if text.startswith("```"): lines = text.split(...)`
- ❌ **불안정한 정규식 JSON 파싱 금지**: `re.search(r"\{[\s\S]*\}", text)`
- ❌ **취약한 다중 fallback 중첩 금지**: `try: json.loads(...) except: try: eval(...)`
- ❌ **불필요한 ExecutionDTO 보일러플레이트 금지**: `class XExecutionDTO(XInputDTO, XConfigDTO): pass` 작성 지양

---

## 4. 전역 예외 처리 및 도메인 에러 패턴 (Centralized Global Exception Handling)

### 4.1 도메인 예외 계층 구조 (Domain Exception Hierarchy)
모든 파이프라인 예외는 `modules.common.exceptions`에 정의된 **`PipelineBaseError` 하위 클래스를 사용**합니다.

```
PipelineBaseError (HTTP 500 / 기본 에러)
 ├── ModuleExecutionError (HTTP 422 / 모듈 실행 실패)
 │    ├── ModuleValidationError (HTTP 422 / 입력·설정 검증 실패)
 │    ├── ProviderApiError (HTTP 502 / LLM·임베딩 API 및 네트워크 오류)
 │    ├── StorageError (HTTP 500 / DB, pgvector, 아티팩트 I/O 오류)
 │    └── DocumentParsingError (HTTP 422 / Excel, VLM 구조 파싱 실패)
```

### 4.2 `BaseModule.run()` 템플릿 메서드 에러 가드 (Zero Exception Boilerplate in `execute()`)
- 개별 모듈의 `execute()` 내부에 `try-except Exception ... raise ModuleExecutionError(...)`와 같은 **불필요한 중복 래핑을 작성하지 않습니다**.
- 최상위 `BaseModule.run()` 템플릿 메서드가 실행 과정에서 발생하는 모든 저수준 예외(Pydantic ValidationError, OpenAI API Timeout, Rate Limit, 연결 오류 등)를 **`ProviderApiError`, `ModuleValidationError`, `ModuleExecutionError`로 자동 판별·분류하고 `module_type`과 함께 표준 래핑**합니다.
- 단, Agentic Tool 내부(`Tool._run()`)에서 발생하는 파라미터 오탈자나 수식 오류는 파이프라인을 크래시시키지 않고 LLM이 스스로 인지하여 재시도할 수 있도록 Tool 메시지 문자열(`"Calculation error: ..."` 등)을 반환합니다.

### 4.3 FastAPI 전역 Exception Handler 표준 응답
- `backend/main.py`의 전역 핸들러(`@app.exception_handler(PipelineBaseError)`)가 모든 파이프라인 에러를 표준화된 JSON 규격으로 클라이언트에 응답합니다:
  ```json
  {
    "error_code": "PROVIDER_API_ERROR",
    "message": "모듈 [reader] 외부 API 호출 실패: Rate limit exceeded",
    "module_type": "reader",
    "details": { "provider": "openai" }
  }
  ```
