# 자동시험·정적 검증 요약

최초 실측 로그는 같은 디렉터리에 보존했다. 수정 후 2026-09-01에 전체 게이트를 다시 실행한 결과는 다음과 같다.

| 검사 | 최초 실측 | 수정 후 | 현재 판정 |
| --- | --- | --- | --- |
| Backend pytest | 341 pass / 1 fail / 2 skip | 379 pass / 2 skip / 1 warning | 통과 |
| Ruff | pass | pass | 통과 |
| Pyright | 2 errors | 0 errors | 통과 |
| Frontend lint/typecheck/test/build | 181 tests, build pass | 181 tests, build pass | 통과 |

최신 배포 직후 전체 게이트를 다시 실행했다. Decomposer의 catalog 보정·빈 계획 재시도, Reader 완전성 prompt, 다기업 route 채점, worker schema 소유권, 자원 기반 queue capacity, 무중단 rollout 계약을 포함한 회귀 테스트가 모두 통과했다. 유일한 warning은 Starlette TestClient의 `httpx` 사용 deprecation이며 기능 실패는 아니다.

추가 배포 검증은 Helm lint 1 chart/0 failure, Helm template 성공, `local.sh` Bash syntax 성공이다.
