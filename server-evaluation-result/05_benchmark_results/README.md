# 벤치마크 실행 결과

## 기준선 418 run

세 데이터셋을 `full`, cache off 조건으로 모두 완료했다. 실패·timeout도 분모에 포함했다.

| 평가 대상 | 사례/run | Answer | Route | Plan | Sheet exact | Evidence Hit@k | Evidence Recall@k | Citation coverage | 오류율 |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1차 포함 | 86 / 172 | 29.07% | 55.04% | N/A | 56.59% | 46.91% | 42.92% | 21.66% | 25.00% |
| 2차-A IBM | 87 / 174 | 57.47% | 75.00% | N/A | 75.00% | 70.69% | 67.82% | 62.93% | 14.94% |
| 2차-B Holdout | 36 / 72 | 43.06% | 69.70% | N/A | 69.70% | 69.64% | 59.44% | 43.15% | 8.33% |
| 2차 전체 | 123 / 246 | 53.25% | 73.36% | N/A | 73.36% | 70.43% | 65.78% | 58.11% | 13.01% |

Plan은 `expected_plan` 골드가 0건이므로 정확도를 산출하지 않았다. 자동 정량 임계값이 합의되지 않아 품질 판정은 `측정 완료·판정 대기`다.

## Workflow별 운영 효율

| Workflow | run | Answer | Route | Sheet | Evidence Hit@k | 오류율 | 평균 지연 | p95 | p99 | 평균 token | 총 비용 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `bi_metric_extraction` | 209 | 44.02% | 66.10% | 66.67% | 62.24% | 15.31% | 12.20s | 36.78s | 51.98s | 25,212 | $0.454973 |
| `rag_query` | 209 | 42.58% | 66.87% | 67.47% | 59.18% | 20.57% | 11.01s | 31.14s | 46.93s | 19,874 | $0.371520 |
| 합계 | 418 | 43.30% | 66.48% | 67.07% | 60.71% | 17.94% | - | - | - | - | **$0.826493** |

## 사후 개선 160 run

기준선에서 실패·수동검토 중심 80건을 동일 두 Workflow로 재실행했다. 이 결과는 Holdout이 아니며 원래 Holdout 수치를 대체하지 않는다.

| 구분 | Answer | Route | Sheet | Evidence Hit@k | Evidence Recall@k | Citation coverage | 오류율 | 평균 지연 | p95 | 총 비용 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 동일 80건 기준선 | 25.00% | 67.42% | 67.42% | 38.41% | 33.90% | 24.39% | 44.38% | 8.16s | 26.66s | $0.220975 |
| 사후 개선 | 40.00% | 68.31% | 72.54% | 67.39% | 61.74% | 43.44% | 11.25% | 12.49s | 28.97s | $0.316738 |

사후 개선에서 Answer는 +15.0%p, Evidence Hit@k는 +28.99%p, 오류율은 -33.13%p 개선됐다. 반면 평균 지연과 token은 증가했으므로 품질·비용 절충을 최종 임계값과 함께 검토해야 한다.

## 정제 직접 조회 최종 평가 124 run

질문·기업·FEATURE를 전수 감사한 뒤 직접 원본 셀 조회형 124문항을 `rag_query`
단일 workflow로 실행했다. 두 workflow 중복 실행이 아니므로 124문항은 정확히
124 run이다.

| Answer | Route | Sheet exact | strict Evidence Hit@k | strict Recall@k | Citation | 오류율 | 평균 지연 | p95 | 총 비용 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **75.81% (94/124)** | 72.58% | 72.58% | 67.80% | 64.61% | 58.52% | **0%** | 8.358s | 13.806s | **$0.287985** |

실패 30건의 최초 실패 지점은 retrieval/fusion strict gold 셀 미도달 20건,
Reader 부분 근거 7건, Reader 근거 미선택 1건, 답변-채점 의미 차이 2건이다.
추가 수동 의미 검토에서 숫자 골드 중복, 동의어·회계 부호 규칙 때문에 실패한
5건을 확인했다. 공식 exact 점수는 75.81%로 보존하며, 상세 내역은
`corrected-direct-rag-query-report.md`에 있다.

## 실패 분석과 제한

- 주요 자동 실패 원인은 숫자 gold가 기대한 파생값까지 포함했는데 답변은 직접값만 제시한 경우, catalog 밖 기업 또는 기업 생략 질문, Reader 인용 누락, 기간·단위 표현 불일치였다.
- 209문항을 실제 workbook FEATURE와 전수 대조한 결과 93문항의 질문·기업 범위를 수정해야 했다. `매출` 계열 질문과 `Total Revenue` gold의 의미 불일치 25건, `총부채`와 `Total Debt` 불일치 1건 외에도 source sheet·정확한 FEATURE·기간을 명시하지 않은 의미 모호성 43건을 추가 확인했다. 수정본 전체 목록은 `evaluation-set-quality-review.md`에 있다.
- 동일 원시 run을 평가 가능 범위로 재분류하면 `기업 명시 + catalog 존재 + gold 파싱 가능` 322 run의 Answer는 52.17%, 그중 직접 원본 셀 조회형 210 run은 65.71%다. 원시 전체 43.30%는 그대로 보존한다.
- 기존 직접 조회 105문항 회귀실행은 145/210(69.05%), 실행 오류 0건이었지만, 의미 감사 전 평가셋이므로 최종 정확도가 아니라 실행 안정성 증거다. 정제된 직접 조회형은 `rag_query` 단일 workflow 124문항·124 run으로 실행을 완료했고 94/124(75.81%), 실행 오류 0건이었다. 124건은 전체 수정 문항 수가 아니라 포함 204건 중 자동 직접 셀 채점이 가능한 subset이다.
- 기존 실행 로그에서 수정 대상 93문항을 제외한 의미상 유효 subset은 63문항·126 run이며 126/126 정답, 실행 오류 0건이었다. 이는 과거 실행 재분류 진단값이며 새 정제 평가의 최종 성능은 아니다. 상세 내역은 `non-eval-quality-failure-analysis.md`에 있다.
- 실패 중심 post-hoc 중 동일한 유효 직접 조회형 56 run에서는 Answer가 39.29%에서 62.50%로 +23.21%p 개선됐다. 선택 subset이므로 최종 전체 품질값은 아니다.
- `representative-failures.json`에 대표 실패 5건 이상과 실제/기대 답변, 검색·인용 셀, 오류 태그를 보존했다.
- `06_case_review.csv`는 자동 분류 418건(`pass_automated` 141, `fail_automated` 251, `manual_required` 26)을 포함한다. 이는 사람 승인 기록이 아니다.
- 정성적 원인 분석, 과잉 주장, Actual/Forecast 및 파생 골드는 검토자가 승인해야 최종 품질 통과로 전환할 수 있다.
- 완료 Pod가 TTL로 정리된 뒤여서 원본 worker stdout은 회수하지 못했다. `benchmark-worker.log`에 이 증빙 공백을 명시하고 durable job status·timeline·결과 JSON으로 대체했다.

상세 원인, 대표 사례, 이미 적용한 개선과 재평가 원칙은 `rag-quality-root-cause.md`와 `non-eval-quality-failure-analysis.md`에 기록했다. 질문별 원문·수정문·FEATURE·참조·포함 여부를 포함한 전체 209문항은 `evaluation-set-quality-review.md`에 기록했다.

원시 결과는 `benchmark-1-included-86.json`, `benchmark-2a-87.json`, `benchmark-2b-36.json`, `benchmark-summary.json`, 사후 개선 JSON, `benchmark-corrected-direct-rag-query.json`에 보존했다.
