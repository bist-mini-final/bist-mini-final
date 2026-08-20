import math
import re
from collections import Counter
from typing import Any, Dict, List, Tuple, cast

from pydantic import BaseModel, Field

from .base import ExecutableModule, ModuleConfigDTO, ModuleDefinition, ModuleInputDTO
from .cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput
from .decomposer import SubqueriesDTO
from .retrieval_models import RankedSearchResultDTO


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\-%_]+|[가-힣]+")


def tokenize(text: str) -> List[str]:
    return TOKEN_PATTERN.findall(text.lower())


class Bm25RetrieverInputDTO(ModuleInputDTO):
    query_input: SubqueriesDTO = Field(description="질문 측 서브쿼리 입력 포트")
    document_input: CellTextSerializerOutput = Field(
        description="Excel 측 구조화 셀 문서 입력 포트"
    )


class Bm25RetrieverConfigDTO(ModuleConfigDTO):
    k1: float = Field(
        default=1.5,
        gt=0,
        le=10,
        description="Okapi BM25 term-frequency saturation 상수",
    )
    b: float = Field(
        default=0.75,
        ge=0,
        le=1,
        description="Okapi BM25 문서 길이 정규화 상수",
    )
    top_k: int = Field(
        default=1000,
        gt=0,
        le=10000,
        description="각 서브쿼리별 BM25 후보 최대 개수",
    )


class Bm25RetrieverExecutionDTO(Bm25RetrieverInputDTO, Bm25RetrieverConfigDTO):
    """Internal union of retrieval data and BM25 policy."""


class Bm25RetrieverModule(ExecutableModule):
    definition = ModuleDefinition(
        type="bm25_retriever",
        label="BM25 Keyword Retriever",
        category="Logic",
        description="서브쿼리와 Excel 셀 문서를 받아 Okapi BM25 순위를 계산합니다.",
        inputs=["query_input", "document_input"],
        outputs=["bm25_result"],
        config_fields=["k1", "b", "top_k"],
        raw_output=True,
        version="4",
    )
    input_model = Bm25RetrieverInputDTO
    config_model = Bm25RetrieverConfigDTO
    execution_model = Bm25RetrieverExecutionDTO
    output_model = RankedSearchResultDTO

    @staticmethod
    def _document_scores(
        query: str,
        corpus: List[List[str]],
        document_frequencies: List[Counter],
        inverse_document_frequencies: Dict[str, float],
        average_document_length: float,
        k1: float,
        b: float,
    ) -> List[float]:
        scores = [0.0] * len(corpus)
        for token in tokenize(query):
            inverse_frequency = inverse_document_frequencies.get(token)
            if inverse_frequency is None:
                continue
            for index, frequencies in enumerate(document_frequencies):
                frequency = frequencies.get(token)
                if frequency is None:
                    continue
                document_length = len(corpus[index])
                numerator = frequency * (k1 + 1)
                denominator = frequency + k1 * (
                    1 - b + b * document_length / average_document_length
                )
                scores[index] += inverse_frequency * numerator / denominator
        return scores

    @staticmethod
    def _rank_query(
        documents: List[CellTextDocumentDTO],
        scores: List[float],
        query: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        best_by_cell: Dict[str, Tuple[float, CellTextDocumentDTO, str]] = {}
        for document, score in zip(documents, scores):
            if score <= 0:
                continue
            current = best_by_cell.get(document.cell_id)
            if current is None or score > current[0]:
                best_by_cell[document.cell_id] = (score, document, query)

        ranked = sorted(
            best_by_cell.values(),
            key=lambda item: (-item[0], item[1].cell_id),
        )[:top_k]
        return [
            {
                "rank": rank,
                "cell_id": document.cell_id,
                "score": round(score, 10),
                "text": document.text,
                "matched_subquery": matched_query,
            }
            for rank, (score, document, matched_query) in enumerate(ranked, start=1)
        ]

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(Bm25RetrieverExecutionDTO, payload)
        documents = input_data.document_input.items
        query_context = input_data.query_input.query_context.model_dump(mode="json")
        document_context = {
            "file_name": input_data.document_input.file_name,
            "workbook_hash": input_data.document_input.workbook_hash,
        }
        if not documents:
            return {
                "query_context": query_context,
                "document_context": document_context,
                "items": [],
            }

        # 1. Corpus tokenization & document lengths
        corpus = [tokenize(document.text) for document in documents]
        doc_lengths = [len(tokens) for tokens in corpus]
        document_count = len(corpus)
        average_document_length = (
            sum(doc_lengths) / document_count
        ) if document_count > 0 else 1.0

        # 2. Build Inverted Index: token -> list of (doc_index, term_frequency)
        inverted_index: Dict[str, List[Tuple[int, int]]] = {}
        for doc_idx, tokens in enumerate(corpus):
            counts = Counter(tokens)
            for token, freq in counts.items():
                if token not in inverted_index:
                    inverted_index[token] = []
                inverted_index[token].append((doc_idx, freq))

        # 3. Calculate IDF for all unique tokens in corpus
        inverse_document_frequencies = {
            token: math.log(
                1.0 + (document_count - len(postings) + 0.5) / (len(postings) + 0.5)
            )
            for token, postings in inverted_index.items()
        }

        # 4. High-performance inverted index scoring per subquery
        ranked_items: List[Dict[str, Any]] = []
        k1 = input_data.k1
        b = input_data.b
        top_k = input_data.top_k

        for query in input_data.query_input.subqueries:
            scores: Dict[int, float] = {}
            for token in tokenize(query):
                inv_freq = inverse_document_frequencies.get(token)
                if inv_freq is None:
                    continue
                for doc_idx, freq in inverted_index.get(token, []):
                    doc_len = doc_lengths[doc_idx]
                    num = freq * (k1 + 1)
                    denom = freq + k1 * (
                        1 - b + b * doc_len / average_document_length
                    )
                    scores[doc_idx] = scores.get(doc_idx, 0.0) + (
                        inv_freq * num / denom
                    )

            best_by_cell: Dict[str, Tuple[float, CellTextDocumentDTO, str]] = {}
            for doc_idx, score in scores.items():
                if score <= 0:
                    continue
                document = documents[doc_idx]
                current = best_by_cell.get(document.cell_id)
                if current is None or score > current[0]:
                    best_by_cell[document.cell_id] = (score, document, query)

            ranked = sorted(
                best_by_cell.values(),
                key=lambda item: (-item[0], item[1].cell_id),
            )[:top_k]

            ranked_items.extend(
                [
                    {
                        "rank": rank,
                        "cell_id": document.cell_id,
                        "score": round(score, 10),
                        "text": document.text,
                        "matched_subquery": query,
                    }
                    for rank, (score, document, _) in enumerate(ranked, start=1)
                ]
            )

        return {
            "query_context": query_context,
            "document_context": document_context,
            "items": ranked_items,
        }
