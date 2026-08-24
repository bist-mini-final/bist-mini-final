from datetime import datetime

from pydantic import Field

from .models import (
    BiContractModel,
    BiMaterializationJob,
    BiMaterializationSource,
    CompanyId,
    JobId,
    MaterializationStatus,
    RefreshStatus,
    SnapshotId,
    SnapshotStatus,
)


class BiCompanySummary(BiContractModel):
    """BI 기업 요약 및 최신 스냅샷/머티리얼라이제이션 상태 DTO."""

    company_id: CompanyId = Field(..., description="기업 고유 식별자")
    display_name: str = Field(..., description="기업 표시명 (예: '현대모비스', '삼성전자')")
    source: BiMaterializationSource | None = Field(default=None, description="바인딩된 엑셀 파일 및 인덱스 정보")
    current_snapshot_id: SnapshotId | None = Field(default=None, description="발행된 최신 대시보드 스냅샷 ID")
    snapshot_status: SnapshotStatus | None = Field(default=None, description="스냅샷 상태 (ready, partial)")
    refresh_status: RefreshStatus = Field(..., description="지표 질문 재계산 상태 (idle, queued, indexing, profiling, extracting, materializing, failed)")
    updated_at: datetime | None = Field(default=None, description="최종 갱신 일시")


class BiCompanyListResponse(BiContractModel):
    """BI 등록 기업 목록 응답 DTO."""

    companies: tuple[BiCompanySummary, ...] = Field(..., description="등록된 기업 요약 목록")


class BiDashboardPendingResponse(BiContractModel):
    """BI 대시보드 생성 진행 중(202 Accepted) 응답 DTO."""

    job: BiMaterializationJob = Field(..., description="진행 중인 머티리얼라이제이션 백그라운드 작업 정보")


class BiMaterializationAccepted(BiContractModel):
    """BI 머티리얼라이제이션 작업 등록 수락 응답 DTO."""

    job_id: JobId = Field(..., description="등록된 머티리얼라이제이션 작업 식별자")
    status: MaterializationStatus = Field(..., description="작업 상태 (queued, profiling, extracting, ready 등)")
    published_snapshot_id: SnapshotId | None = Field(default=None, description="기존에 발행된 스냅샷 ID (있는 경우)")
