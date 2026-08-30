# [SEC-404] 코드베이스 리팩토링과 아키텍처 거버넌스
> **Chapter:** 4. 시스템 구현 및 MVP 진화 | **Section:** 4.4 | **Status:** Implemented & Ongoing

---

## 1. 완료된 구조 개선

1. `api`, `bootstrap`, `features`, `engine`, `modules`, `providers`, `storage` 책임을 분리했습니다.
2. `ApplicationContainer`를 `RuntimeContainer`, `ExecutionContainer`, `DomainServicesContainer`로 분해했습니다.
3. 모듈 생성 recipe와 실행 인스턴스를 `ModuleRegistry`의 lazy singleton 계약으로 통합했습니다.
4. durable queue 제출·재개·취소를 `WorkflowExecutionService` 경계로 이동했습니다.
5. async DAG/provider/DB 경로를 만들고 남은 동기 I/O는 worker thread 또는 one-shot worker로 격리했습니다.
6. API의 정식 `/api/v1` 경로와 typed dependency/composition root를 정리했습니다.
7. 기존 Company Comparison/V2 중복 frontend와 legacy backend 계산기를 제거하고 단일 도메인으로 통합했습니다.
8. 불변 payload와 current head 수명주기를 `VersionedSnapshotRepository` port로 추상화했습니다.
9. module count, API, DB schema, 화면 route를 코드 기준으로 문서화했습니다.

검증되지 않은 코드량 절감률이나 성능 향상률은 리팩토링 성과로 사용하지 않습니다.

---

## 2. 실행 가능한 거버넌스

| 규칙 | 검증 |
| :--- | :--- |
| feature → API 역방향 import 금지 | AST architecture test |
| module 내부 provider/DB 직접 생성 금지 | AST architecture test |
| Kubernetes worker spec과 renderer 동기화 | manifest contract test |
| Alembic head와 migration chain | Alembic contract test |
| Company Comparison source/evidence/forecast/rank 무결성 | backend snapshot tests |
| frontend route·Zod·ranking·페이지 상태 | Vitest |
| Python lint/type | Ruff, Pyright |
| TypeScript/type/build | `tsc`, Vite production build |

---

## 3. 변경 시 체크리스트

- 새 제품 기능은 기존 도메인의 namespace를 재사용하기 전에 제품 책임과 담당 API를 확인합니다.
- schema 변경은 migration, runtime initializer, model, repository, tests, ERD를 함께 바꿉니다.
- module 추가/삭제는 registry, module endpoint, BP-302, contract test를 함께 바꿉니다.
- frontend route 변경은 router, navigation, home launcher, route tests, BP-601을 함께 바꿉니다.
- 과거 설계를 유지해야 할 때는 “현재 계약”처럼 쓰지 않고 구현 이력에 명시합니다.
- synthetic fallback이나 조용한 heuristic으로 source-data 결함을 숨기지 않습니다.
