# 서버 실측평가 환경

- 측정 일자: 2026-09-01 KST
- 실행자: Codex / 정제 직접 조회 평가 사용자 승인 완료
- 소스 브랜치: `dev`
- 실제 HEAD 및 `origin/dev`: `38a18ed2c1bb6ef4c40067ccf7ad3f8e7c22f98a`
- 전달 패키지 기준 SHA: `e74cb5c92fced488583b77572703bda589fdb148`
- 기준 SHA 일치: 아니오. 전달 이후 최신 `dev`와 평가 중 개선 코드를 사용했다.
- 작업 트리: dirty(66개 경로). 사용자 변경과 평가 개선이 함께 있으며 content fingerprint 태그로 배포 이미지를 구분했다.

## 런타임·배포

| 구분 | 실제 실행값 |
| --- | --- |
| 호스트 | Windows NT 10.0.26200.0, 8 logical CPU |
| Docker 자원 | 8 CPU, 15.56GiB memory |
| 컨테이너 노드 | K3s Linux / WSL2, node 1개 |
| Python | 3.11.16 |
| Node / npm | Node 24.19.0 / npm 11.17.0 |
| Docker | Docker Desktop Engine 29.7.2 |
| Kubernetes | context `k3d-bist-local`, client 1.36.1, K3s 1.35.5+k3s1 |
| Namespace | `bist-batch` |
| API / Frontend / Redis | 각 1 replica ready; API/frontend restart 0, Redis restart 1(Docker Desktop 재기동 이력) |
| KEDA | 6 ScaledJob ready·inactive, 최대 3 Job(ingestion vector 2) |
| Ingress | `http://127.0.0.1:8080`, 외부 `http://kosa165.iptime.org:54000` |
| PostgreSQL / pgvector | 16.15 / 0.8.6 |
| DB 크기 | 1,916,935,191 bytes |
| Redis | 7.4.11, 단일 in-cluster deployment |
| Alembic | `20260901_0009 (head)` |
| 배포 tag | backend/worker/frontend `38a18ed2c1bb-dirty-5a5d1f46011f` |
| OCI provenance | revision `38a18ed2...f98a`, dirty label true, build date 포함; fingerprint는 tag에 포함 |

## 로컬 이미지 ID

로컬 k3d 배포라 registry manifest digest는 없으며, 아래 Docker content-addressed image ID와 OCI revision·dirty fingerprint로 실행 이미지를 식별한다.

| 이미지 | local image ID |
| --- | --- |
| `bist-backend:38a18ed2c1bb-dirty-5a5d1f46011f` | `sha256:edab8ffe6bb94601e78c08c68246c1ef4991818737431aa8db854b4c47c118d1` |
| `bist-workflow-worker:38a18ed2c1bb-dirty-5a5d1f46011f` | `sha256:34a339e17d25805be3eab4b7b3d211a984201ef2af7c8d28fe5ee6a012cb2de3` |
| `bist-frontend:38a18ed2c1bb-dirty-5a5d1f46011f` | `sha256:8fab9c05b65f31c972e145edde8678b7b1b8949d2211d54ac0848993bdc0cfa9` |

## 모델·검색·워크플로

| 구분 | 실제 실행값 |
| --- | --- |
| LLM | OpenAI `gpt-5.6-luna`; key 존재·인증 성공, 값은 미기록 |
| Embedding | `text-embedding-3-large`, 3,072 dimensions |
| 기준선 평가 Workflow | `bi_metric_extraction`, `rag_query` |
| 정제 직접 조회 평가 Workflow | `rag_query` |
| Workflow hash | BI `9bec11c9...a8e79`, RAG `1c221c0a...1297a` |
| Dense / keyword top-k | 각 100 |
| RRF | k=60, dense 1.0, keyword 1.0, fused top-k 100 |
| Context expansion | top-k 100, max blocks 1,000 |
| Cache | 기준선·사후 검증 모두 off |

## DB·색인 현황

- pgvector collection 9개, embedding row 89,948개
- 평가 대상 4개 collection 45,120 vector
- 대상 workbook hash별 활성 index 각 1개, staging/retired 잔여 0개
- catalog: `IBM`, `기업 A`, `Coldplay`, `DH Innovation`

## 재현성 제한

1. Git SHA·dirty fingerprint·OCI revision으로 추적되지만 clean signed tag가 아니므로 release 수준 재현성은 아니다.
2. canonical 평가 JSON 두 파일이 없어 전달 Markdown에서 재구성했다.
3. index `published_version`은 현재 API가 노출하지 않는다.
4. `expected_plan` 골드가 0건이라 Plan accuracy는 N/A다.
5. 서명 세션 인증·RBAC·단일 tenant 경계는 구성·실측 완료했다. 외부 공인 TLS만 DNS·공유기 443 forwarding·인증서 권한을 기다린다.
