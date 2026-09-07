# 서버 실측 평가 기록

[프로젝트 소개](../README.md) · [최종 프로젝트 요약](../docs/PROJECT_SUMMARY.md) · [전체 문서](../docs/README.md)

이 디렉터리는 **2026-09-01~02에 수행한 서버 실측·회귀 검증의 원본 기록**입니다. 문서에 적힌 `dev`, 커밋, 배포 이미지, 평가 문항 수와 결과는 실행 당시 조건이며 현재 `main`의 상태나 최신 실행 결과로 바꿔 읽지 않습니다.

## 읽는 순서

| 목적 | 문서 |
| --- | --- |
| 평가 환경·범위·결론 파악 | [서버 실측 평가 요약](10_summary.md) |
| 단위 테스트·타입·정적 검사 | [정적 검증 기록](02_static_tests/README.md) |
| 요청 구성과 평가 조건 | [벤치마크 요청 안내](04_benchmark_requests/README.md) |
| 평가셋·실험별 결과 구분 | [벤치마크 결과 안내](05_benchmark_results/README.md) |
| 2차 직접 질의 자동평가 | [corrected-direct-rag-query 보고](05_benchmark_results/corrected-direct-rag-query-report.md) |
| 부하와 장애 복구 확인 | [부하 테스트](07_loadtest/README.md) · [복구 테스트](08_resilience/README.md) |
| 보안 검증과 제외 범위 | [보안 검토](09_security/security-review.md) |
| 실측 화면 근거 | [스크린샷 안내](12_screenshots/README.md) |

## 최종 보고 수치와의 관계

최종 발표·보고서 정확도 **81.45%**와 이 폴더의 직접 질의 자동채점 **75.81% · 94/124**는 같은 자동채점 결과가 아닙니다. 최종 판정 기준과 원본 보존 원칙은 [완료 요약](../docs/PROJECT_SUMMARY.md#평가-결과를-읽는-방법)에 정리했습니다.

과거 결과는 비교·추적을 위해 유지합니다. 이후 재평가는 새 실행 기록으로 추가하고 실행 조건·분모·채점 방식을 명시합니다. 부분집합 재실행, 사후 보정, 개발 중 회귀 점검을 독립 평가셋의 전체 정확도로 소개하지 않습니다.
