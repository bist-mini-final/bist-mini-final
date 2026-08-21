# 🚀 Deployment Architecture & Container Units

이 디렉터리는 **BIST RAG 파이프라인**의 인프라스트럭처 컨테이너 및 대규모 분산 배치 실행 환경을 정의합니다.

---

## 📁 디렉터리 구조 및 역할 분리

```
deploy/
├── README.md                      # [현재 파일] 배포 아키텍처 및 운영 가이드
├── db/                            # [1. 기본 인프라] PostgreSQL 16 + pgvector 데이터베이스
│   └── docker-compose.yml         # pgvector 컨테이너 정의 (포트 5432)
└── kubernetes/                    # [2. 배치/스케일링] 대규모 Excel 수집 및 분산 평가 환경
    ├── README.md                  # Kubernetes & KEDA ScaledJob 세부 가이드
    ├── capacity.py                # 노드 리소스 및 스케일링 사이징 유틸리티
    ├── local.sh                   # 로컬 k8s(k3d/kind) 클러스터 프로비저닝 스크립트
    ├── render.py                  # KEDA ScaledJob 매니페스트 렌더러
    ├── render_database.py         # K8s 내부 DB 서비스 매니페스트 렌더러
    └── templates/                 # K8s YAML 템플릿 (Namespace, Service, ScaledJob)
        ├── namespace.yaml
        ├── postgres-service.yaml
        └── excel-ingestion-scaledjob.yaml
```

---

## 🧱 1. 기본 인프라 (`deploy/db/`)

로컬 개발 및 백엔드 서버 운영에 필요한 핵심 데이터베이스(PostgreSQL + pgvector)를 컨테이너로 구동합니다.

### 실행 방법
```bash
# pgvector 컨테이너 백그라운드 구동
docker compose -f deploy/db/docker-compose.yml up -d

# 상태 확인
docker compose -f deploy/db/docker-compose.yml ps

# 컨테이너 종료
docker compose -f deploy/db/docker-compose.yml down
```

- **이미지**: `pgvector/pgvector:pg16`
- **기본 포트**: `127.0.0.1:5432`
- **기본 DB/계정**: `rag_flow` / `postgres`

---

## ☸️ 2. 분산 배치 실행 (`deploy/kubernetes/`)

대규모 엑셀 파일 수집(Ingestion) 및 수백 문항의 E2E 평가를 분산 병렬 처리하기 위한 Kubernetes Manifests 및 자동 스케일러(KEDA ScaledJob)입니다.

> 💡 **`jobs/`와의 관계**:
> - `jobs/` 폴더는 실제 실행되는 Python 배치 비즈니스 로직(예: `jobs/excel_ingestion_runner.py`)을 포함합니다.
> - `deploy/kubernetes/`는 이 배치 작업들을 다중 Pod로 병렬 분산하고 Auto-scaling하기 위한 **인프라 배포 정의**입니다.

### 실행 방법
```bash
# 로컬 Kubernetes 클러스터 생성 및 전체 파이프라인 배포
./deploy/kubernetes/local.sh all

# 배포 상태 및 Pod 모니터링
./deploy/kubernetes/local.sh status

# 로그 확인
./deploy/kubernetes/local.sh logs
```
