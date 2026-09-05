"""Reduce long fast-forward source recordings without changing their timeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument("--dense-until", type=float, required=True)
    parser.add_argument("--dense-after", type=float, required=True)
    parser.add_argument("--sparse-step", type=float, default=4.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    recording_path = args.recording.resolve()
    frame_dir = recording_path.parent / "frames"
    recording = json.loads(recording_path.read_text(encoding="utf-8"))
    kept: list[dict[str, object]] = []
    next_sparse = args.dense_until
    for frame in recording["frames"]:
        timestamp = float(frame["t"])
        if timestamp <= args.dense_until or timestamp >= args.dense_after:
            kept.append(frame)
            continue
        if timestamp >= next_sparse:
            kept.append(frame)
            next_sparse = timestamp + args.sparse_step
    if recording["frames"][-1] not in kept:
        kept.append(recording["frames"][-1])

    names = {str(frame["file"]) for frame in kept}
    removed = 0
    removed_bytes = 0
    for path in frame_dir.iterdir():
        if not path.is_file() or path.name in names:
            continue
        removed_bytes += path.stat().st_size
        path.unlink()
        removed += 1

    recording["frames"] = kept
    recording["pruned_source_frames"] = removed
    recording_path.write_text(json.dumps(recording, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "kept": len(kept),
        "removed": removed,
        "freed_mb": round(removed_bytes / (1024 * 1024), 1),
    }))


if __name__ == "__main__":
    main()
