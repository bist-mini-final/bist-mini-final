# [SEC-401] [1차 MVP] 데이터 파싱, Luna VLM 표 감지 & Binary COPY 적재
> **Chapter:** 4. 시스템 구현 및 3단계 MVP 진화 과정 | **Section:** 4.1 | **Status:** Approved Baseline  
> **Classification:** MVP 1 Implementation Results: Parsing, Vision & Binary COPY Pipeline

---

## 1. 1차 MVP 핵심 과제 및 구현 목표

* **목표**: 비정형 다중 시트 재무 엑셀(`.xlsx`)을 2차원 시각적 맥락 손실 없이 고속으로 추출하여 pgvector에 적재하는 파이프라인 완성.
* **주관 엔지니어**: **김지환 (Team Lead)**, **권혁준 (RAG Framework)**, **전명준 (Data Modeling)**.

---

## 2. 세부 구현 산출물 및 모듈

1. **OpenPyXL 2D 직교 좌표계 파서 ([`BP-201`](file:///c:/Repos/bist-mini-final/docs/blueprints/02_data_engine_blueprints/BP-201_spreadsheet_coordinate_parser.md))**:
   - 병합 영역(`A1:C1`)의 부모 헤더 텍스트를 모든 자식 셀(`A1`, `B1`, `C1`)로 브로드캐스팅하여 좌표 누락 원천 차단.
2. **Luna VLM 1-Shot 표 바운딩박스 검출기 ([`BP-202`](file:///c:/Repos/bist-mini-final/docs/blueprints/02_data_engine_blueprints/BP-202_luna_vlm_vision_detector.md))**:
   - Pillow 이미지 래스터라이징 후 GPT-5.6 Luna VLM을 통해 다층 헤더 및 표 경계를 시각적으로 1-Shot 검출.
3. **PostgreSQL Native Binary COPY 파이프라인 ([`BP-203`](file:///c:/Repos/bist-mini-final/docs/blueprints/02_data_engine_blueprints/BP-203_binary_copy_vector_pipeline.md))**:
   - 텍스트 SQL `INSERT`를 폐기하고 네이티브 바이너리 스트리밍으로 대량 3072d 벡터를 초고속 주입.