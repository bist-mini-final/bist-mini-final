# Project documentation

프로젝트의 사람이 관리하는 설계 문서와 자동 생성 API·모듈 문서의 진입점입니다.

## 문서 지도

| 문서 | 관리 방식 | 내용 |
|---|---|---|
| [프로젝트 README](../README.md) | 수동 | 설치, 실행, 전체 구조, 주요 워크플로와 API |
| [Backend module architecture](./backend_module_architecture.md) | 수동 | DTO 경계, 데이터 계보, 독립 실행, 모듈 추가 규칙 |
| [Module guides](../backend/modules/docs/README.md) | 자동 생성 | 등록된 25개 모듈의 포트와 Input/Config/Output DTO 사용법 |
| ReDoc `/redoc` | 런타임 자동 생성 | 읽기 중심 전체 REST API 레퍼런스 |
| Swagger UI `/docs` | 런타임 자동 생성 | 모듈별 JSON 요청·응답 확인 및 API 직접 실행 |
| OpenAPI `/openapi.json` | 런타임 자동 생성 | 외부 도구와 클라이언트 생성용 기계 판독 계약 |

## 문서 소스

API와 모듈 문서의 기준은 다음 코드 선언입니다.

1. 모듈 클래스와 메서드의 docstring
2. `ModuleDefinition`의 type, label, description, ports, version
3. Pydantic `InputDTO`, `ConfigDTO`, `ExecutionDTO`, `OutputDTO`
4. FastAPI route의 summary, description, request/response model

ReDoc과 Swagger는 서버 시작 시 이 선언에서 자동으로 갱신됩니다. 모듈별 Markdown은 체크인 가능한 정적 문서이므로 DTO 또는 포트를 변경한 후 재생성합니다.

```bash
python -m backend.tools.generate_module_docs
```

`backend/modules/docs/*.md`는 생성 결과이므로 직접 수정하지 않습니다. 생성기와 실제 파일이 다르면 백엔드 테스트가 실패합니다.

## 문서 변경 체크리스트

모듈 또는 워크플로 계약을 변경할 때 함께 확인합니다.

- Input과 Config 분류가 [분류 규칙](./backend_module_architecture.md#dto-field-classification)을 따르는가?
- Output이 다음 모듈에서 필요한 질문·문서 계보를 유지하는가?
- `ModuleDefinition.inputs/outputs`와 DTO 필드가 일치하는가?
- 모듈 version을 변경해 이전 캐시와 구분했는가?
- 저장된 예제 워크플로가 새 포트 계약으로 검증되는가?
- 모듈 Markdown을 재생성했는가?
- `/redoc`, `/docs`, `/openapi.json`에 새 계약이 표시되는가?
- 백엔드 테스트와 프론트 빌드가 통과하는가?

```bash
python -m unittest discover -s tests
cd frontend && npm run build
```
