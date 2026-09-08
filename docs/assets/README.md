# 시연 자료

[프로젝트 소개·GIF 시연](../../README.md#주요-기능과-시연) · [문서 통합 목차](../README.md)

실제 프론트엔드를 활용한 **통합 시연 영상·기능별 GIF·README 이미지**를 관리합니다. 루트 README에서는 GitHub 내장 영상 플레이어와 기능 GIF를 바로 볼 수 있습니다.

## 통합 시연 영상

https://github.com/user-attachments/assets/6acd636c-8bf7-487a-8281-b722cd55a29d

[원본 MP4 다운로드](https://github.com/bist-mini-final/bist-mini-final/raw/refs/heads/main/docs/assets/demo/coldplay-demo-ko.mp4) · [한글 자막 SRT](demo/coldplay-demo-ko.srt) · [챕터·재현 범위](demo/README.md)

약 5분 30초 · 1080p · 30fps · 한글 자막 포함. 실제 프론트 코드와 저장된 실행 결과를 활용한 오프라인 재현으로, 실시간 성능 측정 영상이 아닙니다.

## 기능별 GIF

`previews/`는 README용 800×450·12fps 미리보기입니다. 전체 사용 흐름을 유지하되 용량을 줄였으며, 기존 1920×1080 원본은 그대로 보존합니다. **원본을 교체할 때는 해당 미리보기도 함께 갱신**합니다.

| 자료 | README 미리보기 | 고해상도 원본 |
| --- | --- | --- |
| 서비스 전체 흐름 | [GIF](previews/excel-rag-core-user-flow.gif) | [1920×1080](excel-rag-core-user-flow.gif) |
| 데이터 소스·적재 | [GIF](previews/excel-rag-data-ingestion.gif) | [1920×1080](excel-rag-data-ingestion.gif) |
| 재무 챗봇 | [GIF](previews/excel-rag-chatbot-user-flow.gif) | [1920×1080](excel-rag-chatbot-user-flow.gif) |
| BI 대시보드 | [GIF](previews/excel-rag-bi-dashboard-flow.gif) | [1920×1080](excel-rag-bi-dashboard-flow.gif) |
| 기업 비교 | [GIF](previews/excel-rag-company-comparison-flow.gif) | [1920×1080](excel-rag-company-comparison-flow.gif) |
| RAG 플레이그라운드 | [GIF](previews/excel-rag-playground-workflow.gif) | [1920×1080](excel-rag-playground-workflow.gif) |

## README 이미지

[프로젝트 커버](readme-cover.svg) · [시스템 아키텍처](readme-architecture.svg) · [영상 미리보기](demo/poster.png)

팀 소개에는 각 기여자의 공개 GitHub 프로필 이미지를 사용하고 해당 계정으로 연결합니다. 별도의 증명사진은 저장소에 복제하지 않습니다.

## 관리 기준

- 영상은 재생에 API 키·네트워크가 필요하지 않은 MP4로 보관하고, 자막과 챕터 설명을 함께 갱신합니다.
- 렌더링 중간 프레임·로컬 API 응답·개인 작업 디렉터리는 이 폴더에 포함하지 않습니다.
- 재현 데이터와 실제 실행 기록을 혼동하지 않도록 영상 안과 안내 문서에 재현 범위를 표시합니다.

평가 실행을 증명하는 캡처는 이 폴더의 시연 자료와 구분하여 [평가 화면 근거](../evaluation/12_screenshots/README.md)에 보관합니다.
