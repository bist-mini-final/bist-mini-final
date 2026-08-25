from datetime import datetime
from typing import assert_never

from pydantic import Field, field_validator

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

    @field_validator("companies")
    @classmethod
    def keep_dashboard_companies(
        cls,
        companies: tuple[BiCompanySummary, ...],
    ) -> tuple[BiCompanySummary, ...]:
        """
        Filter companies to those eligible for inclusion in the dashboard list.
        
        Parameters:
            companies (tuple[BiCompanySummary, ...]): Company summaries to evaluate.
        
        Returns:
            tuple[BiCompanySummary, ...]: Company summaries that should appear in the dashboard list.
        """
        return tuple(company for company in companies if _should_list_company(company))


class BiDashboardPendingResponse(BiContractModel):
    """BI 대시보드 생성 진행 중(202 Accepted) 응답 DTO."""

    job: BiMaterializationJob = Field(..., description="진행 중인 머티리얼라이제이션 백그라운드 작업 정보")


class BiMaterializationAccepted(BiContractModel):
    """BI 머티리얼라이제이션 작업 등록 수락 응답 DTO."""

    job_id: JobId = Field(..., description="등록된 머티리얼라이제이션 작업 식별자")
    status: MaterializationStatus = Field(..., description="작업 상태 (queued, profiling, extracting, ready 등)")
    published_snapshot_id: SnapshotId | None = Field(default=None, description="기존에 발행된 스냅샷 ID (있는 경우)")


def _should_list_company(company: BiCompanySummary) -> bool:
    """
    Determine whether a company should appear in the dashboard list.
    
    Parameters:
        company (BiCompanySummary): Company summary to evaluate.
    
    Returns:
        bool: `true` if the company has a ready snapshot or an active refresh, `false` otherwise.
    """
    match company.snapshot_status:
        case SnapshotStatus.READY:
            return True
        case SnapshotStatus.PARTIAL | None:
            match company.refresh_status:
                case (
                    RefreshStatus.QUEUED
                    | RefreshStatus.INDEXING
                    | RefreshStatus.PROFILING
                    | RefreshStatus.EXTRACTING
                    | RefreshStatus.MATERIALIZING
                ):
                    return True
                case RefreshStatus.IDLE | RefreshStatus.FAILED:
                    return False
                case unreachable:
                    assert_never(unreachable)
        case unreachable:
            assert_never(unreachable)
