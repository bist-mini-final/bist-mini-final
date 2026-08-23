"""Backfill a DB-only ingestion run for an existing pgvector collection."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any

from backend.bootstrap.container import ApplicationContainer
from backend.engine.workflows.models import RunBatchState, RunNodeState, WorkflowRun
from backend.storage.data_sources.ingestion_jobs import IngestionJobService


def _timestamp(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(timezone.utc).isoformat()


def _outputs(
    *,
    index_id: str,
    metadata: dict[str, Any],
    sheets: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    file_name = str(metadata.get("file_name") or index_id)
    workbook_hash = str(metadata.get("workbook_hash") or "")
    model = str(metadata.get("model") or "text-embedding-3-small")
    dimension = int(metadata.get("dimension") or 1536)
    document_count = int(metadata.get("document_count") or 0)
    company_name = str(metadata.get("company_name") or "")
    ticker = str(metadata.get("ticker") or "")
    sheet_names = [
        str(sheet["sheet_name"])
        for sheet in sheets
        if sheet.get("is_visible", True)
    ]
    tables = [
        table
        for sheet in sheets
        for table in (sheet.get("detected_tables") or [])
        if isinstance(table, dict)
    ]
    index_output = {
        "index_id": index_id,
        "file_name": file_name,
        "workbook_hash": workbook_hash,
        "model": model,
        "dimension": dimension,
        "document_count": document_count,
    }
    return {
        "processed_file_selector": {
            "file_name": file_name,
            "workbook_hash": workbook_hash,
            "sheet_names": sheet_names,
        },
        "luna_vlm_structure_detector": {
            "file_name": file_name,
            "workbook_hash": workbook_hash,
            "company_name": company_name or None,
            "sheet_names": sheet_names,
            "tables": tables,
            "failed_sheets": [],
        },
        "pgvector_index_writer": index_output,
        "sheet_metadata_persistence": {
            "sheets_saved": len(sheets),
            "sheet_details": [
                {
                    "sheet_name": sheet["sheet_name"],
                    "row_count": sheet["row_count"],
                    "column_count": sheet["column_count"],
                    "table_count": len(sheet.get("detected_tables") or []),
                }
                for sheet in sheets
            ],
        },
        "company_entity_extractor": {
            "company_name": company_name,
            "ticker": ticker,
            "display_name": company_name,
            "index_id": index_id,
            "confidence": "high" if company_name else "low",
            "source": "collection_metadata",
        },
    }


def backfill_ingestion_run(
    container: ApplicationContainer,
    index_id: str,
) -> tuple[WorkflowRun, bool]:
    """Return an inspectable run, creating one only when durable history is absent."""

    services = container.runtime.services
    jobs = IngestionJobService(
        services.workflow_store,
        services.run_store,
        services.workflow_executor,
        container.workflow_dispatcher,
    )
    try:
        existing = jobs.find_by_index(index_id)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        structure = jobs.node_output(existing, "luna_vlm_structure_detector")
        if structure is not None and isinstance(structure.get("tables"), list):
            return existing, False

    metadata = services.pgvector_store.get_index_metadata(index_id)
    workbook_hash = str(metadata.get("workbook_hash") or "")
    if not workbook_hash:
        raise RuntimeError("collection metadata에 workbook_hash가 없습니다")
    sheets = services.db_manager.list_sheets(workbook_hash)
    if not sheets:
        raise RuntimeError(
            "복구할 sheet/table metadata가 없습니다. 원본 Excel을 다시 인덱싱하세요"
        )

    workflow = services.workflow_store.load("excel_ingestion")
    graph = workflow.graph.model_copy(deep=True)
    batches = services.workflow_executor.validate_graph(graph)
    batch_index_by_node = {
        node_id: batch_index
        for batch_index, node_ids in enumerate(batches)
        for node_id in node_ids
    }
    output_by_module = _outputs(
        index_id=index_id,
        metadata=metadata,
        sheets=sheets,
    )
    recovered_at = datetime.now(timezone.utc).isoformat()
    source_created_at = _timestamp(metadata.get("created_at"))
    file_name = str(metadata.get("file_name") or index_id)
    run = WorkflowRun(
        id=f"run-backfill-{index_id.removeprefix('idx_')[:32]}",
        workflow_id=workflow.id,
        workflow_updated_at=workflow.updated_at,
        status="completed",
        created_at=recovered_at,
        updated_at=recovered_at,
        graph=graph,
        runtime_inputs={"source": {"file_name": file_name}},
        use_cache=True,
        batches=[
            RunBatchState(
                index=batch_index,
                node_ids=node_ids,
                status="completed",
                started_at=recovered_at,
                completed_at=recovered_at,
            )
            for batch_index, node_ids in enumerate(batches)
        ],
        nodes={
            node.id: RunNodeState(
                node_id=node.id,
                module_type=node.module_type,
                batch_index=batch_index_by_node[node.id],
                status="succeeded",
                output=output_by_module.get(node.module_type),
                started_at=recovered_at,
                completed_at=recovered_at,
                elapsed_ms=0,
                progress={
                    "phase": "history_backfill",
                    "recovered": True,
                    "source_created_at": source_created_at,
                },
            )
            for node in graph.nodes
        },
    )
    return services.run_store.save(run), True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "기존 pgvector collection의 sheet/table metadata로 "
            "inspectable Excel ingestion run을 PostgreSQL에 복구합니다"
        )
    )
    parser.add_argument("index_id")
    args = parser.parse_args()

    container = ApplicationContainer.create()
    try:
        run, created = backfill_ingestion_run(container, args.index_id)
        print(
            f"run_id={run.id} status={run.status} "
            f"created={'true' if created else 'false'}"
        )
    finally:
        container.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["backfill_ingestion_run", "main"]
