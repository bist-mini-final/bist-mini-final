from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from typing import Final, assert_never
from uuid import uuid4

from pydantic import ValidationError

from .materialization_models import BiCompanyIndex, BiCompanyIndexEntry
from .models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    CompanyId,
    JobId,
    MaterializationStatus,
    SnapshotId,
)


DEFAULT_BI_ARTIFACT_DIR: Final = (
    Path(__file__).resolve().parents[2] / "data" / "artifacts" / "bi"
)


@dataclass(frozen=True, slots=True)
class BiSnapshotStoreCorruption(Exception):
    path: Path

    def __str__(self) -> str:
        return f"invalid BI artifact: {self.path}"


class FileBiSnapshotStore:
    def __init__(self, root: Path = DEFAULT_BI_ARTIFACT_DIR) -> None:
        self._root = root

    def publish(self, snapshot: BiDashboardSnapshot) -> None:
        company_id = snapshot.company.company_id
        snapshot_id = snapshot.snapshot.snapshot_id
        self._write(
            self._snapshot_path(company_id, snapshot_id),
            snapshot,
        )
        current = self._load_company_index()
        companies = dict(current.companies)
        companies[company_id] = BiCompanyIndexEntry(
            company=snapshot.company,
            current_snapshot_id=snapshot_id,
        )
        self._write(
            self._root / "companies.json",
            BiCompanyIndex(companies=companies),
        )

    def register_company(self, company: BiCompany) -> None:
        current = self._load_company_index()
        companies = dict(current.companies)
        previous = companies.get(company.company_id)
        companies[company.company_id] = BiCompanyIndexEntry(
            company=company,
            current_snapshot_id=(
                previous.current_snapshot_id if previous is not None else None
            ),
        )
        self._write(
            self._root / "companies.json",
            BiCompanyIndex(companies=companies),
        )

    def get_company(self, company_id: CompanyId) -> BiCompany | None:
        entry = self._load_company_index().companies.get(company_id)
        return entry.company if entry is not None else None

    def list_companies(self) -> tuple[BiCompanyIndexEntry, ...]:
        return tuple(self._load_company_index().companies.values())

    def get_current(self, company_id: CompanyId) -> BiDashboardSnapshot | None:
        entry = self._load_company_index().companies.get(company_id)
        if entry is None or entry.current_snapshot_id is None:
            return None
        return self.get_snapshot(company_id, entry.current_snapshot_id)

    def get_snapshot(
        self,
        company_id: CompanyId,
        snapshot_id: SnapshotId,
    ) -> BiDashboardSnapshot | None:
        path = self._snapshot_path(company_id, snapshot_id)
        if not path.is_file():
            return None
        try:
            return BiDashboardSnapshot.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except ValidationError as error:
            raise BiSnapshotStoreCorruption(path=path) from error

    def save_job(self, job: BiMaterializationJob) -> None:
        self._write(self._root / "jobs" / f"{job.job_id}.json", job)

    def fail_interrupted_jobs(
        self,
        failed_at: datetime,
    ) -> tuple[BiMaterializationJob, ...]:
        recovered: list[BiMaterializationJob] = []
        for job in self._list_jobs():
            match job.status:
                case (
                    MaterializationStatus.QUEUED
                    | MaterializationStatus.INDEXING
                    | MaterializationStatus.PROFILING
                    | MaterializationStatus.EXTRACTING
                    | MaterializationStatus.MATERIALIZING
                ):
                    failed = job.model_copy(
                        update={
                            "status": MaterializationStatus.FAILED,
                            "error_code": "materialization_interrupted",
                            "message": (
                                "서버가 재시작되어 작업이 중단되었습니다. "
                                "데이터 처리를 다시 요청해주세요."
                            ),
                            "updated_at": failed_at,
                        }
                    )
                    self.save_job(failed)
                    recovered.append(failed)
                case (
                    MaterializationStatus.READY
                    | MaterializationStatus.PARTIAL
                    | MaterializationStatus.FAILED
                ):
                    continue
                case unreachable:
                    assert_never(unreachable)
        return tuple(recovered)

    def get_job(self, job_id: JobId) -> BiMaterializationJob | None:
        path = self._root / "jobs" / f"{job_id}.json"
        if not path.is_file():
            return None
        return self._load_job(path)

    def get_latest_job(
        self,
        company_id: CompanyId,
    ) -> BiMaterializationJob | None:
        return max(
            (
                job
                for job in self._list_jobs()
                if job.company_id == company_id
            ),
            key=lambda job: job.updated_at,
            default=None,
        )

    def find_latest_job(
        self,
        company_id: CompanyId,
        workbook_hash: str,
    ) -> BiMaterializationJob | None:
        return max(
            (
                job
                for job in self._list_jobs()
                if job.company_id == company_id
                and job.workbook_hash == workbook_hash
            ),
            key=lambda job: job.updated_at,
            default=None,
        )

    def _list_jobs(self) -> tuple[BiMaterializationJob, ...]:
        jobs_dir = self._root / "jobs"
        if not jobs_dir.is_dir():
            return ()
        return tuple(self._load_job(path) for path in jobs_dir.glob("*.json"))

    @staticmethod
    def _load_job(path: Path) -> BiMaterializationJob:
        try:
            return BiMaterializationJob.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except ValidationError as error:
            raise BiSnapshotStoreCorruption(path=path) from error

    def _load_company_index(self) -> BiCompanyIndex:
        path = self._root / "companies.json"
        if not path.is_file():
            return BiCompanyIndex()
        try:
            return BiCompanyIndex.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as error:
            raise BiSnapshotStoreCorruption(path=path) from error

    def _snapshot_path(
        self,
        company_id: CompanyId,
        snapshot_id: SnapshotId,
    ) -> Path:
        return self._root / "snapshots" / str(company_id) / f"{snapshot_id}.json"

    @staticmethod
    def _write(
        path: Path,
        model: BiDashboardSnapshot | BiMaterializationJob | BiCompanyIndex,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(model.model_dump_json(indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
