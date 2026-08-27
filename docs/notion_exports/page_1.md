[목차]
> 
## 1. 프로젝트 개요 및 데이터 스코프
### 1-1. 프로젝트 개요
본 프로젝트는 S&P Capital IQ Pro 엑셀 모델의 방대한 재무 데이터를 기반으로, 사용자의 자연어 질의에 대해 정확한 재무 수치 도출, 출처(Cell) 명시, 인과관계 추론 및 리포트 작성을 수행하는 AI 에이전트 시스템을 구축하는 것을 목표로 합니다.
MVP Phase 1에서는 수식을 직접 해석하지 않고 캐시된 수치 값(Value)만을 활용하여 높은 정확도의 Q&A 프로토타입을 빠르게 검증하며, 추후 Phase 2에서 수식 구조 연동 및 분석 스코프 확장을 추진합니다.
### 1-2. 데이터 스코프 및 MVP 포함 여부
S&P Capital IQ Pro 기반 6개 엑셀 모델(총 35개 시트) 중 핵심 재무 지표를 우선 선정하였습니다. 또한 우선적으로 안에 있는 수식을 추출하지 않고 먼저 캐시로 남아있는 value만을 활용하여 우선적으로 프로토타입을 제작하기로 결정하였습니다. (추후에 MVP phase 2에서 수식 내용까지 활용하여 기능을 고도화할 예정입니다.) (※ 데이터 상세 분석 내용 및 상세 선정 과정은 문서 최하단 [부록] 참조)
| 소속 엑셀 파일 | 주요 시트명 | 시트 목적 및 역할 | MVP 포함 여부 |
| --- | --- | --- | --- |
| SPG_Company_KeyStats | Key_Stats | 종합 KPI 대시보드 (주요 성과 요약) | 1차 포함 |
|  | Income_Statement | 3대 재무제표: 손익계산서 상세 분석 | 1차 포함 |
|  | Balance_Sheet | 3대 재무제표: 재무상태표 (자산/부채) | 1차 포함 |
|  | Cash_Flow | 3대 재무제표: 현금흐름표 | 1차 포함 |
|  | Multiples, Capitalization 등 | 밸류에이션, 자본조달, 재무비율 등 | 추후 추가 |
|  | Supplemental | 일회성 비용, 사업부문별 매출 등 보충 정보 | 제외 |
| SPG_FinancialSnapshot | CompanySummary | 메인 대시보드 (1페이지 요약 시각화) | UI 참고용 |
| SPG_KeyDevelopments | Key_Developments | 기업 주요 이벤트 스크리닝 리포트 | 기능 참고용 |
| SPG_MAIPOTransaction | M&A_Transaction_ID | M&A 피어 트랜잭션 및 밸류에이션 분석 | 기능 참고용 |
| SPG_PrivateCompany | Detailed_Headcount | 비상장 기업 인력 규모/구성/펀딩 분석 | 기능 참고용 |
| SPG_Worldwide_Ownership | Summary, Detailed 등 | 글로벌 주주 지분 구조 및 피어 비교 | 추후 추가 |
## 2. 문제 정의 및 타겟 페르소나
기존 재무 데이터 분석 과정에서 발생하는 병목 현상을 해결하기 위해 두 가지 타겟 페르소나를 설정하고 핵심 요구사항을 도출했습니다.
### 2-1. 타겟 페르소나 및 페인 포인트(Pain Point)
| 구분 | Persona A (단일 기업 심층 분석) — MVP Phase 1 Focus | Persona B (다중 기업 비교 분석) — MVP Phase 2 연기 |
| --- | --- | --- |
| 대상 | 단일 기업 (예: IBM, Coldplay 등) | 복수 기업 (예: Coldplay vs 비스텔리젼스, 동종 피어 그룹) |
| 주요 역할 | 단일 회사의 세부 지표 수치 즉각 도출, 시계열 추이 분석, 개별 재무제표 간 수치 계산 및 원인 추론 | 기업 간 실적 수평 비교, 피어 대비 경쟁력 평가, M&A/투자 검토용 융합 분석 |
| 핵심 니즈 | 여러 시트(IS, BS, CF, KS)를 오가는 수동 검색 없이 정확한 수치, 수식 계산, 답변 근거(Cell 출처) 즉시 확보 | 다종 기업 재무 데이터를 정규화하여 상대적 우위/열위 파악 및 산업 내 위치 추론 |
| 페인 포인트 | 흩어진 시트 대조로 인한 리소스 소모, 비현금 조정 항목/재무 사건의 인과관계 파악 지연 | 기업 간 통화/회계 처리 방식 차이로 인한 비교 난이도 증대 |
### 2-2. 핵심 기능 요구사항 (MVP 1단계)
1. 6대 쿼리 시나리오 완전 지원 Q&A 모듈:
1. Tearsheet UI/UX 및 투명한 근거 출력 (Source Attribution):
### 2-3. QA 쿼리 시나리오 6대 유형 체계
사용자 질의 패턴을 분석하여 아래와 같이 6가지 대표 쿼리 유형으로 체계화하였습니다. (※ 각 유형별 상세 질문 108종은 문서 최하단 [부록] 참조)
| 쿼리 유형 | 핵심 분석 특징 | 처리 파이프라인 주요 로직 | 대표 질문 예시 |
| --- | --- | --- | --- |
| [유형 1] 단일 지표 조회 | 단일 시트/시점 정량 수치 탐색 | SQL Tool-Calling 셀 직접 조치 (Exact Look-up) | “IBM의 LTM 시가총액과 TEV는 얼마인가?” |
| [유형 2] 기간 및 추세 분석 | 연도/분기 시계열 변동 및 성장률 산출 | 시계열 범위 추출 및 YoY/CAGR 계산 연산 | “2021~2025년 IBM 매출액 연평균 성장률(CAGR)은?” |
| [유형 3] 복수 지표 조회 | 둘 이상의 시트 데이터 교차 결합 | Multi-Sheet Join 및 병렬 컬럼 정규화 | “IBM의 자본구조(부채/현금)와 멀티플(P/E) 정리해줘” |
| [유형 4] 재무 계산 | 흩어진 지표들을 수식으로 결합 산출 | 재무 비율/지표 수식 오케스트레이션 | “2025년 당기순이익 대비 영업현금흐름 비율은?” |
| [유형 5] 심층 추론/원인 분석 | 비현금 항목, 재무 사건 간 인과 추론 | RAG Context 주입 + LLM Reasoning Prompt | “순이익 급감에도 영업현금흐름이 유지된 원인은?” |
| [유형 6] 지표 전망 및 예측 | 과거 추세/외삽 가정을 통한 미래 예측 | 외삽(Extrapolation) 수식 + 가정 전제 보정 | “최근 성장 추세 유지 시 2026년 Total Revenue는?” |
## 3. 시스템 아키텍처 및 파이프라인 설계 (PoC)
전체 아키텍쳐 샘플 (방법론에 따라 구조 변경될 가능성 매우 높음)
[image]
PixelRag 및 FRTR 방법론을 활용한 사전 실험을 바탕으로 3개의 핵심 파이프라인을 설계하고 초기 실험 방향을 정하였습니다. (답변 생성 LLM 파이프라인은 고품질 데이터 입력 시 최신 LLM의 성능이 보장된다고 전제하여 추후 검증으로 미룸)
### 3-1. [RAG 파이프라인 (다각도 방법론 조사 & 실험)]
데이터 포맷(이미지, 텍스트, Rule-based PDF/구조화 엑셀)에 따라 최적화된 여러 RAG 파이프라인 방법론을 다각도로 비교·실험합니다. 다음은 예시 파이프라인 후보들입니다. 여러 오픈소스들을 조사하며 추가될 수 있습니다.
1) 이미지 포맷 RAG 파이프라인 (HITL 5단계 + Pixel RAG)
엑셀 시트를 이미지로 변환한 경우, FAST Table Detection과 HITL 5단계 보정(BFS 테이블 그룹화 + 바운딩 박스 변환/병합)을 거쳐 Pixel RAG 검색을 수행합니다.

flowchart LR
    %% 이미지 포맷 RAG: HITL 5단계 + Pixel RAG
    subgraph S1 ["1단계: 고해상도 이미지 추출"]
        A1["S&P 엑셀 (.xlsx)"] --> A2["시트별 고해상도 이미지"]
    end
    
    subgraph S2 ["2단계: Fast Table Detection"]
        A2 --> B1["Docling / PaddleOCR"] --> B2["Primary Bounding Box"]
    end

    subgraph S3 ["3단계: HITL UI 1차 보정"]
        B2 --> C1["HITL Preprocessing UI"] --> C2["사용자 위치/경계 검수"]
    end

    subgraph S4 ["4단계: Region Classification"]
        C2 --> D1["영역 성격 분류"] --> D2["Main Table / Header / Data"]
    end

    subgraph S5 ["5단계: Pixel RAG Storage & Retrieval"]
        D2 --> E1["Pixel Embedding Engine"] --> E2[("Pixel Vector DB")]
        E2 -. "Multi-Sub-Query 검색" .-> RAG1["Pixel RAG Search"]
        RAG1 --> LLM1["LLM 추론 & 정량 수치 출력"]
    end
2) 텍스트 포맷 RAG 파이프라인 (FRTR: Header & Context 직렬화)
Markdown 또는 텍스트 기반 엑셀 셀 데이터의 경우, 테이블의 상/하/좌/우 계층 헤더와 주변 컨텍스트를 직렬화(Flat Text Restructuring)하여 FRTR RAG 검색을 수행합니다.

flowchart LR
    %% 텍스트 포맷 RAG: FRTR 직렬화 파이프라인
    subgraph T1 ["1단계: Text / OpenPyXL Cell 추출"]
        A1["S&P 엑셀 / Markdown"] --> A2["Raw Text & Cell Coordinate"]
    end

    subgraph T2 ["2단계: FRTR 계층 직렬화"]
        A2 --> B1["Flat Row/Col Header Matcher"]
        B1 --> B2["Row Context + Column Context 텍스트 결합"]
    end

    subgraph T3 ["3단계: FRTR Storage & Hybrid RAG"]
        B2 --> C1[("FRTR Vector DB")]
        C1 -. "Context Embedding 검색" .-> D1["Cross-Encoder Re-Ranker"]
        D1 --> E1["Context Prompt Builder"] --> LLM2["LLM 추론 & 재무 표 출력"]
    end
3) Rule-Based / PDF / 구조화 엑셀 파이프라인 (BFS + LLM Boundary Detection + 계층 트리 + SQL)
PDF 문서나 구조화된 엑셀 테이블에 대해 BFS 알고리즘 기반 테이블 그룹화, LLM Boundary Detection, 좌표 기반 계층형 컬럼 트리 구축 및 SQL 셀 좌표 직접 매핑(Cell Attribution)을 수행합니다.

flowchart LR
    %% Rule-Based / PDF 파이프라인: BFS + LLM Boundary + 계층 트리 + SQL Cell Attribution
    subgraph STEP1 ["1. BFS 알고리즘 테이블 그룹화"]
        direction TB
        PDF["PDF / Excel Cell Matrix"] --> BFS["BFS 4방향 탐색<br/>(빈 셀=벽 취급)"]
        BFS --> BBOX["Bounding Box 산출<br/>(min_r, max_r, min_c, max_c)"]
        BBOX --> MERGE["인접 바운딩 박스 병합<br/>(_merge_adjacent_bounds)"]
    end

    subgraph STEP2 ["2. LLM Boundary Detection"]
        direction TB
        MERGE --> TOP10["상위 10행 데이터 추출"]
        TOP10 --> PROMPT["LLM Prompt 생성"]
        PROMPT --> LLM_BD["LLM Boundary Call<br/>(Pydantic Structured Output)"]
        LLM_BD --> BD_RES["LLMBoundaryResponse<br/>- title_row_end<br/>- data_start_row<br/>- index_column_count"]
    end

    subgraph STEP3 ["3. 좌표 기반 계층형 컬럼 트리"]
        direction TB
        BD_RES --> POST["제목/헤더 후처리 검증"]
        POST --> TREE["계층형 컬럼 트리 구축<br/>(TableHeaderInfo & ColumnHeaderSchema)"]
        TREE --> PARENT_CHILD["부모-자식 열범위 연결"]
    end

    subgraph STEP4 ["4. SQL DB 적재 & Exact Cell Lookup"]
        direction TB
        PARENT_CHILD --> SQL_DB[("Relational DB (SQL)<br/>셀 좌표 매핑 (Cell Attribution)")]
        SQL_DB -. "Structured SQL Tool Calling" .-> TOOL_CALL["Exact Cell Lookup Engine"]
        TOOL_CALL --> LLM_OUT["LLM 추론 & 근거 셀(e.g., IS Cell Q23) 출력"]
    end

    STEP1 --> STEP2 --> STEP3 --> STEP4
4) 기타 표 전용 AI 모델 & 코드 실행 에이전트 파이프라인 (TAPEX / CodeLlama Pandas Execution)
TAPEX, TableLlama 등 표 사전학습(Table Pre-trained) AI 모델 및 CodeLlama / Pandas DataFrame Agent를 활용하여, 엑셀 데이터를 Dataframe/Markdown 파싱 후 Python 코드를 자동 생성·실행하여 정밀 연산 및 셀 조회를 수행합니다.

flowchart LR
    %% 표 전용 AI 모델 & 코드 실행 에이전트 파이프라인
    subgraph TAB1 ["1단계: Structured Table 변환"]
        direction TB
        XLSX["S&P 엑셀 (.xlsx, .csv)"] --> DF_GEN["Pandas DataFrame / Markdown Table 변환"]
    end

    subgraph TAB2 ["2단계: 표 전용 AI 모델 & Code Agent 파싱"]
        direction TB
        DF_GEN --> M1["Table Pre-trained Model<br/>(TAPEX / TableLlama / TAPAS)"]
        DF_GEN --> M2["Code Execution LLM<br/>(CodeLlama / DeepSeek-Coder)"]
    end

    subgraph TAB3 ["3단계: Python Code Generation & Execution"]
        direction TB
        M2 --> CODE_GEN["Pandas / OpenPyXL 수식 연산 코드 생성"]
        CODE_GEN --> SANDBOX["Python Exec Sandbox Engine<br/>(df.query / df.groupby 연산)"]
    end

    subgraph TAB4 ["4단계: 연산 결과 동기화 & LLM 추론"]
        direction TB
        M1 & SANDBOX --> RES_MERGE["정확한 수치 연산 결과 & 셀 좌표 동기화"]
        RES_MERGE --> FINAL_LLM["LLM 추론 & 정밀 답변 (Cell 출처 표기)"]
    end

    TAB1 --> TAB2 --> TAB3 --> TAB4
### 3-2. [LangGraph 기반 오케스트레이션 & 서브 쿼리 파이프라인 (전체 구동 틀)]
LangGraph 오케스트레이션 프레임워크를 통해 전체 질의응답 8단계 상태(State) 관리, 6대 쿼리 유형별 의도 파악, 데이터 검색 라우팅 분기 제어 및 결과 후처리를 통합 수행하는 시스템 전체 구동 틀입니다. RAG 파이프라인에 따라 4번 데이터 검색 & 연산 레이어는 변경될 수 있습니다.

flowchart TD
    %% 노션(Notion) Dagre 레이아웃 완벽 호환 - 1단계부터 8단계까지 Top-to-Bottom 순차 렌더링
    
    subgraph STEP1 ["① 사용자 인터페이스"]
        UI["Web / Mobile Tearsheet UI<br/>(자연어 질의 입력)"]
    end

    subgraph STEP2 ["② 질의 이해"]
        INTENT["질문 의도 파악 & 엔티티 추출<br/>(6대 쿼리 유형 분류)"]
    end

    subgraph STEP3 ["③ 검색 및 실행 계획 수립"]
        ROUTER{"6대 쿼리 유형별<br/>라우팅 분기 결정"}
    end

    UI --> INTENT --> ROUTER

    subgraph STEP4 ["④ 데이터 검색 & 연산"]
        direction LR
        BRANCH_RDB["Structured RDB Tool Calling<br/>"]
        BRANCH_CODE["Pandas Code Exec Agent<br/>"]
        BRANCH_RAG["Hybrid RAG Pipeline<br/>"]
        BRANCH_MODEL["Table-based Model<br/>"]
    end

    ROUTER -- "[유형 1]" --> BRANCH_RDB
    ROUTER -- "[유형 2, 4]" --> BRANCH_CODE
    ROUTER -- "[유형 3, 5]" --> BRANCH_RAG
    ROUTER -- "[유형 6]" --> BRANCH_MODEL

    subgraph STEP5 ["⑤ 컨텍스트 구성"]
        CTX["검색 결과 정제, 중복 제거/정렬<br/>컨텍스트 요약 & 프롬프트 구성"]
    end

    BRANCH_RDB & BRANCH_CODE & BRANCH_RAG & BRANCH_MODEL --> CTX

    subgraph STEP6 ["⑥ LLM 응답 생성"]
        LLM_GEN["LLM Engine 답변 생성<br/>(근거/출처 Cell Source 포함)"]
    end

    CTX --> LLM_GEN

    subgraph STEP7 ["⑦ 결과 후처리 및 검증"]
        POST_PROC["답변/수치 검증 & Cell 출처 평가<br/>표/수식 시각화 및 출력 정리"]
    end

    LLM_GEN --> POST_PROC

    subgraph STEP8 ["⑧ 결과 반환"]
        OUT_DISP["최종 답변 표시<br/>출처 명시 & 표 시각화 제공"]
    end

    POST_PROC --> OUT_DISP
## 4. 프로젝트 실행 마일스톤 및 향후 계획
### 4.1. 팀원별 핵심 역할 분담 (R&R)
- 팀원 A (가데이터 생성 및 도메인 분석): 
- 팀원 B, C (RAG 파이프라인 방법론 조사 및 비교 실험): 
- 팀원 D (LangGraph Orchestrator 구축):
### 4.2. 세부 작업 일정 (마일스톤)
[image]
| 단계 | 목표 | 주요 수행 과제 |
| --- | --- | --- |
| 1단계 | 기반 데이터 구축 및 PoC 착수 |   • 팀원 A: 가데이터 및 6대 쿼리 정답셋 108종 생성 완료
  • 팀원 B & C: 데이터 포맷별 Parsing 및 여러 RAG 오픈소스들 비교 평가지표 설계
  • 팀원 D: LangGraph 오케스트레이터 구조 설계 및 6대 쿼리 Intent Classifier 구축 |
| 2단계 | 파이프라인 핵심 로직 고도화 |   • 팀원 A: 가데이터 주입을 통한 도메인 정확도 중간 점검
  • 팀원 B & C: 조사한 RAG 방법론 실험결과 정리 및 RAG 파이프라인 아키텍처 결정
  • 팀원 D: LangGraph 기반 RDB Tool Calling / RAG / Code Agent 동적 라우팅 분기 개발 |
| 3단계 | 시스템 통합 및 QA 검증 |   • LangGraph 오케스트레이터 중심 전 파이프라인 최종 통합
  • 6대 Q&A 유형별 108종 쿼리 전수 테스트 및 셀 출처 표기 정합성 검증
  • 정답셋 대조를 통한 환각 케이스 분석 및 디버깅 |
| 4단계 | 결과물 안정화 및 데모 |   • Tearsheet UI 연동 및 답변 속도/정확도 종합 테스트
  • 멘토 피드백 반영 및 MVP 1단계 최종 보고서/데모 준비 |
## 5. 향후 확장 계획 (MVP Phase 2)
MVP 1단계에서 신뢰할 수 있는 재무 데이터 검색기(Retriever)의 구축을 완료하고, 이 핵심 로직을 통해 MVP 2단계에서 서비스 품질의 시장 전체를 조망하고, 향후 기업의 의사결정의 근거로 활용할 수 있는 재무 애널리스트로 발전하는 것을 목표로 합니다.
5.1. Persona B 심층 구현: 글로벌 다중 기업 벤치마킹
단일 기업을 넘어, 다수 기업의 재무 상태를 정규화하여 실질적인 우위/열위를 평가하는 다차원 비교 분석을 자동화합니다.
- 이종 통화 및 회계기준 자동 정규화: 미국(USD, 12월 결산)과 한국(KRW, 3월/12월 결산) 기업 비교 시, 백엔드(Intermediate) 환율표를 참조해 에이전트가 단일 통화 및 TTM(최근 12개월) 기준으로 자동 환산하여 완벽한 수평 비교를 제공합니다.
- 동적 피어 그룹 자동 랭킹: 사용자가 벤치마크 대상을 직접 지정하지 않아도, GICS 산업분류나 시가총액을 바탕으로 AI가 경쟁사를 스스로 추출해 핵심 지표 순위표를 생성합니다.
- 교차 및 추월 시점 외삽 시뮬레이터: 후발 주자의 최근 3~5년 CAGR을 바탕으로, 선두 주자의 시가총액이나 매출 규모를 언제쯤 역전할 수 있을지 교차 시점을 시뮬레이션하고 꺾은선 차트로 시각화합니다.
5.2. 비재무 및 이벤트 데이터 융합 추론 (MVP 제외 시트 연동)
MVP 1단계에서 보류되었던 주요 공시, M&A, 주주 구조, 비상장사 인력 시트를 재무 수치와 결합하여 '왜(Why)'에 대한 입체적 스토리를 완성합니다.
- 이벤트-실적 인과성 탐지 (Key_Developments 시트 연동): 재무 시계열 차트의 급등락(Spike/Drop) 구간 위에 CEO 교체, 대규모 소송, 인수합병 발표 등의 공시 타임라인을 마커로 오버레이하여 실적 변동의 정성적 원인을 규명합니다.
- 과거 트랜잭션 기반 밸류에이션 추산 (MAIPOTransaction 시트 연동): 과거 동종 업계의 M&A 거래 배수(EV/EBITDA 등) 및 IPO 공모가 데이터를 불러와, 현재 타겟 기업의 적정 인수가치(Implied Valuation)와 프리미엄을 역추산합니다.
- 행동주의 투자 및 지배구조 리스크 진단 (Worldwide_Ownership 시트 연동): 포트폴리오 회전율이 높거나 단기 매매 성향이 강한 기관(액티브 펀드)의 지분 변동 트렌드를 분석하여, 향후 배당 압박이나 오버행(Overhang) 리스크 가능성을 선제적으로 추론합니다.
- 인력 동향 기반 선행 지표 추론 (PrivateCompanyHeadcount 시트 연동): R&D 및 영업 인력의 분기별 증감률을 분석하여, 인력 투자가 향후 매출 성장이나 판관비(SG&A) 압박에 미칠 시차(Lag) 효과를 유추합니다.
## 부록 (Appendix)
> 상세 분석 내용
> 상세 선정 과정
> 재무 QA 시스템 6대 쿼리 유형 종합 분류표

