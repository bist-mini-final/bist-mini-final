import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from ..core.settings import PROCESSED_DATA_DIR, VECTOR_INDEX_DIR
from ..storage.vector_index import VectorIndexStore
from .base import (
    EmptyModuleConfigDTO,
    ExecutableModule,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
    ModuleDTO,
)


class PrebuiltIndexLoaderInputDTO(ModuleInputDTO):
    file_name: str = Field(
        default="SPG_Company_KeyStats_v3_prebuilt.parquet",
        min_length=1,
        description="data/processed 또는 data/vector_db에 공유된 사전 구축 인덱스 (.parquet / .json) 파일명",
    )


class DocumentOutputDTO(ModuleDTO):
    file_name: str
    workbook_hash: str
    items: List[Dict[str, Any]]


class IndexOutputDTO(ModuleDTO):
    index_id: str
    file_name: str
    workbook_hash: str
    model: str
    dimension: int
    document_count: int


class PrebuiltIndexLoaderOutput(ModuleDTO):
    document_output: DocumentOutputDTO
    index_output: IndexOutputDTO


class PrebuiltIndexLoaderModule(ExecutableModule):
    _PARQUET_ITEM_COLUMNS = (
        "cell_id",
        "sheet_name",
        "cell_coord",
        "row_header",
        "column_header",
        "cell_value",
        "variant",
        "text",
    )

    definition = ModuleDefinition(
        type="prebuilt_index_loader",
        label="Pre-built Vector Index Loader",
        category="Source",
        description="공유된 사전 인덱싱 단일 파일(.parquet / .json)을 로드하여 document_output과 index_output을 즉시 생성합니다.",
        inputs=[],
        outputs=["document_output", "index_output"],
        config_fields=[],
        raw_output=False,
        version="2",
    )
    input_model = PrebuiltIndexLoaderInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = PrebuiltIndexLoaderInputDTO
    output_model = PrebuiltIndexLoaderOutput

    def __init__(
        self,
        vector_index_store: Optional[VectorIndexStore] = None,
        search_dirs: Optional[List[Path]] = None,
    ) -> None:
        self.vector_index_store = vector_index_store or VectorIndexStore()
        self.search_dirs = search_dirs or [PROCESSED_DATA_DIR, VECTOR_INDEX_DIR]

    def _find_file(self, file_name: str) -> Path:
        target_name = file_name.strip()
        if not target_name:
            raise ModuleExecutionError("파일 이름이 지정되지 않았습니다")

        # 1. Direct path check if absolute or relative
        path = Path(target_name)
        if path.is_file():
            return path

        # 2. Check search directories
        for directory in self.search_dirs:
            candidate = directory / target_name
            if candidate.is_file():
                return candidate
            if target_name.endswith(".json"):
                candidate_parquet = directory / (target_name[:-5] + ".parquet")
                if candidate_parquet.is_file():
                    return candidate_parquet
            if target_name.endswith(".parquet"):
                candidate_json = directory / (target_name[:-8] + ".json")
                if candidate_json.is_file():
                    return candidate_json

        raise ModuleExecutionError(
            f"사전 구축 인덱스 파일을 찾을 수 없습니다: {target_name}. "
            f"파일을 data/processed/ 디렉터리에 복사해 주세요."
        )

    def _read_data(self, file_path: Path) -> Dict[str, Any]:
        if file_path.suffix.lower() == ".parquet":
            try:
                import numpy
                import pyarrow as pa
                import pyarrow.parquet as pq
            except ImportError as error:
                raise ModuleExecutionError(
                    "Parquet 인덱스를 읽으려면 pyarrow가 필요합니다. "
                    "pip install -r requirements.txt를 실행해 주세요"
                ) from error

            try:
                parquet_file = pq.ParquetFile(file_path)
                available_columns = set(parquet_file.schema_arrow.names)
                required_columns = {*self._PARQUET_ITEM_COLUMNS, "embedding"}
                missing_columns = sorted(required_columns - available_columns)
                if missing_columns:
                    raise ValueError(
                        "필수 컬럼 누락: " + ", ".join(missing_columns)
                    )

                schema_meta = parquet_file.schema_arrow.metadata or {}
                file_name = (
                    schema_meta.get(b"file_name", b"").decode("utf-8")
                    or file_path.name
                )
                workbook_hash = (
                    schema_meta.get(b"workbook_hash", b"").decode("utf-8") or ""
                )
                model_name = (
                    schema_meta.get(b"model", b"").decode("utf-8")
                    or "text-embedding-3-large"
                )

                item_table = parquet_file.read(
                    columns=list(self._PARQUET_ITEM_COLUMNS),
                    use_threads=True,
                )
                pydict = item_table.to_pydict()
                num_rows = parquet_file.metadata.num_rows

                items: List[Dict[str, Any]] = []
                for i in range(num_rows):
                    row_h = pydict["row_header"][i]
                    col_h = pydict["column_header"][i]
                    items.append(
                        {
                            "cell_id": pydict["cell_id"][i],
                            "sheet_name": pydict["sheet_name"][i],
                            "cell_coord": pydict["cell_coord"][i],
                            "row_header": list(row_h) if isinstance(row_h, (list, tuple)) else [str(row_h)],
                            "column_header": list(col_h) if isinstance(col_h, (list, tuple)) else [str(col_h)],
                            "cell_value": pydict["cell_value"][i],
                            "variant": pydict["variant"][i],
                            "text": pydict["text"][i],
                        }
                    )

                vectors = None
                vector_dimension: Optional[int] = None
                vector_offset = 0
                for batch in parquet_file.iter_batches(
                    batch_size=256,
                    columns=["embedding"],
                    use_threads=True,
                ):
                    embedding_array = batch.column(0)
                    if embedding_array.null_count:
                        raise ValueError("embedding 컬럼에 null 벡터가 있습니다")

                    if pa.types.is_fixed_size_list(embedding_array.type):
                        batch_dimension = embedding_array.type.list_size
                        flat_values = embedding_array.values.to_numpy(
                            zero_copy_only=False
                        )
                    elif (
                        pa.types.is_list(embedding_array.type)
                        or pa.types.is_large_list(embedding_array.type)
                    ):
                        offsets = embedding_array.offsets.to_numpy(
                            zero_copy_only=False
                        )
                        lengths = numpy.diff(offsets)
                        if len(lengths) == 0:
                            continue
                        batch_dimension = int(lengths[0])
                        if batch_dimension <= 0 or not numpy.all(
                            lengths == batch_dimension
                        ):
                            raise ValueError(
                                "embedding 벡터의 차원이 일정하지 않습니다"
                            )
                        value_start = int(offsets[0])
                        value_end = int(offsets[-1])
                        flat_values = embedding_array.values.slice(
                            value_start,
                            value_end - value_start,
                        ).to_numpy(zero_copy_only=False)
                    else:
                        raise ValueError(
                            "embedding 컬럼은 list<float> 형식이어야 합니다"
                        )

                    if vector_dimension is None:
                        vector_dimension = batch_dimension
                        vectors = numpy.empty(
                            (num_rows, vector_dimension),
                            dtype="float32",
                        )
                    elif vector_dimension != batch_dimension:
                        raise ValueError(
                            "embedding 벡터의 차원이 일정하지 않습니다"
                        )

                    batch_rows = batch.num_rows
                    batch_matrix = numpy.asarray(
                        flat_values,
                        dtype="float32",
                    ).reshape(batch_rows, vector_dimension)
                    vectors[
                        vector_offset : vector_offset + batch_rows
                    ] = batch_matrix
                    vector_offset += batch_rows

                if vectors is None or vector_offset != num_rows:
                    raise ValueError(
                        "embedding 벡터 개수가 Parquet 행 개수와 일치하지 않습니다"
                    )
                return {
                    "file_name": file_name,
                    "workbook_hash": workbook_hash,
                    "model": model_name,
                    "items": items,
                    "_vectors": vectors,
                }
            except Exception as error:
                raise ModuleExecutionError(
                    f"사전 구축 Parquet 인덱스 파일 해석 실패: {file_path.name} "
                    f"({type(error).__name__}: {error})"
                ) from error

        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise ModuleExecutionError(
                f"사전 구축 인덱스 파일 해석 실패: {file_path.name}"
            ) from error

    @staticmethod
    def _parse_cell_text(
        text: str,
    ) -> tuple[List[str], List[str], str]:
        """Parse the 4-field serialization format:

        ``Sheet: <name> | Row Header: <h> | Column Header: <h> | Cell Value: <v>``

        Returns (row_header, column_header, cell_value).  Falls back to
        ``["?"]`` / ``"?"`` when a segment is missing or still contains only
        the placeholder.
        """
        parts: Dict[str, str] = {}
        for segment in text.split(" | "):
            key, _, value = segment.partition(": ")
            if key:
                parts[key.strip()] = value.strip()

        UNKNOWN = "?"

        def split_header(raw: str) -> List[str]:
            if not raw or raw == UNKNOWN:
                return [UNKNOWN]
            return [h.strip() for h in raw.split(" > ") if h.strip()]

        row_header = split_header(parts.get("Row Header", UNKNOWN))
        col_header = split_header(parts.get("Column Header", UNKNOWN))
        cell_value = parts.get("Cell Value", UNKNOWN) or UNKNOWN
        return row_header, col_header, cell_value

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(PrebuiltIndexLoaderInputDTO, payload)
        file_path = self._find_file(input_data.file_name)

        raw_data = self._read_data(file_path)

        required_keys = {"file_name", "workbook_hash", "model", "items"}
        if not required_keys.issubset(raw_data.keys()):
            raise ModuleExecutionError(
                f"인덱스 파일 형식이 올바르지 않습니다. 필수키: {required_keys}"
            )

        file_name = raw_data["file_name"]
        workbook_hash = raw_data["workbook_hash"]
        model_name = raw_data["model"]
        items = raw_data["items"]
        vector_matrix = raw_data.get("_vectors")

        if not items or not isinstance(items, list):
            raise ModuleExecutionError("인덱스 파일에 셀 문서 항목(items)이 없습니다")
        if vector_matrix is not None and len(vector_matrix) != len(items):
            raise ModuleExecutionError(
                "Parquet embedding 벡터 개수와 셀 문서 개수가 일치하지 않습니다"
            )

        # Extract texts, embeddings, and cell metadata
        doc_items: List[Dict[str, Any]] = []
        vectors: Any = vector_matrix if vector_matrix is not None else []
        metadata_list: List[Dict[str, Any]] = []

        def _clean_excel_coord(raw: Any, fallback_index: int) -> str:
            if raw and isinstance(raw, str):
                candidate = raw.strip()
                import re
                if re.fullmatch(r"[A-Za-z]{1,3}[1-9][0-9]*", candidate):
                    return candidate.upper()
            return f"A{fallback_index + 1}"

        for index, item in enumerate(items):
            text = item.get("text", "")
            vector = (
                vector_matrix[index]
                if vector_matrix is not None
                else item.get("embedding", [])
            )
            sheet_name = item.get("sheet_name", "Sheet1")
            raw_coord = item.get("cell_coord") or item.get("cell_address")
            cell_coord = _clean_excel_coord(raw_coord, index)

            if not text or len(vector) == 0:
                raise ModuleExecutionError(
                    f"항목 {index}에 text 또는 embedding 벡터가 누락되었습니다"
                )

            # Recover structured fields from the serialized text when the
            # stored values are missing or still contain the '?' placeholder.
            # This makes prebuilt indexes built before the full-field export
            # work correctly with ContextExpanderModule.
            raw_row_header: Optional[List[str]] = item.get("row_header")
            raw_col_header: Optional[List[str]] = item.get("column_header")
            raw_cell_value: Optional[str] = item.get("cell_value")

            _unknown = ["?"]
            needs_parse = (
                not raw_row_header
                or raw_row_header == _unknown
                or not raw_col_header
                or raw_col_header == _unknown
                or not raw_cell_value
                or raw_cell_value == "?"
            )
            if needs_parse:
                parsed_row, parsed_col, parsed_val = self._parse_cell_text(text)
                if not raw_row_header or raw_row_header == _unknown:
                    raw_row_header = parsed_row
                if not raw_col_header or raw_col_header == _unknown:
                    raw_col_header = parsed_col
                if not raw_cell_value or raw_cell_value == "?":
                    raw_cell_value = parsed_val

            doc_item = {
                "cell_id": item.get("cell_id") or f"{sheet_name} Cell {cell_coord}",
                "sheet_name": sheet_name,
                "cell_coord": cell_coord,
                "row_header": raw_row_header or ["?"],
                "column_header": raw_col_header or ["?"],
                "cell_value": raw_cell_value or "?",
                "variant": item.get("variant") or "header_with_value",
                "text": text,
                "embedding_index": index,
            }
            doc_items.append(doc_item)
            if vector_matrix is None:
                vectors.append(vector)
            metadata_list.append(doc_item)

        if vector_matrix is not None:
            if vector_matrix.ndim != 2 or vector_matrix.shape[1] <= 0:
                raise ModuleExecutionError("임베딩 벡터의 차원이 올바르지 않습니다")
            dimension = int(vector_matrix.shape[1])
        else:
            dimensions = {len(v) for v in vectors}
            if len(dimensions) != 1 or 0 in dimensions:
                raise ModuleExecutionError("임베딩 벡터의 차원이 일정하지 않습니다")
            dimension = dimensions.pop()

        # Compute deterministic 64-char sha256 index_id based on payload
        artifact_payload = json.dumps(
            {
                "workbook_hash": workbook_hash,
                "model": model_name,
                "texts": [item["text"] for item in doc_items],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        artifact_id = hashlib.sha256(artifact_payload.encode("utf-8")).hexdigest()
        index_id = VectorIndexStore.index_id(artifact_id)

        # Store vectors into VectorIndexStore
        self.vector_index_store.put(
            index_id=index_id,
            vectors=vectors,
            metadata={
                "file_name": file_name,
                "workbook_hash": workbook_hash,
                "model": model_name,
                "dimension": dimension,
                "document_count": len(doc_items),
                "items": metadata_list,
            },
        )

        return {
            "document_output": {
                "file_name": file_name,
                "workbook_hash": workbook_hash,
                "items": [
                    {k: v for k, v in doc.items() if k != "embedding_index"}
                    for doc in doc_items
                ],
            },
            "index_output": {
                "index_id": index_id,
                "file_name": file_name,
                "workbook_hash": workbook_hash,
                "model": model_name,
                "dimension": dimension,
                "document_count": len(doc_items),
            },
        }
