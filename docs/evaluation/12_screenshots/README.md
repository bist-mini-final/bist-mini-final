# 배포 UI 화면 증빙

2026-09-01 KST, 평가 중간 배포(`38a18ed2c1bb-dirty-9152d2eda169`)의 `http://127.0.0.1:8080`을 브라우저에서 직접 열어 캡처했다. 이후 평가셋 의미 보정·검색 순위 보존·Decomposer 명시적 metric/source sheet 보존·Reader 근거 선택 복구와 단일 workflow benchmark 계약까지 포함한 최신 배포 tag는 `38a18ed2c1bb-dirty-5a5d1f46011f`이다. 캡처는 중간 배포 화면 증빙이며 최신 인증 화면을 의미하지 않는다.

- `dashboard.png`: BI 대시보드 라우트와 빈 스냅샷 상태
- `data-sources.png`: 9개 pgvector index catalog 표시
- `jobs.png`: 작업 관제 라우트

화면 캡처는 읽기 전용 탐색으로 수행했고 데이터 생성·삭제·재실행 버튼은 누르지 않았다.
