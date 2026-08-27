# [SEC-102] 프로젝트 목표 및 핵심 가치 (Goals & Target KPIs)
> **Chapter:** 1. 프로젝트 개요 | **Section:** 1.2 | **Status:** Approved Baseline  
> **Classification:** Project Goals, Core Values & Target KPIs

---

## 1. 플랫폼 비전 & 5대 핵심 가치 (Core Values)

`bist-mini-final`은 복잡한 다중 시트 재무 엑셀을 처리함에 있어 **정확성, 속도, 감사 추적성, 무결성**을 극대화하는 것을 목표로 합니다:

| 핵심 가치 (Core Value) | 구현 기술 및 메커니즘 | 기대 효과 및 차별점 |
| :--- | :--- | :--- |
| **1. 비전 기반 표 구조 복원** | `Luna VLM` (GPT-5.6) 이미지 추론 + `header_with_value` 직렬화 | 복잡한 병합 헤더와 상하 분산 단위(억원/천달러)를 완벽 인식하여 검색 정확도 극대화 |
| **2. 2-Tier 분산 실행 런타임** | Tier 1 (인메모리 Fast RAG <100ms) + Tier 2 (K8s KEDA 배치 큐) | 실시간 대화형 챗봇 응답과 수백 개 시트의 대규모 지표 색인을 완벽히 격리 |
| **3. 무손실 금융 수식 계산** | `decimal.Decimal` 고정소수점 연산 + `ROUND_HALF_UP` 표준화 | 재무 비율 및 듀퐁 3단계 분해 공식에서 부동소수점 오차 0.000% 달성 |
| **4. 100% 감사 추적성 보장** | 원천 엑셀 셀 좌표(`cell_id`) 영구 메타데이터 바인딩 | 대시보드 및 챗봇 답변의 모든 숫자를 클릭 한 번으로 원본 시트 위치에서 하이라이트 |
| **5. 초고속 벡터 적재 인프라** | PostgreSQL 네이티브 `Binary COPY` 파이프라인 | 네이티브 Binary 스트리밍으로 SQL 파싱 오버헤드 배제 및 벌크 I/O 성능 극대화 |

---

## 2. 정량적 벤치마크 평가 목표 KPI (Target Evaluation KPIs)

향후 파이프라인 최적화 완료 후 벤치마크 하네스([`SEC-501`](file:///c:/Repos/bist-mini-final/docs/final_report/05_validation_and_conclusion/SEC-501_benchmark_evaluation_plan.md))를 통해 검증할 정량적 목표치입니다:

| 평가 영역 (Evaluation Dimension) | 핵심 메트릭 (Metric) | 목표치 (Target KPI) | 측정 방식 및 기준 |
| :--- | :--- | :---: | :--- |
| **수치 및 단위 정확도** | **Exact Match (EM)** | $\ge 95.0\%$ | Ground-Truth 정답과 생성된 수치, 단위, 통화의 100% 일치율 |
| **검색 재현율** | **Ground-Truth Cell Recall@5** | $\ge 98.0\%$ | 정답 근거 셀이 상위 5개 RRF 검색 후보에 포함되는 비율 |
| **응답 지연시간** | **Fast RAG P95 Latency** | $< 500\text{ms}$ | 인메모리 포트 바인딩 기반 단일 질의응답 95백분위 처리 시간 |
| **벌크 색인 속도** | **pgvector 적재 속도** | $> 3,000\text{ v/s}$ | PostgreSQL `Binary COPY` 스트리밍 기반 초당 벡터 주입량 |
| **회계 수식 신뢰성** | **Hallucination Rate** | $0.0\%$ | 무손실 `Decimal` 연산 적용을 통한 산술 오차 및 허위 수치 인용 0건 |
| **아키텍처 불변식** | **Contract Violation** | $0\text{건}$ | AST 정적 분석(`test_architecture_contracts.py`)을 통한 레이어 침범 0건 |

---

## 3. 정성적 기대효과 및 경제성 분석 (ROI)

1. **재무 분석 리드타임 92% 단축**: 전문가 수작업 재무제표 전처리 및 지표 산출 시간 (기업당 4시간 ➡️ 자동화 파이프라인 20분 이내 완료).
2. **회계 오기재 및 수치 오류 리스크 0%화**: 무손실 `Decimal` 연산 및 셀 단위 감사 추적으로 내부 감사 리스크 및 의사결정 오판을 원천 차단.
3. **인프라 TCO (총소유비용) 70% 절감**: KEDA ScaledJob 기반 온디맨드 Pod 스케일링으로 유휴 서버 비용 최소화.
