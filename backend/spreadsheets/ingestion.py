"""Excel Ingestion and Vector Index Management Service with PostgreSQL + pgvector support."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence

from ..core.settings import (
    EMBEDDING_ARTIFACT_DIR,
    PROCESSED_DATA_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    USE_PGVECTOR,
    VECTOR_INDEX_DIR,
)
from ..embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from ..modules.base import ModuleExecutionError
from ..modules.cell_text_embedder import (
    CellTextEmbedderExecutionDTO,
    CellTextEmbedderModule,
)
from ..modules.cell_text_serializer import (
    CellTextDocumentDTO,
    CellTextSerializerInputDTO,
    CellTextSerializerModule,
    CellTextSerializerOutput,
)
from ..modules.exhaustive_cell_text_serializer import (
    ExhaustiveCellTextSerializerExecutionDTO,
    ExhaustiveCellTextSerializerModule,
)
from ..modules.luna_vlm_structure_detector import (
    LunaVlmStructureDetectorExecutionDTO,
    LunaVlmStructureDetectorModule,
)
from ..modules.vector_index_writer import (
    VectorIndexDTO,
    VectorIndexWriterInputDTO,
    VectorIndexWriterModule,
)
from ..modules.pgvector_index_writer import (
    PgVectorIndexWriterInputDTO,
    PgVectorIndexWriterModule,
)
from .company_extractor import extract_company_metadata
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PgVectorStore
from ..storage.vector_index import VectorIndexStore
from .workbook_catalog import SUPPORTED_WORKBOOK_SUFFIXES, WorkbookCatalog


def list_processed_files(
    processed_dir: Path = PROCESSED_DATA_DIR,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
) -> List[Dict[str, Any]]:
    """List all files in data/processed directory with sheet details and index status."""
    if not processed_dir.exists():
        return []

    existing_indexes = list_vector_indexes(
        vector_index_dir=(vector_index_store.directory if vector_index_store else VECTOR_INDEX_DIR),
        pgvector_store=pgvector_store,
    )
    index_map_by_hash: Dict[str, List[str]] = {}
    for idx in existing_indexes:
        wb_hash = idx.get("workbook_hash")
        if wb_hash:
            index_map_by_hash.setdefault(wb_hash, []).append(idx["index_id"])

    files: List[Dict[str, Any]] = []
    for path in sorted(processed_dir.iterdir()):
        if not path.is_file() or path.name.startswith((".", "~$")):
            continue

        stat = path.stat()
        suffix = path.suffix.lower()
        file_type = (
            "excel"
            if suffix in SUPPORTED_WORKBOOK_SUFFIXES
            else ("parquet" if suffix == ".parquet" else ("json" if suffix == ".json" else "other"))
        )

        sheet_names: List[str] = []
        workbook_hash: str = ""

        if file_type == "excel":
            try:
                workbook_hash = WorkbookCatalog.sha256(path)
                sheet_names = WorkbookCatalog.sheet_names(path)
            except Exception:
                sheet_names = []
        elif file_type == "parquet":
            workbook_hash = path.stem.replace("_prebuilt", "")
        elif file_type == "json":
            try:
                wb_digest = hashlib.sha256()
                with path.open("rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        wb_digest.update(chunk)
                workbook_hash = wb_digest.hexdigest()
            except Exception:
                workbook_hash = ""

        files.append({
            "file_name": path.name,
            "size_bytes": stat.st_size,
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "file_type": file_type,
            "sheet_names": sheet_names,
            "workbook_hash": workbook_hash,
            "associated_index_ids": index_map_by_hash.get(workbook_hash, []),
        })

    return files


def preview_excel_sheet(
    file_name: str,
    sheet_name: Optional[str] = None,
    max_rows: int = 15,
    max_cols: int = 15,
    processed_dir: Path = PROCESSED_DATA_DIR,
) -> Dict[str, Any]:
    """Read a preview table from a specific sheet in an Excel workbook."""
    catalog = WorkbookCatalog(processed_dir)
    path = catalog.resolve(file_name)

    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        available_sheets = WorkbookCatalog.sheet_names(path)
        target_sheet_name = sheet_name or (available_sheets[0] if available_sheets else wb.sheetnames[0])
        if target_sheet_name not in wb.sheetnames:
            raise ModuleExecutionError(f"시트를 찾을 수 없습니다: {target_sheet_name}")

        ws = wb[target_sheet_name]
        rows: List[List[Any]] = []
        for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if r_idx >= max_rows:
                break
            rows.append([str(cell) if cell is not None else "" for cell in list(row)[:max_cols]])

        return {
            "file_name": file_name,
            "sheet_name": target_sheet_name,
            "available_sheets": available_sheets,
            "total_sheets": len(available_sheets),
            "preview_rows": rows,
        }
    finally:
        wb.close()


def list_vector_indexes(
    vector_index_dir: Path = VECTOR_INDEX_DIR,
    pgvector_store: Optional[PgVectorStore] = None,
) -> List[Dict[str, Any]]:
    """List all stored vector indexes directly from pgvector DB."""
    pg = pgvector_store or PgVectorStore()
    if pg.is_connected():
        return pg.list_indexes()
    return []


def get_vector_index_detail(
    index_id: str,
    sample_items_count: int = 15,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
) -> Dict[str, Any]:
    """Retrieve full metadata and sample serialized items directly from pgvector DB."""
    pg = pgvector_store or PgVectorStore()
    if not pg.is_connected():
        raise ModuleExecutionError("pgvector 데이터베이스에 연결할 수 없습니다. Docker 컨테이너를 구동해주세요.")
    return pg.get_index_detail(index_id, limit=sample_items_count)


def delete_vector_index(
    index_id: str,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
) -> bool:
    """Delete an index directly from pgvector DB."""
    pg = pgvector_store or PgVectorStore()
    if not pg.is_connected():
        raise ModuleExecutionError("pgvector 데이터베이스에 연결할 수 없습니다")
    return pg.delete(index_id)


def search_vector_index(
    index_id: str,
    query_text: str,
    limit: int = 5,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
) -> List[Dict[str, Any]]:
    """Execute cosine similarity search directly against pgvector DB using LangChain."""
    pg = pgvector_store or PgVectorStore()
    if not pg.is_connected():
        raise ModuleExecutionError("pgvector 데이터베이스에 연결할 수 없습니다")

    # Retrieve model name from pgvector metadata
    model_name = "text-embedding-3-large"
    try:
        detail = pg.get_index_detail(index_id, limit=1)
        model_name = detail.get("model") or "text-embedding-3-large"
    except Exception:
        pass

    hits = pg.search(
        index_id,
        query_text=query_text,
        model_name=model_name,
        embedding_encoder=embedding_encoder,
        limit=limit,
    )
    return [
        {
            "score": round(float(score), 4),
            "cell_id": doc.get("cell_id", ""),
            "sheet_name": doc.get("sheet_name", ""),
            "cell_coord": doc.get("cell_coord") or doc.get("cell_address", ""),
            "row_header": doc.get("row_header", []),
            "column_header": doc.get("column_header", []),
            "cell_value": doc.get("cell_value", ""),
            "text": doc.get("text", ""),
            "storage": "pgvector (LangChain)",
        }
        for score, doc in hits
    ]


def ingest_excel_workbook(
    file_name: str,
    model: str = "text-embedding-3-large",
    variant_mode: Literal["header_only", "header_with_value", "both"] = "header_only",
    sheet_names: Optional[List[str]] = None,
    batch_size: int = 64,
    structure_mode: Literal["auto", "luna_vlm", "exhaustive"] = "auto",
    processed_dir: Path = PROCESSED_DATA_DIR,
    spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
    embedding_artifact_store: Optional[EmbeddingArtifactStore] = None,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
) -> Dict[str, Any]:
    """End-to-end ingestion pipeline: Excel -> Luna VLM Structure Detector -> Structured Cell Serializer -> Dense Embeddings -> Vector DB (pgvector & local)."""
    catalog = WorkbookCatalog(processed_dir)
    workbook_path = catalog.resolve(file_name)
    workbook_hash = catalog.sha256(workbook_path)
    all_sheets = catalog.sheet_names(workbook_path)

    visible_sheets = [s for s in (sheet_names or all_sheets) if s in all_sheets]
    if not visible_sheets:
        raise ModuleExecutionError("인덱싱할 대상 시트가 없습니다")

    # Step 0: Extract Company Entity Metadata (LLM with heuristic fallback)
    company_info = extract_company_metadata(workbook_path, file_name, visible_sheets)
    company_name = company_info.get("display_name") or company_info.get("company_name", "")
    ticker = company_info.get("ticker", "")

    # Step 1: Structure Detection & Cell Text Serialization (Luna VLM + Structured Serializer)
    documents: List[CellTextDocumentDTO] = []
    used_pipeline = "exhaustive"

    if structure_mode in ("luna_vlm", "auto") and os.getenv("OPENAI_API_KEY"):
        try:
            detector = LunaVlmStructureDetectorModule(
                artifact_dir=spreadsheet_artifact_dir,
                catalog=catalog,
            )
            detector_input = LunaVlmStructureDetectorExecutionDTO(
                file_name=file_name,
                workbook_hash=workbook_hash,
                sheet_names=visible_sheets,
                model="gpt-5.6-luna",
                reasoning_effort="low",
                max_rows=400,
                max_columns=60,
                max_context_cells=50000,
            )
            structure_output = detector.execute(detector_input)
            tables = structure_output.get("tables") or []
            if tables:
                serializer = CellTextSerializerModule(processed_dir=processed_dir)
                serializer_input = CellTextSerializerInputDTO(
                    file_name=file_name,
                    workbook_hash=workbook_hash,
                    tables=tables,
                )
                serialized = serializer.execute(serializer_input)
                raw_docs = serialized.get("items") or []
                documents = [
                    d if isinstance(d, CellTextDocumentDTO) else CellTextDocumentDTO(**d)
                    for d in raw_docs
                ]
                if documents:
                    used_pipeline = "luna_vlm_structured"
        except Exception:
            documents = []

    if not documents:
        # Fallback to exhaustive cell serializer
        serializer = ExhaustiveCellTextSerializerModule(processed_dir=processed_dir)
        serializer_input = ExhaustiveCellTextSerializerExecutionDTO(
            file_name=file_name,
            workbook_hash=workbook_hash,
            sheet_names=visible_sheets,
            variant_mode=variant_mode,
            deduplicate_header_values=True,
        )
        serialized_result = serializer.execute(serializer_input)
        raw_docs = serialized_result.get("items") or []
        documents = [
            d if isinstance(d, CellTextDocumentDTO) else CellTextDocumentDTO(**d)
            for d in raw_docs
        ]
        used_pipeline = "exhaustive"

    if not documents:
        raise ModuleExecutionError("생성된 셀 문서가 없습니다")

    # Step 2: Embedding
    artifact_store = embedding_artifact_store or EmbeddingArtifactStore(EMBEDDING_ARTIFACT_DIR)
    embedder = CellTextEmbedderModule(encoder=embedding_encoder, artifact_store=artifact_store)
    embedder_input = CellTextEmbedderExecutionDTO(
        file_name=file_name,
        workbook_hash=workbook_hash,
        items=documents,
        model=model,
        batch_size=batch_size,
    )
    embedding_result = embedder.execute(embedder_input)

    # Step 3: Vector Index Writing (Local store)
    index_store = vector_index_store or VectorIndexStore(VECTOR_INDEX_DIR)
    writer = VectorIndexWriterModule(artifact_store=artifact_store, index_store=index_store)
    writer_input = VectorIndexWriterInputDTO(
        file_name=file_name,
        workbook_hash=workbook_hash,
        model=embedding_result["model"],
        artifact_id=embedding_result["artifact_id"],
        dimension=embedding_result["dimension"],
        items=embedding_result["items"],
    )
    index_result = writer.execute(writer_input)
    index_id = index_result["index_id"]

    # Step 4: Write to PostgreSQL full ERD + pgvector via PgVectorIndexWriterModule
    pg = pgvector_store or PgVectorStore()
    db_mgr = DatabaseManager()
    stored_in_pgvector = False

    if db_mgr.is_connected():
        try:
            # 1. Execute modular PgVectorIndexWriterModule (persists source_files, chunks, indexes, embeddings)
            pg_writer = PgVectorIndexWriterModule(
                artifact_store=artifact_store,
                db_manager=db_mgr,
                pgvector_store=pg,
                embedding_encoder=embedding_encoder,
            )
            pg_writer_input = PgVectorIndexWriterInputDTO(
                file_name=file_name,
                workbook_hash=workbook_hash,
                model=embedding_result["model"],
                artifact_id=embedding_result["artifact_id"],
                dimension=embedding_result["dimension"],
                items=embedding_result["items"],
            )
            pg_writer.execute(pg_writer_input)

            # 2. Save sheets metadata with accurate row and column counts
            sheet_dims: Dict[str, Tuple[int, int]] = {}
            try:
                import openpyxl
                wb_dim = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
                for s in wb_dim.sheetnames:
                    ws_dim = wb_dim[s]
                    sheet_dims[s] = (ws_dim.max_row or 0, ws_dim.max_column or 0)
                wb_dim.close()
            except Exception:
                pass

            sheets_data = []
            for s_idx, s_name in enumerate(visible_sheets):
                s_rows, s_cols = sheet_dims.get(s_name, (0, 0))
                # Fallback to document coordinates if openpyxl was unavailable
                if s_rows == 0:
                    sheet_docs = [d for d in documents if getattr(d, "sheet_name", "") == s_name]
                    s_rows = len(sheet_docs)

                sheet_tables = [
                    t.model_dump(mode="json") if hasattr(t, "model_dump") else t
                    for t in tables
                    if (getattr(t, "sheet_name", None) or (isinstance(t, dict) and t.get("sheet_name"))) == s_name
                ] if ('tables' in locals() and tables) else []

                sheets_data.append({
                    "sheet_name": s_name,
                    "sheet_index": s_idx,
                    "is_visible": True,
                    "row_count": s_rows,
                    "column_count": s_cols,
                    "detected_tables": sheet_tables,
                })
            db_mgr.save_sheets(file_id=workbook_hash, sheets_info=sheets_data)
            stored_in_pgvector = True

            # 3. Attach company metadata and sheet list to pgvector collection
            if company_name:
                try:
                    pg.update_index_company(index_id, company_name)
                except Exception:
                    pass
        except Exception as err:
            import traceback
            traceback.print_exc()
            stored_in_pgvector = False

    raw_tables = [
        t.model_dump(mode="json") if hasattr(t, "model_dump") else t
        for t in (tables if ('tables' in locals() and tables) else [])
    ]
    luna_out = {
        "file_name": file_name,
        "workbook_hash": workbook_hash,
        "sheet_names": visible_sheets,
        "tables": raw_tables,
    } if raw_tables else None

    return {
        "index_id": index_id,
        "file_name": file_name,
        "workbook_hash": workbook_hash,
        "company_name": company_name,
        "ticker": ticker,
        "model": model,
        "dimension": index_result["dimension"],
        "document_count": index_result["document_count"],
        "sheet_count": len(visible_sheets),
        "sheets": visible_sheets,
        "sheet_names": visible_sheets,
        "tables": raw_tables,
        "luna_output": luna_out,
        "pipeline": used_pipeline,
        "duration_seconds": embedding_result.get("duration_seconds"),
        "total_tokens": embedding_result.get("total_tokens"),
        "estimated_cost_usd": embedding_result.get("estimated_cost_usd"),
        "estimated_cost_krw": embedding_result.get("estimated_cost_krw"),
        "batch_size": batch_size,
        "storage": "pgvector (LangChain)" if stored_in_pgvector else "local",
    }
