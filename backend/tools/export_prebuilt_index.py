import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy

from ..core.settings import PROCESSED_DATA_DIR, VECTOR_INDEX_DIR
from ..storage.vector_index import VectorIndexStore


def export_prebuilt_index(
    index_id: str,
    output_path: Path,
    vector_index_store: VectorIndexStore = None,
) -> Path:
    vector_index_store = vector_index_store or VectorIndexStore(VECTOR_INDEX_DIR)

    index_path, metadata_path = vector_index_store._paths(index_id)
    meta = vector_index_store.metadata(index_id)
    matrix = numpy.load(index_path, allow_pickle=False)

    # items stored by VectorIndexWriterModule contain full CellTextDocumentDTO fields
    metadata_items = meta.get("metadata") or meta.get("items") or []

    items: List[Dict[str, Any]] = []
    for row_idx, doc in enumerate(metadata_items):
        # Preserve every field from CellTextDocumentDTO so that the loader
        # can reconstruct row_header, column_header, and cell_value correctly.
        # Also support legacy 'cell_address' key as a fallback for cell_coord.
        items.append({
            "cell_id": doc.get("cell_id", ""),
            "sheet_name": doc.get("sheet_name", ""),
            "cell_coord": doc.get("cell_coord") or doc.get("cell_address", ""),
            "row_header": doc.get("row_header") or [],
            "column_header": doc.get("column_header") or [],
            "cell_value": doc.get("cell_value", ""),
            "variant": doc.get("variant", "header_with_value"),
            "text": doc.get("text", ""),
            "embedding": matrix[row_idx].tolist(),
        })

    payload = {
        "file_name": meta.get("file_name", "exported_workbook.xlsx"),
        "workbook_hash": meta.get("workbook_hash", ""),
        "model": meta.get("model", ""),
        "dimension": int(meta.get("dimension", matrix.shape[1])),
        "items": items,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Export an indexed vector DB as a single prebuilt JSON file for Google Drive sharing.")
    parser.add_argument("--index-id", required=True, help="Index ID in vector_db to export")
    parser.add_argument("--output", default=None, help="Output JSON path (default: data/source_files/<index_id>_prebuilt.json)")
    args = parser.parse_args()

    vector_index_store = VectorIndexStore(VECTOR_INDEX_DIR)
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = PROCESSED_DATA_DIR / f"{args.index_id}_prebuilt.json"

    result_path = export_prebuilt_index(args.index_id, out_path, vector_index_store)
    print(f"Successfully exported prebuilt index ({len(result_path.name)} bytes) to: {result_path}")


if __name__ == "__main__":
    main()
