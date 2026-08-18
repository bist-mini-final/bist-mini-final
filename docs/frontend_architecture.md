# Frontend architecture

프론트엔드는 서비스 전체 화면과 개별 기능을 분리합니다. 홈과 메뉴는 공통 App Shell을 사용하고, 기존 파이프라인 캔버스는 `playground`라는 하나의 독립 기능으로 취급합니다.

## Routes

| URL | 소유 영역 | 상태 |
|---|---|---|
| `/` | 서비스 홈 | 구현됨 |
| `/playground` | 모듈 기반 RAG 실험 공간 | 구현됨 |
| `/data-sources` | 데이터·인덱스 자산 관리 | 팀 구현 영역 |
| `/evaluations` | 실험 품질·비용 비교 | 팀 구현 영역 |
| `/bi` | BI 기능 작업 공간 | 팀 구현 영역 |

라우트와 사이드바 메뉴의 기준은 `frontend/src/app/routes.ts` 한 파일입니다. `AppShell`이나 `HomePage`에 별도의 라우팅 분기를 추가하지 않습니다.

## Directory boundaries

```text
frontend/src/
├── app/                       # 라우팅과 서비스 공통 셸
├── features/
│   ├── bi/                    # BI 기능 작업 영역
│   │   └── BiPage.tsx
│   └── playground/            # 기존 캔버스 기능 전체
│       ├── components/
│       ├── config/
│       ├── contexts/
│       ├── hooks/
│       ├── services/
│       ├── utils/
│       ├── PlaygroundPage.tsx
│       └── playground.css
├── pages/                     # URL 단위 서비스 페이지
├── shared/                    # 둘 이상의 페이지가 사용하는 UI
├── styles/                    # 전역 토큰과 App Shell 스타일
├── App.tsx
└── main.tsx
```

의존 방향은 `App → app/pages → features/shared`입니다. `playground` 내부 코드는 다른 서비스 페이지에서 직접 가져오지 않습니다. 두 기능에서 실제로 재사용되는 코드가 생긴 경우에만 `shared`로 승격합니다.

Playground는 지연 로딩되므로 홈 초기 번들에 React Flow와 캔버스 구현이 포함되지 않습니다. 기능 스타일도 `features/playground/playground.css`에서 별도로 로드됩니다.

## Adding a team page

1. 독립 기능은 `frontend/src/features/<feature>/<Feature>Page.tsx`를 생성합니다.
2. `frontend/src/app/routes.ts`에 경로, 메뉴명, 설명, 아이콘, 컴포넌트를 등록합니다.
3. 구현이 시작되면 route의 `status`를 `planned`에서 `ready`로 바꿉니다.
4. 페이지 전용 상태와 컴포넌트는 해당 `frontend/src/features/<feature>/` 안에서 관리하고 Page는 조립만 담당합니다.
5. 공통 App Shell을 수정하지 않고 페이지 경계 안에서 개발합니다.

현재 빈 페이지는 `PlannedFeaturePage`를 사용합니다. 팀원이 기능을 구현할 때 해당 페이지 파일의 내용을 실제 feature entry point로 교체하면 됩니다.

## Navigation and server fallback

내부 링크는 `AppLink`와 브라우저 History API를 사용합니다. FastAPI는 `/playground` 같은 프론트 URL로 직접 접근하거나 새로고침해도 `dist/index.html`을 반환합니다. `/api`, `/docs`, `/redoc`, `/openapi.json`, `/assets`는 기존 백엔드 라우트가 우선합니다.

## Verification

```bash
cd frontend
npm run build

cd ..
python3 -m unittest discover -s tests
```

브라우저에서는 데스크톱과 모바일에서 다음을 확인합니다.

- 홈에서 Playground 진입
- 사이드바의 active 메뉴와 모바일 drawer
- `/playground` 직접 새로고침
- planned 페이지 진입 후 공통 셸 유지
