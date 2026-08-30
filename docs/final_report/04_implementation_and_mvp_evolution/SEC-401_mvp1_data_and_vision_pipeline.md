# [SEC-401] [1차 MVP 및 현재화] Spreadsheet ingestion 기반
> **Chapter:** 4. 시스템 구현 및 MVP 진화 | **Section:** 4.1 | **Status:** Current Historical Record

---

## 1. 초기 목표

1차 MVP는 여러 sheet와 병합 셀을 가진 재무 workbook을 2D 좌표 문맥을 보존한 채 검색 가능한 데이터로 변환하는 것이 목표였습니다. 초기 코드명에 Luna가 포함됐지만 현재 구조 감지는 외부 OpenAI vision provider를 사용하며 실제 model ID는 런타임 설정으로 결정합니다.

---

## 2. 현재 남은 구현

| 단계 | 현재 구현 |
| :--- | :--- |
| 원본 등록 | 파일 해시·메타데이터와 sheet 정보 저장 |
| 좌표 파싱 | OpenPyXL 기반 병합 셀/행·열 좌표 정규화 |
| 구조 감지 | raster preview를 외부 vision provider에 전달하고 구조화 JSON 검증 |
| 직렬화 | header와 cell value를 좌표 문맥이 보존된 검색 텍스트로 변환 |
| 임베딩 | OpenAI embedding adapter가 batch artifact 생성 |
| 적재 | `PgVectorBinaryCopyStream`으로 3072d vector와 metadata 적재 |
| 실행 | PostgreSQL durable ingestion run과 KEDA one-shot worker |

관련 청사진은 [`BP-201`](file:///c:/Repos/bist-mini-final/docs/blueprints/02_data_engine_blueprints/BP-201_spreadsheet_coordinate_parser.md), [`BP-202`](file:///c:/Repos/bist-mini-final/docs/blueprints/02_data_engine_blueprints/BP-202_luna_vlm_vision_detector.md), [`BP-203`](file:///c:/Repos/bist-mini-final/docs/blueprints/02_data_engine_blueprints/BP-203_binary_copy_vector_pipeline.md)입니다.

---

## 3. 현재화된 결정

- 로컬·온디바이스 VLM은 구현하지 않습니다.
- vision 실패를 임의 좌표 heuristic으로 숨기지 않습니다.
- 수동 bounding-box 수정/승인 workflow는 현재 공개 기능이 아닙니다.
- 검증되지 않은 처리량·메모리 절감 수치는 성과로 주장하지 않습니다.
- 원본 좌표, sheet, cell text, embedding metadata를 통해 근거를 역추적합니다.
