# 협업·컨벤션·품질 관리

[프로젝트 소개](../../README.md) · [문서 목차](../README.md) · [실행 가이드](SETUP.md)

이 문서는 프로젝트에서 사용한 협업 자동화와 코드 규칙을 저장소 설정에 근거해 정리합니다. GitHub의 브랜치 보호·필수 승인 설정은 이 파일만으로 활성화되지 않습니다.

## 브랜치와 변경 흐름

프로젝트 완료 소스는 `main`을 기준으로 보며, 개발 과정에서 `dev`를 통합 브랜치로 사용했습니다. CI는 두 브랜치 대상 push와 PR에서 실행됩니다.

```text
변경 범위 정의 → 작업 브랜치 → 구현·문서·테스트 → PR
              → CI와 자동 리뷰 확인 → 작성자 수정·사람 검토 → 통합
```

후속 변경은 한 PR에 하나의 목적을 담고, API·DB·모듈 계약이 바뀌면 관련 문서와 테스트를 함께 갱신합니다. 브랜치 덮어쓰기와 강제 push는 일반 협업 절차로 사용하지 않습니다.

## PR 제목과 설명

PR 제목 자동화는 `type(scope): Summary` 형식을 사용합니다. 지원 type은 `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `perf`, `ci`, `style`이며 scope는 선택입니다. 요약은 짧은 영어 명령형으로 작성하고 끝에 마침표를 붙이지 않습니다.

```text
feat(chatbot): Add cell evidence preview
fix(ingestion): Validate sheet boundaries
docs: Organize final project documentation
```

PR 설명에는 다음을 포함합니다.

- 변경 이유와 영향 범위
- 달라진 동작 또는 화면과 확인 방법
- 실행한 테스트, 생략한 테스트와 이유
- API·DB·배포 설정 변경 여부와 필요한 적용 순서

이 설명 항목은 협업 가이드이며 PR 템플릿이나 강제 검사로 구현되었다는 의미는 아닙니다.

## 자동 검사와 리뷰

| 자동화 | 현재 저장소의 동작 | 주의할 점 |
| --- | --- | --- |
| 백엔드 CI | Python 3.12·uv 0.12.5, 잠금 의존성 설치, PostgreSQL 마이그레이션, pytest, Ruff, Pyright | CI PostgreSQL·Redis 서비스 사용. 외부 모델 기능의 실측 품질을 자동 보장하지 않음 |
| 배포 계약 검사 | `jobs` 선언과 Kubernetes 렌더 결과의 ScaledJob 수·종류 비교 | 실제 클러스터 설치·부하·장애 실험과는 별개 |
| 프론트엔드 CI | Node.js 20, `npm ci`, TypeScript 검사, Vitest, production build | ESLint는 현재 CI의 별도 단계가 아니라 로컬 `npm run check`에 포함 |
| CodeRabbit | 한국어 리뷰, `chill` 프로필, 자동 리뷰와 대화 응답 | 자동 리뷰는 사람의 승인·검토를 대체하지 않음 |
| PR 제목 정리 | `dev`·`main` 대상 비초안 PR의 제목을 모델로 정리 | API 키가 없거나 호출이 실패하면 건너뜀. 품질 통과 판정 기능이 아님 |

구성 근거: [CI workflow](../../.github/workflows/ci.yml), [CodeRabbit 설정](../../.coderabbit.yaml), [PR 제목 workflow](../../.github/workflows/auto_format_pr_title.yml), [제목 정리 스크립트](../../.github/scripts/format_pr_title.py).

## 코드 컨벤션

### 백엔드와 파이프라인

- `presentation → application → domain` 방향을 유지하며 외부 저장소와 모델 연동은 infrastructure adapter로 분리합니다.
- 구체 구현의 생성·결합은 `backend/bootstrap`, 프로세스 시작은 `backend/entrypoints`가 담당합니다.
- 모듈 입력·설정·출력은 Pydantic 계약으로 명시하며 새 기능은 공통 모듈 실행 규격을 재사용합니다.
- DB 변경은 새 Alembic revision으로 남기고 공개 API·SSE·셀 근거 계약의 변경 영향을 검증합니다.
- Ruff·Pyright와 구조 계약 테스트를 기준으로 스타일, 타입, 의존 경계를 검사합니다.

근거: [Python 설정](../../pyproject.toml), [백엔드 책임 경계](../blueprints/01_system_blueprints/BP-102_backend_layered_architecture.md), [구조 계약 테스트](../../tests/modules/test_architecture_contracts.py), [마이그레이션 안내](MIGRATIONS.md).

### 프론트엔드

- 제품 기능은 `frontend/src/features`, 공용 UI·토큰은 `frontend/src/shared`에 두어 페이지 간 중복을 줄입니다.
- 라우트와 메뉴는 공통 route registry를 기준으로 연결합니다.
- TypeScript 타입 검사, ESLint, Vitest와 production build를 함께 확인합니다.

근거: [프론트엔드 스크립트](../../frontend/package.json), [route registry](../../frontend/src/app/routes.ts), [UI 설계](../blueprints/06_frontend_blueprints/BP-601_frontend_component_wiring.md).

## 로컬 검증

모든 명령은 저장소 루트에서 실행합니다. 전체 백엔드 테스트에는 PostgreSQL이 필요합니다. `DATABASE_URL`은 **별도 테스트 DB**를 지정하고, 통합 검증 시 `INTEGRATION_DATABASE_URL`과 `REDIS_URL`도 CI와 같은 용도로 설정합니다. 운영 DB에 테스트나 마이그레이션을 실행하지 않습니다.

```bash
uv sync --frozen
npm --prefix frontend ci

# 테스트 DB 주소를 설정·확인한 뒤 최초 준비 또는 schema 변경 시 실행
uv run alembic upgrade head

# 백엔드
uv run pytest -q
uv run ruff check modules backend jobs tests
uv run pyright

# 프론트엔드: lint → typecheck → test → build
npm --prefix frontend run check
```

문서·OpenAPI 계약만 확인할 때도 테스트 모듈이 애플리케이션을 구성하므로 DB 준비가 필요합니다.

```bash
uv run pytest -q tests/modules/test_blueprint_consistency.py
```

## 문서와 검증 기록 관리

- 현재 구현 사실은 [기준선](../CURRENT_IMPLEMENTATION_BASELINE.md), 유지할 설계 계약은 [청사진](../blueprints/README.md), 설치 명령은 [실행 가이드](SETUP.md)에 기록합니다.
- 평가 결과에는 데이터셋, 실행 시점, 코드·이미지와 채점 조건을 남깁니다. 과거 원본 수치를 최종 발표 수치로 덮어쓰지 않습니다.
- `.env`, API 키, 인증 Secret, 실제 사용자 데이터와 내부 접속 정보는 PR·로그·시연 자료에 노출하지 않습니다.
- 개인 임시 파일과 발표 초안은 코드 변경에 섞어 일괄 커밋하지 않습니다.
