"""HTTP response DTOs for benchmark endpoints."""

from pydantic import BaseModel, Field


class BenchmarkJobCreateResponse(BaseModel):
    id: str = Field(..., description="등록된 벤치마크 작업 식별자")


class BenchmarkJobStatusResponse(BaseModel):
    id: str = Field(..., description="벤치마크 작업 ID")
    status: str = Field(
        ...,
        description="작업 상태 (queued, running, paused, completed, cancelled, failed)",
    )


__all__ = ["BenchmarkJobCreateResponse", "BenchmarkJobStatusResponse"]
