# 제품 및 기능 명세

이 디렉터리는 구현과 검증에서 사용하는 제품 계약의 단일 진입점이다. ADR은 왜 그렇게 설계했는지를 기록하고, 이 명세는 무엇을 구현하고 언제 완료로 판단하는지를 정의한다.

| 문서 | 책임 |
| --- | --- |
| [클린 아키텍처 계약](ARCHITECTURE_CONTRACT.md) | 계층 의존 방향, 객체 수명, Job/Kubernetes 단일 소스와 KEDA 실행 계약 |
| [제품 요구사항](PRODUCT_REQUIREMENTS.md) | 제품 목표, 실행 경계, SLO, 비기능 요구사항 |
| [기능 요구사항](FUNCTIONAL_REQUIREMENTS.md) | 사용자 기능과 정상·실패 동작 |
| [Job/DAG 명세](JOB_WORKFLOW_SPEC.md) | 표준 Job의 노드, 엣지, 큐, 입력·출력 |
| [API 계약](API_CONTRACTS.md) | HTTP 상태, 비동기 실행, SSE와 오류 계약 |
| [검증 매트릭스](VERIFICATION_MATRIX.md) | 요구사항별 자동·통합·운영 검증 |

## 명세 규칙

- 모든 요구사항에는 변경되지 않는 식별자를 부여한다.
- `modules/`는 계산 단위의 단일 소스이고, `jobs/`는 모듈을 연결하는 선언형 DAG의 단일 소스이다.
- backend는 API·런타임·영속성·오케스트레이션만 담당하고 계산 로직을 복제하지 않는다.
- frontend는 서버 계약을 소비하며 모듈 종류나 표준 DAG를 자체 하드코딩하지 않는다.
- Kubernetes Job 외부에서 모듈의 `execute`를 호출하는 제품 경로는 허용하지 않는다.
- 완료 판정은 [검증 매트릭스](VERIFICATION_MATRIX.md)를 통과했을 때만 가능하다.
