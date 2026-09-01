# 벤치마크 요청·골드셋 상태

## 실행 요청

| 데이터셋 | 사례 | Workflow | 실행 run | 조건 | 상태 |
| --- | ---: | ---: | ---: | --- | --- |
| 1차 포함 | 86 | 2 | 172 | `full`, cache off | 완료 |
| 2차-A IBM | 87 | 2 | 174 | `full`, cache off | 완료 |
| 2차-B Holdout | 36 | 2 | 72 | `full`, cache off | 완료 |
| 합계 | 209 | 2 | 418 | 동일 배포·모델·색인 | 완료 |

세 요청 파일은 실제 `BenchmarkRequest` Pydantic 계약을 통과했다. 평가 Workflow는 `bi_metric_extraction`, `rag_query`이며 동일 데이터·검색 설정에서 Reader prompt 차이를 비교한다.

## 골드셋 품질 감사

전달 패키지에 명시된 canonical `evaluation_dataset.json`, `evaluation_sets_combined.json`이 없어 Markdown 부록에서 요청을 재구성했다. 이 때문에 전달 문서에 적힌 canonical JSON SHA-256은 대조할 수 없다.

- 1차 86건: 직접 좌표 39, 파생·수동 42, 파싱 불가 5
- 2차-A 87건: 직접 좌표 65, 파생·수동 22
- 2차-B 36건: 직접 좌표 14, 파생·수동 14, 파싱 불가 8
- `expected_plan`: 0건. 전달 지침대로 사람 검수 없이 질문에서 자동 생성하지 않았다.
- 독립 실행 범위가 불완전한 다기업 문항: `F2B-U3-05`, `F2B-U3-06`, `F2B-U5-06`
- 암묵적 다기업 범위 경고: `F2B-U3-05`, `F2B-U4-06`, `F2B-U5-06`
- 1차의 catalog 밖 `BAC` 사례와 기업 생략 질문은 fail-closed가 올바른 동작이며, 점수를 높이기 위해 scope 안전성을 완화하지 않았다.

자동 숫자·근거 지표는 실행됐지만 파생·정성 골드의 최종 승인은 사람 검토가 필요하다. 상세 감사는 `gold-reference-audit.json`, `benchmark-data-quality.json`, 각 `*.review.json`에 보존했다.

## FEATURE 기준 전수검사와 수정 평가셋

단순 reference 파싱 여부만으로는 질문과 정답 FEATURE의 의미가 같은지 확인할
수 없으므로, 209문항을 실제 workbook의 행 label·FEATURE code까지 대조했다.

| 항목 | 건수 |
| --- | ---: |
| 전체 질문 | 209 |
| 질문 문구 또는 기업 범위 수정 | 93 |
| 정제 평가 포함 | 204 |
| 현재 프로젝트 범위상 제외 | 5 |
| 포함된 원본 셀 직접 조회형 | 124 |
| 포함된 파생 계산·판단형 | 80 |

주요 결함은 `매출` 계열과 `Total Revenue` 계열 의미 불일치 25건,
`총부채`와 `Total Debt` 불일치 1건, 기업 범위 생략 31건,
추가 FEATURE·시트·기간 의미 명시 43건, 암묵적 기업 그룹 3건,
catalog 밖 기업 3건이다. 적용 규칙은
`총매출/총매출액 = Total Revenue`, `매출/매출액 = Revenue`,
`총부채 = Total Liabilities`, `총차입금 = Total Debt`다.

- 전체 수정본: `benchmark-questions-corrected.json`
- 문항별 원문·FEATURE·참조·제외 사유: `benchmark-question-quality-audit.json`
- 최종 RAG 직접 조회 재평가 요청: `benchmark-request-corrected-direct-124.json`
  (`rag_query` 단일 workflow, 124문항 = 124 run)
- 사람이 읽는 전체 209문항 목록:
  `../05_benchmark_results/evaluation-set-quality-review.md`

기존 `benchmark-request-valid-direct-105.json`은 최초 진단 재현용으로 보존하지만,
의미 전수검사 전 파일이므로 최종 성능 측정에는 사용하지 않는다.

124건은 수정한 질문의 전체 건수가 아니다. 전체 209건 중 93건의 표현·범위를
수정했고 204건을 평가 범위에 포함했다. 그중 현재 숫자·셀 근거 scorer로 자동
채점 가능한 직접 조회형이 124건이며, 나머지 80건은 별도 formula/qualitative
scorer가 필요한 계산·비교·판단형이다. BI는 이 RAG 질문을 중복 실행하지 않고
21개 metric catalog·exact-evidence·snapshot 회귀시험으로 별도 검증한다.

- 직접 조회형 124건: 수정된 문항 61건 + 원문 유지 문항 63건
- 파생·판단형 80건: 수정된 문항 32건 + 원문 유지 문항 48건
- 수정 문항 합계: 61 + 32 = 93건

## 사후 개선 검증

기준선 결과를 확인한 뒤 Decomposer catalog 보정·빈 계획 재시도, Reader 완전성 지시, 다기업 route 채점을 개선했다. Holdout 오염을 피하기 위해 이 결과는 **사후 개선(post-hoc)** 으로 명시하고, 원래 2차-B Holdout 결과를 대체하지 않는다.

- 재실행: 실패·수동검토 중심 80건 × 2 Workflow = 160 run
- 실행 방식: 8건씩 10개 shard, cache off
- 요청: `benchmark-request-posthoc-remediation.json`
- 결과: `../05_benchmark_results/benchmark-posthoc-remediation-sharded.json`
