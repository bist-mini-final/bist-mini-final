from dataclasses import dataclass
from typing import Mapping, Protocol

from backend.domains.bi.domain.extraction_models import (
    BiMetricExtractionRequest,
    BiMetricExtractionResult,
)
from backend.domains.bi.domain.models import BiMaterializationSource, IndexId
from backend.domains.bi.domain.question_records import BiQuestionRecord


class BiQuestionExtractorPort(Protocol):
    def extract_question(
        self,
        request: BiMetricExtractionRequest,
        question: str,
    ) -> BiMetricExtractionResult: ...


class BiQuestionSourceResolverPort(Protocol):
    def resolve(self, question: BiQuestionRecord) -> BiMaterializationSource: ...


class IndexMetadataStorePort(Protocol):
    def get_index_metadata(self, index_id: str) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class BiQuestionSourceError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


class PgVectorQuestionSourceResolver:
    def __init__(self, store: IndexMetadataStorePort) -> None:
        self._store = store
        self._sources: dict[str, BiMaterializationSource] = {}

    def resolve(self, question: BiQuestionRecord) -> BiMaterializationSource:
        index_id = str(question.index_id)
        cached = self._sources.get(index_id)
        if cached is not None:
            return self._require_matching_lineage(question, cached)
        metadata = self._store.get_index_metadata(index_id)
        source = BiMaterializationSource(
            file_name=str(metadata.get("file_name") or ""),
            workbook_hash=str(metadata.get("workbook_hash") or ""),
            index_id=IndexId(index_id),
        )
        self._sources[index_id] = source
        return self._require_matching_lineage(question, source)

    @staticmethod
    def _require_matching_lineage(
        question: BiQuestionRecord,
        source: BiMaterializationSource,
    ) -> BiMaterializationSource:
        if (
            source.workbook_hash != question.workbook_hash
            or source.index_id != question.index_id
        ):
            raise BiQuestionSourceError(code="question_source_lineage_mismatch")
        return source


class BiQuestionPipeline:
    def __init__(
        self,
        extractor: BiQuestionExtractorPort,
        source_resolver: BiQuestionSourceResolverPort,
    ) -> None:
        self._extractor = extractor
        self._source_resolver = source_resolver

    def execute(self, question: BiQuestionRecord) -> BiMetricExtractionResult:
        source = self._source_resolver.resolve(question)
        request = BiMetricExtractionRequest(
            request_id=str(question.question_id),
            metric_id=question.metric_id,
            period_id=question.period_id,
            period_label=str(question.period_id),
            source=source,
        )
        return self._extractor.extract_question(request, question.question_text)
