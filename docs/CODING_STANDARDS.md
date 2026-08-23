# RAG Pipeline Coding Standards & Module Patterns

본 문서는 `bist-mini-final` 프로젝트의 파이프라인 모듈 아키텍처, 코드 배치 표준, Pydantic 기반 구조화 입출력 규칙 및 데이터 직렬화 가이드라인을 정의합니다.

---

## 1. 핵심 아키텍처 원칙

### 1.1 단일 소스 원칙 (Single Source of Truth)
- 모든 RAG 파이프라인 모듈은 **`modules/` 디렉토리 아래에서만 관리**합니다.
- 중복 래퍼 모듈, 분신 디렉토리(`backend/pipeline/` 등) 생성을 엄격히 금지합니다.
- 백엔드 런타임(`backend/engine/runtime/registry.py`)은 오직 `modules.*`에서 모듈을 직접 import하여 등록합니다.

### 1.2 하드코딩 정적 사전 및 캐시 배제 (Zero Hardcoded Thesaurus)
- 수백 줄에 달하는 하드코딩 정적 동의어 사전, thesaurus 테이블, 과거 질의 캐시 등의 불투명한 임시 패치는 금지합니다.
- 모든 자연어 쿼리 분석 및 원자적 서브쿼리 확장은 **최신 LLM 프롬프트와 Pydantic 모델**을 통해 결정론적으로 수행합니다.

### 1.3 `BaseLLMModule` / `BaseEmbeddingModule` 기반 호출 단일화
- LLM 호출, Pydantic JSON 파싱, 멀티턴 도구 호출 루프(Tool Calling Loop), 토큰 사용량 집계, OpenAI 비용 계산, 지연 시간 측정을 자식 모듈마다 수십 줄씩 반복 작성하지 않습니다.
- **부모 클래스(`BaseLLMModule`, `BaseEmbeddingModule`)의 책임**:
  - `self.complete_structured(...)` : 1-shot 구조화 생성, Pydantic 파싱, 토큰/비용/지연 집계
  - `self.complete_text(...)` : 1-shot 텍스트 생성, 토큰/비용/지연 집계
  - `self.complete_agentic(...)` : 공식 Responses API의 stateful 멀티턴 도구 루프, 도구 자동 invoke, 에러 피드백, 턴 누적 토큰/비용/지연 일괄 집계
  - `self.encode_texts(...)` / `self.encode_batches_streaming(...)` : 배치 임베딩, 차원 검증, 스트리밍 진행 보고
- **자식 모듈의 책임**:
  - 오직 자신만의 고유한 Pydantic DTO 선언, 프롬프트 템플릿, 도메인 Tool 정의 및 부모 메서드 1줄 호출만 수행합니다.

### 1.4 `ExecutionDTO` 보일러플레이트 배제 (Dynamic DTO Resolution)
- `BaseModule`이 `input_model`과 `config_model`을 런타임에 동적으로 바인딩하므로, 껍데기 상속 클래스인 `class XExecutionDTO(XInputDTO, XConfigDTO): pass`를 작성하지 않습니다.

---

## 2. 표준 모듈 배치 레이아웃 (Standard Module Layout)

모든 모듈 파일은 아래의 일관된 **4단계 배치 순서**를 준수합니다:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Imports & Logger Setup                                   │
│    - __future__, 표준 라이브러리, typing, Pydantic           │
│    - modules.common (BaseModule, BaseLLMModule 등)          │
│    - logger = logging.getLogger(__name__) (모든 모듈 통일)   │
├─────────────────────────────────────────────────────────────┤
│ 2. Prompts & Presets (LLM 모듈인 경우)                      │
│    - MODULE_SYSTEM_PROMPT                                   │
│    - MODULE_USER_TEMPLATE                                   │
├─────────────────────────────────────────────────────────────┤
│ 3. DTOs & Item Models                                       │
│    - Domain Pydantic Models (직렬화 메서드 포함)             │
│    - ModuleInputDTO                                         │
│    - ModuleConfigDTO                                        │
│    - ModuleOutputDTO                                        │
├─────────────────────────────────────────────────────────────┤
│ 4. Module Implementation                                    │
│    - class XModule(BaseLLMModule 또는 BaseModule):          │
│        * definition: ModuleDefinition                       │
│        * input_model, config_model, output_model 바인딩      │
│        * __init__()                                         │
│        * execute()                                          │
├─────────────────────────────────────────────────────────────┤
│ 5. __all__                                                  │
│    - 알파벳순 정렬된 공개 심볼 리스트                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Pydantic Structured Output & 파싱 규칙

### 3.1 LLM 호출 및 파싱 표준 패턴 (Structured Output Standard)
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

### 3.2 금지 패턴 (Anti-Patterns)
- ❌ **마크다운 백틱 자르기 금지**: `if text.startswith("```"): lines = text.split(...)`
- ❌ **불안정한 정규식 파싱 금지**: `re.search(r"\{[\s\S]*\}", text)`
- ❌ **취약한 다중 fallback 중첩 금지**: `try: json.loads(...) except: try: eval(...)`
- ❌ **빈 껍데기 ExecutionDTO 다중 상속 금지**: 불필요한 DTO 클래스 선언 지양

---

## 4. 도구(Tools) 모듈화 및 Agentic 파이프라인 패턴

- 재무 수식 계산(AST 연산), 공간 셀 검증(PG DB 쿼리)과 같이 복합적 연산을 수행하는 기능은 모듈 내부나 파이프라인 노드로 난잡하게 흩뿌리지 않고 **`modules/<domain>/tools/`** 하위에 순수 함수/도구로 캡슐화합니다.
- 복합 메인 모듈(예: `ReaderModule`)은 이 도구들을 내부에서 체이닝하여 **단일 실행만으로 답변 생성, 수치 검증, 메타데이터 교정을 완결하는 Agentic 구조**를 갖춥니다.

---

## 5. 전역 예외 처리 및 도메인 에러 패턴 (Centralized Global Exception Handling)

### 5.1 도메인 예외 계층 구조 (Domain Exception Hierarchy)
모든 파이프라인 예외는 `modules.common.exceptions`에 정의된 **`PipelineBaseError` 하위 클래스를 사용**하며, 문자열 기반의 단순 예외 포획 대신 원인별로 명확히 분리된 예외 타입을 사용합니다.

```
PipelineBaseError (HTTP 500 / 기본 에러)
 ├── ModuleExecutionError (HTTP 422 / 모듈 실행 실패)
 │    ├── ModuleValidationError (HTTP 422 / 입력·설정 검증 실패)
 │    ├── ProviderApiError (HTTP 502 / LLM·임베딩 API 및 네트워크 오류)
 │    ├── StorageError (HTTP 500 / DB, pgvector, 아티팩트 I/O 오류)
 │    └── DocumentParsingError (HTTP 422 / Excel, VLM 구조 파싱 실패)
```

### 5.2 `BaseModule.run()` 템플릿 메서드 에러 가드 (Zero Exception Boilerplate)
- 개별 모듈의 `execute()`는 저수준 `try-except`로 에러를 감싸지 않고 **순수 도메인 로직(Happy path)**에 집중합니다.
- 상위 `BaseModule.run()` 템플릿 메서드가 실행 과정에서 발생하는 모든 저수준 예외(Pydantic ValidationError, OpenAI API Timeout, 출력 스키마 불일치 등)를 **도메인 예외로 자동 분류하고 `module_type`과 함께 래핑**합니다.

```python
# ✅ 권장: 모듈 execute() 내부는 순수 비즈니스 로직에 집중 (BaseModule이 자동 가드)
class MyLogicModule(BaseModule):
    input_model = MyInputDTO
    config_model = MyConfigDTO
    output_model = MyOutputDTO

    def execute(self, input_data: MyInputDTO, config: Optional[MyConfigDTO] = None) -> Dict[str, Any]:
        # 검증, 파싱 에러는 BaseModule.run()이 자동으로 ModuleValidationError / ModuleExecutionError로 포맷팅함
        result = do_business_logic(input_data.text)
        return {"result": result}
```

### 5.3 FastAPI 전역 Exception Handler 표준 응답
- 개별 API 엔드포인트에서 `try-except HTTPException`을 수동으로 작성하지 않습니다.
- `backend/main.py`의 전역 핸들러(`@app.exception_handler(PipelineBaseError)`)가 모든 파이프라인 에러를 표준화된 JSON 규격으로 클라이언트에 응답합니다:
  ```json
  {
    "detail": {
      "code": "PROVIDER_API_ERROR",
      "message": "외부 모델 호출에 실패했습니다.",
      "retryable": true,
      "context": { "module_type": "embedder" }
    }
  }
  ```
