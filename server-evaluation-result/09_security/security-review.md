# 보안 점검 결과

## 결론

학생 기업 주제 프로젝트의 보안 범위는 **통과**다. API 명세 차단, 보안 헤더, rate limit, 업로드 검증과 더불어 서명 세션 인증·RBAC·단일 tenant 경계를 구현·재배포해 실측 통과했다. 공인 인증서와 외부 443 포트 연결은 상용 공개 운영 범위로 분리한다.

| 항목 | 최신 실측 | 판정 |
| --- | --- | --- |
| HTTP / HTTPS | 외부 HTTP root 200; Helm 운영 profile은 TLS Secret·redirect 입력 지원 | 프로젝트 범위 제외 |
| 인증 | 익명 index 조회 401, login/session 200, HttpOnly·SameSite=Strict 서명 cookie | 통과 |
| RBAC | viewer/operator/admin method 권한, DELETE admin 제한 단위·계약 시험 | 통과 |
| tenant | principal tenant와 다른 `X-Tenant-ID` 요청 403; 현재 배포는 `default` 단일 tenant | 통과(단일 tenant) |
| API 명세 비공개 | `/docs`, `/redoc`, `/openapi.json` 외부·로컬 404 | 통과 |
| 내부 readiness 비공개 | ingress `/readyz` 404; Kubernetes probe는 내부 경로 사용 | 통과 |
| 보안 헤더 | CSP, frame deny, nosniff, referrer, permissions 정책 확인 | 통과 |
| HSTS | HTTP 시연 배포이므로 없음 | 프로젝트 범위 제외 |
| CORS | 임의 origin 400, 허용 개발 origin 200 | 통과 |
| rate limit | 240 burst 중 200=50, 429=190; p95 401.07ms | 통과 |
| 업로드 확장자·시그니처 | 위장 확장자·가짜 OpenXML·2MiB 가짜 xlsx 모두 422 | 통과 |
| 500MiB 경계 | 정확한 상한은 시그니처 422, +1 byte는 413, ingestion Job 미생성 | 통과 |
| prompt injection | 검색 셀 원문은 신뢰할 수 없는 user-data 영역에만 배치하고 지시문 실행 금지 계약을 회귀 시험 | 통과(계약 시험) |
| 경로 조작·매크로 | 셀 좌표 traversal 거부, 업로드 파일명 격리 저장, OpenXML은 수식·매크로 코드를 실행하지 않음 | 통과(계약 시험) |
| Secret 저장·노출 | Kubernetes Secret reference 사용, source/log scan에 실제 key·DB URL 0 | 통과(표본) |
| 로그 본문 노출 | 최근 표본에서 질문·답변·셀 값 marker 0 | 통과(표본) |
| audit append-only | source file·BI company·benchmark lifecycle trigger와 append-only 제약, mutation 차단 확인 | 통과 |

## 적용된 개선

- 운영 FastAPI와 frontend/Ingress/Vite의 Swagger·ReDoc·OpenAPI 노출 경로를 제거했다.
- API와 Nginx에 CSP, `X-Frame-Options`, `X-Content-Type-Options`, referrer/permissions 정책을 적용했다.
- Ingress에 `limit-rps=30`, burst multiplier 3, connection 50 제한을 적용했다.
- 데이터소스 업로드는 확장자와 OpenXML ZIP 필수 엔트리를 함께 검사하고 실패 임시 파일을 즉시 제거한다.
- Reader는 검색된 셀 문자열을 신뢰하지 않는 데이터로 취급하고 system instruction과 분리한다.
- source file·BI company 변경과 benchmark lifecycle을 append-only `audit_logs`에 남기며, schema 변경은 migration 프로세스만 수행하도록 분리했다.

## 상용 공개 운영으로 확장할 때의 추가 조치

1. 유효 인증서를 이용한 TLS termination과 HTTP→HTTPS redirect/HSTS 적용.
2. 다중 tenant 제품화 시 collection row에 tenant key를 추가하고 repository query까지 tenant predicate를 확장. 현재 단일 tenant 배포에는 해당하지 않음.
3. 유료 모델 호출·업로드·삭제 API에 주체별 quota와 audit actor 연결.

공인 TLS는 DNS·공유기 443 forwarding·인증서 발급 권한이 필요한 범위이므로 임의의 self-signed 우회로 통과 처리하지 않았다. 원시 결과는 `security-probe.json`, `auth-rbac-probe.json`, `source-secret-scan.json`, `log-scan.json`에 있다. `openapi.json`은 명세 노출을 차단하기 전 수집한 내부 감사용 역사적 스냅샷이며 현재 공개 endpoint의 응답이 아니다.
