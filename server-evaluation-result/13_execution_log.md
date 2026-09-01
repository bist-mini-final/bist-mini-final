# 재현 명령 기록

실제 Secret 값은 기록하지 않았다. Windows PowerShell 기준이며 endpoint와 식별자는 산출물 JSON에 연결된다.

## 배포·상태

```powershell
& 'C:\Program Files\Git\bin\bash.exe' deploy/kubernetes/local.sh all
kubectl get deployment,pod,job,scaledjob -n bist-batch
kubectl rollout status deployment/backend-api -n bist-batch --timeout=180s
```

## 자동시험

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pyright.exe
npm --prefix frontend run check
helm lint .\deploy\helm\bist
helm template bist .\deploy\helm\bist --namespace bist-batch --values .\deploy\helm\bist\values.yaml
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/kubernetes/local.sh
```

## 벤치마크

```text
POST /api/v1/benchmarks/jobs
GET  /api/v1/benchmarks/jobs/{job_id}
GET  /api/v1/benchmarks/{benchmark_id}
```

요청 본문은 `04_benchmark_requests/benchmark-request-*.json`, job·run ID와 응답은 `05_benchmark_results/`에 있다. 기준선은 full/cache off 418 run, 사후 개선은 10 shard·160 run이다.

원인 분석 후 209문항을 workbook FEATURE·시트·기간까지 전수검사해 93문항을 수정하고,
현재 프로젝트 범위에 포함되는 직접 원본 셀 조회형 124문항을
`04_benchmark_requests/benchmark-request-corrected-direct-124.json`으로
동결했다. 수정본 전체 질문은
`04_benchmark_requests/benchmark-questions-corrected.json`과
`05_benchmark_results/evaluation-set-quality-review.md`에 있다. 최종 RAG 평가는
`rag_query` 단일 workflow 124 run이며 재실행기는
`tmp/evaluation-benchmark/run_valid_direct_sharded.mjs`다. 사용자 승인 후 아래
설정으로 9개 샤드를 제출해 124/124 완료했다.

```powershell
$env:EVAL_REQUEST_FILE = 'benchmark-request-corrected-direct-124.json'
$env:EVAL_OUTPUT_FILE = 'benchmark-corrected-direct-rag-query.json'
$env:EVAL_ARTIFACT_PREFIX = 'corrected-direct-rag-query'
$env:EVAL_RESULT_KIND = 'corrected-direct-rag-query-sharded'
$env:EVAL_SHARD_SIZE = '15'
node tmp/evaluation-benchmark/run_valid_direct_sharded.mjs
node tmp/evaluation-benchmark/analyze_corrected_direct_results.mjs
```

Job ID는 `05_benchmark_results/corrected-direct-rag-query-shard-submissions.json`,
상태는 `corrected-direct-rag-query-shard-status.json`에 보존했다.

## 부하·복구·보안

```powershell
node tmp/evaluation-loadtest/read_api_loadtest.mjs http://127.0.0.1:8080 server-evaluation-result/07_loadtest/read-api-five-minute.json 300000
node tmp/evaluation-loadtest/api_rollout_monitor.mjs http://127.0.0.1:8080 server-evaluation-result/08_resilience/api-rollout.json
node tmp/evaluation-security/security_probe.mjs
kubectl scale deployment/backend-api -n bist-batch --replicas=2
kubectl rollout restart deployment/backend-api -n bist-batch
kubectl scale deployment/backend-api -n bist-batch --replicas=1
```

인증 실측은 Kubernetes bootstrap Secret 값을 PowerShell 메모리 안에서만 복호화해 login에 사용했으며, 결과 파일에는 상태 코드와 쿠키 속성만 기록했다. PostgreSQL 복구는 영속 볼륨을 보존한 `docker stop bist-pgvector` / `docker start bist-pgvector`로 측정했다.

RAG 동시성, SSE, upload boundary, benchmark queue/worker 장애의 상세 입력·run ID·timestamp는 해당 원시 JSON에 보존했다. 평가 종료 후 `bist-eval-staging` namespace와 임시 port-forward를 제거했다.
