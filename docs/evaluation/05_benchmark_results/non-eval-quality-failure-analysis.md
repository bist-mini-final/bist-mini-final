# 평가셋 품질 외 실패 원인 분석

## 결론

기존 105문항 직접 조회 회귀 결과를 저장된 노드 실행 로그까지 다시 추적했다.
최초 분류에서는 54 run이 검색·Reader 실패처럼 보였지만, 각 질문을 실제 workbook
FEATURE·시트·기간과 대조하자 54건 모두 아직 수정되지 않았던 평가 의미 불일치에
연결됐다. 해당 문항을 정제 대상으로 재분류한 뒤 남은 의미상 유효한 63문항,
2개 workflow의 126 run은 **126/126 정답, 실행 오류 0건**이었다.

이 수치는 과거 실행 중 의미가 명확한 subset을 재분류한 진단값이다. 수정 질문 중
직접 조회형 `rag_query` 124 run의 새 실행 결과를 대신하지 않으며, 최종 정확도로 주장하지
않는다.

## 최초 54건의 표면적 분류와 실제 원인

| 표면 분류 | run | 노드 로그에서 확인한 실제 원인 |
| --- | ---: | --- |
| Retrieval/Fusion miss | 17 | 질문이 gold FEATURE·시트·기간을 유일하게 지정하지 않아 다른 합리적 metric이 검색됨 |
| Reader evidence selection | 14 | 답변 본문은 생성했지만 평가가 기대한 FEATURE와 질문 의미가 달라 근거 선택이 불안정해짐 |
| Reader partial evidence | 23 | 비교·파생 질문의 피연산자, 기간 또는 source sheet가 질문에 완전히 명시되지 않음 |

대표적으로 `현금성 자산`은 `Total Cash & ST Investments`, `보통주자본`은
`Common Stock`, `감가상각비`는 현금흐름표의 `D&A Total`, `매입채무 변동`은
현금흐름표의 `Change in Accounts Payable`, `보통주 발행액`은 현금흐름표의
issuance proceeds를 gold로 사용하면서 질문에는 해당 FEATURE와 source sheet가
명시되지 않았다. 실제/추정 기간이 섞인 질문과 `Net Income`, CAPEX, stock-based
compensation, DPS의 workbook 변형을 구분하지 않은 질문도 같은 범주였다.

## 제품 로직에서 별도로 보강한 항목

평가셋 결함으로 분류됐더라도 실제 사용자 질의에서 재발할 수 있는 경계 조건은
평가 정답에 맞춘 하드코딩이 아니라 일반 계약으로 수정했다.

1. **검색 순위 보존**: Context Expander가 RRF 결과를 set·행 번호 순으로 다시
   정렬하지 않고 최초 융합 순위를 유지한다.
2. **명시적 metric 보존**: `총매출/Total Revenue`, `매출/Revenue`,
   `총부채/Total Liabilities`, `총차입금/Total Debt`를 서로 다른 workbook
   metric으로 유지한다.
3. **명시적 source sheet 보존**: 단일 atomic query에서 사용자가
   현금흐름표·손익계산서·재무상태표·Key Stats를 명시하면 Decomposer가 이를
   hard constraint로 적용한다. 여러 피연산자가 섞인 질의에는 문장 전체의 sheet를
   일괄 적용하지 않아 서로 다른 route를 훼손하지 않는다.
4. **Reader 근거 선택 복구**: Reader가 충분한 셀 후보로 본문을 생성했지만 유효한
   `evidence_id`를 하나도 선택하지 않은 경우에만, 원 질문과 전체 후보를 그대로
   유지한 구조화 선택을 한 번 재시도한다. 후보 압축, 서버측 근거 추측, 임의 좌표
   보충은 하지 않는다.
5. **완전성 계약**: 비교·추세·계산은 필요한 모든 원본값과 피연산 근거를 선택하고
   Actual/Forecast를 구분하도록 Reader 계약을 강화했다.

관련 쿼리 분해·Reader·문맥 확장 회귀시험은 44건 모두 통과했고 Ruff도 통과했다.

## 재평가 상태

- 전체 질문: 209
- 질문 문구 또는 기업 범위 수정: 93
- 포함: 204, 프로젝트 범위 제외: 5
- 직접 원본 셀 조회형: 124
- 파생 계산·판단형: 80
- 과거 실행의 정제 가능 subset: 63문항×2 workflow = 126/126 통과
- 새 정제 직접 조회 실행: 124문항×`rag_query` = 124 run, 124/124 완료,
  Answer 94/124(75.81%), 실행 오류 0

새 실행의 총 추정비용은 $0.287985다. 기계 판독 가능한 과거 재분류 결과는
`non-eval-quality-failure-analysis.json`, 새 실행 분석은
`corrected-direct-rag-query-analysis.json`에 보존했다.
