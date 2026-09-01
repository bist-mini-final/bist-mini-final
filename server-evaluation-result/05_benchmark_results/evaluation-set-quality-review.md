# 평가셋 의미·근거 품질 전수검사 및 수정본

생성일: 2026-09-01T16:57:51.344Z

## 결론

원본 209건을 질문 문구, 원본 Excel FEATURE, 참조 셀, 기업 범위, 채점 방식 기준으로 다시 검사했다. 93건은 질문 또는 대상 범위를 수정했고, 204건은 정제 평가에 포함하며 5건은 현재 프로젝트 범위에서 제외한다.

가장 중요한 의미 규칙은 `총매출/총매출액 = Total Revenue`, `매출/매출액 = Revenue`이다. 원본 평가셋처럼 `매출` 질문을 `Total Revenue` 셀로 채점하면 정상적인 검색 결과를 오답으로 만들 수 있으므로 애플리케이션 코드를 그 평가셋에 맞춰 왜곡해서는 안 된다.

## 품질 집계

| 항목 | 건수 |
| --- | ---: |
| 전체 | 209 |
| 질문/범위 수정 | 93 |
| 정제 평가 포함 | 204 |
| 프로젝트 범위상 제외 | 5 |
| 원본 셀 직접 채점(포함 대상) | 124 |
| 파생식 전용 채점 필요(포함 대상) | 80 |
| 파생식 분류 전체(제외 대상 포함) | 85 |

### 발견 유형

| 유형 | 건수 |
| --- | ---: |
| catalog_target_unavailable | 3 |
| debt_feature_mismatch | 1 |
| derived_gold_requires_formula_scorer | 78 |
| gold_target_scope_incomplete | 3 |
| implicit_company_group | 3 |
| implicit_company_scope | 31 |
| manual_semantic_rewrite | 43 |
| reference_not_machine_parseable | 5 |
| revenue_feature_mismatch | 25 |
| sheet_not_ingested_by_project | 5 |

## 적용 원칙

1. 원본 FEATURE가 `Total Revenue`이면 질문에 `총매출`을 명시한다. 단순 `매출`은 `Revenue`로 유지한다.
2. `Total Liabilities`는 총부채, `Total Debt`는 총차입금으로 구분한다.
3. 질문 하나만 떼어 실행해도 대상을 알 수 있도록 IBM 또는 비교 기업 목록을 명시한다.
4. 원본 셀 값과 파생 계산 결과를 한 가지 숫자 포함 scorer로 섞지 않는다.
5. 현재 적재하지 않는 RAT/CAP/DO/SUM 시트와 미적재 기업은 학생 프로젝트 합격 기준에서 제외한다.
6. 정제 과정이 개입된 2차-B는 더 이상 독립 holdout으로 부르지 않고 회귀 평가셋으로 관리한다.

## 변경된 질문

| ID | 원문 | 수정 질문 | 수정 사유 |
| --- | --- | --- | --- |
| F1-Q004 | 2024-12-31 기준 희석 EPS와 DPS는 얼마인가? | IBM 기준, 2024-12-31 기준 희석 EPS와 DPS는 얼마인가? | implicit_company_scope |
| F1-Q005 | 2025년 기준 현금 및 단기투자자산 총액은? | IBM 기준, 2025년 기준 현금 및 단기투자자산 총액은? | implicit_company_scope |
| F1-Q006 | 2025년 기준 총자산과 총부채는 얼마인가? | IBM 기준, 2025년 기준 총자산과 총부채는 얼마인가? | implicit_company_scope |
| F1-Q007 | 2025년 영업활동 현금흐름과 자본지출은? | IBM 기준, 2025년 영업활동 현금흐름과 자본지출은? | implicit_company_scope |
| F1-Q008 | 2025년 집행된 총 배당금 규모는? | IBM 기준, 2025년 집행된 총 배당금 규모는? | implicit_company_scope |
| F1-Q009 | IBM의 최근 회계연도(FY0) 매출액은 얼마인가? | IBM의 최근 회계연도(FY0) 총매출액은 얼마인가? | revenue_feature_mismatch |
| F1-Q021 | IBM의 LTM 매출은 얼마인가? | IBM의 LTM 총매출은 얼마인가? | revenue_feature_mismatch |
| F1-Q023 | IBM의 LTM 순이익은 얼마인가? | IBM의 LTM 지배기업 순이익(Net Income to Company)은 얼마인가? | manual_semantic_rewrite |
| F1-Q027 | IBM의 LTM CAPEX는 얼마인가? | IBM의 LTM 현금흐름표상 자본지출(Capital Expenditure)은 얼마인가? | manual_semantic_rewrite |
| F1-Q028 | 2021년부터 2025년까지 IBM의 매출액 CAGR 및 연도별 YoY는? | 2021년부터 2025년까지 IBM의 총매출액 CAGR 및 연도별 YoY는? | revenue_feature_mismatch, derived_gold_requires_formula_scorer |
| F1-Q029 | 최근 4년간 Gross Margin, EBITDA Margin, EBIT Margin의 변화 추이는? | IBM 기준, 최근 4년간 Gross Margin, EBITDA Margin, EBIT Margin의 변화 추이는? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q030 | 최근 5년간 장기부채와 단기부채의 변동 경향은? | IBM 기준, 최근 5년간 장기부채와 단기부채의 변동 경향은? | implicit_company_scope |
| F1-Q033 | 2024년 대비 2025년 매출과 영업이익은 얼마나 증가했나? | IBM 기준, 2024년 대비 2025년 총매출과 영업이익은 얼마나 증가했나? | revenue_feature_mismatch, implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q034 | 2024년과 2025년 Total Assets 및 Total Liabilities를 비교해줘. | IBM 기준, 2024년과 2025년 Total Assets 및 Total Liabilities를 비교해줘. | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q035 | 2024년 대비 2025년 영업현금흐름과 CapEx는 어떻게 변했나? | IBM 기준, 2024년 대비 2025년 영업현금흐름과 CapEx는 어떻게 변했나? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q036 | 2024년 대비 2025년 Diluted EPS와 DPS를 비교해줘. | IBM 기준, 2024년 대비 2025년 Diluted EPS와 DPS를 비교해줘. | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q037 | IBM의 FY0 매출과 LTM 매출을 알려줘. | IBM의 FY0 총매출과 LTM 총매출을 알려줘. | revenue_feature_mismatch |
| F1-Q038 | IBM의 최근 3년 매출 추세를 알려줘. | IBM의 최근 3년 총매출 추세를 알려줘. | revenue_feature_mismatch |
| F1-Q044 | IBM의 최근 매출은 얼마야? | IBM의 최근 총매출은 얼마야? | revenue_feature_mismatch |
| F1-Q045 | IBM의 매출 성장률과 EBITDA 마진 추이를 같이 보여줘. | IBM의 총매출 성장률과 EBITDA 마진 추이를 같이 보여줘. | revenue_feature_mismatch, derived_gold_requires_formula_scorer |
| F1-Q046 | IBM의 자본구조와 밸류에이션 멀티플을 함께 정리해줘. | IBM의 최신 총현금·단기투자자산, 총차입금, 보통주 자본, TEV/EBITDA 및 P/E를 정리해줘. | manual_semantic_rewrite |
| F1-Q053 | IBM의 LTM 매출, EBITDA, 순이익을 알려줘. | IBM의 LTM 총매출, EBITDA, 순이익을 알려줘. | revenue_feature_mismatch |
| F1-Q055 | IBM의 현금성 자산과 장기부채를 알려줘. | IBM의 LTM 총현금·단기투자자산(Total Cash & ST Investments)과 장기부채(Long-Term Debt)를 알려줘. | manual_semantic_rewrite |
| F1-Q058 | IBM의 매출과 영업현금흐름을 알려줘. | IBM의 총매출과 영업현금흐름을 알려줘. | revenue_feature_mismatch |
| F1-Q064 | IBM의 매출과 TEV를 비교해줘. | IBM의 총매출과 TEV를 비교해줘. | revenue_feature_mismatch, derived_gold_requires_formula_scorer |
| F1-Q066 | 2025년 Cash Conversion Ratio는? | IBM 기준, 2025년 Cash Conversion Ratio는? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q067 | Key Stats의 TEV가 총부채 및 현금 수치와 정합성을 이루는가? | IBM 기준, Key Stats의 TEV가 총부채 및 현금 수치와 정합성을 이루는가? | implicit_company_scope |
| F1-Q069 | FCF 대비 배당 및 자사주 매입 집행 비중은? | IBM 기준, FCF 대비 배당 및 자사주 매입 집행 비중은? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q070 | DSO 및 DIO의 추이는? | IBM 기준, DSO 및 DIO의 추이는? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q072 | 2025년 매출총이익률과 영업이익률은? | IBM 기준, 2025년 매출총이익률과 영업이익률은? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q073 | 2025년 단순 잉여현금흐름은? | IBM 기준, 2025년 단순 잉여현금흐름은? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q074 | 2025년 총자산 대비 총부채 비율은? | IBM 기준, 2025년 총자산 대비 총부채 비율은? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q076 | FY-1 대비 FY0 매출 성장률은? | IBM 기준, FY-1 대비 FY0 총매출 성장률은? | revenue_feature_mismatch, implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q077 | 최근 순이익 성장률은? | IBM 기준, 최근 순이익 성장률은? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q082 | 영업현금흐름과 CAPEX로 FCF를 계산해줘. | IBM 기준, 영업현금흐름과 CAPEX로 FCF를 계산해줘. | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q083 | 종가와 발행주식수로 시가총액을 계산해줘. | IBM 기준, 종가와 발행주식수로 시가총액을 계산해줘. | implicit_company_scope |
| F1-Q084 | IBM의 TEV는 LTM 매출의 몇 배야? | IBM의 TEV는 LTM 총매출의 몇 배야? | revenue_feature_mismatch, derived_gold_requires_formula_scorer |
| F1-Q085 | IBM의 최근 3년 평균 매출은 얼마야? | IBM의 최근 3년 평균 총매출은 얼마야? | revenue_feature_mismatch, derived_gold_requires_formula_scorer |
| F1-Q086 | 장기부채가 현금성 자산보다 얼마나 큰가? | IBM 기준, 장기부채가 현금성 자산보다 얼마나 큰가? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q087 | 2022년 순이익이 급감했음에도 영업현금흐름이 유지된 원인은? | IBM 기준, 2022년 순이익이 급감했음에도 영업현금흐름이 유지된 원인은? | implicit_company_scope |
| F1-Q088 | 총부채가 크게 변동한 배경은 차입금 발행인가, M&A/투자 지출 때문인가? | IBM의 총차입금(Total Debt)이 크게 변동한 배경은 차입금 발행인가, M&A/투자 지출 때문인가? | debt_feature_mismatch, manual_semantic_rewrite |
| F1-Q090 | CapEx와 PP&E 증가 및 이후 매출 성장 간에 시차가 존재하는가? | IBM 기준, CapEx와 PP&E 증가 및 이후 총매출 성장 간에 시차가 존재하는가? | revenue_feature_mismatch, implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q101 | 2025년 Actual과 2026\~2028년 매출 및 EPS 성장 전망은? | IBM 기준, 2025년 Actual과 2026\~2028년 총매출 및 EPS 성장 전망은? | revenue_feature_mismatch, implicit_company_scope |
| F1-Q102 | FY2025 대비 NTM/FY2026\~2028 TEV/EBITDA 멀티플 변화 전망은? | IBM 기준, FY2025 대비 NTM/FY2026\~2028 TEV/EBITDA 멀티플 변화 전망은? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q103 | 최근 매출 성장 추세가 유지되면 2026년 Total Revenue는? | IBM 기준, 최근 총매출 성장 추세가 유지되면 2026년 Total Revenue는? | revenue_feature_mismatch, implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q104 | 현재 영업이익률이 유지될 때 2026년 Operating Income은? | IBM 기준, 현재 영업이익률이 유지될 때 2026년 Operating Income은? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q105 | 영업현금흐름이 5% 증가하고 CapEx가 동일하면 2026년 FCF는? | IBM 기준, 영업현금흐름이 5% 증가하고 CapEx가 동일하면 2026년 FCF는? | implicit_company_scope, derived_gold_requires_formula_scorer |
| F1-Q106 | 현재 TEV/Revenue 배수를 유지할 경우 2026년 예상 TEV는? | IBM 기준, 현재 TEV/Total Revenue 배수를 유지할 경우 2026년 예상 TEV는? | implicit_company_scope, revenue_feature_mismatch, derived_gold_requires_formula_scorer |
| F2A-O1-02 | 2024년 기준 IBM의 매입채무 변동을 알려줄래? | IBM의 2024년 현금흐름표상 매입채무 변동(Change in Acc. Payable)은 얼마인가? | manual_semantic_rewrite |
| F2A-O1-06 | IBM은 2025년에 기본주당순이익을 얼마로 기록했어? | IBM의 2025년 특이항목 포함 기본주당순이익(Basic EPS)은 얼마인가? | manual_semantic_rewrite |
| F2A-O1-10 | 2025년 기준 IBM의 가중평균 기본주식수를 알려줄래? | IBM의 2025년 손익계산서상 실제 가중평균 기본주식수는 얼마인가? | manual_semantic_rewrite |
| F2A-O1-17 | IBM의 2025년 보통주자본은 얼마인가? | IBM의 2025년 보통주 계정(Common Stock)은 얼마인가? | manual_semantic_rewrite |
| F2A-O1-21 | 2025년 IBM 금융부문 매출 수치는 얼마야? | IBM의 2025년 금융부문 매출(Finance Div. Revenue)은 얼마인가? | manual_semantic_rewrite |
| F2A-O2-27 | IBM의 감가상각비는 2024년에서 2025년 사이에 어떻게 변했어? | IBM의 현금흐름표상 총 감가상각·상각비는 2024년에서 2025년 사이에 어떻게 변했는가? | manual_semantic_rewrite |
| F2A-O2-31 | 2024년과 2025년 IBM 총주식보상비용을 비교해줘? | IBM의 손익계산서상 총주식보상비용은 2024년과 2025년에 각각 얼마인가? | manual_semantic_rewrite |
| F2A-O2-32 | IBM의 주당배당금은 2024년에서 2025년 사이에 어떻게 변했어? | IBM의 주당배당금(Dividends per Share)은 2024년에서 2025년 사이에 어떻게 변했는가? | manual_semantic_rewrite |
| F2A-O2-34 | 2023년과 2024년 IBM 보통주 발행액을 비교해줘? | IBM의 현금흐름표상 보통주 발행대금은 2023년과 2024년에 각각 얼마인가? | manual_semantic_rewrite |
| F2A-O3-41 | IBM 총부채는 매출채권 변동과 비교하면 얼마야? | IBM의 2025년 총부채(Total Liabilities)와 2024년 현금흐름표상 매출채권 변동을 같이 알려줘. | manual_semantic_rewrite |
| F2A-O3-42 | IBM 총유동자산은 사업 매각대금과 비교하면 얼마야? | IBM의 2025년 총유동자산과 사업 매각대금(Divestitures)을 같이 알려줘. | manual_semantic_rewrite |
| F2A-O3-43 | IBM의 특이항목 제외 세전이익과 총자본화를 같이 알려줘? | IBM의 2025년 특이항목 제외 세전이익과 총자본화(Total Capitalization)를 같이 알려줘. | manual_semantic_rewrite |
| F2A-O3-44 | IBM의 법적 합의 비용과 순유형자산을 같이 알려줘? | IBM의 2016년 법적 합의 비용과 2025년 순유형자산(Net Property, Plant & Equipment)을 같이 알려줘. | manual_semantic_rewrite |
| F2A-O3-45 | IBM 매입채무는 유형자산 취득원가와 비교하면 얼마야? | IBM의 2025년 매입채무와 2024년 유형자산 취득원가(Gross Property, Plant & Equipment)를 비교해줘. | manual_semantic_rewrite |
| F2A-O3-46 | IBM 기타무형자산은 주식보상비용과 비교하면 얼마야? | IBM의 2025년 기타무형자산과 현금흐름표상 주식보상비용을 같이 알려줘. | manual_semantic_rewrite |
| F2A-O3-47 | IBM의 법인세비용과 이자·투자수익을 같이 알려줘? | IBM의 2025년 법인세비용과 2024년 이자·투자수익을 같이 알려줘. | manual_semantic_rewrite |
| F2A-O3-49 | IBM 총직원 수는 순운전자본과 비교하면 얼마야? | IBM의 2024년 총직원 수와 2025년 순운전자본을 같이 알려줘. | manual_semantic_rewrite |
| F2A-O3-50 | IBM의 투자자산 처분손익과 이자비용을 같이 알려줘? | IBM의 2024년 투자자산 처분손익과 2025년 이자비용을 같이 알려줘. | manual_semantic_rewrite |
| F2A-O3-51 | IBM 장기차입금은 순차입부채와 비교하면 얼마야? | IBM의 2025년 장기차입금과 순차입부채(Net Debt)를 비교해줘. | manual_semantic_rewrite |
| F2A-O3-52 | IBM 재고자산은 자사주 매입액과 비교하면 얼마야? | IBM의 2025년 재고자산과 2024년 자사주 매입액을 비교해줘. | manual_semantic_rewrite |
| F2A-O3-54 | IBM의 배당성향과 희석주당순이익을 같이 알려줘? | IBM의 2025년 배당성향(Payout Ratio)과 특이항목 포함 희석주당순이익을 같이 알려줘. | manual_semantic_rewrite |
| F2A-O5-77 | IBM의 연금·퇴직급여부채와 비유동 선수수익 중 어느 쪽이 더 커? | IBM의 2025년 연금·퇴직급여부채와 비유동 선수수익 중 어느 쪽이 더 큰가? | manual_semantic_rewrite |
| F2A-O5-78 | IBM의 기타 매출과 유형자산 취득원가 중 어느 쪽이 더 커? | IBM의 2025년 기타 매출과 2024년 유형자산 취득원가 중 어느 쪽이 더 큰가? | manual_semantic_rewrite |
| F2A-O5-81 | IBM의 특이항목 제외 세전이익과 기타비유동부채 중 어느 쪽이 더 커? | IBM의 2025년 특이항목 제외 세전이익과 기타비유동부채 중 어느 쪽이 더 큰가? | manual_semantic_rewrite |
| F2B-U1-01 | 기업 A가 최근 결산에서 올린 전체 매출은 얼마 정도야? | 기업 A의 2025 회계연도(FY0) 총매출(Total Revenue)은 얼마인가? | revenue_feature_mismatch, manual_semantic_rewrite |
| F2B-U1-02 | 기업 A는 2025년에 영업으로 현금을 얼마나 벌어들였어? | 기업 A의 2025년 영업활동현금흐름(Cash from Ops.)은 얼마인가? | manual_semantic_rewrite |
| F2B-U1-03 | Coldplay가 최근 기준으로 안고 있는 차입금은 전부 얼마야? | Coldplay의 2025 회계연도(FY0) 총차입금(Total Debt)은 얼마인가? | manual_semantic_rewrite |
| F2B-U1-04 | Coldplay는 2025년에 본업으로 얼마의 이익을 남겼어? | Coldplay의 2025년 영업이익(Operating Income)은 얼마인가? | manual_semantic_rewrite |
| F2B-U1-05 | DH Innovation이 1년 안에 현금화할 수 있는 자산을 다 합치면 얼마야? | DH Innovation의 2025년 총유동자산(Total Current Assets)은 얼마인가? | manual_semantic_rewrite |
| F2B-U1-06 | DH Innovation은 2025년에 최종적으로 이익을 냈어, 손실을 냈어? | DH Innovation의 2025년 지배기업 순이익(Net Income to Company)은 얼마인가? | manual_semantic_rewrite |
| F2B-U2-01 | 기업 A는 최근 3년 동안 매출이 꾸준히 성장한 회사야? | 기업 A는 최근 3년 동안 총매출이 꾸준히 성장한 회사야? | revenue_feature_mismatch |
| F2B-U2-05 | DH Innovation은 차입금을 조금 줄였는데도 실제 빚 부담이 커지고 있어? | DH Innovation의 최근 3년 총차입금(Total Debt)은 줄었지만 순차입부채(Net Debt)는 증가했는가? | manual_semantic_rewrite |
| F2B-U2-06 | DH Innovation의 매출 하락은 최근에도 계속 이어지고 있어? | DH Innovation의 총매출 하락은 최근에도 계속 이어지고 있어? | revenue_feature_mismatch |
| F2B-U3-05 | 세 회사 중 매출이 가장 큰 회사가 EBITDA 수익성도 가장 좋아? | 기업 A, Coldplay, DH Innovation 세 회사 중 총매출이 가장 큰 회사가 EBITDA 수익성도 가장 좋아? | gold_target_scope_incomplete, revenue_feature_mismatch, implicit_company_group |
| F2B-U3-06 | 세 회사 중 가진 현금성 자산에 비해 차입금이 가장 부담스러운 곳은 어디야? | 기업 A, Coldplay, DH Innovation 세 회사 중 가진 현금성 자산에 비해 차입금이 가장 부담스러운 곳은 어디야? | gold_target_scope_incomplete, implicit_company_group |
| F2B-U4-01 | 기업 A는 매출 100달러당 EBITDA를 얼마나 남겨? | 기업 A는 총매출 100달러당 EBITDA를 얼마나 남겨? | revenue_feature_mismatch, derived_gold_requires_formula_scorer |
| F2B-U4-04 | Coldplay 매출은 2024년보다 2025년에 얼마나 늘었어? | Coldplay의 총매출(Total Revenue)은 2024년보다 2025년에 얼마나 증가했는가? | revenue_feature_mismatch, manual_semantic_rewrite |
| F2B-U4-06 | 현재 EBITDA로 순차입금을 갚는다고 보면 어느 회사가 가장 오래 걸릴까? | 기업 A, Coldplay, DH Innovation 중 현재 Net Debt/EBITDA가 가장 큰 회사는 어디인가? | gold_target_scope_incomplete, manual_semantic_rewrite |
| F2B-U5-02 | Coldplay의 영업현금 증가가 재고 감소 덕분이라고 단정해도 돼? | Coldplay의 최근 3년 영업현금흐름 증가가 재고 감소만으로 설명되는지 판단해줘. | manual_semantic_rewrite |
| F2B-U5-06 | 세 회사 중 재무적으로 가장 안정적인 회사와 가장 우려되는 회사는 어디야? | 기업 A, Coldplay, DH Innovation 세 회사 중 재무적으로 가장 안정적인 회사와 가장 우려되는 회사는 어디야? | implicit_company_group, derived_gold_requires_formula_scorer |
| F2B-U6-01 | 기업 A의 성장세가 내년에도 이어질까? | 기업 A의 2025년 총매출과 성장률 대비 2026년 추정 총매출 성장세가 이어지는가? | manual_semantic_rewrite |
| F2B-U6-02 | 내년에도 기업 A의 영업수익성이 더 좋아질 것으로 보고 있어? | 기업 A의 EBIT 마진은 2025년보다 2026년 추정치에서 개선되는가? | manual_semantic_rewrite, derived_gold_requires_formula_scorer |
| F2B-U6-03 | Coldplay 내년 매출은 올해보다 얼마나 더 나올 것으로 예상돼? | Coldplay 내년 총매출은 올해보다 얼마나 더 나올 것으로 예상돼? | revenue_feature_mismatch, derived_gold_requires_formula_scorer |
| F2B-U6-05 | DH Innovation은 내년에 영업적자에서 벗어날 수 있을까? | DH Innovation은 2026년 추정 EBIT 마진 기준으로 적자에서 벗어날 수 있는가? | manual_semantic_rewrite |
| F2B-U6-06 | DH Innovation은 전망 기간 안에 순이익 흑자로 돌아설 것으로 예상돼? | DH Innovation의 2025년 및 2026~2028년 추정 순이익률을 보면 전망 기간 안에 흑자 전환하는가? | manual_semantic_rewrite |

## 수정 평가셋 전체 질문 목록

| No. | 세트 | ID | 포함 여부 | 채점 | 수정 질문 | 정답 FEATURE | 참조 |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1차 포함 | F1-Q001 | include | derived_formula | IBM의 LTM 기준 시가총액과 TEV는 각각 얼마인가? | = Market Capitalization; = Total Enterprise Value (TEV) | KS Cell E60, E69 |
| 2 | 1차 포함 | F1-Q002 | include | direct_cell | IBM의 기준일 종가와 발행주식수는? | Day Close Price; x Shares Outstanding | KS Cell E57, E58, E64 |
| 3 | 1차 포함 | F1-Q003 | include | direct_cell | 2025년 LTM 기준 IBM의 총매출액, 매출총이익, 영업이익은? | Total Revenue [IQ_TOTAL_REV]; Gross Profit [IQ_GP]; Operating Income [IQ_OPER_INC] | IS Cell Q23, Q29, Q43 |
| 4 | 1차 포함 | F1-Q004 | include | direct_cell | IBM 기준, 2024-12-31 기준 희석 EPS와 DPS는 얼마인가? | Diluted EPS [IQ_DILUT_EPS_AFTER_EXTRA]; Dividends per Share [IQ_COMMON_DIV_DECLARED] | IS Cell O86, O93 |
| 5 | 1차 포함 | F1-Q005 | include | direct_cell | IBM 기준, 2025년 기준 현금 및 단기투자자산 총액은? | Total Cash & ST Investments [IQ_CASH_ST_INVEST] | BS Cell P19 |
| 6 | 1차 포함 | F1-Q006 | include | direct_cell | IBM 기준, 2025년 기준 총자산과 총부채는 얼마인가? | Total Assets [IQ_TOTAL_ASSETS]; Total Liabilities [IQ_TOTAL_LIAB] | BS Cell P50, P74 |
| 7 | 1차 포함 | F1-Q007 | include | direct_cell | IBM 기준, 2025년 영업활동 현금흐름과 자본지출은? | Cash from Ops. [IQ_CASH_OPER]; Capital Expenditure [IQ_CAPEX] | CF Cell P42, P44 |
| 8 | 1차 포함 | F1-Q008 | include | direct_cell | IBM 기준, 2025년 집행된 총 배당금 규모는? | Total Dividends Paid [IQ_TOTAL_DIV_PAID_CF] | CF Cell P70 |
| 9 | 1차 포함 | F1-Q009 | include | direct_cell | IBM의 최근 회계연도(FY0) 총매출액은 얼마인가? | Total Revenue [IQ_TOTAL_REV] | KS Cell I33 |
| 10 | 1차 포함 | F1-Q010 | include | direct_cell | IBM의 LTM 기준 EBITDA 마진은 몇 %인가? | EBITDA Margin % [IQ_EBITDA] | KS Cell J40 |
| 11 | 1차 포함 | F1-Q011 | exclude_unsupported_sheet | derived_formula | IBM의 부채비율(Debt/Equity)은 얼마인가? | 수동 근거 | RAT Cell J52 |
| 12 | 1차 포함 | F1-Q012 | exclude_unsupported_sheet | derived_formula | IBM의 최근 분기 시가총액은? | 수동 근거 | CAP Cell J16, J11 |
| 13 | 1차 포함 | F1-Q013 | exclude_unavailable_target | derived_formula | Bank of America의 최대주주(1위 Holder)는 누구인가? | 수동 근거 | DO Cell B6:F6 |
| 14 | 1차 포함 | F1-Q014 | exclude_unavailable_target | derived_formula | BAC의 기관투자자 지분율은? | 수동 근거 | SUM Cell C48 |
| 15 | 1차 포함 | F1-Q015 | exclude_unavailable_target | derived_formula | BAC의 CEO는 누구인가? | 수동 근거 | SUM Cell B23:C23 |
| 16 | 1차 포함 | F1-Q019 | include | direct_cell | IBM의 LTM 시가총액은 얼마인가? | = Market Capitalization | KS Cell E60 |
| 17 | 1차 포함 | F1-Q020 | include | direct_cell | IBM의 LTM TEV는 얼마인가? | = Total Enterprise Value (TEV) | KS Cell E69 |
| 18 | 1차 포함 | F1-Q021 | include | direct_cell | IBM의 LTM 총매출은 얼마인가? | Total Revenue [IQ_TOTAL_REV] | IS Cell Q23 |
| 19 | 1차 포함 | F1-Q022 | include | direct_cell | IBM의 LTM EBITDA는 얼마인가? | EBITDA [IQ_EBITDA] | IS Cell Q101 |
| 20 | 1차 포함 | F1-Q023 | include | direct_cell | IBM의 LTM 지배기업 순이익(Net Income to Company)은 얼마인가? | Net Income to Company [IQ_NET_INC] | IS Cell Q71 |
| 21 | 1차 포함 | F1-Q024 | include | direct_cell | IBM의 LTM 총자산은 얼마인가? | Total Assets [IQ_TOTAL_ASSETS] | BS Cell Q50 |
| 22 | 1차 포함 | F1-Q025 | include | direct_cell | IBM의 LTM 장기부채는 얼마인가? | Long-Term Debt [IQ_LT_DEBT] | BS Cell Q66 |
| 23 | 1차 포함 | F1-Q026 | include | direct_cell | IBM의 LTM 영업현금흐름은 얼마인가? | Cash from Ops. [IQ_CASH_OPER] | CF Cell Q42 |
| 24 | 1차 포함 | F1-Q027 | include | direct_cell | IBM의 LTM 현금흐름표상 자본지출(Capital Expenditure)은 얼마인가? | Capital Expenditure [IQ_CAPEX] | CF Cell Q44 |
| 25 | 1차 포함 | F1-Q028 | include | derived_formula | 2021년부터 2025년까지 IBM의 총매출액 CAGR 및 연도별 YoY는? | Total Revenue [IQ_TOTAL_REV] | IS Cell L23:P23 |
| 26 | 1차 포함 | F1-Q029 | include | derived_formula | IBM 기준, 최근 4년간 Gross Margin, EBITDA Margin, EBIT Margin의 변화 추이는? | Gross Profit Margin % [IQ_GP]; EBITDA Margin % [IQ_EBITDA]; EBIT Margin % [IQ_EBIT] | KS Cell F37:I37, F40:I40, F43:I43 |
| 27 | 1차 포함 | F1-Q030 | include | direct_cell | IBM 기준, 최근 5년간 장기부채와 단기부채의 변동 경향은? | Long-Term Debt [IQ_LT_DEBT]; Total Debt Current [IQ_TOTAL_DEBT_CURRENT] | BS Cell L66:P66, L131:P131 |
| 28 | 1차 포함 | F1-Q033 | include | derived_formula | IBM 기준, 2024년 대비 2025년 총매출과 영업이익은 얼마나 증가했나? | Total Revenue [IQ_TOTAL_REV]; Operating Income [IQ_OPER_INC] | IS Cell O23:P23, O43:P43 |
| 29 | 1차 포함 | F1-Q034 | include | derived_formula | IBM 기준, 2024년과 2025년 Total Assets 및 Total Liabilities를 비교해줘. | Total Assets [IQ_TOTAL_ASSETS]; Total Liabilities [IQ_TOTAL_LIAB] | BS Cell O50:P50, O74:P74 |
| 30 | 1차 포함 | F1-Q035 | include | derived_formula | IBM 기준, 2024년 대비 2025년 영업현금흐름과 CapEx는 어떻게 변했나? | Cash from Ops. [IQ_CASH_OPER]; Capital Expenditure [IQ_CAPEX] | CF Cell O42:P42, O44:P44 |
| 31 | 1차 포함 | F1-Q036 | include | derived_formula | IBM 기준, 2024년 대비 2025년 Diluted EPS와 DPS를 비교해줘. | Diluted EPS [IQ_DILUT_EPS_AFTER_EXTRA]; Dividends per Share [IQ_COMMON_DIV_DECLARED] | IS Cell O86:P86, O93:P93 |
| 32 | 1차 포함 | F1-Q037 | include | direct_cell | IBM의 FY0 총매출과 LTM 총매출을 알려줘. | Total Revenue [IQ_TOTAL_REV] | IS Cell P23:Q23 |
| 33 | 1차 포함 | F1-Q038 | include | direct_cell | IBM의 최근 3년 총매출 추세를 알려줘. | Total Revenue [IQ_TOTAL_REV] | IS Cell N23:P23 |
| 34 | 1차 포함 | F1-Q039 | include | direct_cell | IBM의 최근 3년 EBITDA 추세를 알려줘. | EBITDA [IQ_EBITDA] | IS Cell N101:P101 |
| 35 | 1차 포함 | F1-Q040 | include | direct_cell | IBM의 최근 3년 순이익 추세를 알려줘. | Net Income to Company [IQ_NET_INC] | IS Cell N71:P71 |
| 36 | 1차 포함 | F1-Q041 | include | direct_cell | IBM의 최근 3년 총자산 변화를 알려줘. | Total Assets [IQ_TOTAL_ASSETS] | BS Cell N50:P50 |
| 37 | 1차 포함 | F1-Q042 | include | direct_cell | IBM의 최근 3년 장기부채가 증가했는지 알려줘. | Long-Term Debt [IQ_LT_DEBT] | BS Cell N66:P66 |
| 38 | 1차 포함 | F1-Q043 | include | direct_cell | IBM의 최근 3년 영업현금흐름 추세를 알려줘. | Cash from Ops. [IQ_CASH_OPER] | CF Cell N42:P42 |
| 39 | 1차 포함 | F1-Q044 | include | direct_cell | IBM의 최근 총매출은 얼마야? | Total Revenue [IQ_TOTAL_REV]; Period Ended [IQ_PERIOD_END] | IS Cell P23, P13 |
| 40 | 1차 포함 | F1-Q045 | include | derived_formula | IBM의 총매출 성장률과 EBITDA 마진 추이를 같이 보여줘. | Total Revenues, 1 Year Growth (%) [IQ_TOTAL_REV_1YR_ANN_GROWTH]; EBITDA Margin % [IQ_EBITDA] | KS Cell E34:J34, E40:J40 |
| 41 | 1차 포함 | F1-Q046 | include | direct_cell | IBM의 최신 총현금·단기투자자산, 총차입금, 보통주 자본, TEV/EBITDA 및 P/E를 정리해줘. | - Cash & Short Term Investments [IQ_CASH_ST_INVEST]; + Total Debt [IQ_TOTAL_DEBT]; Total Common Equity [IQ_TOTAL_COMMON_EQUITY]; TEV/EBITDA (x) [SP_TEV_EBITDA_FWD]; Price/ EPS  (x) [SP_PE_EST] | KS Cell E65:E66, E71, E112, E114 |
| 42 | 1차 포함 | F1-Q053 | include | direct_cell | IBM의 LTM 총매출, EBITDA, 순이익을 알려줘. | Total Revenue [IQ_TOTAL_REV]; EBITDA [IQ_EBITDA]; Net Income to Company [IQ_NET_INC] | IS Cell Q23, Q101, Q71 |
| 43 | 1차 포함 | F1-Q054 | include | direct_cell | IBM의 LTM 총자산과 총부채를 알려줘. | Total Assets [IQ_TOTAL_ASSETS]; Total Liabilities [IQ_TOTAL_LIAB] | BS Cell Q50, Q74 |
| 44 | 1차 포함 | F1-Q055 | include | direct_cell | IBM의 LTM 총현금·단기투자자산(Total Cash & ST Investments)과 장기부채(Long-Term Debt)를 알려줘. | Total Cash & ST Investments [IQ_CASH_ST_INVEST]; Long-Term Debt [IQ_LT_DEBT] | BS Cell Q19, Q66 |
| 45 | 1차 포함 | F1-Q056 | include | direct_cell | IBM의 영업현금흐름과 CAPEX를 알려줘. | Cash from Ops. [IQ_CASH_OPER]; Capital Expenditure [IQ_CAPEX] | CF Cell Q42, Q44 |
| 46 | 1차 포함 | F1-Q057 | include | direct_cell | IBM의 영업·투자·재무 현금흐름을 알려줘. | Cash from Ops. [IQ_CASH_OPER]; Cash from Investing [IQ_CASH_INVEST]; Cash from Financing [IQ_CASH_FINAN] | CF Cell Q42, Q53, Q74 |
| 47 | 1차 포함 | F1-Q058 | include | direct_cell | IBM의 총매출과 영업현금흐름을 알려줘. | Total Revenue [IQ_TOTAL_REV]; Cash from Ops. [IQ_CASH_OPER] | IS Cell Q23, CF Cell Q42 |
| 48 | 1차 포함 | F1-Q059 | include | derived_formula | IBM의 TEV와 시가총액 중 무엇이 더 커? | = Market Capitalization; = Total Enterprise Value (TEV) | KS Cell E60, E69 |
| 49 | 1차 포함 | F1-Q060 | include | derived_formula | IBM의 EBITDA와 영업현금흐름을 비교해줘. | EBITDA [IQ_EBITDA]; Cash from Ops. [IQ_CASH_OPER] | IS Cell Q101, CF Cell Q42 |
| 50 | 1차 포함 | F1-Q061 | include | derived_formula | IBM의 총부채와 보통주 자본을 비교해줘. | Total Liabilities [IQ_TOTAL_LIAB]; Total Common Equity [IQ_TOTAL_COMMON_EQUITY] | BS Cell Q74, Q88 |
| 51 | 1차 포함 | F1-Q062 | include | derived_formula | IBM의 순이익과 영업현금흐름을 비교해줘. | Net Income to Company [IQ_NET_INC]; Cash from Ops. [IQ_CASH_OPER] | IS Cell Q71, CF Cell Q42 |
| 52 | 1차 포함 | F1-Q063 | include | derived_formula | IBM의 현금성 자산과 장기부채를 비교해줘. | Total Cash & ST Investments [IQ_CASH_ST_INVEST]; Long-Term Debt [IQ_LT_DEBT] | BS Cell Q19, Q66 |
| 53 | 1차 포함 | F1-Q064 | include | derived_formula | IBM의 총매출과 TEV를 비교해줘. | Total Revenue [IQ_TOTAL_REV]; = Total Enterprise Value (TEV) | IS Cell Q23, KS Cell E69 |
| 54 | 1차 포함 | F1-Q065 | include | derived_formula | IBM의 2025년 ROE와 ROA는 얼마인가? | Net Income to Company [IQ_NET_INC]; Total Common Equity [IQ_TOTAL_COMMON_EQUITY]; Total Assets [IQ_TOTAL_ASSETS] | IS Cell P71, BS Cell P88, P50 |
| 55 | 1차 포함 | F1-Q066 | include | derived_formula | IBM 기준, 2025년 Cash Conversion Ratio는? | Net Income to Company [IQ_NET_INC]; Cash from Ops. [IQ_CASH_OPER] | IS Cell P71, CF Cell P42 |
| 56 | 1차 포함 | F1-Q067 | include | direct_cell | IBM 기준, Key Stats의 TEV가 총부채 및 현금 수치와 정합성을 이루는가? | = Market Capitalization; - Cash & Short Term Investments [IQ_CASH_ST_INVEST]; + Total Debt [IQ_TOTAL_DEBT]; + Total Preferred Equity [IQ_TOTAL_PREF_EQUITY]; + Total Minority Interest [IQ_MINORITY_INTEREST_TOTAL]; = Total Enterprise Value (TEV) | KS Cell E60, E65:E69 |
| 57 | 1차 포함 | F1-Q068 | include | derived_formula | IBM의 Net Debt/EBITDA와 유동비율은 얼마인가? | Total Debt [IQ_TOTAL_DEBT]; Total Cash & ST Investments [IQ_CASH_ST_INVEST]; Total Current Assets [IQ_TOTAL_CA]; Total Current Liabilities [IQ_TOTAL_CL]; EBITDA [IQ_EBITDA] | BS Cell P130, P19, P34, P64, IS Cell P101 |
| 58 | 1차 포함 | F1-Q069 | include | derived_formula | IBM 기준, FCF 대비 배당 및 자사주 매입 집행 비중은? | Cash from Ops. [IQ_CASH_OPER]; Capital Expenditure [IQ_CAPEX]; Repurchase of Common [IQ_COMMON_REP]; Total Dividends Paid [IQ_TOTAL_DIV_PAID_CF] | CF Cell P42, P44, P63, P70 |
| 59 | 1차 포함 | F1-Q070 | include | derived_formula | IBM 기준, DSO 및 DIO의 추이는? | Accounts Receivable [IQ_AR]; Inventory [IQ_INVENTORY]; Total Revenue [IQ_TOTAL_REV]; Cost Of Goods Sold [IQ_COGS] | BS Cell L21:P21, L26:P26, IS Cell L23:P23, L25:P25 |
| 60 | 1차 포함 | F1-Q071 | include | derived_formula | IBM의 LTM 순부채성 금액을 TEV와 Market Cap 차이로 계산하면? | = Market Capitalization; = Total Enterprise Value (TEV) | KS Cell E60, E69 |
| 61 | 1차 포함 | F1-Q072 | include | derived_formula | IBM 기준, 2025년 매출총이익률과 영업이익률은? | Total Revenue [IQ_TOTAL_REV]; Gross Profit [IQ_GP]; Operating Income [IQ_OPER_INC] | IS Cell P23, P29, P43 |
| 62 | 1차 포함 | F1-Q073 | include | derived_formula | IBM 기준, 2025년 단순 잉여현금흐름은? | Cash from Ops. [IQ_CASH_OPER]; Capital Expenditure [IQ_CAPEX] | CF Cell P42, P44 |
| 63 | 1차 포함 | F1-Q074 | include | derived_formula | IBM 기준, 2025년 총자산 대비 총부채 비율은? | Total Assets [IQ_TOTAL_ASSETS]; Total Liabilities [IQ_TOTAL_LIAB] | BS Cell P50, P74 |
| 64 | 1차 포함 | F1-Q075 | include | derived_formula | IBM의 TEV가 시가총액보다 얼마나 큰가? | = Market Capitalization; = Total Enterprise Value (TEV) | KS Cell E60, E69 |
| 65 | 1차 포함 | F1-Q076 | include | derived_formula | IBM 기준, FY-1 대비 FY0 총매출 성장률은? | Total Revenue [IQ_TOTAL_REV] | IS Cell O23, P23 |
| 66 | 1차 포함 | F1-Q077 | include | derived_formula | IBM 기준, 최근 순이익 성장률은? | Net Income to Company [IQ_NET_INC] | IS Cell O71, P71 |
| 67 | 1차 포함 | F1-Q078 | include | derived_formula | IBM의 LTM 매출총이익률을 계산해줘. | Gross Profit [IQ_GP]; Total Revenue [IQ_TOTAL_REV] | IS Cell Q29, Q23 |
| 68 | 1차 포함 | F1-Q079 | include | derived_formula | IBM의 LTM 영업이익률은? | Operating Income [IQ_OPER_INC]; Total Revenue [IQ_TOTAL_REV] | IS Cell Q43, Q23 |
| 69 | 1차 포함 | F1-Q080 | include | derived_formula | IBM의 LTM 순이익률을 계산해줘. | Net Income to Company [IQ_NET_INC]; Total Revenue [IQ_TOTAL_REV] | IS Cell Q71, Q23 |
| 70 | 1차 포함 | F1-Q081 | include | derived_formula | IBM의 LTM 유동비율은? | Total Current Assets [IQ_TOTAL_CA]; Total Current Liabilities [IQ_TOTAL_CL] | BS Cell Q34, Q64 |
| 71 | 1차 포함 | F1-Q082 | include | derived_formula | IBM 기준, 영업현금흐름과 CAPEX로 FCF를 계산해줘. | Cash from Ops. [IQ_CASH_OPER]; Capital Expenditure [IQ_CAPEX] | CF Cell Q42, Q44 |
| 72 | 1차 포함 | F1-Q083 | include | direct_cell | IBM 기준, 종가와 발행주식수로 시가총액을 계산해줘. | Day Close Price; x Shares Outstanding; Divide By; = Market Capitalization | KS Cell E57:E60 |
| 73 | 1차 포함 | F1-Q084 | include | derived_formula | IBM의 TEV는 LTM 총매출의 몇 배야? | = Total Enterprise Value (TEV); Total Revenue [IQ_TOTAL_REV] | KS Cell E69, IS Cell Q23 |
| 74 | 1차 포함 | F1-Q085 | include | derived_formula | IBM의 최근 3년 평균 총매출은 얼마야? | Total Revenue [IQ_TOTAL_REV] | IS Cell N23:P23 |
| 75 | 1차 포함 | F1-Q086 | include | derived_formula | IBM 기준, 장기부채가 현금성 자산보다 얼마나 큰가? | Long-Term Debt [IQ_LT_DEBT]; Total Cash & ST Investments [IQ_CASH_ST_INVEST] | BS Cell Q66, Q19 |
| 76 | 1차 포함 | F1-Q087 | include | direct_cell | IBM 기준, 2022년 순이익이 급감했음에도 영업현금흐름이 유지된 원인은? | Net Income [IQ_NI_CF]; Depreciation & Amort. [IQ_DA_SUPPL_CF]; Amort. of Goodwill and Intangibles [IQ_GW_INTAN_AMORT_CF]; Impair. of Oil, Gas & Mineral Prop. [IQ_OIL_IMPAIR]; Depreciation & Amort., Total [IQ_DA_CF]; Other Amortization [IQ_OTHER_AMORT]; Minority Int. in Earnings [IQ_MINORITY_INTEREST_CF]; (Gain) Loss From Sale Of Asset [IQ_GAIN_ASSETS_CF]; (Gain) Loss On Sale Of Invest. [IQ_GAIN_INVEST_CF]; Asset Writedown & Restructuring Costs [IQ_ASSET_WRITEDOWN_CF]; Net (Increase) Decrease in Loans Orig./Sold [IQ_LOANS_CF]; Provision for Credit Losses [IQ_CREDIT_LOSS_CF]; (Income) Loss on Equity Invest. [IQ_INC_EQUITY_CF]; Stock-Based Compensation [IQ_STOCK_BASED_CF]; Tax Benefit from Stock Options [IQ_TAX_BENEFIT_OPTIONS]; Provision & Write-off of Bad debts [IQ_PROV_BAD_DEBTS_CF]; Net Cash From Discontinued Ops. [IQ_DO_CF]; Other Operating Activities [IQ_OTHER_OPER_ACT]; Change in Trad. Asset Securities [IQ_CHANGE_TRADING_ASSETS]; Change in Acc. Receivable [IQ_CHANGE_AR]; Change In Inventories [IQ_CHANGE_INVENTORY]; Change in Acc. Payable [IQ_CHANGE_AP]; Change in Unearned Rev. [IQ_CHANGE_UNEARN_REV]; Change in Inc. Taxes [IQ_CHANGE_INC_TAX]; Change in Def. Taxes [IQ_CHANGE_DEF_TAX]; Change In Other Net Operating Assets [IQ_CHANGE_OTHER_NET_OPER_ASSETS]; Cash from Ops. [IQ_CASH_OPER] | CF Cell M15:M42 |
| 77 | 1차 포함 | F1-Q088 | include | direct_cell | IBM의 총차입금(Total Debt)이 크게 변동한 배경은 차입금 발행인가, M&A/투자 지출 때문인가? | Total Debt [IQ_TOTAL_DEBT]; Cash Acquisitions [IQ_CASH_ACQUIRE_CF]; Total Debt Issued [IQ_TOTAL_DEBT_ISSUED]; Total Debt Repaid [IQ_TOTAL_DEBT_REPAID] | BS Cell L130:P130, CF Cell L46:P46, L57:P57, L60:P60 |
| 78 | 1차 포함 | F1-Q089 | include | derived_formula | IBM이 영업현금흐름을 초과하는 주주환원을 집행했는가? | Cash from Ops. [IQ_CASH_OPER]; Capital Expenditure [IQ_CAPEX]; Repurchase of Common [IQ_COMMON_REP]; Total Dividends Paid [IQ_TOTAL_DIV_PAID_CF]; Total Cash & ST Investments [IQ_CASH_ST_INVEST]; Total Debt [IQ_TOTAL_DEBT] | CF Cell P42, P44, P63, P70, BS Cell O19:P19, O130:P130 |
| 79 | 1차 포함 | F1-Q090 | include | derived_formula | IBM 기준, CapEx와 PP&E 증가 및 이후 총매출 성장 간에 시차가 존재하는가? | Capital Expenditure [IQ_CAPEX]; Net Property, Plant & Equipment [IQ_NPPE]; Total Revenue [IQ_TOTAL_REV] | CF Cell L44:P44, BS Cell L38:P38, IS Cell L23:P23 |
| 80 | 1차 포함 | F1-Q091 | include | derived_formula | 현재 TEV/EBITDA 멀티플이 IBM의 수익성과 성장 전망 대비 적정한가? | TEV/EBITDA (x) [SP_TEV_EBITDA_FWD]; EBITDA Margin % [IQ_EBITDA]; Total Revenue [IQ_TOTAL_REV] | KS Cell E112, I40, N33:P33, N40:P40 |
| 81 | 1차 포함 | F1-Q101 | include | direct_cell | IBM 기준, 2025년 Actual과 2026\~2028년 총매출 및 EPS 성장 전망은? | Total Revenue [IQ_TOTAL_REV]; Diluted EPS Excl. Extra Items [IQ_DILUT_EPS_BEFORE_EXTRA] | KS Cell I33, I51, N33:P33, N51:P51 |
| 82 | 1차 포함 | F1-Q102 | include | derived_formula | IBM 기준, FY2025 대비 NTM/FY2026\~2028 TEV/EBITDA 멀티플 변화 전망은? | TEV/EBITDA (x) [SP_TEV_EBITDA_FWD] | KS Cell E112:J112 |
| 83 | 1차 포함 | F1-Q103 | include | derived_formula | IBM 기준, 최근 총매출 성장 추세가 유지되면 2026년 Total Revenue는? | Total Revenue [IQ_TOTAL_REV] | IS Cell L23:P23 |
| 84 | 1차 포함 | F1-Q104 | include | derived_formula | IBM 기준, 현재 영업이익률이 유지될 때 2026년 Operating Income은? | Total Revenue [IQ_TOTAL_REV]; Operating Income [IQ_OPER_INC] | IS Cell P23, P43, L23:P23 |
| 85 | 1차 포함 | F1-Q105 | include | derived_formula | IBM 기준, 영업현금흐름이 5% 증가하고 CapEx가 동일하면 2026년 FCF는? | Cash from Ops. [IQ_CASH_OPER]; Capital Expenditure [IQ_CAPEX] | CF Cell P42, P44 |
| 86 | 1차 포함 | F1-Q106 | include | derived_formula | IBM 기준, 현재 TEV/Total Revenue 배수를 유지할 경우 2026년 예상 TEV는? | = Total Enterprise Value (TEV); Total Revenue [IQ_TOTAL_REV] | KS Cell E69, IS Cell Q23, L23:P23 |
| 87 | 2차-A | F2A-O1-01 | include | direct_cell | 2025년 IBM 현금·단기투자자산 수치는 얼마야? | Total Cash & ST Investments [IQ_CASH_ST_INVEST] | BS Cell P19 |
| 88 | 2차-A | F2A-O1-02 | include | direct_cell | IBM의 2024년 현금흐름표상 매입채무 변동(Change in Acc. Payable)은 얼마인가? | Change in Acc. Payable [IQ_CHANGE_AP] | CF Cell O37 |
| 89 | 2차-A | F2A-O1-03 | include | direct_cell | IBM은 2025년에 매출채권을 얼마로 기록했어? | Accounts Receivable [IQ_AR] | BS Cell P21 |
| 90 | 2차-A | F2A-O1-04 | include | direct_cell | IBM의 2025년 현금 순변동은 얼마인가? | Net Change in Cash [IQ_CASH_NET_CHANGE] | CF Cell P78 |
| 91 | 2차-A | F2A-O1-05 | include | direct_cell | IBM의 2024년 감가상각누계액은 얼마인가? | Accumulated Depreciation [IQ_ACCUM_DEPRECIATION] | BS Cell O37 |
| 92 | 2차-A | F2A-O1-06 | include | direct_cell | IBM의 2025년 특이항목 포함 기본주당순이익(Basic EPS)은 얼마인가? | Basic EPS [IQ_BASIC_EPS_AFTER_EXTRA] | IS Cell P82 |
| 93 | 2차-A | F2A-O1-07 | include | direct_cell | IBM은 2025년에 장기이연법인세자산을 얼마로 기록했어? | Deferred Tax Assets, LT [IQ_DEF_TAX_ASSETS_LT] | BS Cell P47 |
| 94 | 2차-A | F2A-O1-08 | include | direct_cell | IBM은 2025년에 현금 인수지출을 얼마로 기록했어? | Cash Acquisitions [IQ_CASH_ACQUIRE_CF] | CF Cell P46 |
| 95 | 2차-A | F2A-O1-09 | include | direct_cell | IBM의 2025년 보통주자본총계는 얼마인가? | Total Common Equity [IQ_TOTAL_COMMON_EQUITY] | BS Cell P88 |
| 96 | 2차-A | F2A-O1-10 | include | direct_cell | IBM의 2025년 손익계산서상 실제 가중평균 기본주식수는 얼마인가? | Weighted Avg. Basic Shares Out. (actual) [IQ_AVG_BASIC_SHARES_OUT] | IS Cell P84 |
| 97 | 2차-A | F2A-O1-11 | include | direct_cell | 2025년 기준 IBM의 미지급비용을 알려줄래? | Accrued Exp. [IQ_AE] | BS Cell P54 |
| 98 | 2차-A | F2A-O1-12 | include | direct_cell | IBM은 2023년에 유효세율을 얼마로 기록했어? | Effective Tax Rate (%) [IQ_EFFECT_TAX_RATE] | IS Cell N146 |
| 99 | 2차-A | F2A-O1-13 | include | direct_cell | IBM의 2025년 영업권은 얼마인가? | Goodwill [IQ_GOODWILL] | BS Cell P41 |
| 100 | 2차-A | F2A-O1-14 | include | direct_cell | 2024년 IBM 현금 이자지급액 수치는 얼마야? | Cash Interest Paid [IQ_CASH_INTEREST] | CF Cell O81 |
| 101 | 2차-A | F2A-O1-15 | include | direct_cell | 2024년 IBM 환율 관련 손익 수치는 얼마야? | Currency Exchange Gains (Loss) [IQ_CURRENCY_GAIN] | IS Cell O50 |
| 102 | 2차-A | F2A-O1-16 | include | direct_cell | IBM의 2024년 광고비는 얼마인가? | Advertising Expense [IQ_ADVERTISING] | IS Cell O150 |
| 103 | 2차-A | F2A-O1-17 | include | direct_cell | IBM의 2025년 보통주 계정(Common Stock)은 얼마인가? | Common Stock [IQ_COMMON_STOCK] | BS Cell P83 |
| 104 | 2차-A | F2A-O1-18 | include | direct_cell | 2024년 기준 IBM의 유동성 장기부채를 알려줄래? | Current Portion of Long Term Debt [IQ_CURRENT_PORT_DEBT] | BS Cell O56 |
| 105 | 2차-A | F2A-O1-19 | include | direct_cell | 2025년 기준 IBM의 특이항목 포함 세전이익을 알려줄래? | EBT Incl Unusual Items [IQ_EBT] | IS Cell P64 |
| 106 | 2차-A | F2A-O1-20 | include | direct_cell | 2024년 IBM 정규직 직원 수 수치는 얼마야? | Full Time Employees (actual) [IQ_FULL_TIME] | BS Cell O164 |
| 107 | 2차-A | F2A-O1-21 | include | direct_cell | IBM의 2025년 금융부문 매출(Finance Div. Revenue)은 얼마인가? | Finance Div. Revenue [IQ_FIN_DIV_REV] | IS Cell P17 |
| 108 | 2차-A | F2A-O1-22 | include | direct_cell | IBM의 2025년 계속영업이익은 얼마인가? | Earnings from Cont. Ops. [IQ_EARNINGS_CONT_OPS] | IS Cell P67 |
| 109 | 2차-A | F2A-O1-23 | include | direct_cell | 2025년 기준 IBM의 자본적지출을 알려줄래? | Capital Expenditure [IQ_CAPEX] | CF Cell P44 |
| 110 | 2차-A | F2A-O1-24 | include | direct_cell | 2025년 IBM 현금 및 현금성자산 수치는 얼마야? | Cash And Equivalents [IQ_CASH_EQUIV] | BS Cell P16 |
| 111 | 2차-A | F2A-O1-25 | include | direct_cell | IBM은 기준일에 시가총액을 얼마로 기록했어? | = Market Capitalization | KS Cell E60 |
| 112 | 2차-A | F2A-O2-26 | include | direct_cell | 2024년과 2025년 IBM 기타비유동자산을 비교해줘? | Other Long-Term Assets [IQ_OTHER_LT_ASSETS] | BS Cell O49, BS Cell P49 |
| 113 | 2차-A | F2A-O2-27 | include | direct_cell | IBM의 현금흐름표상 총 감가상각·상각비는 2024년에서 2025년 사이에 어떻게 변했는가? | Depreciation & Amort., Total [IQ_DA_CF] | CF Cell O19, CF Cell P19 |
| 114 | 2차-A | F2A-O2-28 | include | direct_cell | IBM의 자산 처분손익은 2023년에서 2024년 사이에 어떻게 변했어? | Gain (Loss) On Sale Of Assets [IQ_GAIN_ASSETS] | IS Cell N58, IS Cell O58 |
| 115 | 2차-A | F2A-O2-29 | include | direct_cell | IBM의 총자산은 2024년에서 2025년 사이에 어떻게 변했어? | Total Assets [IQ_TOTAL_ASSETS] | BS Cell O50, BS Cell P50 |
| 116 | 2차-A | F2A-O2-30 | include | direct_cell | 2024년과 2025년 IBM 재무활동현금흐름을 비교해줘? | Cash from Financing [IQ_CASH_FINAN] | CF Cell O74, CF Cell P74 |
| 117 | 2차-A | F2A-O2-31 | include | direct_cell | IBM의 손익계산서상 총주식보상비용은 2024년과 2025년에 각각 얼마인가? | Stock-Based Comp., Total [IQ_STOCK_BASED_TOTAL] | IS Cell O174, IS Cell P174 |
| 118 | 2차-A | F2A-O2-32 | include | direct_cell | IBM의 주당배당금(Dividends per Share)은 2024년에서 2025년 사이에 어떻게 변했는가? | Dividends per Share [IQ_COMMON_DIV_DECLARED] | IS Cell O93, IS Cell P93 |
| 119 | 2차-A | F2A-O2-33 | include | direct_cell | IBM의 장기투자자산은 2024년에서 2025년 사이에 어떻게 변했어? | Long-term Investments [IQ_LT_INVEST] | BS Cell O40, BS Cell P40 |
| 120 | 2차-A | F2A-O2-34 | include | direct_cell | IBM의 현금흐름표상 보통주 발행대금은 2023년과 2024년에 각각 얼마인가? | Issuance of Common Stock [IQ_COMMON_ISSUED] | CF Cell N62, CF Cell O62 |
| 121 | 2차-A | F2A-O2-35 | include | direct_cell | 2024년과 2025년 IBM 매출원가를 비교해줘? | Cost Of Goods Sold [IQ_COGS] | IS Cell O25, IS Cell P25 |
| 122 | 2차-A | F2A-O2-36 | include | direct_cell | IBM의 기타비유동부채는 2024년에서 2025년 사이에 어떻게 변했어? | Other Non-Current Liabilities [IQ_OTHER_LIAB_LT] | BS Cell O73, BS Cell P73 |
| 123 | 2차-A | F2A-O2-37 | include | direct_cell | 2024년과 2025년 IBM 중단영업이익을 비교해줘? | Earnings of Discontinued Ops. [IQ_EARNINGS_DISCONTINUED_OPS] | IS Cell O69, IS Cell P69 |
| 124 | 2차-A | F2A-O2-38 | include | direct_cell | IBM의 가중평균 희석주식수는 2024년에서 2025년 사이에 어떻게 변했어? | Weighted Avg. Diluted Shares Out. (actual) [IQ_AVG_DILUT_SHARES_OUT] | IS Cell O88, IS Cell P88 |
| 125 | 2차-A | F2A-O2-39 | include | direct_cell | IBM의 현금 법인세지급액은 2023년에서 2024년 사이에 어떻게 변했어? | Cash Taxes Paid [IQ_CASH_TAXES] | CF Cell N82, CF Cell O82 |
| 126 | 2차-A | F2A-O2-40 | include | direct_cell | 2024년과 2025년 IBM 기타유동자산을 비교해줘? | Other Current Assets [IQ_OTHER_CA_SUPPL] | BS Cell O33, BS Cell P33 |
| 127 | 2차-A | F2A-O3-41 | include | direct_cell | IBM의 2025년 총부채(Total Liabilities)와 2024년 현금흐름표상 매출채권 변동을 같이 알려줘. | Total Liabilities [IQ_TOTAL_LIAB]; Change in Acc. Receivable [IQ_CHANGE_AR] | BS Cell P74, CF Cell O35 |
| 128 | 2차-A | F2A-O3-42 | include | direct_cell | IBM의 2025년 총유동자산과 사업 매각대금(Divestitures)을 같이 알려줘. | Total Current Assets [IQ_TOTAL_CA]; Divestitures [IQ_DIVEST_CF] | BS Cell P34, CF Cell P47 |
| 129 | 2차-A | F2A-O3-43 | include | direct_cell | IBM의 2025년 특이항목 제외 세전이익과 총자본화(Total Capitalization)를 같이 알려줘. | EBT Excl Unusual Items [IQ_EBT_EXCL]; Total Capitalization [IQ_TOTAL_CAP] | IS Cell P52, BS Cell P135 |
| 130 | 2차-A | F2A-O3-44 | include | direct_cell | IBM의 2016년 법적 합의 비용과 2025년 순유형자산(Net Property, Plant & Equipment)을 같이 알려줘. | Legal Settlements [IQ_LEGAL_SETTLE]; Net Property, Plant & Equipment [IQ_NPPE] | IS Cell G62, BS Cell P38 |
| 131 | 2차-A | F2A-O3-45 | include | direct_cell | IBM의 2025년 매입채무와 2024년 유형자산 취득원가(Gross Property, Plant & Equipment)를 비교해줘. | Accounts Payable [IQ_AP]; Gross Property, Plant & Equipment [IQ_GPPE] | BS Cell P53, BS Cell O36 |
| 132 | 2차-A | F2A-O3-46 | include | direct_cell | IBM의 2025년 기타무형자산과 현금흐름표상 주식보상비용을 같이 알려줘. | Other Intangibles [IQ_OTHER_INTAN]; Stock-Based Compensation [IQ_STOCK_BASED_CF] | BS Cell P42, CF Cell P29 |
| 133 | 2차-A | F2A-O3-47 | include | direct_cell | IBM의 2025년 법인세비용과 2024년 이자·투자수익을 같이 알려줘. | Income Tax Expense [IQ_INC_TAX]; Interest and Invest. Income [IQ_INTEREST_INVEST_INC] | IS Cell P66, IS Cell O46 |
| 134 | 2차-A | F2A-O3-48 | include | direct_cell | IBM의 기타 매출과 총무형자산을 같이 알려줘? | Other Revenue [IQ_OTHER_REV_SUPPL]; Total Intangible Assets [IQ_GW_INTAN] | IS Cell P22, BS Cell P128 |
| 135 | 2차-A | F2A-O3-49 | include | direct_cell | IBM의 2024년 총직원 수와 2025년 순운전자본을 같이 알려줘. | Total Employees [IQ_TOTAL_EMPLOYEES]; Net Working Capital [IQ_NET_WORKING_CAP] | BS Cell O166, BS Cell P137 |
| 136 | 2차-A | F2A-O3-50 | include | direct_cell | IBM의 2024년 투자자산 처분손익과 2025년 이자비용을 같이 알려줘. | Gain (Loss) On Sale Of Invest. [IQ_GAIN_INVEST]; Interest Expense [IQ_INTEREST_EXP] | IS Cell O57, IS Cell P45 |
| 137 | 2차-A | F2A-O3-51 | include | direct_cell | IBM의 2025년 장기차입금과 순차입부채(Net Debt)를 비교해줘. | Long-Term Debt [IQ_LT_DEBT]; Net Debt [IQ_NET_DEBT] | BS Cell P66, BS Cell P133 |
| 138 | 2차-A | F2A-O3-52 | include | direct_cell | IBM의 2025년 재고자산과 2024년 자사주 매입액을 비교해줘. | Inventory [IQ_INVENTORY]; Repurchase of Common [IQ_COMMON_REP] | BS Cell P26, CF Cell O63 |
| 139 | 2차-A | F2A-O3-53 | include | direct_cell | IBM의 EBITA와 연금·퇴직급여부채를 같이 알려줘? | EBITA [IQ_EBITA]; Pension & Other Post-Retire. Benefits [IQ_PENSION] | IS Cell P112, BS Cell P71 |
| 140 | 2차-A | F2A-O3-54 | include | direct_cell | IBM의 2025년 배당성향(Payout Ratio)과 특이항목 포함 희석주당순이익을 같이 알려줘. | Payout Ratio (%) [IQ_PAYOUT_RATIO]; Diluted EPS [IQ_DILUT_EPS_AFTER_EXTRA] | IS Cell P147, IS Cell P86 |
| 141 | 2차-A | F2A-O4-55 | include | derived_formula | IBM의 총주식보상비용과 장기투자자산 차이는 얼마야? | Stock-Based Comp., Total [IQ_STOCK_BASED_TOTAL]; Long-term Investments [IQ_LT_INVEST] | IS Cell P174, BS Cell P40 |
| 142 | 2차-A | F2A-O4-56 | include | derived_formula | IBM의 총차입부채 대비 유가증권 투자액 비율은 어느 정도야? | Invest. in Marketable & Equity Sec. [IQ_INVEST_SECURITY_CF]; Total Debt [IQ_TOTAL_DEBT] | CF Cell P50, BS Cell P130 |
| 143 | 2차-A | F2A-O4-57 | include | derived_formula | IBM의 연구개발비와 이익잉여금 차이는 얼마야? | R & D Exp. [IQ_RD_EXP]; Retained Earnings [IQ_RETAINED_EARNINGS] | IS Cell P36, BS Cell P85 |
| 144 | 2차-A | F2A-O4-58 | include | derived_formula | IBM의 매출 대비 단기투자자산 비율은 어느 정도야? | Short Term Investments [IQ_ST_INVEST]; Revenue [IQ_REV] | BS Cell P17, IS Cell P16 |
| 145 | 2차-A | F2A-O4-59 | include | derived_formula | IBM의 단기차입금 대비 재고자산 변동 비율은 어느 정도야? | Change In Inventories [IQ_CHANGE_INVENTORY]; Short-term Borrowings [IQ_ST_DEBT] | CF Cell O36, BS Cell P55 |
| 146 | 2차-A | F2A-O4-60 | include | derived_formula | IBM의 총무형자산 대비 영업권 비율은 어느 정도야? | Goodwill [IQ_GOODWILL]; Total Intangible Assets [IQ_GW_INTAN] | BS Cell P41, BS Cell P128 |
| 147 | 2차-A | F2A-O4-61 | include | derived_formula | IBM의 합병 관련 구조조정 비용과 순이자비용 차이는 얼마야? | Merger & Related Restruct. Charges [IQ_MERGER_RESTRUCTURE]; Net Interest Exp. [IQ_NET_INTEREST_EXP] | IS Cell O55, IS Cell P47 |
| 148 | 2차-A | F2A-O4-62 | include | derived_formula | IBM의 기타비유동자산 대비 장기부채 발행액 비율은 어느 정도야? | Long-Term Debt Issued [IQ_LT_DEBT_ISSUED]; Other Long-Term Assets [IQ_OTHER_LT_ASSETS] | CF Cell P56, BS Cell P49 |
| 149 | 2차-A | F2A-O4-63 | include | derived_formula | IBM의 특이항목 포함 세전이익과 총자산 차이는 얼마야? | EBT Incl Unusual Items [IQ_EBT]; Total Assets [IQ_TOTAL_ASSETS] | IS Cell P64, BS Cell P50 |
| 150 | 2차-A | F2A-O4-64 | include | derived_formula | IBM의 영업이익과 총자본 차이는 얼마야? | Operating Income [IQ_OPER_INC]; Total Equity [IQ_TOTAL_EQUITY] | IS Cell P43, BS Cell P91 |
| 151 | 2차-A | F2A-O4-65 | include | derived_formula | IBM의 선급비용 대비 기타수취채권 비율은 어느 정도야? | Other Receivables [IQ_OTHER_RECEIV]; Prepaid Exp. [IQ_PREPAID_EXP] | BS Cell P22, BS Cell P27 |
| 152 | 2차-A | F2A-O4-66 | include | derived_formula | IBM의 판매·마케팅비와 판매관리비 차이는 얼마야? | Selling and Marketing Expense [IQ_SALES_MARKETING]; Selling General & Admin Exp. [IQ_SGA] | IS Cell O152, IS Cell P31 |
| 153 | 2차-A | F2A-O4-67 | include | derived_formula | IBM의 감가상각누계액 대비 현금흐름표 순이익 비율은 어느 정도야? | Net Income [IQ_NI_CF]; Accumulated Depreciation [IQ_ACCUM_DEPRECIATION] | CF Cell P15, BS Cell O37 |
| 154 | 2차-A | F2A-O4-68 | include | derived_formula | IBM의 금융부문 매출과 기타유동자산 차이는 얼마야? | Finance Div. Revenue [IQ_FIN_DIV_REV]; Other Current Assets [IQ_OTHER_CA_SUPPL] | IS Cell P17, BS Cell P33 |
| 155 | 2차-A | F2A-O4-69 | include | derived_formula | IBM의 환율 관련 손익과 현금 및 현금성자산 차이는 얼마야? | Currency Exchange Gains (Loss) [IQ_CURRENCY_GAIN]; Cash And Equivalents [IQ_CASH_EQUIV] | IS Cell O50, BS Cell P16 |
| 156 | 2차-A | F2A-O4-70 | include | derived_formula | IBM의 총부채 대비 총자본화 비율은 어느 정도야? | Total Capitalization [IQ_TOTAL_CAP]; Total Liabilities [IQ_TOTAL_LIAB] | BS Cell P135, BS Cell P74 |
| 157 | 2차-A | F2A-O4-71 | include | derived_formula | IBM의 기타 특이항목 대비 유동 선수수익 비율은 어느 정도야? | Unearned Revenue, Current [IQ_UNEARN_REV_CURRENT]; Other Unusual Items [IQ_OTHER_UNUSUAL] | BS Cell P61, IS Cell O63 |
| 158 | 2차-A | F2A-O4-72 | include | derived_formula | IBM의 정규화 순이익과 유형장부가치 차이는 얼마야? | Normalized Net Income [IQ_NI_NORM]; Tangible Book Value [IQ_TANG_EQUITY] | IS Cell P132, BS Cell P127 |
| 159 | 2차-A | F2A-O4-73 | include | derived_formula | IBM의 장기이연법인세자산 대비 총수취채권 비율은 어느 정도야? | Total Receivables [IQ_TOTAL_RECEIV]; Deferred Tax Assets, LT [IQ_DEF_TAX_ASSETS_LT] | BS Cell P24, BS Cell P47 |
| 160 | 2차-A | F2A-O4-74 | include | derived_formula | IBM의 EBITDAR와 총유동부채 차이는 얼마야? | EBITDAR [IQ_EBITDAR]; Total Current Liabilities [IQ_TOTAL_CL] | IS Cell O116, BS Cell P64 |
| 161 | 2차-A | F2A-O4-75 | include | derived_formula | IBM의 구조조정 비용과 총영업비용 차이는 얼마야? | Restructuring Charges [IQ_RESTRUCTURE]; Total Operating Expenses [IQ_TOTAL_OPER_EXPEN] | IS Cell O54, IS Cell P164 |
| 162 | 2차-A | F2A-O4-76 | include | derived_formula | IBM의 비유동 선수수익 대비 투자활동현금흐름 비율은 어느 정도야? | Cash from Investing [IQ_CASH_INVEST]; Unearned Revenue, Non-Current [IQ_UNEARN_REV_LT] | CF Cell P53, BS Cell P70 |
| 163 | 2차-A | F2A-O5-77 | include | direct_cell | IBM의 2025년 연금·퇴직급여부채와 비유동 선수수익 중 어느 쪽이 더 큰가? | Pension & Other Post-Retire. Benefits [IQ_PENSION]; Unearned Revenue, Non-Current [IQ_UNEARN_REV_LT] | BS Cell P71, BS Cell P70 |
| 164 | 2차-A | F2A-O5-78 | include | direct_cell | IBM의 2025년 기타 매출과 2024년 유형자산 취득원가 중 어느 쪽이 더 큰가? | Other Revenue [IQ_OTHER_REV_SUPPL]; Gross Property, Plant & Equipment [IQ_GPPE] | IS Cell P22, BS Cell O36 |
| 165 | 2차-A | F2A-O5-79 | include | direct_cell | IBM의 영업활동현금흐름과 현금·단기투자자산 중 어느 쪽이 더 커? | Cash from Ops. [IQ_CASH_OPER]; Total Cash & ST Investments [IQ_CASH_ST_INVEST] | CF Cell P42, BS Cell P19 |
| 166 | 2차-A | F2A-O5-80 | include | direct_cell | IBM의 총유동자산과 미지급비용 중 어느 쪽이 더 커? | Total Current Assets [IQ_TOTAL_CA]; Accrued Exp. [IQ_AE] | BS Cell P34, BS Cell P54 |
| 167 | 2차-A | F2A-O5-81 | include | direct_cell | IBM의 2025년 특이항목 제외 세전이익과 기타비유동부채 중 어느 쪽이 더 큰가? | EBT Excl Unusual Items [IQ_EBT_EXCL]; Other Non-Current Liabilities [IQ_OTHER_LIAB_LT] | IS Cell P52, BS Cell P73 |
| 168 | 2차-A | F2A-O6-82 | include | direct_cell | IBM의 2026년 추정치 EBIT 마진 전망치는 얼마야? | EBIT Margin % [IQ_EBIT] | KS Cell N43 |
| 169 | 2차-A | F2A-O6-83 | include | direct_cell | 2026년 추정치 IBM 특이항목 제외 희석주당순이익 추정값을 알려줄래? | Diluted EPS Excl. Extra Items [IQ_DILUT_EPS_BEFORE_EXTRA] | KS Cell N51 |
| 170 | 2차-A | F2A-O6-84 | include | direct_cell | 2026년 추정치 IBM 총매출 추정값을 알려줄래? | Total Revenue [IQ_TOTAL_REV] | KS Cell N33 |
| 171 | 2차-A | F2A-O6-85 | include | direct_cell | IBM의 2026년 추정치 매출총이익률 전망치는 얼마야? | Gross Profit Margin % [IQ_GP] | KS Cell N37 |
| 172 | 2차-A | F2A-O6-86 | include | direct_cell | 2026년 추정치 IBM EBITDA 마진 추정값을 알려줄래? | EBITDA Margin % [IQ_EBITDA] | KS Cell N40 |
| 173 | 2차-A | F2A-O6-87 | include | direct_cell | IBM의 2026년 추정치 순이익률 전망치는 얼마야? | Net Income Margin % [IQ_NET_INC] | KS Cell N49 |
| 174 | 2차-B | F2B-U1-01 | include | direct_cell | 기업 A의 2025 회계연도(FY0) 총매출(Total Revenue)은 얼마인가? | Total Revenue [IQ_TOTAL_REV] | IS Cell P23 |
| 175 | 2차-B | F2B-U1-02 | include | direct_cell | 기업 A의 2025년 영업활동현금흐름(Cash from Ops.)은 얼마인가? | Cash from Ops. [IQ_CASH_OPER] | CF Cell P42 |
| 176 | 2차-B | F2B-U1-03 | include | direct_cell | Coldplay의 2025 회계연도(FY0) 총차입금(Total Debt)은 얼마인가? | Total Debt [IQ_TOTAL_DEBT] | BS Cell P130 |
| 177 | 2차-B | F2B-U1-04 | include | direct_cell | Coldplay의 2025년 영업이익(Operating Income)은 얼마인가? | Operating Income [IQ_OPER_INC] | IS Cell P43 |
| 178 | 2차-B | F2B-U1-05 | include | direct_cell | DH Innovation의 2025년 총유동자산(Total Current Assets)은 얼마인가? | Total Current Assets [IQ_TOTAL_CA] | BS Cell P34 |
| 179 | 2차-B | F2B-U1-06 | include | direct_cell | DH Innovation의 2025년 지배기업 순이익(Net Income to Company)은 얼마인가? | Net Income to Company [IQ_NET_INC] | IS Cell P71 |
| 180 | 2차-B | F2B-U2-01 | include | direct_cell | 기업 A는 최근 3년 동안 총매출이 꾸준히 성장한 회사야? | Total Revenue [IQ_TOTAL_REV] | IS N23:P23 |
| 181 | 2차-B | F2B-U2-02 | include | direct_cell | 기업 A의 현금창출력도 최근 계속 좋아지고 있어? | Cash from Ops. [IQ_CASH_OPER] | CF N42:P42 |
| 182 | 2차-B | F2B-U2-03 | include | direct_cell | Coldplay는 재고 부담이 최근 줄어드는 추세야? | Inventory [IQ_INVENTORY] | BS N26:P26 |
| 183 | 2차-B | F2B-U2-04 | include | direct_cell | Coldplay가 영업으로 벌어들이는 현금은 안정적으로 늘고 있어? | Cash from Ops. [IQ_CASH_OPER] | CF N42:P42 |
| 184 | 2차-B | F2B-U2-05 | include | direct_cell | DH Innovation의 최근 3년 총차입금(Total Debt)은 줄었지만 순차입부채(Net Debt)는 증가했는가? | Total Debt [IQ_TOTAL_DEBT]; Net Debt [IQ_NET_DEBT] | BS N130:P130, N133:P133 |
| 185 | 2차-B | F2B-U2-06 | include | direct_cell | DH Innovation의 총매출 하락은 최근에도 계속 이어지고 있어? | Total Revenue [IQ_TOTAL_REV] | IS N23:P23 |
| 186 | 2차-B | F2B-U3-01 | include | derived_formula | 기업 A는 지금 가진 현금성 자산으로 차입금을 전부 갚고도 남아? | Total Cash & ST Investments [IQ_CASH_ST_INVEST]; Total Debt [IQ_TOTAL_DEBT] | BS P19, P130 |
| 187 | 2차-B | F2B-U3-02 | include | direct_cell | Coldplay는 자산에서 부채를 전부 빼면 얼마나 남아? | Total Assets [IQ_TOTAL_ASSETS]; Total Liabilities [IQ_TOTAL_LIAB]; Total Common Equity [IQ_TOTAL_COMMON_EQUITY] | BS P50, P74, P88 |
| 188 | 2차-B | F2B-U3-03 | include | derived_formula | Coldplay가 2025년에 영업으로 번 현금만으로 투자활동 전체를 감당했어? | Cash from Ops. [IQ_CASH_OPER]; Cash from Investing [IQ_CASH_INVEST] | CF P42, P53 |
| 189 | 2차-B | F2B-U3-04 | include | direct_cell | DH Innovation은 매출총이익을 내고도 영업에서는 적자인 거야? | Gross Profit [IQ_GP]; Operating Income [IQ_OPER_INC] | IS P29, P43 |
| 190 | 2차-B | F2B-U3-05 | include | direct_cell | 기업 A, Coldplay, DH Innovation 세 회사 중 총매출이 가장 큰 회사가 EBITDA 수익성도 가장 좋아? | Total Revenue [IQ_TOTAL_REV]; EBITDA Margin % [IQ_EBITDA] | 각 사 KS I33, I40 |
| 191 | 2차-B | F2B-U3-06 | include | direct_cell | 기업 A, Coldplay, DH Innovation 세 회사 중 가진 현금성 자산에 비해 차입금이 가장 부담스러운 곳은 어디야? | Total Cash & ST Investments [IQ_CASH_ST_INVEST]; Total Debt [IQ_TOTAL_DEBT]; Net Debt [IQ_NET_DEBT] | 각 사 BS P19, P130, P133 |
| 192 | 2차-B | F2B-U4-01 | include | derived_formula | 기업 A는 총매출 100달러당 EBITDA를 얼마나 남겨? | EBITDA [IQ_EBITDA]; Total Revenue [IQ_TOTAL_REV] | IS P101÷P23 = 3,600÷18,000 |
| 193 | 2차-B | F2B-U4-02 | include | derived_formula | 기업 A가 2025년에 영업으로 번 현금에서 설비투자까지 하고 나면 얼마가 남아? | Cash from Ops. [IQ_CASH_OPER]; Capital Expenditure [IQ_CAPEX] | CF P42+P44 = 2,844+(-1,386) |
| 194 | 2차-B | F2B-U4-03 | include | derived_formula | Coldplay의 차입금에서 현금성 자산을 빼면 실제 부담은 얼마야? | Total Debt [IQ_TOTAL_DEBT]; Total Cash & ST Investments [IQ_CASH_ST_INVEST] | BS P130-P19 = 2,124-2,478 |
| 195 | 2차-B | F2B-U4-04 | include | derived_formula | Coldplay의 총매출(Total Revenue)은 2024년보다 2025년에 얼마나 증가했는가? | Total Revenue [IQ_TOTAL_REV] | IS Cell O23:P23; formula=(P23-O23), (P23/O23-1) |
| 196 | 2차-B | F2B-U4-05 | include | derived_formula | DH Innovation은 단기 자산으로 단기 부채를 몇 배 정도 감당할 수 있어? | Total Current Assets [IQ_TOTAL_CA]; Total Current Liabilities [IQ_TOTAL_CL] | BS P34÷P64 = 5,270÷4,092 |
| 197 | 2차-B | F2B-U4-06 | include | derived_formula | 기업 A, Coldplay, DH Innovation 중 현재 Net Debt/EBITDA가 가장 큰 회사는 어디인가? | Net Debt [IQ_NET_DEBT]; EBITDA [IQ_EBITDA] | 각 회사 Net Debt 및 EBITDA; formula=Net Debt/EBITDA |
| 198 | 2차-B | F2B-U5-01 | include | derived_formula | 기업 A는 영업현금을 많이 벌었는데 왜 현금 증가액은 313에 그쳤어? | Cash from Ops. [IQ_CASH_OPER]; Cash from Investing [IQ_CASH_INVEST]; Cash from Financing [IQ_CASH_FINAN]; Net Change in Cash [IQ_CASH_NET_CHANGE] | CF P42, P53, P74, P78 |
| 199 | 2차-B | F2B-U5-02 | include | direct_cell | Coldplay의 최근 3년 영업현금흐름 증가가 재고 감소만으로 설명되는지 판단해줘. | Inventory [IQ_INVENTORY]; Cash from Ops. [IQ_CASH_OPER] | BS N:P26, CF N:P42 |
| 200 | 2차-B | F2B-U5-03 | include | derived_formula | Coldplay의 최근 실적은 안정적인 질적 개선으로 볼 수 있어? | Total Revenue [IQ_TOTAL_REV]; EBITDA [IQ_EBITDA]; Inventory [IQ_INVENTORY]; Cash from Ops. [IQ_CASH_OPER]; Levered Free Cash Flow [IQ_LEVERED_FCF] | IS N:P23·101, BS N:P26, CF N:P42·85 |
| 201 | 2차-B | F2B-U5-04 | include | derived_formula | DH Innovation은 잠깐 실적이 안 좋은 거야, 아니면 상태가 계속 나빠지고 있는 거야? | Total Revenue [IQ_TOTAL_REV]; Operating Income [IQ_OPER_INC]; Net Debt [IQ_NET_DEBT]; Cash from Ops. [IQ_CASH_OPER] | IS N:P23·43, BS N:P133, CF N:P42 |
| 202 | 2차-B | F2B-U5-05 | include | derived_formula | DH Innovation이 현재 차입금을 감당하기 부담스러운 수준이라고 봐도 돼? | Total Cash & ST Investments [IQ_CASH_ST_INVEST]; Total Common Equity [IQ_TOTAL_COMMON_EQUITY]; Total Debt [IQ_TOTAL_DEBT]; Net Debt [IQ_NET_DEBT]; EBITDA [IQ_EBITDA]; Cash from Ops. [IQ_CASH_OPER] | BS P19·P88·P130·P133, IS P101, CF P42 |
| 203 | 2차-B | F2B-U5-06 | include | derived_formula | 기업 A, Coldplay, DH Innovation 세 회사 중 재무적으로 가장 안정적인 회사와 가장 우려되는 회사는 어디야? | Total Revenue [IQ_TOTAL_REV]; Total Revenues, 1 Year Growth (%) [IQ_TOTAL_REV_1YR_ANN_GROWTH]; Gross Profit [IQ_GP]; Gross Profit Margin % [IQ_GP]; EBITDA [IQ_EBITDA]; EBITDA Margin % [IQ_EBITDA]; EBIT [IQ_EBIT]; EBIT Margin % [IQ_EBIT]; Earnings from Cont. Ops. [IQ_EARNINGS_CONT_OPS]; Earnings from Cont. Ops. Margin % [IQ_EARNINGS_CONT_OPS]; Net Income [IQ_NET_INC]; Net Income Margin % [IQ_NET_INC]; Total Cash & ST Investments [IQ_CASH_ST_INVEST]; Total Debt [IQ_TOTAL_DEBT]; Net Debt [IQ_NET_DEBT]; Cash from Ops. [IQ_CASH_OPER]; Levered Free Cash Flow [IQ_LEVERED_FCF] | 각 사 KS I33:I49, BS P19·P130·P133, CF P42·P85 |
| 204 | 2차-B | F2B-U6-01 | include | direct_cell | 기업 A의 2025년 총매출과 성장률 대비 2026년 추정 총매출 성장세가 이어지는가? | Total Revenue [IQ_TOTAL_REV]; Total Revenues, 1 Year Growth (%) [IQ_TOTAL_REV_1YR_ANN_GROWTH] | 2025 KS I33·I34, 2026E KS N33·N34 |
| 205 | 2차-B | F2B-U6-02 | include | derived_formula | 기업 A의 EBIT 마진은 2025년보다 2026년 추정치에서 개선되는가? | EBIT Margin % [IQ_EBIT] | 2025 KS I43, 2026E KS N43 |
| 206 | 2차-B | F2B-U6-03 | include | derived_formula | Coldplay 내년 총매출은 올해보다 얼마나 더 나올 것으로 예상돼? | Total Revenue [IQ_TOTAL_REV]; Total Revenues, 1 Year Growth (%) [IQ_TOTAL_REV_1YR_ANN_GROWTH] | 2025 KS I33, 2026E KS N33·N34 |
| 207 | 2차-B | F2B-U6-04 | include | derived_formula | Coldplay 주당이익은 내년에 얼마나 좋아질 것으로 보여? | Diluted EPS Excl. Extra Items [IQ_DILUT_EPS_BEFORE_EXTRA] | 2025 KS I51, 2026E KS N51 |
| 208 | 2차-B | F2B-U6-05 | include | direct_cell | DH Innovation은 2026년 추정 EBIT 마진 기준으로 적자에서 벗어날 수 있는가? | EBIT Margin % [IQ_EBIT] | 2025 KS I43, 2026E~2028E KS N:P43 |
| 209 | 2차-B | F2B-U6-06 | include | direct_cell | DH Innovation의 2025년 및 2026~2028년 추정 순이익률을 보면 전망 기간 안에 흑자 전환하는가? | Net Income Margin % [IQ_NET_INC] | 2025 KS I49, 2026E~2028E KS N:P49 |

## 산출물 무결성

- corrected JSON SHA-256: `a92e838c10769f2caa2bd9dc0dfa6fccaaaec9d0cf3dc446e5c05bf3c7e3bd26`
- quality audit JSON SHA-256: `b7e49f50d8e2df131015ddcbdad169e15b45e33d889d4348b21110eb28485885`
