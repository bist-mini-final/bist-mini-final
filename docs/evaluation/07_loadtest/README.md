# 성능·부하 실측 결과

클라이언트와 k3d cluster가 같은 Windows 호스트에 있어 WAN 지연은 제외된다. 모든 읽기 단계는 `/healthz`, `/api/v1/workflows`, `/api/v1/data-sources/indexes`를 순환했고 단계별 warm-up 10초, 측정 5분, timeout 5초를 사용했다.

## Health/read API: 5분 × 4단계

| 동시성 | 요청 | 200 | 429 | 5xx/timeout | RPS | p50 | p95 | p99 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 6,592 | 6,592 | 0 | 0 | 21.97 | 17.39ms | 42.65ms | 46.10ms |
| 10 | 85,582 | 37,529 | 48,053 | 0 | 285.23 | 6.41ms | 25.87ms | 41.12ms |
| 25 | 213,207 | 80,070 | 133,137 | 0 | 710.61 | 7.73ms | 21.28ms | 33.40ms |
| 50 | 398,559 | 141,855 | 256,704 | 0 | 1,328.31 | 10.28ms | 27.20ms | 34.25ms |

총 703,940건 중 200은 266,046건, 429는 437,894건(62.2062%)이며 5xx와 timeout은 0건이다. 동시성 10 이상에서 보이는 오류율은 서버 장애가 아니라 단일 IP가 Ingress 정책(`limit-rps=30`, burst multiplier 3, connection 50)을 초과해 제어 차단된 결과다. 보안 정책을 포함한 공개 ingress 용량 시험이므로 429도 분모에서 제외하지 않았다.

부하 중 표본에서 동시성 10은 node 3%/backend 111m CPU·129MiB, 동시성 25는 node 4%/backend 116m CPU·129MiB였다. CPU·메모리 포화가 아니라 admission control이 먼저 작동했다. 원시 결과는 `read-api-five-minute.json`이다.

비교용 15초 예비 시험은 rate limit 적용 전 총 4,677건/오류 0, 동시성 1/10/25/50 RPS 39.12/96.21/84.70/84.45, p95 53.8/338.0/1,018.8/1,784.5ms였다. 이는 병목 탐색 참고값이며 정식 5분 결과를 대체하지 않는다.

## 유료 RAG 동시성

비용을 제한하기 위해 각 동시성에서 유한 burst만 실행했다. cache off이며 총 비용은 **$0.052281**이다.

| 동시성 | 완료/실패 | wall | 처리량 | p50 | p95 | p99 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1/0 | 19.86s | 3.02/min | 19.72s | 19.72s | 19.72s |
| 3 | 3/0 | 17.74s | 10.15/min | 15.21s | 17.57s | 17.57s |
| 5 | 5/0 | 29.21s | 10.27/min | 20.37s | 28.99s | 28.99s |
| 10 | 10/0 | 62.94s | 9.53/min | 30.93s | 62.12s | 62.12s |

동시성 5부터 처리량이 약 10 run/min으로 평탄화되고, 동시성 10 p95가 62.12초로 증가한다. 원시 run ID·token·cost는 `rag-concurrency.json`에 있다.

## Queue·업로드·SSE

- Benchmark queue: 자원 산정 전 과대 병렬 설정을 수정해 Docker 8 CPU/15.56GiB 기준 최대 3 Job으로 제한했다. 세 기준선 Job 418 run 완료 및 worker 장애 회수를 확인했다.
- 대표 4개 workbook ingestion: 모두 completed, 4 sheets, 총 vector 45,120개. 세부 시간·token·비용은 `../03_ingestion_manifest.csv`에 있다.
- 500MiB 경계: 정확히 524,288,000 bytes는 크기 검사를 통과한 뒤 가짜 OpenXML이라 422, +1 byte는 413이다. 둘 다 ingestion Job을 만들지 않았다. 실제 500MiB 유효 Excel의 전체 embedding은 비용·시간 때문에 미실행이다.
- 다중 API SSE: API 2 replica, 구독자 4/4 terminal 수신, 중복 terminal 0, 약 14초.
- Redis fallback SSE: Redis 중단 중 구독자 2/2 terminal 수신, 중복 0, 14.51초.

원시 결과: `read-api-five-minute.json`, `read-api-smoke.json`, `rag-concurrency.json`, `upload-500mib-boundary.json`, `sse-multi-api.json`.
