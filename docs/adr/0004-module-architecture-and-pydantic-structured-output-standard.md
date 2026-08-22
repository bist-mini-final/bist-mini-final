# ADR-004: Module Architecture Simplification & Pydantic Structured Output Standard

- **상태(Status)**: `Accepted`
- **날짜(Date)**: 2026-08-22
- **결정자(Deciders)**: RAG Engine Team
- **영향 범위(Scope)**: `modules/`, `backend/engine/runtime/`, `backend/semantic_matching/`

---

## 1. 배경 및 문제점 (Context & Problem Statement)

기존 파이프라인 아키텍처는 다음과 같은 기술적 부채와 잠재적 런타임 위험을 안고 있었습니다:

1. **중복 디렉토리 및 불필요한 래퍼 모듈**:
   - `modules/`와 동일한 역할을 하던 `backend/pipeline/` 디렉토리가 공존하여 변경 시 동기화 누락 및 유지보수 비용 발생.
   - `DecomposerModule` 주위에 실질적 기능 차이가 없는 `AdaptiveQueryDecomposer`, `TemplateQueryDecomposer`, `DirectQueryDecomposer` 등 중복 껍데기 모듈 다수 존재.
2. **불안정한 비정형 문자열 파싱 (String Splitting & Regex Hacks)**:
   - LLM이 반환하는 마크다운 백틱(````json ... ````)을 수동으로 split하거나, 비정형 텍스트에서 `{...}`을 정규식으로 추출하려 시도.
   - 복잡한 80여 줄의 문자열 정규화 함수(`normalize_structured_query`, `normalize_subqueries`, `augment_subqueries`)로 인해 런타임 오류 가능성 상존.
3. **하드코딩된 대규모 정적 사전**:
   - ~400줄에 달하는 `financial_thesaurus.py` 정적 매핑 테이블로 인해 모델의 유연한 자연어 이해가 제한되고 불필요한 코드 복잡도 가중.

---

## 2. 의사결정 (Decision)

### 2.1 단일 소스 원칙 및 디렉토리 단일화
- `backend/pipeline/` 디렉토리를 완전히 삭제하고, 모든 RAG 모듈을 **`modules/` 단일 디렉토리로 통합**.
- `DecomposerModule` 하나만 남기고 `Adaptive`, `Template`, `Direct`, `Thesaurus` 디컴포저 모듈을 영구 삭제.
- 정적 thesaurus 사전(`financial_thesaurus.py`)을 완전히 폐기하고 프롬프트와 LLM 추론에 위임.

### 2.2 Pydantic Structured Output 전면 도입
- 모든 LLM 호출 시 `complete_with_metadata(..., response_format={"type": "json_object"})`를 사용.
- 수동 백틱 자르기, regex 검색, 다중 try-except fallback을 전면 폐지하고 `PydanticModel.model_validate_json()`으로 단일 단계 역직렬화 수행.
- 벡터 검색 직렬화 로직은 Item Pydantic 모델의 `.to_serialized_query()` 메서드로 캡슐화.

### 2.3 4단계 표준 레이아웃 적용
모든 모듈은 아래 4단계 구조를 일관되게 적용:
1. `Imports`
2. `Prompts & Presets`
3. `DTOs & Item Models`
4. `Module Implementation`
5. `__all__`

---

## 3. 결과 및 효과 (Consequences)

### 긍정적 효과 (Positive)
- **코드량 대폭 감소**: 중복 디렉토리(`backend/pipeline/`, ~5,000줄) 및 레거시 파싱 코드 제거로 약 5,500줄 이상의 기술 부채 청산.
- **안전성 및 타입 보장 (Type Safety)**: Pydantic 모델이 런타임 입력/출력 유효성을 100% 보장하여 JSONDecodeError 및 파싱 실패 원천 차단.
- **유지보수성 향상**: 모든 모듈이 동일한 레이아웃과 직관적인 데이터 흐름을 공유하여 신규 모듈 개발 및 디버깅 용이.

### 위험 및 완화 (Risks & Mitigations)
- **OpenAI API JSON Object 의존**: OpenAI 호환 API의 `response_format`을 활용하므로, 로컬 LLM 연동 시에도 `vLLM`, `Ollama` 등의 OpenAI 호환 JSON 모드 endpoint 사용을 권장.
