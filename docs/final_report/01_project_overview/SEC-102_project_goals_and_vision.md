# [SEC-102] 프로젝트 목표 및 핵심 가치

> **Chapter:** 1. 프로젝트 개요 | **Section:** 1.2 | **Status:** Implementation-aligned

---

## 1. 플랫폼 목표

`bist-mini-final`의 목표는 재무 Excel을 검색 가능한 좌표 데이터로 바꾸고, 동일한 근거 체계 위에서 BI·챗봇·기업 비교를 제공하는 것입니다.

| 목표 | 구현 기준 |
| :--- | :--- |
| 근거 중심 분석 | 답변·BI·비교 수치에 시트·셀 좌표와 원문을 연결 |
| 명시적 누락 | 없는 값을 추정하지 않고 상태·제외 사유로 표현 |
| 분리된 제품 도메인 | BI, Chat, Company Comparison이 각자 API·DTO·수명주기를 소유 |
| 재현 가능한 실행 | PostgreSQL durable queue와 불변 스냅샷 버전 사용 |
| 확장 가능한 파이프라인 | 19개 등록 모듈과 Pydantic 핀 계약으로 DAG 구성 |
| 배포 일관성 | Docker 이미지, Helm, KEDA worker와 Alembic migration 사용 |

## 2. 제품별 성공 조건

### Financial BI

- `MetricId`와 `METRIC_CATALOG`의 21개 지표를 current snapshot으로 제공합니다.
- FY/LTM, 통화, 배율과 원본 근거를 보존합니다.
- 파생식은 `Decimal`과 버전형 formula contract를 사용합니다.

### AI Financial Chat

- 세션·메시지·첨부파일을 PostgreSQL에 영속화합니다.
- RAG가 필요한 메시지는 durable workflow run으로 처리합니다.
- 완료 메시지는 검증된 근거와 함께 동기화합니다.

### Company Comparison

- `/company-comparison` 단일 화면과 `/api/v1/company-comparisons` 전용 API를 사용합니다.
- 완전한 BI snapshot이 2개 이상일 때만 발행합니다.
- 성장성 35%, 수익성 35%, 안정성 30%의 버전형 정책을 사용합니다.
- 실제 관측값과 3개년 가정 기반 전망을 구분합니다.

## 3. 품질 목표와 측정 상태

| 품질 축 | 목표 | 현재 측정 상태 |
| :--- | :--- | :--- |
| 수치·단위 정확도 | Ground-Truth exact match ≥ 95% | benchmark job으로 측정하는 목표값; 달성값으로 단정하지 않음 |
| 근거 검색 | Cell Recall@5 ≥ 98% | benchmark set별 측정 대상 |
| 아키텍처 | 정적 계약 위반 0건 | 현재 Ruff·Pyright·계약 테스트 통과 |
| 회귀 안정성 | 백엔드·프런트 전체 테스트 통과 | 166 passed/2 skipped, 112 passed |
| 기업 비교 무결성 | synthetic fallback 0건, 근거 불완전 기업 제외 | builder·API 회귀 테스트로 검증 |

비즈니스 시간 절감률과 인프라 비용 절감률은 실제 운영 관측이 필요한 기대효과이며, 검증되지 않은 확정 성과로 표현하지 않습니다.
