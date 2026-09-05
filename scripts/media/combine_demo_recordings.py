"""Combine segmented browser recordings into one renderer-compatible timeline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--gap", type=float, default=0.35)
    parser.add_argument(
        "--start-times",
        nargs="*",
        type=float,
        default=None,
        help="Optional per-recording trim start times in seconds.",
    )
    return parser.parse_args()


def link_or_copy(source: Path, target: Path) -> None:
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def shifted(items: list[dict[str, Any]], offset: float, *keys: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        copied = dict(item)
        for key in keys:
            if key in copied:
                copied[key] = float(copied[key]) + offset
        result.append(copied)
    return result


def main() -> None:
    args = parse_args()
    recordings = [
        json.loads(path.resolve().read_text(encoding="utf-8"))
        for path in args.recordings
    ]
    if not recordings:
        raise ValueError("At least one recording is required")
    start_times = args.start_times or [0.0] * len(recordings)
    if len(start_times) != len(recordings):
        raise ValueError("--start-times must contain one value per recording")

    width = max(int(recording["width"]) for recording in recordings)
    height = max(int(recording["height"]) for recording in recordings)

    output_dir = args.output_dir.resolve()
    frame_dir = output_dir / "frames"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    frame_dir.mkdir(parents=True)

    frames: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    fast_forward: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    offset = 0.0

    for recording_index, (recording_path, recording) in enumerate(
        zip(args.recordings, recordings, strict=True)
    ):
        source_frame_dir = recording_path.resolve().parent / "frames"
        scale_x = width / int(recording["width"])
        scale_y = height / int(recording["height"])
        source_start = max(0.0, float(start_times[recording_index]))
        segment_start = offset
        selected_frames = [
            frame for frame in recording["frames"]
            if float(frame["t"]) >= source_start
        ]
        if not selected_frames:
            raise ValueError(f"No frames remain after trimming {recording_path}")
        for frame in selected_frames:
            target_name = f"{len(frames):06d}{Path(frame['file']).suffix.lower()}"
            link_or_copy(source_frame_dir / frame["file"], frame_dir / target_name)
            frames.append(
                {
                    "file": target_name,
                    "t": offset + max(0.0, float(frame["t"]) - source_start),
                }
            )

        shifted_actions = shifted(
                [
                    action for action in recording.get("actions", [])
                    if float(action["t"]) >= source_start
                ],
                offset - source_start,
                "t",
            )
        for action in shifted_actions:
            action["x"] = float(action["x"]) * scale_x
            action["y"] = float(action["y"]) * scale_y
        actions.extend(shifted_actions)
        for segment in recording.get("fast_forward", []):
            clipped_start = max(source_start, float(segment["start"]))
            clipped_end = float(segment["end"])
            if clipped_end <= clipped_start:
                continue
            copied_segment = dict(segment)
            copied_segment["start"] = offset + clipped_start - source_start
            copied_segment["end"] = offset + clipped_end - source_start
            fast_forward.append(copied_segment)
        duration = max(0.0, float(recording["duration"]) - source_start)
        offset += duration
        segments.append(
            {
                "source": str(recording_path.resolve()),
                "source_start": source_start,
                "start": segment_start,
                "end": offset,
            }
        )
        if recording_index < len(recordings) - 1:
            offset += max(0.0, args.gap)

    combined = {
        "width": width,
        "height": height,
        "camera_mode": "track",
        "frame_sampling": "nearest",
        "started_at": recordings[0].get("started_at"),
        "duration": offset,
        "frames": frames,
        "actions": actions,
        "fast_forward": fast_forward,
        "segments": segments,
        "source_files": [recording.get("source_file") for recording in recordings],
    }
    recording_path = output_dir / "recording.json"
    recording_path.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "recording": str(recording_path),
                "segments": len(segments),
                "frames": len(frames),
                "actions": len(actions),
                "duration": round(offset, 3),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
