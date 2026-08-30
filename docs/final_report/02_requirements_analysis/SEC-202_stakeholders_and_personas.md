# [SEC-202] 이해관계자 및 5대 페르소나

> **Chapter:** 2. 프로젝트 요구 분석 | **Section:** 2.2 | **Status:** Implementation-aligned

---

| 페르소나 | 핵심 문제 | 사용 워크스페이스 | 성공 조건 |
| :--- | :--- | :--- | :--- |
| 데이터 엔지니어 | 대형 Excel의 업로드·색인·실패 복구 | Data Sources, Jobs | 파일·인덱스·작업 상태가 PostgreSQL에 남고 재실행 가능 |
| RAG 엔지니어 | 검색·생성 파이프라인 조합과 성능 관찰 | Playground, Benchmark | 19개 모듈 핀 계약, durable run, SSE 상태와 평가 결과 |
| 재무 분석가/CFO | 한 기업의 다년도 수치·추세·근거 확인 | Financial BI | 21개 지표의 상태·통화·배율·원본 셀 확인 |
| M&A·전략기획 담당 | 여러 기업의 성장·수익·안정성 비교 | Company Comparison | 동일 정책 순위, 2개 기업 비교, 누락 기업 제외 사유와 BI 딥링크 |
| 투자 리서처 | 자연어 질문과 대화 맥락 유지 | AI Chatbot | 세션 영속화, durable RAG 결과, 근거가 있는 답변 |

## 의사결정 원칙

- 분석가는 임의 보간보다 누락·모호 상태를 확인할 수 있어야 합니다.
- M&A 담당자는 가상 기업이나 임의 부채율이 섞이지 않은 실제 BI snapshot만 비교해야 합니다.
- 운영자는 Redis나 worker가 일시적으로 실패해도 PostgreSQL에서 최종 상태를 재구성할 수 있어야 합니다.
- 개발자는 BI와 Company Comparison을 별도 API·DTO로 변경할 수 있어야 합니다.
- 로컬 VLM과 Cross-Encoder reranker 운영은 현재 페르소나 요구 범위에 포함하지 않습니다.
