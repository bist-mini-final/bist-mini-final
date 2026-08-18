"""Excel Ingestion and Vector Index Management Service with PostgreSQL + pgvector support."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

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

logger = logging.getLogger(__name__)


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
    from_step: Literal["luna_vlm", "serializer", "embedder", "vector_store"] = "luna_vlm",
    processed_dir: Path = PROCESSED_DATA_DIR,
    spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    vector_index_store: Optional[VectorIndexStore] = None,
    pgvector_store: Optional[PgVectorStore] = None,
    embedding_artifact_store: Optional[EmbeddingArtifactStore] = None,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
) -> Dict[str, Any]:
    """End-to-end ingestion pipeline: Excel -> Luna VLM Structure Detector -> Structured Cell Serializer -> Dense Embeddings -> Vector DB (pgvector & local).

    Parameters:
        from_step: Starting step for partial re-run.
            'luna_vlm'    — full pipeline from scratch (default)
            'serializer'  — skip Luna VLM; restore detected_tables from DB sheets table
            'embedder'    — skip Luna VLM + Serializer; load serialized_docs.json cache
            'vector_store'— skip everything; re-index from existing embedding artifacts
    """
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

    # Helper: path for the serialized_docs cache (written after Step 1 success)
    _artifact_hash_dir = spreadsheet_artifact_dir / workbook_hash[:16]
    _serialized_cache_path = _artifact_hash_dir / "serialized_docs.json"

    # Step 1: Structure Detection & Cell Text Serialization (Luna VLM + Structured Serializer)
    documents: List[CellTextDocumentDTO] = []
    used_pipeline = "exhaustive"
    detected_tables_list: List[Any] = []  # All detected tables across all sheets (for DB persistence)

    # ── Re-run shortcuts: skip earlier steps if from_step says so ──────────────
    if from_step == "embedder" and _serialized_cache_path.is_file():
        # Restore documents from the serialized_docs.json cache written after Step 1
        logger.info("[재실행] serialized_docs.json 캐시에서 직렬화 결과 복원: %s", _serialized_cache_path)
        try:
            _cached = json.loads(_serialized_cache_path.read_text(encoding="utf-8"))
            raw_docs = _cached.get("items") or []
            documents = [
                d if isinstance(d, CellTextDocumentDTO) else CellTextDocumentDTO(**d)
                for d in raw_docs
            ]
            used_pipeline = _cached.get("used_pipeline", "luna_vlm_structured")
            logger.info("[재실행] 캐시에서 %d개 문서 복원 완료", len(documents))
        except Exception as cache_err:
            logger.warning("[재실행] serialized_docs.json 캐시 로드 실패 — Step 1부터 재실행: %s", cache_err)
            documents = []

    elif from_step == "serializer":
        # Restore detected_tables from DB sheets table; then re-run the serializer
        logger.info("[재실행] DB sheets 테이블에서 detected_tables 복원 후 Serializer 재실행")
        try:
            db_mgr_restore = DatabaseManager()
            _restored_tables: List[Any] = []
            if db_mgr_restore.is_connected():
                _restored_raw = db_mgr_restore.get_detected_tables(workbook_hash)
                _restored_tables = _restored_raw
                logger.info("[재실행] DB에서 복원된 테이블 수: %d", len(_restored_tables))
            if _restored_tables:
                from ..modules.spreadsheet_structure import ClassifiedTableDTO
                serializer = CellTextSerializerModule(processed_dir=processed_dir)
                tables_dtos = []
                for t in _restored_tables:
                    if hasattr(t, "sheet_name"):
                        tables_dtos.append(t)
                    else:
                        try:
                            tables_dtos.append(ClassifiedTableDTO(**t))
                        except Exception as dto_err:
                            logger.warning(
                                "[재실행] DB 복원 테이블 ClassifiedTableDTO 변환 실패 (건너뜀): %s | 데이터: %s",
                                dto_err,
                                str(t)[:200],
                            )
                if not tables_dtos:
                    logger.warning("[재실행] DB 복원 테이블 모두 변환 실패 — Step 1부터 재실행")
                    _restored_tables = []
                else:
                    detected_tables_list = _restored_tables  # Track for DB persistence

                serializer_input = CellTextSerializerInputDTO(
                    file_name=file_name,
                    workbook_hash=workbook_hash,
                    tables=tables_dtos,
                )
                serialized = serializer.execute(serializer_input)
                raw_docs = serialized.get("items") or []
                documents = [
                    d if isinstance(d, CellTextDocumentDTO) else CellTextDocumentDTO(**d)
                    for d in raw_docs
                ]
                if documents:
                    used_pipeline = "luna_vlm_structured"
                    logger.info("[재실행] Serializer 완료: %d개 문서", len(documents))
        except Exception as restore_err:
            logger.warning("[재실행] Serializer 재실행 실패 — Step 1부터 재실행: %s", restore_err)
            documents = []

    # ── Normal Step 1: Luna VLM Structure Detection ──────────────────────────
    if from_step in ("luna_vlm",) or (from_step in ("serializer", "embedder") and not documents):
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
                _detected = structure_output.get("tables") or []
                if _detected:
                    detected_tables_list = _detected  # Track for DB persistence
                    serializer = CellTextSerializerModule(processed_dir=processed_dir)
                    serializer_input = CellTextSerializerInputDTO(
                        file_name=file_name,
                        workbook_hash=workbook_hash,
                        tables=_detected,
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
                logger.error(
                    "[Luna VLM] 구조 검출 실패 — exhaustive 폴백으로 전환합니다.\n"
                    "파일: %s, 시트: %s\n%s",
                    file_name,
                    visible_sheets,
                    traceback.format_exc(),
                )
                documents = []

    if not documents and from_step in ("luna_vlm",):
        # Fallback to exhaustive cell serializer (only when running from start)
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

    if not documents and from_step != "vector_store":
        raise ModuleExecutionError("생성된 셀 문서가 없습니다")

    # ── Cache: save serialized_docs.json after successful Step 1 ─────────────
    if used_pipeline == "luna_vlm_structured" and from_step not in ("embedder", "vector_store"):
        try:
            _artifact_hash_dir.mkdir(parents=True, exist_ok=True)
            _cache_payload = {
                "file_name": file_name,
                "workbook_hash": workbook_hash,
                "used_pipeline": used_pipeline,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "items": [d.model_dump() if hasattr(d, "model_dump") else d for d in documents],
            }
            _serialized_cache_path.write_text(
                json.dumps(_cache_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("[캐시] serialized_docs.json 저장 완료: %d문서 → %s", len(documents), _serialized_cache_path)
        except Exception as cache_write_err:
            logger.warning("[캐시] serialized_docs.json 저장 실패 (무시): %s", cache_write_err)

    # Step 2: Embedding (skip if from_step=vector_store and existing artifact found)
    artifact_store = embedding_artifact_store or EmbeddingArtifactStore(EMBEDDING_ARTIFACT_DIR)
    embedding_result: Dict[str, Any] = {}

    if from_step == "vector_store":
        # Try to restore embedding_result from existing pgvector collection metadata
        _pg_restore = pgvector_store or PgVectorStore()
        _restored = False
        # Find an existing collection for this workbook
        try:
            _existing_indexes = list_vector_indexes(
                vector_index_dir=VECTOR_INDEX_DIR,
                pgvector_store=_pg_restore,
            )
            _matching = [idx for idx in _existing_indexes if idx.get("workbook_hash") == workbook_hash]
            if _matching:
                _meta = _matching[0]
                _artifact_id = _meta.get("artifact_id") or ""
                _dim = _meta.get("dimension") or 0
                _model_name = _meta.get("model") or model
                if _artifact_id and _dim:
                    # Load items from serialized_docs cache if available, else from exhaustive
                    if _serialized_cache_path.is_file():
                        _cached = json.loads(_serialized_cache_path.read_text(encoding="utf-8"))
                        raw_docs = _cached.get("items") or []
                        documents = [
                            d if isinstance(d, CellTextDocumentDTO) else CellTextDocumentDTO(**d)
                            for d in raw_docs
                        ]
                    elif not documents:
                        # Cannot find documents; fall through to re-embed
                        logger.warning("[재실행] vector_store 재실행: 직렬화 캐시 없음, re-embed 진행")
                    if documents:
                        embedding_result = {
                            "file_name": file_name,
                            "workbook_hash": workbook_hash,
                            "model": _model_name,
                            "artifact_id": _artifact_id,
                            "dimension": _dim,
                            "duration_seconds": 0,
                            "total_tokens": 0,
                            "estimated_cost_usd": 0.0,
                            "estimated_cost_krw": 0.0,
                            "batch_size": batch_size,
                            "items": [
                                {**(d.model_dump() if hasattr(d, "model_dump") else d), "embedding_index": i}
                                for i, d in enumerate(documents)
                            ],
                        }
                        _restored = True
                        logger.info("[재실행] vector_store 재실행: 기존 artifact 재사용 (%s)", _artifact_id[:16])
        except Exception as restore_err:
            logger.warning("[재실행] vector_store 재실행 메타데이터 복원 실패, re-embed 진행: %s", restore_err)

        if not _restored:
            if not documents:
                raise ModuleExecutionError("재실행에 필요한 직렬화 문서를 복원할 수 없습니다")
            embedder = CellTextEmbedderModule(encoder=embedding_encoder, artifact_store=artifact_store)
            embedder_input = CellTextEmbedderExecutionDTO(
                file_name=file_name,
                workbook_hash=workbook_hash,
                items=documents,
                model=model,
                batch_size=batch_size,
            )
            embedding_result = embedder.execute(embedder_input)
    else:
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
                    for t in detected_tables_list
                    if (getattr(t, "sheet_name", None) or (isinstance(t, dict) and t.get("sheet_name"))) == s_name
                ]

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
