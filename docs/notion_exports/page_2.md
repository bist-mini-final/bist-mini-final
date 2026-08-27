[목차]
## 1. 역할 분배
| 이름 | MVP 1차 역할 |
| --- | --- |
| 전명준 | 정답셋 구성, 범용 LLM 답변셋 생성 |
| 김정원 | 시맨틱 쿼리 매칭 라우팅 파이프라인, 코드 기반 CLI 방법론, 하이브리드 BM25 + Dense RRF 기능, 쿼리 분해 |
| 권혁준 | 엑셀 데이터 구조화 추출, FRTR 방법론 |
| 김지환 | PixelRAG 방법론, LangGraph Orchestrator 전체 파이프라인 틀 구축 |
---
## 2. 평가셋 데이터 품질 개선 및 재구축 계획
1차 평가셋으로 러프하게 파이프라인을 돌려본 결과, 모델의 실제 성능이나 검색 정확도와 무관하게 평가셋 데이터 자체의 정의 모호성, 엄격한 단일 셀 매칭 방식, 그리고 특정 지표 및 유형 편중 등 다수의 한계점이 확인되었습니다. 이를 종합적으로 해결하고 평가의 객관성과 신뢰성을 확보하기 위해 현재 전면적인 평가셋 재구축 및 파이프라인 고도화를 추진하고 있습니다.
### 2-1. 1차 파이프라인 검증 결과 주요 이슈 및 한계
- 용어 혼선으로 인한 오답 처리: '총부채'나 '현금성 자산' 같은 단일 한국어 명칭이 원본 데이터의 서로 다른 회계 지표(Total\ Liabilities vs. Total\ Debt, Cash\ \&\ Equivalents vs. Cash\ \&\ ST\ Investments)를 혼용하여 지칭하고 있어, 모델이 올바른 지표를 선택하고도 오답 처리되는 문제 발생
- 단일 Cell ID 매칭의 한계: 수치와 의미가 완전히 검증된 대체 출처(예: 손익계산서와 Key Stats 간의 동일 매출/이익 셀)임에도 기존 평가셋에 등록된 단일 기준 셀과 일치하지 않아 PARTIAL 처리됨
- 상태값 및 부가 조건 누락: NA 같은 결측치나 질문에 명시되지 않은 부가 설명·기준일 조건이 필수로 평가되어 불필요한 감점 유발
- 유형 및 지표 편중: 특정 재무 지표와 단순 단일 지표 조회 유형에 질문이 과도하게 집중되어 모델의 전반적인 다차원 추론 능력을 검증하는 데 한계 존재
### 2.2 쿼리 유형 정의 및 재설정 (6대 유형)
모델의 입체적 성능 검증을 위해 쿼리 유형을 전면 재정비하였으며, 핵심 6대 유형과 세부 정의는 다음과 같습니다.
| 유형 | 분류 | 설명 및 대표 질문 예시 |
| --- | --- | --- |
| [유형 1] | 단일 지표 조회 | 특정 시점 또는 기간의 단일 재무 항목을 정확히 추출하는 쿼리
• 예시: "IBM의 LTM 기준 시가총액과 TEV는 각각 얼마인가?" |
| [유형 2] | 기간 및 추세 분석 | 다년간의 시계열 데이터를 바탕으로 성장률 및 추세를 파악하는 쿼리
• 예시: "2021년부터 2025년까지 IBM의 매출액 CAGR 및 연도별 YoY는?" |
| [유형 3] | 복수 지표 조회 및 비교 | 상호 연관된 여러 지표를 동시에 조회하고 비교하는 쿼리
• 예시: "IBM의 자본구조와 밸류에이션 멀티플을 함께 정리해줘." |
| [유형 4] | 재무 계산 | 재무제표 데이터를 활용해 특정 비율이나 지표를 직접 산출하는 쿼리
• 예시: "Key Stats의 TEV가 총부채 및 현금 수치와 정합성을 이루는가?" |
| [유형 5] | 심층 추론/원인 분석 | 재무 지표 간의 괴리나 특이 변동에 대한 원인을 논리적으로 추론하는 쿼리
• 예시: "현재 TEV/EBITDA 멀티플이 IBM의 수익성과 성장 전망 대비 적정한가?" |
| [유형 6] | 지표 전망 및 예측 | 과거 추세를 기반으로 향후 실적이나 지표를 추정하는 쿼리
• 예시: "최근 추세 유지 시 2026년 Total Revenue는?" |
### 2.3 핵심 개선 방안 및 데이터 밸런싱 계획
확인된 데이터 정의 이슈를 해소하고 균형 잡힌 평가셋을 구축하기 위해 적용 중인 세부 작업 계획은 다음과 같습니다.
- 원천 지표 명칭 및 용어 정비 (P0)
- 대체 출처(Alternative Cell Sets) 및 Fact Registry 도입
- 유형별 균등 배분 및 커버리지 다변화
---
## 3. RAG 방법론 조사
### 3-1. 코드 실행 기반 RAG
LLM이 직접 파이썬 pandas 코드를 작성하고 execution 샌드박스에서 실행하여 정제된 DataFrame(21개)을 대상으로 수치를 직접 연산·조회하는 대안적 방식입니다.
- 장점: 검색 단계가 없으므로 인덱싱 미흡이나 검색 실패 자체가 없으며, pandas 연산 엔진으로 집계·정렬·그룹화 연산에서 높은 정확도를 보입니다.
- 단점: 프롬프트 생성 → 코드 작성 → 런타임 실행 → Self-Correction 루프로 최소 2회 이상의 LLM 호출이 발생하여 응답 속도가 가장 느리고, 시계열 구간 선택 시 pandas 인덱싱 오류가 발생할 위험이 높습니다.
---
### 3-2. 사전 검증 — 데이터 성격별 적합도 비교 (86문항, 649문서 코퍼스)
정형·반정형·비정형이 섞인 실제 데이터 특성에 맞춰 5개 방법론—직렬화 임베딩 검색, 코드 실행(pandas), 계층적 라우터, 하이브리드 검색(RRF), 쿼리 분해—을 동일 코퍼스·동일 답변 프롬프트 조건으로 통제 비교하는 사전 검증을 진행했습니다. 성능 차이가 순수하게 검색 방식의 차이에서만 오도록 변인을 통제했습니다.
코퍼스 정비: 정답셋 셀 주소가 실제 파일과 1행/1열 어긋나는 문제를 발견·보정하고, 누락된 IS/BS/CF 시트와 Key_Stats 하단 블록(시가총액·멀티플)을 추가해 코퍼스를 377건→649건으로 확장했습니다. 검색 실패 원인 중 하나로 보일러플레이트 텍스트에 의한 신호 희석 문제도 진단·수정했습니다.
데이터 성격별 적합도
| 데이터 성격 | 예시 | 직렬화 임베딩 | 코드실행 | 계층적 라우터 | 하이브리드(RRF) | 쿼리분해 |
| --- | --- | --- | --- | --- | --- | --- |
| 정형 재무제표 (계정명·수치) | "IBM LTM 총자산은?" | 보통 | 강함 | 보통 | 강함 | 보통 |
| 집계·전체스캔 (최대값·정렬·평균) | "임직원 최다 비상장사는?" | 약함 | 강함 | 약함 | 약함 | 약함 |
| 자연어 텍스트 (뉴스·설명) | "제품 관련 발표 알려줘" | 강함 | 보통 | 보통 | 강함 | 보통 |
| 고유명사·ID (거래ID·인수자명) | "Emirates NBD가 인수한 회사는?" | 보통 | 강함 | 보통 | 강함 | 보통 |
| 다중대상 비교 (기업간 지표비교) | "IBM과 비스텔리전스 성장률 비교" | 약함 | 강함 | 보통 | 보통 | 강함 |
유형별 완전정답률 (86문항, 직렬화·코드실행·하이브리드 3종)
| 방법론 | 유형1 단일조회 | 유형2 추세 | 유형3 복수지표 | 유형4 계산 | 유형5 추론 | 유형6 전망 |
| --- | --- | --- | --- | --- | --- | --- |
| 직렬화 임베딩 검색 | 13/24 (54%) | 6/15 (40%) | 7/14 (50%) | 10/22 (45%) | 1/5 (20%) | 1/6 (17%) |
| 코드 실행(pandas) | 17/24 (71%) | 3/15 (20%) | 12/14 (86%) | 15/22 (68%) | 0/5 (0%) | 1/6 (17%) |
| 하이브리드 검색(RRF) | 17/24 (71%) | 11/15 (73%) | 7/14 (50%) | 14/22 (64%) | 0/5 (0%) | 2/6 (33%) |
시사점: 정형 재무제표·집계 질문에서는 코드 실행 방식과 하이브리드 검색이 일관되게 우세를 보였습니다. 다만 유형 5(심층추론)·유형 6(전망)은 이 사전 검증 단계에서도 전 방법론 공통으로 취약했습니다(코드실행 유형5 0%, 직렬화 임베딩 유형6 17%) 
---
### 3-3. PixelRAG
개요 및 초기 가설
- 가설: “복잡한 엑셀 스프레드시트를 이미지 형태 그대로 임베딩하면, 표의 2차원 공간 구조를 손실 없이 보존하여 검색할 수 있을 것이다.”
한계점
- 내용 희석: 시트 내 데이터 양이 많아질수록 세부 수치 내용이 벡터 공간에서 희석됩니다.
- 거시적 구조 위주 검색: 픽셀 임베딩이 표의 크기·외형 같은 기하 형태만 뛰어난 성능으로 검색하는 현상이 발생했습니다.
- 고비용 및 환각 문제: 높은 비전 토큰 비용과 미세 폰트 수치 판독 과정의 환각 문제가 확인되었습니다.
---
### 3-4. FRTR 방법론 ← 최종 채택
전환 계기 및 핵심 아이디어
- PixelRAG의 한계를 극복하기 위해 엑셀 시트 내부의 데이터와 헤더 간 명확한 분류 및 상하/좌우 헤더와 데이터 간의 부모-자식 계층 관계 매핑이 필수적이라는 결론에 도달했습니다.
- 엑셀 구조 분석을 통해 헤더와 데이터 밸류 간 관계를 도출하고, 약속된 구조화 텍스트 포맷으로 정제하여 임베딩하는 방식을 고안했습니다.
성과 및 채택 이유
- 비용 절감 및 속도 향상: 비전 타일 대신 정제된 텍스트를 임베딩하여 비전 토큰 비용을 획기적으로 절감하고 인퍼런스 속도를 향상시켰습니다.
- 검색 및 답변 정확도 극대화: 픽셀 희석 없이 헤더-데이터 간 계층 관계가 명확히 인코딩되어 데이터 규모가 커져도 정밀한 수치 검색이 가능합니다.
---
### 3-5. 방법론 비교
| 비교 항목 | PixelRAG | FRTR 방법론 | 코드 실행 기반 RAG |
| --- | --- | --- | --- |
| 기반 데이터 | 고해상도 이미지 타일 | 헤더-데이터 계층 정제 셀 텍스트 | pandas DataFrame (21개) |
| 핵심 기술 | Qwen3-VL 임베딩 + FAISS + VLM | GPT-5.6 Luna Full-Sheet VLM + BM25/Dense RRF | LLM + Code Generation + Execution |
| 검색 특성 | 픽셀 희석 → 외형 위주 | 부모-자식 헤더 매핑 → 정밀 수치 검색 | 검색 단계 없음 (직접 연산) |
| 수치 연산 정확도 | 보통 (환각 위험) | 양호 (Context 복원 후 추론) | 최상 (pandas 직접 연산) |
| 처리 속도 / 비용 | 느림 / 높은 비전 토큰 | 빠름 / 저비용 고효율 | 가장 느림 (다단계 루프) |
| 답변 근거 추적성 | 보통 (픽셀 타일 영역) | 최상 (Sheet명 + Cell ID 단위) | 보통 (실행 코드 + console) |
결론: FRTR 방법론이 계산 비용 최소화, 인퍼런스 속도 향상, 정밀 수치 검색 정확도 극대화를 동시에 달성하여 최종 메인 RAG 파이프라인으로 채택했습니다.
---
## 4. 시스템 아키텍처
### 4-1. 전체 시스템 구성
flowchart TB
    subgraph Client ["Client Layer"]
        UI["React Flow Workbench"]
    end

    subgraph Server ["Backend Server Layer"]
        Engine["FastAPI DAG Engine"]
        Registry["Module Registry (실행 모듈들)"]
    end

    subgraph Storage ["Data & Storage Layer"]
        Data[("Data")]
    end

    subgraph External ["External API"]
        OpenAI["OpenAI API"]
    end

    UI <-->|REST API| Engine
    Engine <--> Registry
    Engine <--> Data
    Registry <--> OpenAI

사용자는 React Flow 캔버스에서 노드와 엣지를 시각적으로 조립하고, 백엔드는 이를 위상 정렬하여 결정론적으로 실행합니다.
---
### 4-2. 인덱싱 파이프라인 (Offline)
엑셀 워크북 원본에서 검색 가능한 벡터 인덱스를 사전 구축하는 파이프라인입니다.
flowchart LR
    subgraph Offline ["인덱싱 파이프라인 (Offline)"]
        N1["processed_file_selector\n(파일 검증 & 해시 계산)"] -->|output| N2["luna_vlm_detector\n(GPT5.6 Luna 전체 시트 파싱)"]
        N2 -->|output| N3["cell_text_embedder\n(4-Field 직렬화 & 벡터화)"]
    end
① processed_file_selector
- 분석 대상 엑셀 파일(SPG_Company_KeyStats_v3.xlsm)을 선택하고 SHA-256 해시를 계산하여 파일 변조 여부를 검증합니다.
② luna_vlm_structure_detector (GPT-5.6 Luna)
- 입력: 시트 전체 typed overlay 이미지 + 전체 셀 좌표 컨텍스트(compact tuple)
- 역할: 타일 분할 없이 시트 전체를 한 번에 분석하여 모든 표의 5개 영역(excel_range, title_range, column_header_range, row_header_range, data_range)을 Structured Output(JSON)으로 반환
- 설계 인사이트:
// luna_vlm_structure_detector 출력 예시
{
  "tables": [{
    "excel_range":         "B3:K45",
    "title_range":         "B3:K4",
    "column_header_range": "B5:K7",
    "row_header_range":    "B8:C45",
    "data_range":          "D8:K45"
  }]
}
③ cell_text_embedder (text-embedding-3-large, batch_size=64)
- 입력: luna_vlm_structure_detector의 표 구조 정보
- 역할: 각 데이터 셀에 부모 헤더 경로를 결합한 FRTR 4-Field v포맷으로 직렬화하고, text-embedding-3-large로 벡터화하여 인덱스를 저장
- 직렬화 포맷:
header_only:       Sheet: KeyStats | Row Header: Total Revenue | Column Header: FY-2 | Cell Value: ?
header_with_value: Sheet: KeyStats | Row Header: Total Revenue | Column Header: FY-2 | Cell Value: 61860
- 헤더 계층 조합 폭발 생성: ["Operating Expenses", "R&D"] 같은 다중 계층 헤더에 대해 완전 체인·개별·접두·접미 경로의 모든 조합을 생성하여 인덱싱, 사용자가 어떤 세분화 수준으로 질의해도 매칭 가능하게 처리
- 기간 헤더 LTM 기본값: 열 헤더에 기간 정보가 없는 셀은 LTM을 자동 부여하여 검색 누락 방지
---
### 4-3. 쿼리 파이프라인 (Online, system_architecture.json 기준)
사용자 질문이 들어왔을 때 실시간으로 실행되는 파이프라인입니다.
flowchart TB
    subgraph Online ["쿼리 파이프라인 (Online Execution Flow)"]
        Q_IN["query_input\n(사용자 한국어 질문)"]

        Q_IN -->|question_text| DEC["decomposer\n(GPT 서브쿼리 분해)"]
        DEC -->|output| INSP1["json_inspector 1\n(서브쿼리 목록 검수)"]

        INSP1 -->|output| EMB["embedder\n(text-embedding-3-large)"]
        INSP1 -->|query_input| BM25["bm25_retriever\nk1=1.5, b=0.75, top_k=1000"]

        EMB -->|query_input| DENSE["dense_retriever\ntop_k=1000"]

        %% Inputs from Indexing Pipeline
        LUNA_DOC[("luna_vlm\n(FRTR 구조화 문서)")] -.->|document_input| BM25
        LUNA_DOC -.->|document_input| CTX
        EMB_IDX[("cell_text_embedder\n(사전 벡터 인덱스)")] -.->|index_input| DENSE

        BM25 -->|bm25_result| RRF["rrf_fusion\nrrf_k=60, ratio_penalty=0.4"]
        DENSE -->|dense_result| RRF

        RRF -->|retrieval_json| CTX["context\n(±3행/열 2D 인접 영역 복원)"]

        CTX -->|context_json| READ["reader\n(GPT-5.6 Luna 수치 근거 작성)"]
        Q_IN -->|question_text| READ

        READ -->|answer_json| INSP2["json_inspector 2\n(최종 답변 검수)"]
    end
① query_input (threshold=0.65)
- 사용자 한국어 질문을 수신하고 question_text 출력을 두 경로(decomposer, reader)에 동시에 공급합니다.
② decomposer (gpt-5.6-luna, preset=luna_decomposer)
- 역할: 복잡한 한국어 재무 질문을 벡터 DB의 단일 셀 임베딩과 매칭 가능한 원자적 서브쿼리 배열로 분해
- FRTR 포맷 강제: 모든 서브쿼리는 "Sheet: ? | Row Header: {metric} | Column Header: {period} | Cell Value: ?" 포맷으로 생성
- 원자 셀 원칙: CAGR·YoY·추세 질문은 각 연도별 개별 서브쿼리로 분해 (범위 표현식 금지)
- 도메인 개념 번역: 한국어 재무 개념을 공식 영문 헤더 표현으로 변환 (TEV = Total Enterprise Value = Enterprise Value)
- 기간 동의어 확장: LTM·FY0·FY2025·2025-12-31을 모두 별도 서브쿼리로 생성
예시 입력: "IBM의 LTM 기준 시가총액과 TEV는 각각 얼마인가?"

예시 출력:
[
  "Sheet: ? | Row Header: Market Capitalization | Column Header: LTM | Cell Value: ?",
  "Sheet: ? | Row Header: Market Cap | Column Header: LTM | Cell Value: ?",
  "Sheet: ? | Row Header: Equity Market Value | Column Header: LTM | Cell Value: ?",
  "Sheet: ? | Row Header: Market Capitalization | Column Header: FY0 | Cell Value: ?",
  "Sheet: ? | Row Header: Total Enterprise Value | Column Header: LTM | Cell Value: ?",
  "Sheet: ? | Row Header: Enterprise Value | Column Header: LTM | Cell Value: ?",
  "Sheet: ? | Row Header: TEV | Column Header: LTM | Cell Value: ?",
  ...
]
③ json_inspector
- 분해된 서브쿼리 목록을 육안으로 확인할 수 있는 디버깅용 뷰어 노드입니다.
- 출력은 embedder와 bm25_retriever에 동시에 전달됩니다.
④ embedder (text-embedding-3-large)
- 분해된 서브쿼리 배열을 text-embedding-3-large로 벡터화합니다.
⑤ bm25_retriever (k1=1.5, b=0.75, top_k=1000)
- 두 입력을 받습니다:
- BM25 알고리즘으로 서브쿼리 배열과 FRTR 문서 간 키워드 기반 검색을 수행합니다.
- k1=1.5는 단어 빈도의 포화도를, b=0.75는 문서 길이 정규화를 제어합니다.
⑥ dense_retriever (top_k=1000)
- 두 입력을 받습니다:
- 코사인 유사도 기반 의미 검색을 수행합니다.
⑦ rrf_fusion (rrf_k=60, top_k=100, ratio_penalty=0.4)
- BM25 결과(bm25_result)와 Dense 결과(dense_result)를 RRF 공식으로 통합합니다:
[equation]
- 비율 지표 패널티: 절대값 질문에 EBITDA Margin %, Growth (%) 같은 비율 행이 오검색되는 현상을 방지하기 위해, 쿼리에 비율 의도가 없을 때 비율 행에 ratio_penalty=0.4 감점을 부여합니다.
- 최종 상위 100개 후보를 retrieval_json으로 출력합니다.
⑧ context (adjacent_radius=3, max_blocks=500)
- 두 입력을 받습니다:
- 검색된 셀을 기준으로 ±3행/열 인접 영역을 2D 확장하여 행 단위 컨텍스트 블록을 구성합니다.
- 같은 행의 모든 기간 값을 함께 복원하여 LLM이 시계열 비교·계산을 정확하게 수행할 수 있게 합니다.
예시 컨텍스트 블록:
Sheet: Income_Statement | Row Header: Total Revenue
  [FY2021 (IS Cell C12)]: 57351 |
  [FY2022 (IS Cell D12)]: 60530 |
  [FY2023 (IS Cell E12)]: 61860 |
  [FY2024 (IS Cell F12)]: 62753 |
  [LTM    (IS Cell G12)]: 67535
⑨ reader (gpt-5.6-luna, preset=luna_reader)
- 두 입력을 받습니다:
- 공급된 셀 컨텍스트만을 근거로 한국어로 답변을 생성합니다.
- Cell ID 인용 강제: 모든 수치 주장에 [KS Cell E60] 형태의 Cell ID를 명시하여 원본 엑셀 검증 가능성을 보장합니다.
Reader System Prompt 핵심 규칙:
1. State exact values without inventing missing facts.
2. Cite the supporting Cell ID for every numeric claim, e.g. [KS Cell E60].
3. For calculations, show concise arithmetic steps.
4. Preserve source values such as NA and NM.
5. If the context is insufficient, explicitly say which fact is missing.
6. Respond in Korean unless the user requests another language.
⑩ json_inspector (최종 출력)
- reader의 answer_json을 육안으로 확인할 수 있는 최종 출력 뷰어 노드입니다.
---
## 5. 오케스트레이션 추가 기법 상세
### 5-1. 동의어 자동 확장 (augment_subqueries)
LLM이 동의어를 누락하면 검색 재현율이 떨어지므로, decomposer LLM 응답 이후 결정론적 동의어 자동 확장 단계를 추가했습니다. 재무 메트릭 동의어 그룹과 기간 동의어 그룹의 곱집합을 자동 생성합니다:
METRIC_EQUIVALENT_GROUPS = (
    ("Total Enterprise Value", "Enterprise Value", "TEV"),
    ("Market Capitalization", "Market Cap", "Equity Market Value"),
    ("Total Revenue", "Total Revenues", "Revenue", "Net Sales"),
    ("Operating Income", "EBIT", "Operating Profit"),
    ...
)
PERIOD_EQUIVALENT_GROUPS = (
    ("LTM", "FY0", "FY2025", "2025-12-31"),
    ("FY-1", "FY2024", "2024-12-31"),
    ...
)
### 5-2. 시맨틱 쿼리 매칭 라우팅
사용자 질문을 임베딩하여 미리 라벨링해둔 예시 질문 세트(source/sheet 라벨 520건)와 최근접 이웃 유사도 검색을 수행함으로써 “이 질문에는 어떤 파일/시트/도구를 참조해야 하는가”를 결정하는 라우팅 방식입니다. LLM Function Calling 대비 비용이 적고 일관성이 높으며, 답변 생성 이전 단계(라우팅+검색)를 전부 비LLM으로 구성하는 것을 목표로 설계했습니다.
시맨틱 쿼리 매칭(예시 질문 기반 라우팅)은 시맨틱 캐시(과거 완성 답변 재사용)와 다릅니다. 라우팅은 "어디서 찾을지"만 결정하고 실제 데이터는 만지지 않는 반면, 캐시는 오래되거나 문맥이 다른 과거 답변을 그대로 반환할 위험이 있어 목적 자체가 다릅니다.
5-2-1. 검증 실험: 라우터 2종 × 검색기 5종 (analysis/routing_retrieval_experiment.py)
라우팅과 검색을 독립된 축으로 분리하여, 6개 유형에서 등간격 추출한 35문항을 대상으로 2×5=10개 조합을 통제 비교했습니다. (동일 770개 문서 코퍼스, 동일 답변 모델·temperature=0·프롬프트, k=8)
- 라우터 A (LLM 라우팅): LLM에게 질문을 보여주고 소스를 직접 판단시킴 (호출 2회)
- 라우터 B (시맨틱 예시매칭, 채택안): 질문 임베딩과 예시 520건의 최근접 이웃 라벨을 그대로 사용 (LLM 호출 0회)
- 검색기 5종: Dense, BM25, Hybrid-RRF, 규칙 기반 Multi-query(한·영 지표 동의어 확장 + 복수절 분리 후 RRF), 이웃문맥 확장(Hybrid seed 기준 인접 행 추가)
| 라우터 | 검색기 | 완전정답 | 정답률 | 귀속 LLM 호출 |
| --- | --- | --- | --- | --- |
| LLM | BM25 | 18/35 | 51.4% | 2회 |
| LLM | Multi-query | 17/35 | 48.6% | 2회 |
| 시맨틱 | Multi-query | 17/35 | 48.6% | 1회 |
| 시맨틱 | BM25 | 17/35 | 48.6% | 1회 |
| 시맨틱 | Hybrid-RRF | 12/35 | 34.3% | 1회 |
시맨틱 라우팅은 Dense·Multi-query·Neighbor 검색기에서 LLM 라우팅과 완전정답률이 동일했고, BM25·Hybrid에서 2.9%p 낮았습니다(35문항 중 1문항 차이 수준). 
5-2-2. 86문항 × 3회 반복 검증 (2026-08-11)
시맨틱 라우팅을 고정하고 86문항 × 5검색기 × 3반복, 총 1,290개 답변을 평가하여 신뢰구간을 확인했습니다. 라우팅·검색은 전부 비LLM이며 조합당 LLM 호출은 최종 답변 생성 1회입니다.
| 검색기 | 평균 완전정답률 | 표준편차 | 근거커버리지 |
| --- | --- | --- | --- |
| Multi-query | 67.1% | ±1.3%p | 81.4% |
| BM25 | 58.5% | ±0.7%p | 74.8% |
| Hybrid-RRF | 55.0% | ±0.7%p | 73.5% |
| Neighbor | 32.6% | ±0.0%p | 51.6% |
| Dense | 24.0% | ±0.7%p | 48.4% |
유형 1–4는 Multi-query가 가장 높거나 경쟁력 있는 성능을 보였으나, 유형 5(심층 추론)는 최고 20.0%, 유형 6(전망·예측)은 모든 검색기에서 0.0%로 검색기 교체만으로는 해결되지 않았습니다 — 유형 5는 원인 설명용 이벤트·주석 코퍼스, 유형 6은 공식 레지스트리·결정론적 계산 엔진 보강이 필요하다는 결론입니다. 라우팅 258건 중 129건(50.0%)은 임계값(0.74) 미달로 전체 검색 폴백했으나, 오라우팅은 0건이었습니다.
5-2-3. 라우팅 범위 ablation
시맨틱 라우팅의 predicted sheet를 hard filter(해당 시트만 강제 검색)로 썼을 때와 source 단위로만 제한했을 때를 비교했습니다.
| 검색기 | source-only | strict-sheet | 차이 |
| --- | --- | --- | --- |
| BM25 | 48.6% | 34.3% | +14.3%p |
| Hybrid-RRF | 34.3% | 25.7% | +8.6%p |
| Multi-query | 48.6% | 34.3% | +14.3%p |
| Neighbor | 31.4% | 25.7% | +5.7%p |
single-sheet hard filter는 복수 시트에 근거가 걸쳐 있는 질문의 정답을 검색 후보에서 아예 제거해 성능을 크게 떨어뜨립니다. predicted sheet는 soft boost(가산점) 또는 진단 신호로만 사용해야 한다는 운영 원칙을 확정했습니다.
5-2-4. 라우팅 전용 반복 최적화
문서 검색·답변 생성을 제외하고 라우팅 정확도만 별도로 최적화했습니다. 기존 520개 예시를 템플릿 그룹 단위 5개 시드로 홀드아웃하고, 학습에 쓰지 않은 86개 질문에 표현 변형 4종을 적용한 344건 + OOD 30건(보정 15/최종홀드아웃 15)으로 평가했습니다.
최적화 내용: ① 7개 세부 target을 실제 검색 필터 단위인 3개 source로 통합 ② source별 상위 3개 근거만 집계해 예시 수 불균형 영향 축소 ③ 유형 4–6 포함 독립 예시 30건 보강 ④ 대상 별칭이 명시되면 엔티티 가드로 확정, 없을 때만 유사도 임계값 적용 ⑤ 임계값을 0.60으로 재조정
| 평가셋 | 방법 | 성공률 | 오라우팅 |
| --- | --- | --- | --- |
| 86문항×4변형(344건) | 기존 | 33.1% | 0.0% |
| 86문항×4변형(344건) | 최적화 | 98.0% | 0.0% |
| OOD 최종 15건 | 최적화 | 100.0% 안전 폴백 | 0.0% |
표현 변형(오탈자, 구어체, 축약 등)에 대한 라우팅 강건성을 33.1%→98.0%로 끌어올렸고, 전 구간에서 오라우팅 0건을 유지했습니다. 다만 100%가 나온 유형도 표본이 작고 대부분 IBM 질문이라 신규 기업·다중 도메인 질문을 지속 보강할 예정입니다.
---
## 6. 오케스트레이션 구현
파이프라인 흐름 시연 예정
[image]
---
## 7. 2차 수정 평가셋 기반 평가 수행 및 분석
평가셋 데이터가 아직 완전히 정비되지 않은 상태(TEV 관련 단순 문항의 과도한 집중 및 '총부채' 등 용어 모호성으로 인한 오판 유발)였기 때문에, 본 분석에서는 모델의 정답률 대신 파이프라인 실행에 소모된 토큰 사용량과 비용 효율성에 초점을 맞춰 살펴봅니다.
### 7.1 전체 종합 토큰 및 비용 통계 (Total 87 Questions)
- 실행 환경: GPT-5.6 Luna (gpt-5.6-luna) Dense Retriever + Reranker + Hybrid Reader 파이프라인
- 평가 대상: 선별 87개 문항 (유형 1 ~ 유형 6 전체)
- 총 토큰 사용량: 1,492,109 토큰 (입력: 1,468,989 / 출력: 23,120, 문항당 평균: 17,151 토큰)
- 추정 실행 비용 (단가: Input $0.20 / Cached Input $0.02 / Output $1.20 per 1M):
### 7.2 유형별(Scenario) 토큰 통계
평가셋 전반의 유형별 토큰 소비량과 예상 비용은 고른 분포를 보였습니다.
| 지표 | 수치 | 비고 |
| --- | --- | --- |
| 총 평가 문항 수 | 87개 | 유형 1~6 전체 |
| Pass (완전 일치) | 67개 | 수치 및 재무 로직 완전 일치 |
| Fail (오답/불일치) | 20개 | 용어 차이(6건), 연도 기준 차이(12건), 계산/인출 오류(2건) |
| 전체 정답률 (Pass Rate) | 77.0% | 67 / 87 |
| 평균 처리 시간 (Latency) | 65.75초 | 최소 40.80s ~ 최대 121.99s |
| 평균 토큰 사용량 | 17151 토큰 | Prompt: 16885 / Completion: 266 |
### 7.3 비용 효율성 시사점
- 입력 토큰 중심의 비용 구조: 전체 토큰의 약 96.5% 이상이 Prompt(입력) 영역에서 발생하고 있어, RAG 검색 과정에서 주입되는 컨텍스트의 볼륨이 전체 비용을 좌우하는 핵심 요인임을 확인했습니다.
- 안정적인 비용 예측 가능성: TEV 관련 문항 집중이나 용어 혼선 등 평가셋 데이터의 제약 속에서도 6개 유형 간 문항당 토큰 소비량 편차가 적어(1.47\text{k} \sim 1.69\text{k} 범위), 향후 평가셋 재구축 후 전수(87문항) 확장 시에도 안정적인 예산 산정과 비용 집행이 가능할 것으로 분석됩니다.
- 향후 개선 계획: 평가셋 데이터 재구축이 완료된 이후에는 검색 단계에서의 Hit@K 지표를 면밀히 살펴보고, 모델의 검색 성능 저하를 방지하는 선에서 컨텍스트 주입량을 효율적으로 최적화 및 조절할 계획입니다.
### 7.4 수정된 평가셋 데이터 통계
| 유형 | 문항 범위 | 문항 수 | Pass | Fail | 정답률 (%) |
| --- | --- | --- | --- | --- | --- |
| 유형 1: 단일 지표 조회 | Q1 ~ Q25 | 25개 | 24 | 1 | 96.0% |
| 유형 2: 기간 및 추세 분석 | Q26 ~ Q40 | 15개 | 14 | 1 | 93.3% |
| 유형 3: 복수 지표 조회 및 비교 | Q41 ~ Q54 | 14개 | 10 | 4 | 71.4% |
| 유형 4: 재무 계산 | Q55 ~ Q76 | 22개 | 9 | 13 | 40.9% |
| 유형 5: 심층 추론 및 원인 분석 | Q77 ~ Q81 | 5개 | 5 | 0 | 100.0% |
| 유형 6: 지표 전망 및 예측 | Q82 ~ Q87 | 6개 | 5 | 1 | 83.3% |
| 합계 | Q1 ~ Q87 | 87개 | 67 | 20 | 77.0% |
---
### 7-5. 오답 케이스 분석
❌ Q70 — IBM의 총부채 대비 총자본화 비율은 어느 정도야?
- 참조 위치 (Ref): BS Cell P135, BS Cell P74
- 노션 정답셋 기준:
- 파이프라인 답변 (Ref: KS Cell E74, KS Cell E75):
- 원인 및 시사점:
## 8. MVP 2단계 확장 계획
### 8-1. 다수 기업 재무 상태 비교 기능
- 달러/원화 기준 자동 통일: 미국 기업(달러)과 한국 기업(원화)을 AI가 환율 반영하여 동일 기준으로 자동 비교합니다.
- 경쟁사 자동 추천 및 순위 매기기: 동일 업계 경쟁사를 자동 추천하고 주요 재무 지표 순위표를 생성합니다.
- 미래 역전 시점 예측: 현재 성장 속도 기반으로 후발 주자의 선두 추월 시점을 그래프로 시각화합니다.
### 8-2. 추가 시트 연동
- 실적 변화 원인 추적: 공시 뉴스(Key Developments)를 매칭하여 매출/이익 변화의 정성적 원인을 제공합니다.
- M&A 가치 계산: 과거 M&A 거래 데이터로 인수 적정 가치를 예측합니다.
- 지분 변동 및 지배구조 리스크 점검: 주요 주주 지분 변동 추이로 주식 매각 리스크를 사전 감지합니다.
- 직원 수 변화 선행 지표: R&D·영업 직원 수 증감률로 미래 매출 성장 가능성을 예측합니다.
### 8-3. UI 대시보드
- 한 페이지 요약 화면 (Tearsheet): 재무 정보와 AI 분석 결과를 단 한 장의 대시보드로 정리합니다.
- AI 분석 과정 시각화: AI 에이전트가 어떤 순서로 데이터를 찾고 분석하는지 흐름도로 제공합니다.
- 정확한 데이터 출처 표시: 분석 결과 옆에 원본 엑셀 시트명과 셀 좌표를 정확히 표시하여 AI 답변의 신뢰성을 증명합니다.
## 9. 역할 분배 예시 (미정)
| 이름 | MVP 2차 역할 |
| --- | --- |
| 권혁준 | UI 대시보드 개발
• Tearsheet 한 페이지 요약 화면 구현
• AI 분석 과정 실시간 시각화 및 원본 엑셀 셀 좌표 출처 표시 UI 구축 |
| 전명준 | 가데이터 생성 및 평가셋 전면 재구축
• MVP 2 다중 기업 비교 검증을 위한 가데이터(Synthetic Data) 생성
• 6대 유형 균등 할당 및 Fact Registry 기반의 평가셋 고도화 |
| 김정원 | 다수 기업 비교 및 추가 시트 연동 RAG 파이프라인 확장
• 달러/원화 환율 자동 반영 및 경쟁사 추천·순위 매기기 로직 구현
• 공시 뉴스(Key Developments) 및 M&A·지분 변동 등 추가 시트 대상 검색 |
| 김지환 | 멀티 에이전트 오케스트레이션 및 LangGraph 확장
• 다중 기업 비교 및 미래 역전 시점 예측 워크플로우를 위한 LangGraph 오케스트레이터 고도화
• 에이전트 간 상태(State) 관리 및 복합 멀티홉 추론 에이전트 체인 구축 |
