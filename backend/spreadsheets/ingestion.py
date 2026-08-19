"""Read-only data-source helpers around Excel files and pgvector indexes."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.settings import PROCESSED_DATA_DIR
from ..embeddings.factory import EmbeddingEncoder
from ..modules.base import ModuleExecutionError
from ..storage.pgvector_store import PgVectorStore
from .workbook_catalog import SUPPORTED_WORKBOOK_SUFFIXES, WorkbookCatalog


def get_processed_file_info(
    path: Path,
    *,
    workbook_hash: Optional[str] = None,
    associated_index_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build metadata for one source file without scanning the source directory."""

    stat = path.stat()
    suffix = path.suffix.lower()
    file_type = (
        "excel"
        if suffix in SUPPORTED_WORKBOOK_SUFFIXES
        else "parquet"
        if suffix == ".parquet"
        else "json"
        if suffix == ".json"
        else "other"
    )
    resolved_hash = workbook_hash or ""
    sheet_names: List[str] = []

    if file_type == "excel":
        try:
            resolved_hash = resolved_hash or WorkbookCatalog.sha256(path)
            sheet_names = WorkbookCatalog.sheet_names(path)
        except Exception:
            sheet_names = []
    elif file_type == "parquet":
        resolved_hash = resolved_hash or path.stem.replace("_prebuilt", "")
    elif file_type == "json" and not resolved_hash:
        try:
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            resolved_hash = digest.hexdigest()
        except OSError:
            resolved_hash = ""

    return {
        "file_name": path.name,
        "size_bytes": stat.st_size,
        "updated_at": datetime.fromtimestamp(
            stat.st_mtime,
            tz=timezone.utc,
        ).isoformat(),
        "file_type": file_type,
        "sheet_names": sheet_names,
        "workbook_hash": resolved_hash,
        "associated_index_ids": associated_index_ids or [],
    }


def list_processed_files(
    processed_dir: Path = PROCESSED_DATA_DIR,
    pgvector_store: Optional[PgVectorStore] = None,
) -> List[Dict[str, Any]]:
    """List source files with workbook metadata and associated pgvector indexes."""

    if not processed_dir.exists():
        return []

    index_ids_by_hash: Dict[str, List[str]] = {}
    for index in list_vector_indexes(pgvector_store):
        workbook_hash = index.get("workbook_hash")
        if workbook_hash:
            index_ids_by_hash.setdefault(workbook_hash, []).append(
                index["index_id"]
            )

    files: List[Dict[str, Any]] = []
    for path in sorted(processed_dir.iterdir()):
        if not path.is_file() or path.name.startswith((".", "~$")):
            continue
        info = get_processed_file_info(path)
        files.append(
            {
                **info,
                "associated_index_ids": index_ids_by_hash.get(
                    info["workbook_hash"],
                    [],
                ),
            }
        )

    return files


def preview_excel_sheet(
    file_name: str,
    sheet_name: Optional[str] = None,
    max_rows: int = 15,
    max_cols: int = 15,
    processed_dir: Path = PROCESSED_DATA_DIR,
) -> Dict[str, Any]:
    """Read a bounded preview from one visible workbook sheet."""

    catalog = WorkbookCatalog(processed_dir)
    path = catalog.resolve(file_name)

    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        available_sheets = WorkbookCatalog.sheet_names(path)
        target_sheet = sheet_name or (
            available_sheets[0]
            if available_sheets
            else workbook.sheetnames[0]
        )
        if target_sheet not in workbook.sheetnames:
            raise ModuleExecutionError(f"시트를 찾을 수 없습니다: {target_sheet}")

        worksheet = workbook[target_sheet]
        rows: List[List[str]] = []
        for row_index, row in enumerate(worksheet.iter_rows(values_only=True)):
            if row_index >= max_rows:
                break
            rows.append(
                [
                    str(cell) if cell is not None else ""
                    for cell in list(row)[:max_cols]
                ]
            )

        return {
            "file_name": file_name,
            "sheet_name": target_sheet,
            "available_sheets": available_sheets,
            "total_sheets": len(available_sheets),
            "preview_rows": rows,
        }
    finally:
        workbook.close()


def list_vector_indexes(
    pgvector_store: Optional[PgVectorStore] = None,
) -> List[Dict[str, Any]]:
    """List indexes directly from pgvector."""

    store = pgvector_store or PgVectorStore()
    return store.list_indexes() if store.is_connected() else []


def get_vector_index_detail(
    index_id: str,
    sample_items_count: int = 15,
    pgvector_store: Optional[PgVectorStore] = None,
) -> Dict[str, Any]:
    """Return pgvector collection metadata and sample cell documents."""

    store = pgvector_store or PgVectorStore()
    if not store.is_connected():
        raise ModuleExecutionError(
            "pgvector 데이터베이스에 연결할 수 없습니다. "
            "Docker 컨테이너를 구동해주세요."
        )
    return store.get_index_detail(index_id, limit=sample_items_count)


def delete_vector_index(
    index_id: str,
    pgvector_store: Optional[PgVectorStore] = None,
) -> bool:
    """Delete one pgvector collection."""

    store = pgvector_store or PgVectorStore()
    if not store.is_connected():
        raise ModuleExecutionError("pgvector 데이터베이스에 연결할 수 없습니다")
    return store.delete(index_id)


def search_vector_index(
    index_id: str,
    query_text: str,
    limit: int = 5,
    pgvector_store: Optional[PgVectorStore] = None,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
) -> List[Dict[str, Any]]:
    """Run similarity search against one pgvector collection."""

    store = pgvector_store or PgVectorStore()
    if not store.is_connected():
        raise ModuleExecutionError("pgvector 데이터베이스에 연결할 수 없습니다")

    model_name = "text-embedding-3-large"
    try:
        detail = store.get_index_detail(index_id, limit=1)
        model_name = detail.get("model") or model_name
    except Exception:
        pass

    hits = store.search(
        index_id,
        query_text=query_text,
        model_name=model_name,
        embedding_encoder=embedding_encoder,
        limit=limit,
    )
    return [
        {
            "score": round(float(score), 4),
            "cell_id": document.get("cell_id", ""),
            "sheet_name": document.get("sheet_name", ""),
            "cell_coord": document.get("cell_coord")
            or document.get("cell_address", ""),
            "row_header": document.get("row_header", []),
            "column_header": document.get("column_header", []),
            "cell_value": document.get("cell_value", ""),
            "text": document.get("text", ""),
            "storage": "pgvector (LangChain)",
        }
        for score, document in hits
    ]
