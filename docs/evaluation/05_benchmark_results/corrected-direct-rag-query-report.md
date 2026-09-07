# 정제 직접 조회 RAG 최종 실행 보고

## 실행 조건

- 실행 일시: 2026-09-02 KST
- 요청: `benchmark-request-corrected-direct-124.json`
- 대상: 정제 평가 204문항 중 원본 셀 직접 채점이 가능한 124문항
- Workflow: `rag_query` 단일 workflow
- 실행 수: 124문항 = 124 run (중복 workflow 실행 없음)
- cache: off, scope: full
- 샤드: 15건 단위 9개, Kubernetes 최대 동시 Job 3개
- 배포 이미지: `38a18ed2c1bb-dirty-5a5d1f46011f`

## 정량 결과

| 지표 | 결과 |
| --- | ---: |
| 완료 | 124/124 |
| 실행 오류 | 0 |
| Answer 정답 | 94/124 |
| Answer 정확도 | **75.81%** |
| Route 정확도 | 90/124, **72.58%** |
| Sheet exact | 90/124, **72.58%** |
| strict gold-cell Evidence Hit@k | 80/118, **67.80%** |
| strict gold-cell Evidence Recall@k | **64.61%** |
| strict gold-cell Citation coverage | **58.52%** |
| 평균 지연 | 8.358초 |
| p50 / p95 / p99 | 7.722 / 13.806 / 16.155초 |
| 총 token | 3,321,348 |
| 평균 token | 26,785 |
| 총 추정 비용 | **$0.287985** |
| 평균 추정 비용 | $0.002322/run |

Evidence 지표는 골드 감사 파일에 단일 정답 좌표로 기록된 셀과 정확히 일치하는지를
측정한다. 동일 값을 가진 다른 유효 셀을 인용한 경우에도 불일치로 집계될 수 있으므로
Answer 정확도와 함께 해석해야 한다.

## 자동 실패 분류

| 최초 실패 지점 | 건수 | case ID |
| --- | ---: | --- |
| retrieval/fusion에서 strict gold 셀 미도달 | 20 | `F1-Q004`, `F1-Q023`, `F1-Q025`, `F1-Q037`, `F1-Q055`, `F2A-O1-03`, `F2A-O1-06`, `F2A-O1-21`, `F2A-O2-38`, `F2A-O3-54`, `F2A-O5-78`, `F2A-O5-80`, `F2A-O6-87`, `F2B-U1-06`, `F2B-U3-05`, `F2B-U3-06`, `F2B-U5-02`, `F2B-U6-01`, `F2B-U6-05`, `F2B-U6-06` |
| Reader가 일부 골드만 선택 | 7 | `F1-Q030`, `F1-Q054`, `F1-Q067`, `F1-Q087`, `F2A-O3-43`, `F2A-O3-45`, `F2A-O3-50` |
| Reader가 골드 근거를 선택하지 않음 | 1 | `F1-Q010` |
| 검색·근거는 맞지만 답변/채점 불일치 | 2 | `F1-Q008`, `F1-Q101` |

실행 오류와 context expansion 단계의 신규 손실은 0건이었다. 자동 분류의
`retrieval/fusion miss`는 strict 좌표 기준이며, 답변이 다른 유효 셀이나 계산값으로
정답을 제시했는지는 별도 의미 검토가 필요하다.

## 확인된 채점 의미 차이

- `F1-Q008`: 질문은 지급 배당금의 **규모**를 물었고 답변은 `6,255`와 원본의 음수
  표기 이유를 정확히 설명했다. 골드는 `-6,255` 부호만 허용해 자동 오답이 됐다.
- `F1-Q101`: 8개 기대 숫자를 모두 답했지만 필수 단어 `추정` 1개가 본문에 없다는
  이유로 오답 처리됐다. 답변에는 같은 의미의 `전망`이 반복된다.
- `F2B-U1-06`: 질문이 요구한 지배기업 순이익 `-628`을 정확히 답했지만 골드가
  `-628`과 절댓값 `628`을 동시에 필수 숫자로 두고 `손실` 단어까지 강제했다.
- `F2B-U6-01`, `F2B-U6-06`: 기대 숫자는 모두 일치하지만 동의어를 허용하지 않는
  필수 단어 채점 때문에 오답이다.

따라서 자동 exact scorer의 공식 결과는 94/124(75.81%)로 유지한다. 위 5건을 사람이
의미상 정답으로 승인하면 참고 정확도는 99/124(79.84%)지만, 사람 승인 전에는 공식
수치로 대체하지 않는다.

## 남은 제품 개선 우선순위

1. 질문의 명시적 FEATURE와 source sheet를 Decomposer가 더 강하게 보존하도록 한다.
   특히 EPS/DPS, Net Income to Company, Finance Division Revenue, weighted diluted
   shares에서 `Key_Stats`로 과도하게 수렴하는 문제가 남았다.
2. 다중 지표 질문은 각 지표별 검색 성공 여부를 독립적으로 검사하고 누락된 지표만
   재검색한다. 현재 7건은 일부 값만 Reader까지 도달하거나 인용됐다.
3. strict 단일 좌표뿐 아니라 동일 FEATURE·기업·기간의 유효 대체 셀을 허용하는
   evidence scorer를 별도 둔다.
4. 부호가 현금 유출을 뜻하는 항목의 `규모` 질문과 `전망/추정`, `증가/성장세` 같은
   의미 동등어를 허용하도록 Answer scorer를 보강한다.

## 원시 증빙

- 결과: `benchmark-corrected-direct-rag-query.json`
- 실행 로그 기반 분석: `corrected-direct-rag-query-analysis.json`
- 샤드 제출: `corrected-direct-rag-query-shard-submissions.json`
- 샤드 상태: `corrected-direct-rag-query-shard-status.json`
- 전체 질문 감사: `evaluation-set-quality-review.md`
