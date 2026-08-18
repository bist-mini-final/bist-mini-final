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
    USE_PGVECTOR,
    VECTOR_INDEX_DIR,
)
from ..embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from ..modules.base import ModuleExecutionError
from ..modules.cell_text_embedder import (
    CellTextEmbedderExecutionDTO,
    CellTextEmbedderModule,
)
from ..modules.cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput
from ..modules.exhaustive_cell_text_serializer import (
    ExhaustiveCellTextSerializerExecutionDTO,
    ExhaustiveCellTextSerializerModule,
)
from ..modules.vector_index_writer import (
    VectorIndexDTO,
    VectorIndexWriterInputDTO,
    VectorIndexWriterModule,
)
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
    """List all stored vector indexes (from both pgvector DB and local vector_db dir)."""
    index_dict: Dict[str, Dict[str, Any]] = {}

    # 1. Check pgvector store first if available
    pg = pgvector_store or PgVectorStore()
    if pg.is_connected():
        try:
            for idx in pg.list_indexes():
                idx["storage"] = "pgvector"
                index_dict[idx["index_id"]] = idx
        except Exception:
            pass

    # 2. Check local vector_db files
    if vector_index_dir.exists():
        for meta_path in sorted(vector_index_dir.glob("*.json")):
            npy_path = meta_path.with_suffix(".npy")
            if not npy_path.is_file():
                continue

            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            idx_id = data.get("index_id", meta_path.stem)
            total_size = meta_path.stat().st_size + npy_path.stat().st_size
            created_at = datetime.fromtimestamp(meta_path.stat().st_mtime, tz=timezone.utc).isoformat()

            if idx_id in index_dict:
                # Mark as dual / pgvector backed
                index_dict[idx_id]["total_size_bytes"] = total_size
            else:
                index_dict[idx_id] = {
                    "index_id": idx_id,
                    "file_name": data.get("file_name", "unknown"),
                    "workbook_hash": data.get("workbook_hash", ""),
                    "model": data.get("model", "text-embedding-3-large"),
                    "dimension": data.get("dimension", 0),
                    "document_count": data.get("document_count", 0),
                    "created_at": created_at,
                    "total_size_bytes": total_size,
                    "storage": "local",
                }

    return list(index_dict.values())


def get_vector_index_detail(
    index_id: str,
    sample_items_count: int = 15,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
) -> Dict[str, Any]:
    """Retrieve full metadata and sample serialized items for an index."""
    pg = pgvector_store or PgVectorStore()
    if pg.is_connected():
        try:
            return pg.get_index_detail(index_id, limit=sample_items_count)
        except Exception:
            pass

    store = vector_index_store or VectorIndexStore(VECTOR_INDEX_DIR)
    meta = store.metadata(index_id)
    items = meta.get("items") or []

    sample_items = [
        {
            "cell_id": doc.get("cell_id", ""),
            "sheet_name": doc.get("sheet_name", ""),
            "cell_coord": doc.get("cell_coord") or doc.get("cell_address", ""),
            "row_header": doc.get("row_header", []),
            "column_header": doc.get("column_header", []),
            "cell_value": doc.get("cell_value", ""),
            "text": doc.get("text", ""),
        }
        for doc in items[:sample_items_count]
    ]

    return {
        "index_id": index_id,
        "file_name": meta.get("file_name", ""),
        "workbook_hash": meta.get("workbook_hash", ""),
        "model": meta.get("model", ""),
        "dimension": meta.get("dimension", 0),
        "document_count": meta.get("document_count", len(items)),
        "storage": "local",
        "sample_items": sample_items,
    }


def delete_vector_index(
    index_id: str,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
) -> bool:
    """Delete an index from both pgvector and vector_db store."""
    deleted = False

    pg = pgvector_store or PgVectorStore()
    if pg.is_connected():
        try:
            if pg.delete(index_id):
                deleted = True
        except Exception:
            pass

    store = vector_index_store or VectorIndexStore(VECTOR_INDEX_DIR)
    index_path, metadata_path = store._paths(index_id)
    faiss_path = store.directory / f"{index_id}.faiss"

    if index_path.exists():
        index_path.unlink(missing_ok=True)
        deleted = True
    if metadata_path.exists():
        metadata_path.unlink(missing_ok=True)
        deleted = True
    if faiss_path.exists():
        faiss_path.unlink(missing_ok=True)

    return deleted


def search_vector_index(
    index_id: str,
    query_text: str,
    limit: int = 5,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
) -> List[Dict[str, Any]]:
    """Execute a test query search on the specified vector index (via pgvector or local store)."""
    # 1. Retrieve metadata for model name
    store = vector_index_store or VectorIndexStore(VECTOR_INDEX_DIR)
    model_name = "text-embedding-3-large"
    try:
        meta = store.metadata(index_id)
        model_name = meta.get("model", "text-embedding-3-large")
    except Exception:
        pg = pgvector_store or PgVectorStore()
        if pg.is_connected():
            try:
                pg_detail = pg.get_index_detail(index_id, limit=1)
                model_name = pg_detail.get("model", "text-embedding-3-large")
            except Exception:
                pass

    encoder = get_embedding_encoder(model_name, override_encoder=embedding_encoder)
    query_vectors = encoder.encode([query_text])
    if not query_vectors:
        raise ModuleExecutionError("질의 임베딩 생성에 실패했습니다")

    query_vector = query_vectors[0]

    # 2. Try searching pgvector first
    pg = pgvector_store or PgVectorStore()
    if pg.is_connected():
        try:
            hits = pg.search(index_id, query_vector, limit=limit)
            if hits:
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
                        "storage": "pgvector",
                    }
                    for score, doc in hits
                ]
        except Exception:
            pass

    # 3. Fallback to local numpy vector_index_store
    hits = store.search(index_id, query_vector, limit=limit)
    results: List[Dict[str, Any]] = []
    for score, doc in hits:
        results.append({
            "score": round(float(score), 4),
            "cell_id": doc.get("cell_id", ""),
            "sheet_name": doc.get("sheet_name", ""),
            "cell_coord": doc.get("cell_coord") or doc.get("cell_address", ""),
            "row_header": doc.get("row_header", []),
            "column_header": doc.get("column_header", []),
            "cell_value": doc.get("cell_value", ""),
            "text": doc.get("text", ""),
            "storage": "local",
        })

    return results


def ingest_excel_workbook(
    file_name: str,
    model: str = "text-embedding-3-large",
    variant_mode: Literal["header_only", "header_with_value", "both"] = "header_only",
    sheet_names: Optional[List[str]] = None,
    batch_size: int = 64,
    processed_dir: Path = PROCESSED_DATA_DIR,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
    embedding_artifact_store: Optional[EmbeddingArtifactStore] = None,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
) -> Dict[str, Any]:
    """End-to-end ingestion pipeline: Excel -> Serialized Cell Documents -> Dense Embeddings -> Vector DB (pgvector & local)."""
    catalog = WorkbookCatalog(processed_dir)
    workbook_path = catalog.resolve(file_name)
    workbook_hash = catalog.sha256(workbook_path)
    all_sheets = catalog.sheet_names(workbook_path)

    visible_sheets = [s for s in (sheet_names or all_sheets) if s in all_sheets]
    if not visible_sheets:
        raise ModuleExecutionError("인덱싱할 대상 시트가 없습니다")

    # Step 1: Serialization
    serializer = ExhaustiveCellTextSerializerModule(processed_dir=processed_dir)
    serializer_input = ExhaustiveCellTextSerializerExecutionDTO(
        file_name=file_name,
        workbook_hash=workbook_hash,
        sheet_names=visible_sheets,
        variant_mode=variant_mode,
        deduplicate_header_values=True,
    )
    serialized_result = serializer.execute(serializer_input)
    documents = serialized_result.get("items") or []
    if not documents:
        raise ModuleExecutionError("생성된 셀 문서가 없습니다")

    # Step 2: Embedding
    artifact_store = embedding_artifact_store or EmbeddingArtifactStore(EMBEDDING_ARTIFACT_DIR)
    embedder = CellTextEmbedderModule(encoder=embedding_encoder, artifact_store=artifact_store)
    embedder_input = CellTextEmbedderExecutionDTO(
        file_name=file_name,
        workbook_hash=workbook_hash,
        items=[CellTextDocumentDTO(**doc) for doc in documents],
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

    # Step 4: Write to PostgreSQL + pgvector if enabled / connected
    pg = pgvector_store or PgVectorStore()
    stored_in_pgvector = False
    if pg.is_connected():
        try:
            vectors = artifact_store.get(
                embedding_result["artifact_id"],
                len(embedding_result["items"]),
                embedding_result["dimension"],
            )
            pg_metadata = {
                "file_name": file_name,
                "workbook_hash": workbook_hash,
                "model": model,
                "dimension": embedding_result["dimension"],
                "document_count": len(embedding_result["items"]),
                "artifact_id": embedding_result["artifact_id"],
                "items": [item.model_dump(mode="json") for item in embedding_result["items"]],
            }
            pg.put(index_id, vectors, pg_metadata)
            stored_in_pgvector = True
        except Exception:
            stored_in_pgvector = False

    return {
        "index_id": index_id,
        "file_name": file_name,
        "workbook_hash": workbook_hash,
        "model": model,
        "dimension": index_result["dimension"],
        "document_count": index_result["document_count"],
        "sheet_count": len(visible_sheets),
        "sheets": visible_sheets,
        "storage": "pgvector" if stored_in_pgvector else "local",
    }
