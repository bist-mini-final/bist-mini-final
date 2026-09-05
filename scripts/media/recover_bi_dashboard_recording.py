"""Recover the BI snapshot request segment after an interrupted CDP capture."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording_dir", type=Path)
    return parser.parse_args()


def main() -> None:
    recording_dir = parse_args().recording_dir.resolve()
    frame_dir = recording_dir / "frames"
    paths = sorted(frame_dir.glob("*.jpg"))
    if not paths:
        raise ValueError(f"No JPEG frames found in {frame_dir}")
    first_time = paths[0].stat().st_mtime
    frames = [
        {"file": path.name, "t": max(0.0, path.stat().st_mtime - first_time)}
        for path in paths
    ]
    duration = float(frames[-1]["t"])
    actions = [
        {"type": "focus", "label": "BI 대시보드", "x": 1180, "y": 520, "t": 0.15, "zoom": 1.08},
        {"type": "click", "label": "기업 스냅샷 추가", "x": 1680, "y": 382, "t": 3.4, "zoom": 1.28},
        {"type": "click", "label": "비스텔리젼스 선택", "x": 1515, "y": 548, "t": 5.4, "zoom": 1.38},
        {"type": "click", "label": "선택 기업 생성", "x": 1680, "y": 608, "t": 8.0, "zoom": 1.38},
        {"type": "focus", "label": "스냅샷 생성 중", "x": 1525, "y": 530, "t": 10.7, "zoom": 1.42},
        {"type": "focus", "label": "생성 결과 확인", "x": 1525, "y": 530, "t": duration, "zoom": 1.42},
    ]
    payload = {
        "width": 1920,
        "height": 1080,
        "camera_mode": "track",
        "frame_sampling": "nearest",
        "started_at": datetime.fromtimestamp(first_time, tz=timezone.utc).isoformat(),
        "duration": duration,
        "frames": frames,
        "actions": actions,
        "fast_forward": [{
            "label": "BI 스냅샷 생성",
            "start": 8.6,
            "end": max(8.7, duration - 0.2),
            "target_duration": 1.5,
        }],
        "company": "비스텔리젼스",
        "recovered": True,
    }
    output = recording_dir / "recording.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "frames": len(frames), "duration": round(duration, 3)}))


if __name__ == "__main__":
    main()
