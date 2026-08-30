"""Prevent new cyclomatic-complexity debt while legacy hotspots are retired."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPLEXITY_PATTERN = re.compile(r"^`([^`]+)` is too complex \((\d+) > 10\)$")

# Existing hotspots are explicit migration debt, not a blanket C901 exemption.
# Deleting or reducing an entry is allowed; adding one or exceeding its current
# budget fails the suite.
LEGACY_COMPLEXITY_BUDGETS = {
    ("backend/api/bi_routes.py", "create_bi_router"): 12,
    ("backend/api/data_source_ingestion_routes.py", "create_ingestion_router"): 27,
    ("backend/api/data_source_routes.py", "create_data_source_router"): 25,
    ("backend/api/exception_handlers.py", "register_global_exception_handlers"): 12,
    ("backend/api/module_routes.py", "create_module_router"): 12,
    ("backend/api/workflow_routes.py", "create_workflow_router"): 12,
    ("backend/cli/documentation/module_docs.py", "_placeholder"): 13,
    ("backend/domains/bi/domain/formula_dsl.py", "_evaluate_node"): 13,
    ("backend/domains/company_comparison/models.py", "validate_snapshot_links"): 20,
    ("backend/domains/company_comparison/snapshot_builder.py", "_extract_base"): 13,
    ("backend/domains/workflow/application/graph_validation.py", "validate"): 17,
    ("backend/domains/workflow/application/input_assembly.py", "should_execute"): 12,
    ("backend/domains/workflow/application/input_assembly.py", "assemble"): 14,
    ("backend/features/benchmark/service.py", "execute_benchmark_comparison"): 17,
    ("backend/features/benchmark/worker_main.py", "_run"): 14,
    ("backend/features/bi/fast_rag_adapter.py", "_fetch_ranked_cells"): 16,
    ("backend/features/bi/snapshot_builder.py", "_assemble"): 11,
    ("backend/features/chatbot/attachments.py", "compact_evidence"): 11,
    ("backend/features/chatbot/attachments.py", "extract_text"): 13,
    ("backend/providers/openai_responses.py", "create_response"): 14,
    ("backend/providers/openai_responses.py", "create_response_async"): 14,
    ("backend/storage/pgvector_binary_copy.py", "_load_vector_batch"): 12,
    ("backend/storage/pgvector_store.py", "put_documents"): 32,
    ("backend/storage/pgvector_store.py", "get_index_detail"): 11,
    ("backend/storage/repositories/pgvector_retrieval.py", "_cell_metadata_query"): 18,
    ("backend/storage/repositories/pgvector_retrieval.py", "fetch_rows_cells"): 12,
    ("backend/storage/spreadsheets/cell_semantics.py", "collect_non_empty_cells"): 12,
    ("backend/storage/spreadsheets/grid_structure.py", "occupied_cells"): 15,
    ("backend/storage/spreadsheets/grid_structure.py", "build_column_header_tree"): 11,
    ("backend/storage/spreadsheets/sheet_renderer.py", "_cell_text_and_color"): 16,
    ("backend/storage/spreadsheets/sheet_renderer.py", "render"): 23,
    ("modules/common/base_llm.py", "complete_agentic"): 11,
    ("modules/common/base_llm.py", "complete_agentic_async"): 13,
    ("modules/storage/sheet_metadata_persistence.py", "execute"): 11,
    ("modules/structure/luna_vlm_structure_detector.py", "_validate_table"): 25,
    ("modules/structure/luna_vlm_structure_detector.py", "execute"): 13,
}


def _complexity_violations() -> dict[tuple[str, str], int]:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "backend",
            "modules",
            "--select",
            "C901",
            "--config",
            "lint.mccabe.max-complexity=10",
            "--output-format",
            "json",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert process.returncode in {0, 1}, process.stderr
    violations: dict[tuple[str, str], int] = {}
    for item in json.loads(process.stdout):
        match = COMPLEXITY_PATTERN.match(item["message"])
        assert match is not None, item
        relative_path = Path(item["filename"]).resolve().relative_to(PROJECT_ROOT).as_posix()
        violations[(relative_path, match.group(1))] = int(match.group(2))
    return violations


def test_backend_complexity_does_not_exceed_the_migration_budget() -> None:
    observed = _complexity_violations()
    unexpected = set(observed) - set(LEGACY_COMPLEXITY_BUDGETS)
    exceeded = {
        key: (value, LEGACY_COMPLEXITY_BUDGETS[key])
        for key, value in observed.items()
        if key in LEGACY_COMPLEXITY_BUDGETS and value > LEGACY_COMPLEXITY_BUDGETS[key]
    }
    assert not unexpected, f"new C901 hotspots: {sorted(unexpected)}"
    assert not exceeded, f"increased C901 complexity: {exceeded}"
