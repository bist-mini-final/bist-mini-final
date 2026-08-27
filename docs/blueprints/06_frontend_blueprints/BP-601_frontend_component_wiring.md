# [BP-601] React 18 프론트엔드 결선도 & 상태 아키텍처
> **Document Code:** `BP-601` | **Category:** Frontend Blueprint | **Status:** Approved Baseline  
> **Source Directories:** [`frontend/src/app/`](file:///c:/Repos/bist-mini-final/frontend/src/app/), [`frontend/src/pages/`](file:///c:/Repos/bist-mini-final/frontend/src/pages/), [`frontend/src/features/`](file:///c:/Repos/bist-mini-final/frontend/src/features/), [`frontend/src/shared/`](file:///c:/Repos/bist-mini-final/frontend/src/shared/)

---

## 1. 프론트엔드 컴포넌트 계층 트리 (Component Hierarchy Tree)

프론트엔드는 **React 18 + TypeScript + Vite + Tailwind CSS v4** 스택 기반의 고성능 SPA(Single Page Application) 구조로 구축되어 있습니다.

```mermaid
graph TD
    ROOT["main.tsx (Root Provider & StrictMode)"] --> APP["App.tsx"]
    APP --> SHELL["AppShell.tsx (Header, Global Nav, Theme Switcher)"]
    
    SHELL --> ROUTER["AppRouter (History-based SPA Router)"]
    
    ROUTER --> P_HOME["HomePage (/)]"]
    ROUTER --> P_PLAY["PlaygroundPage (/playground) -> PlaygroundView"]
    ROUTER --> P_DS["DataSourcesPage (/data-sources) -> DataSourcesView"]
    ROUTER --> P_BI["BiPage (/bi) -> BiPage / BiDashboard"]
    ROUTER --> P_CHAT["ChatbotPage (/chatbot) -> PlannedFeaturePage [Target: ChatbotView]"]
    ROUTER --> P_COMP["CompanyComparisonPage (/company-comparison) [Target: ComparisonView]"]
    ROUTER --> P_SET["SettingsPage (/settings) -> SettingsView"]
    ROUTER --> P_404["NotFoundPage (404 Fallback)"]

    P_PLAY --> XYFLOW["@xyflow/react (Custom Nodes, Minimap, Controls)"]
    P_DS --> GRID_VIEW["Spreadsheet Table & VLM Overlay Inspector"]
    P_BI --> RECHARTS["Recharts (Area, Bar, Line, ResponsiveContainer)"]
    P_BI --> HEATMAP["FinancialHealthHeatmap (종합 재무 건전성 히트맵)"]
    P_BI --> RESET_DLG["ResetDataDialog (데이터 초기화 & 배치 모니터링)"]
```

---

## 2. 라우팅 및 시스템 포털 배선표 (Route & System Portals Matrix)

### 2.1 React SPA 프론트엔드 라우트 (Client-Side SPA Routes)

| URL Path | 라우트 이름 | 렌더링 컴포넌트 | 워크스페이스 상태 |
| :--- | :--- | :--- | :--- |
| `/` | `Home` | [`HomePage`](file:///c:/Repos/bist-mini-final/frontend/src/pages/HomePage.tsx) | 메인 랜딩 & 워크스페이스 런처 허브 |
| `/playground` | `Pipeline Playground` | [`PlaygroundPage`](file:///c:/Repos/bist-mini-final/frontend/src/pages/PlaygroundPage.tsx) | **[운영중]** React Flow 2D DAG 빌더 & 실행 |
| `/data-sources` | `Data Sources` | [`DataSourcesPage`](file:///c:/Repos/bist-mini-final/frontend/src/pages/DataSourcesPage.tsx) | **[운영중]** 스프레드시트 뷰어 & pgvector 관리 |
| `/bi` | `Financial BI` | [`BiPage`](file:///c:/Repos/bist-mini-final/frontend/src/pages/BiPage.tsx) | **[운영중]** 재무제표 프로파일러 & 40+ 지표 차트 |
| `/chatbot` | `AI Financial Chatbot` | [`ChatbotPage`](file:///c:/Repos/bist-mini-final/frontend/src/pages/ChatbotPage.tsx) | **[설계완료 / 확장예정]** Fast RAG 대화형 질의응답 (WebSocket) |
| `/company-comparison`| `Company Comparison` | [`CompanyComparisonPage`](file:///c:/Repos/bist-mini-final/frontend/src/pages/CompanyComparisonPage.tsx)| **[설계완료 / 확장예정]** 다중 기업 크로스 분석 (Tier 1/2 분리) |
| `/settings` | `Settings` | [`SettingsPage`](file:///c:/Repos/bist-mini-final/frontend/src/pages/SettingsPage.tsx) | 환경 변수 및 DB/큐 튜닝 인디케이터 |

---

### 2.2 백엔드 호스팅 시스템 및 개발자 콘솔 (Backend-Hosted System & Dev Portals)

React SPA 내부 라우팅이 아닌, **FastAPI 백엔드가 1-depth 최상위 경로에서 직접 렌더링하는 시스템 관리 및 API 문서 포털 3종** (AppShell 헤더 및 설정 메뉴에서 링크로 연동):

| URL Path | 포털 명칭 | 제공 기술 / 엔진 | 역할 및 기능 |
| :--- | :--- | :--- | :--- |
| `/jobs` | **K8s Job & Worker Portal** | FastAPI Jinja2 HTML + WebSocket | 백엔드 내장 분산 워커 상태, Pod 라이프사이클 및 실시간 로그 터미널 관제 ([`BP-104 Section 4`](file:///c:/Repos/bist-mini-final/docs/01_system_blueprints/BP-104_distributed_job_and_worker_system.md#4-내장-k8s-배치-잡--워커-실시간-관제-대시보드-jobs)) |
| `/docs` | **Swagger UI Interactive API** | Swagger UI (OpenAPI 3.1) | 30+ REST API 엔드포인트 대화형 테스트 및 Pydantic 스키마 검증 |
| `/redoc` | **ReDoc API Documentation** | ReDoc Responsive Engine | 구조화된 REST API 공식 레퍼런스 문서 뷰어 |

---

## 3. 전역 상태, 뷰모델 및 접근성 계층 (State, ViewModels & Accessibility)

- **HTTP 통신 라이브러리**: [`ky`](file:///c:/Repos/bist-mini-final/frontend/package.json#L16)를 사용하여 기본 타임아웃, 인터셉터(X-Request-ID 주입), JSON 자동 파싱 처리.
- **실시간 스트리밍**: 브라우저 네이티브 `EventSource` API를 래핑한 커스텀 훅(`useWorkflowStream`)으로 SSE 연결 수명주기 관리.
- **런타임 스키마 검증**: 백엔드 API 응답을 `zod` 스키마로 런타임 검증하여 타입 불일치 사전 차단.
- **적응형 차트 뷰모델 (`chartViewModel.ts`)**: `getProfitabilityMarginDomain` 등 도메인 셀렉터를 통해 음수 마진/영업적자 발생 시 Recharts Y축 도메인을 자동 계산하여 스케일링.
- **접근성(a11y) 표준 모달 훅 (`useModalDialog`)**: 모든 대화상자(`ResetDataDialog`, `EvidenceDialog` 등)에 `role="dialog"`, `aria-modal="true"`, `Escape` 닫기 및 포커스 트랩 표준 적용.

---

## 4. 리팩토링 타깃 (Refactoring Targets)

1. **상태 관리 통합 (Zustand 도입)**:
   - As-Is: React `useState`, `useContext`, `useReducer`가 컴포넌트 트리에 분산되어 있음.
   - To-Be: `Zustand` 글로벌 스토어로 워크플로우 상태, BI 선택 기업, 챗봇 세션 상태를 중앙 집중화.
2. **React Router v6 / TanStack Router 표준 마이그레이션**:
   - As-Is: 커스텀 `router.tsx` 구현체.
   - To-Be: TanStack Router 또는 React Router v6 도입으로 중첩 라우트 및 로더(Loader) 패턴 표준화.
