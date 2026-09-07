# 장애복구 실측 결과

장애 주입은 로컬 영속 볼륨을 보존하고 자동 복구 가능한 범위에서 실행했다. 각 결과는 장애 시각, 복구 시각, 중복 여부를 원시 JSON 또는 상태 기록과 연결했다.

| 시험 | 결과 | 핵심 증빙 | 판정 |
| --- | --- | --- | --- |
| Benchmark worker 종료 | 실행 중 Pod 강제 종료 후 대체 Pod가 lease를 회수해 16/16 완료 | 종료 21:15:39 KST, 진행 재개까지 약 225초, 결과 PK 중복 0 | 통과 |
| Redis 중단 fallback | Redis replica 0 상태에서 PostgreSQL 폴링으로 두 SSE 구독자 모두 `run_finished` 수신 | 2/2 terminal, 중복 terminal 0, 14.51초 | 통과 |
| 다중 API Pod SSE | API 2 replica에서 4개 구독자가 동일 run 종료 수신 | 4/4 terminal, 중복 0, 약 14.0초 | 통과 |
| PostgreSQL 연결 실패 | 격리 namespace에서 잘못된 DB 연결의 API가 준비 상태가 되지 않고 즉시 실패 | RuntimeError, ready Pod 0 | 통과 |
| Migration 실패 | 격리 namespace migration Job을 exit 42로 실패시켜 배포 중단 확인 | Job failed, 기존 production image는 계속 ready | 통과 |
| API rolling restart | `maxUnavailable=0`, `maxSurge=1`, preStop drain 적용 후 공개 경로 연속 호출 | 120초, 952건, 실패 0, 오류율 0% | 통과 |
| Ingestion worker 종료 | 활성 ingestion이 없어 미실행 | 재임베딩 비용·데이터 변경을 피함 | 미시행 |
| 실제 PostgreSQL 중단·복구 | 영속 볼륨을 유지한 채 DB container stop/start | ready `200 → 503 → 200`, DB health `healthy`, 데이터 reset 없음 | 통과 |

## 결함 발견과 개선

최초 API 롤링 시험에서는 907건 중 timeout 2건(0.2205%)이 발생했다. Deployment를 `maxUnavailable: 0`, `maxSurge: 1`, `minReadySeconds: 5`, `terminationGracePeriodSeconds: 30`, `preStop sleep 5`로 보강하고 최신 이미지에 배포한 뒤 재시험해 952건 실패 0건을 확인했다.

Benchmark worker는 동시 runtime schema DDL이 PostgreSQL lock 경합을 만들 수 있어 worker bootstrap을 `initialize_schema=false`로 변경했다. 마이그레이션만 schema 소유권을 가지며, queue capacity는 8 CPU/15.56GiB Docker 자원에서 CPU 2·메모리 4GiB/slot과 reserve를 적용해 최대 3개로 제한했다.

## 제한

실제 PostgreSQL 중단→재연결은 로컬 영속 DB에서 통과했습니다. Ingestion shard 중단 시험은 활성 ingestion을 새로 만들어야 하며 임베딩 비용과 데이터 변경이 수반되므로 별도 승인 없이는 통과로 해석하지 않습니다.

원시 증빙: `api-rollout.json`, `sse-redis-fallback.json`, `postgres-recovery.json`, `../07_loadtest/sse-multi-api.json`, `../05_benchmark_results/benchmark-queue-scale.json`.
