"""Adapter from shared workbook facts to the BI profile contract."""

from __future__ import annotations

import logging
from datetime import datetime
from hashlib import sha256
from typing import Protocol

from backend.domains.bi.application.errors import BiDocumentProfileRepositoryError
from backend.domains.bi.domain.materialization_models import BiDocumentProfile
from backend.domains.bi.domain.models import (
    AmountScale,
    BiEvidence,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    PeriodId,
    PeriodKind,
)
from backend.domains.data_sources.domain.workbook_profiles import (
    WorkbookAmountScale,
    WorkbookPeriodKind,
    WorkbookPeriodProfile,
    WorkbookProfile,
    WorkbookProfileEvidence,
    WorkbookSheetProfile,
    WorkbookSheetRole,
)

logger = logging.getLogger(__name__)


class WorkbookProfileStorePort(Protocol):
    def get(
        self,
        *,
        workbook_hash: str,
        index_id: str,
        profile_version: str | None = None,
    ) -> WorkbookProfile | None: ...

    def save(
        self,
        profile: WorkbookProfile,
        *,
        saved_at: datetime | None = None,
    ) -> WorkbookProfile: ...


class WorkbookProfileResolverPort(Protocol):
    def resolve(
        self,
        *,
        file_name: str,
        workbook_hash: str,
        index_id: str,
        force: bool = False,
    ) -> WorkbookProfile: ...


class WorkbookBiProfileRepository:
    """Translate data-sources-owned profiles without owning their storage."""

    def __init__(
        self,
        *,
        profiles: WorkbookProfileStorePort,
        profile_version: str,
        resolver: WorkbookProfileResolverPort | None = None,
    ) -> None:
        self._profiles = profiles
        self._profile_version = profile_version
        self._resolver = resolver

    def get(self, request: BiMaterializationRequest) -> BiDocumentProfile | None:
        profile = self._get_common(request.source)
        if profile is None or not profile.is_financially_complete:
            return None
        return self._to_bi(profile)

    def rebuild(
        self,
        request: BiMaterializationRequest,
    ) -> BiDocumentProfile | None:
        """Recompute a profile from the original workbook, ignoring storage."""
        if self._resolver is None:
            return None
        source = request.source
        try:
            profile = self._resolver.resolve(
                file_name=source.file_name,
                workbook_hash=source.workbook_hash,
                index_id=str(source.index_id),
                force=True,
            )
        except Exception:
            logger.warning(
                "원본 워크북 프로필 재생성에 실패해 BI 검색 fallback을 사용합니다",
                exc_info=True,
            )
            return None
        return self._to_bi(profile)

    def get_for_source(
        self,
        source: BiMaterializationSource,
    ) -> BiDocumentProfile | None:
        profile = self._get_common(source)
        return self._to_bi(profile) if profile is not None and profile.periods else None

    def save(
        self,
        request: BiMaterializationRequest,
        profile: BiDocumentProfile,
        saved_at: datetime,
    ) -> BiDocumentProfile:
        # This is the fresh retrieval/LLM fallback for a new snapshot.  Never
        # merge an older persisted profile into it: doing so can resurrect a
        # stale or truncated period set.
        common = self._from_bi_profile(request.source, profile)
        try:
            stored = self._profiles.save(common, saved_at=saved_at)
        except Exception as error:
            raise BiDocumentProfileRepositoryError("save", str(error)) from error
        converted = self._to_bi(stored)
        if converted is None:
            raise BiDocumentProfileRepositoryError("validate", "profile has no periods")
        return converted

    def _get_common(self, source: BiMaterializationSource) -> WorkbookProfile | None:
        try:
            profile = self._profiles.get(
                workbook_hash=source.workbook_hash,
                index_id=str(source.index_id),
                profile_version=self._profile_version,
            )
        except Exception as error:
            raise BiDocumentProfileRepositoryError("read", str(error)) from error
        if self._resolver is None or (
            profile is not None and profile.is_financially_complete
        ):
            return profile
        try:
            return self._resolver.resolve(
                file_name=source.file_name,
                workbook_hash=source.workbook_hash,
                index_id=str(source.index_id),
            )
        except Exception:
            logger.warning(
                "원본 워크북 프로필 보완에 실패해 BI 검색 fallback을 사용합니다",
                exc_info=True,
            )
            return profile

    @staticmethod
    def _to_bi(profile: WorkbookProfile) -> BiDocumentProfile | None:
        if not profile.periods:
            return None
        return BiDocumentProfile(
            periods=tuple(
                BiPeriod(
                    period_id=PeriodId(item.period_id),
                    kind=PeriodKind(item.kind.value),
                    label=item.label,
                    source_label=item.source_label,
                    end_date=item.end_date,
                    ordinal=item.ordinal,
                )
                for item in profile.periods
            ),
            currency=profile.currency,
            scale=(AmountScale(profile.amount_scale.value) if profile.amount_scale else None),
            relevant_sheets=tuple(
                item.sheet_name
                for item in profile.sheets
                if item.role is not WorkbookSheetRole.UNKNOWN
            ),
            evidence=tuple(
                BiEvidence(
                    cell_id=item.evidence_id,
                    sheet_name=item.sheet_name,
                    cell_coord=item.cell_coord,
                    source_text=item.source_text,
                )
                for item in profile.evidence
            ),
        )

    def _from_bi_profile(
        self,
        source: BiMaterializationSource,
        bi_profile: BiDocumentProfile,
    ) -> WorkbookProfile:
        evidence: dict[str, WorkbookProfileEvidence] = {}
        for item in bi_profile.evidence:
            evidence_id = "wpe-" + sha256(item.cell_id.encode("utf-8")).hexdigest()[:24]
            evidence.setdefault(
                evidence_id,
                WorkbookProfileEvidence(
                    evidence_id=evidence_id,
                    kind="period",
                    sheet_name=item.sheet_name,
                    cell_coord=item.cell_coord,
                    source_text=item.source_text,
                ),
            )
        periods = tuple(
            WorkbookPeriodProfile(
                period_id=str(item.period_id),
                kind=WorkbookPeriodKind(item.kind.value),
                label=item.label,
                source_label=item.source_label,
                end_date=item.end_date,
                ordinal=item.ordinal,
            )
            for item in bi_profile.periods
        )
        sheets = tuple(
            WorkbookSheetProfile(
                sheet_name=sheet_name,
                role=WorkbookSheetRole.UNKNOWN,
                confidence=0,
            )
            for sheet_name in dict.fromkeys(bi_profile.relevant_sheets)
        )
        currency = bi_profile.currency
        amount_scale = (
            WorkbookAmountScale(bi_profile.scale.value)
            if bi_profile.scale is not None
            else None
        )
        complete = bool(periods and currency and amount_scale)
        return WorkbookProfile(
            profile_version=self._profile_version,
            file_name=source.file_name,
            workbook_hash=source.workbook_hash,
            index_id=str(source.index_id),
            status="ready" if complete else "partial",
            currency=currency,
            amount_scale=amount_scale,
            periods=periods,
            sheets=sheets,
            evidence=tuple(evidence.values()),
            diagnostics=() if complete else ("llm_profile_incomplete",),
        )


__all__ = ["WorkbookBiProfileRepository"]
