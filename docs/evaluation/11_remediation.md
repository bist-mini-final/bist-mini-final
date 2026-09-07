# 실측평가 개선·재검증 결과

| 발견 항목 | 개선 내용 | 재검증 결과 |
| --- | --- | --- |
| Decomposer catalog 불일치·빈 계획 | catalog exact company 보정·필터, 1회 구조화 재시도, 다기업 scope prompt 강화 | 사후 80건에서 오류율 44.38%→11.25%, Evidence Hit@k 38.41%→67.39% |
| Reader 근거 누락·불완전 답변 | 요구 지표·기간별 완전성 지시와 근거 ID 선택 계약 보강; 본문은 있으나 유효 ID가 없을 때 원 질문·전체 후보 그대로 1회 구조화 재시도 | 후보 압축·서버측 근거 추측 없이 회귀시험 통과; 정제 124 run에서 실행 오류 0, Reader 근거 미선택 1건·부분 선택 7건 확인 |
| 평가셋 의미 불일치 | 209문항을 workbook FEATURE·source sheet·기간과 대조하고 정확한 metric으로 정제 | 93문항 수정, 204문항 포함·5문항 제외, 전체 수정 질문 보고서화 |
| 명시적 metric·sheet 손실 | 총부채/총차입금, 매출/총매출을 분리하고 단일 atomic query의 명시적 source sheet를 hard constraint로 보존 | 쿼리 분해 회귀시험 통과 |
| 문맥 확장 rank 손실 | RRF 후보를 set/행 번호로 재정렬하지 않고 최초 검색 순서를 보존 | 상위 `Total Revenue`가 하위 `Revenue` 뒤로 밀리는 사례 회귀시험 통과 |
| 다기업 route 채점 | 단일 target 비교 대신 복수 target 정규화 평가 | route 67.42%→68.31%; 불완전 gold scope는 별도 경고 |
| Benchmark worker DB lock | worker runtime schema DDL 제거, migration만 schema 소유 | shard 병렬 실행 완료, worker 장애 후 16/16 회수 |
| Docker 자원 초과 queue | 자원 기반 최대 3 Job, embedding 3/vector 2로 제한 | KEDA 6 ScaledJob ready, Pending 없이 실행 |
| API 롤링 timeout | surge 1/unavailable 0, preStop drain, grace/minReady 적용 | 개선 전 907건 중 2 timeout → 개선 후 952건 실패 0 |
| API 명세 노출 | 운영 docs/OpenAPI 비활성화, frontend·Ingress proxy와 사이드바 링크 제거 | 로컬·외부 `/docs`, `/redoc`, `/openapi.json` 404 |
| 보안 헤더·rate limit | API/Nginx 헤더와 Ingress 30 RPS/connection 제한 | 헤더 확인, burst 240건 중 190건 429 제어 |
| 위장·과대 업로드 | 확장자+OpenXML signature, streaming 500MiB 상한 | 가짜 파일 422, 500MiB+1 413 |
| index catalog 조회 | 신규 index metadata count 사용, legacy만 상관 집계 | 장기 부하에서 5xx/timeout 없음; ingress 제한 초과는 429 |
| readiness blocking | async DB probe와 timeout/failure threshold 조정 | Pod restart 0, rolling 연속성 통과 |
| 인증·권한 경계 | HMAC 서명 세션, PBKDF2 credential, viewer/operator/admin RBAC, 단일 tenant boundary 구현 | 익명 401, 로그인·조회 200, tenant 위반 403, logout 후 401 |
| prompt injection·경로 조작 | 검색 셀을 untrusted data로 분리, 지시문 무시 계약과 좌표 traversal 거부 | Reader·입력 계약 회귀 시험 통과 |
| PostgreSQL 실제 복구 | 영속 볼륨을 보존한 container stop/start | readiness `200→503→200`, DB healthy, data reset 없음 |
| 이미지 provenance | Git SHA+dirty content fingerprint 태그, OCI revision/dirty label | 최신 태그 `38a18ed2c1bb-dirty-5a5d1f46011f` 배포 확인 |
| IBM 회계등식 감사 | minority interest 포함 `Total Equity`로 검사 정정 | 4기간 차이 모두 0 |

## 학생 프로젝트 범위 밖의 후속 항목

- 공인 TLS·외부 443 forwarding은 상용 공개 운영으로 확장할 때 적용한다.
- 209건 전체 수동 gold와 조직 검토 서명 대신, 학생 프로젝트에서는 소규모 미사용 문항을 사람이 확인한다.
- 실제 PostgreSQL 중단/복구는 통과했다. 유료 ingestion worker 장애 주입은 평가 범위에서 제외한다.
- clean signed tag·SBOM·외부 registry digest는 상용 공급망 관리 범위에서 수행한다.
