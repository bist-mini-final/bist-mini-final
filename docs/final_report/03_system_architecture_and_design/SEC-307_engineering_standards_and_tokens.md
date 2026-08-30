# [SEC-307] 엔지니어링 표준과 프런트엔드 규칙

> **Chapter:** 3. 시스템 아키텍처 및 상세 설계 | **Section:** 3.7 | **Status:** Implementation-aligned

---

## 1. 백엔드 표준

1. `modules/`는 DAG 노드의 단일 source이며 등록 목록은 `ModuleRegistry`로 결정합니다.
2. 제품 유스케이스는 `backend/features/`에 두고 API·provider·storage 구현을 직접 소유하지 않도록 port와 composition을 사용합니다.
3. 요청·응답·snapshot payload는 Pydantic으로 검증합니다.
4. BI 파생식은 `Decimal`; Company Comparison은 검증된 BI 관측값만 사용합니다.
5. 장시간 작업은 durable queue, 짧은 조회·계산은 async API 경계에서 실행합니다.
6. 데이터 변경은 Alembic revision으로 관리하고 snapshot history와 audit history를 파괴하는 downgrade는 차단합니다.

## 2. 프런트엔드 표준

- route와 navigation은 `frontend/src/app/routes.ts` 한 곳에서 관리합니다.
- 서버 payload는 feature별 Zod schema를 통과한 뒤 camelCase view model로 변환합니다.
- 화면은 임의 기업 수·연도·평균을 하드코딩하지 않고 snapshot metadata를 사용합니다.
- 일반 액션은 `shared/ui`의 `Button` 또는 `IconButton`, 읽기 전용 상태는 `StatusBadge`를 사용합니다.
- 버튼 높이는 `sm=36px`, `md=40px`, `lg=44px` 토큰으로 제한하고 페이지 CSS에서는 일반 버튼의 시각 상태를 재정의하지 않습니다.
- 아이콘 전용 버튼은 `aria-label`을 필수로 제공하며, 텍스트 버튼은 의미를 보완할 때 Lucide icon을 함께 사용합니다.
- 표 정렬, segmented control, React Flow 노드 조작처럼 선택·공간 모델이 별도인 컨트롤만 feature 전용 버튼 스타일을 소유합니다.
- dialog는 focus 복원, Escape 닫기, `aria-modal`, keyboard navigation을 제공합니다.
- BI와 Company Comparison은 별도 feature directory와 API client를 유지합니다.

## 3. 품질 게이트

- Ruff와 Pyright
- Pytest 전체 suite와 AST architecture contracts
- TypeScript typecheck, Vitest, Vite production build
- Alembic linear head와 Helm/KEDA render 검사

현재 결과는 [`SEC-502`](file:///c:/Repos/bist-mini-final/docs/final_report/05_validation_and_conclusion/SEC-502_contract_testing_results.md)에 기록합니다.
