# 🧪 Spreadsheet RAG Research & Experiment Notebooks

이 디렉터리는 **스프레드시트 RAG 파이프라인의 각 단계별 실험 단위(Experimental Units)**를 모듈화하여 재현 및 평가할 수 있는 연구용 노트북/스크립트 모음입니다.

---

## 📑 실험 단위 구성 (Experimental Hierarchy)

```
notebooks/
├── README.md                                      # 실험 단위 및 가이드라인
├── 01_structure_and_detection_experiments.py      # [실험 1] 2D 구조 인식 및 표/헤더 검출 실험
├── 02_cell_serialization_and_embedding.py        # [실험 2] 셀 직렬화 및 pgvector 임베딩 성능 실험
├── 03_query_decomposition_and_routing.py          # [실험 3] 질의 분해, 시소러스, 시맨틱 라우팅 실험
├── 04_retrieval_and_rrf_fusion.py                 # [실험 4] BM25/Dense RRF 결합 및 컨텍스트 확장 실험
└── 05_reader_and_answer_refinement_eval.py        # [실험 5] E2E Reader 및 셀 공간 교정 123문항 종합 평가
```

---

## 🔬 실험 단위별 상세 정의

### [실험 1] 01_structure_and_detection_experiments.py
- **목적**: 복잡한 다중 시트 엑셀 문서에서 계층형 헤더와 데이터 영역(Table Region)을 정확하게 파싱하는 기법 비교.
- **비교 대상**:
  1. `OpenpyxlRegionDetectorModule` (룰 기반 병합 셀 & 서식 추론)
  2. `DoclingTableDetectorModule` (Docling 파서 기반 계층 분석)
  3. `LunaVlmStructureDetectorModule` (VLM 멀티모달 공간 인식)

### [실험 2] 02_cell_serialization_and_embedding.py
- **목적**: 2D 셀 좌표와 계층 헤더를 결합한 텍스트 직렬화(Serialization) 방식과 배치 임베딩 성능 측정.
- **평가 지표**: 셀당 인코딩 지연 시간(Latency), 토큰 소비량, 인덱스 쓰기 Throughput.

### [실험 3] 03_query_decomposition_and_routing.py
- **목적**: 사용자의 복합 질문을 원자 단위 셀 질의(4-field)로 분해하는 정확도 및 플랜 재사용 안전성 평가.
- **실험 데이터**: `data/benchmark_sets/semantic-routing-comparison-24.json`, `semantic-safety-holdout-30.json`.
- **평가 지표**: 분해 적합성, 시맨틱 라우팅 캐시 히트율, Holdout 안전도(False Positive 방지율).

### [실험 4] 04_retrieval_and_rrf_fusion.py
- **목적**: PostgreSQL pgvector (Dense) + tsvector GIN (BM25) 하이브리드 검색과 RRF(Reciprocal Rank Fusion) 파라미터 최적화.
- **평가 지표**: Recall@K (K=5, 10, 20), RRF k 파라미터(30 vs 60 vs 90) 민감도 분석, 인접 행 확장 반경(radius 1~5) 적중률.

### [실험 5] 05_reader_and_answer_refinement_eval.py
- **목적**: Reader LLM의 수치 근거 인용 정밀도 및 Answer Refiner의 2D 공간 위상 추론을 통한 수치 검증/교정 성능 종합 평가.
- **실험 데이터**: `data/eval/evaluation_sets_combined.json` (총 123개 실전 QA 세트).
- **평가 지표**: 정답 일치율(Exact Match / Numeric Match), 인용 정확도(Citation Precision), Refiner 교정 성공률.

---

## 🚀 실행 방법

각 스크립트는 **Jupyter Interactive (`#%%`)** 환경 또는 **터미널 CLI**에서 즉시 단독 실행 가능합니다:

```bash
# 실험 1 실행
python notebooks/01_structure_and_detection_experiments.py

# 실험 3 실행
python notebooks/03_query_decomposition_and_routing.py

# 실험 5 종합 평가 실행
python notebooks/05_reader_and_answer_refinement_eval.py
```
