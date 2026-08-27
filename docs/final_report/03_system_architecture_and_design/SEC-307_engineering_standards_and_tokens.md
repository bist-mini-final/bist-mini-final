# [SEC-307] 엔지니어링 표준 헌법 및 프론트엔드 디자인 토큰
> **Chapter:** 3. 시스템 아키텍처 및 상세 설계 | **Section:** 3.7 | **Status:** Approved Baseline  
> **Classification:** Engineering Standards, Code Conventions & Frontend Design System

---

## 1. 전사 엔지니어링 4대 헌법 (Core Engineering Standards)

1. **단일 소스 원칙 (Single Source of Truth)**: 모든 RAG 파이프라인 모듈은 `modules/` 디렉토리 아래에서만 단일 관리.
2. **DTO 100% 엄격 타입화 (Strict Pydantic Type-Safety)**: 마크다운 백틱 자르기나 불안정한 정규식 JSON 파싱을 금지하고 `BaseLLMModule.complete_structured` 1줄 파싱 강제.
3. **무손실 금융 수식 연산 (Lossless Decimal Math)**: 40+ 재무 비율 및 듀퐁 공식 연산 시 `decimal.Decimal` 고정소수점 강제.
4. **중복 예외 보일러플레이트 배제 (Zero Exception Boilerplate)**: `BaseModule.run()` 템플릿 메서드에서 모든 예외를 `ProviderApiError`, `ModuleValidationError`, `ModuleExecutionError`로 자동 분류 래핑.

---

## 2. 프론트엔드 무이모티콘 & 디자인 시스템 표준

* **원시 유니코드 이모티콘 전면 배제 (Zero Raw Emojis)**: UI 버튼, 뱃지, 탭에 이모티콘 하드코딩 금지.
* **`lucide-react` SVG 벡터 아이콘 일원화**: 모든 아이콘은 Lucide SVG 라이브러리에서 명시적 import.
* **Web a11y 표준 모달 훅 (`useModalDialog.ts`)**: `EvidenceDialog`, `ResetDataDialog` 등 모든 다이얼로그에 포커스 트랩, ESC 닫기, `aria-modal` 준수.