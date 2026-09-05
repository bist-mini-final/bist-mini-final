"""Burn a smooth demo cursor into a browser recording's source frames."""

from __future__ import annotations

import argparse
import bisect
import json
from pathlib import Path

from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    return parser.parse_args()


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def cursor_position(
    timestamp: float,
    actions: list[dict[str, object]],
    width: int,
    height: int,
) -> tuple[float, float]:
    if not actions:
        return width / 2, height / 2
    times = [float(action["t"]) for action in actions]
    right = bisect.bisect_right(times, timestamp)
    if right <= 0:
        return width / 2, height / 2
    if right >= len(actions):
        return float(actions[-1]["x"]), float(actions[-1]["y"])
    left_action = actions[right - 1]
    right_action = actions[right]
    left_time = float(left_action["t"])
    right_time = float(right_action["t"])
    transition_start = max(left_time, right_time - min(0.58, (right_time - left_time) * 0.42))
    if timestamp <= transition_start:
        return float(left_action["x"]), float(left_action["y"])
    ratio = smoothstep((timestamp - transition_start) / max(0.001, right_time - transition_start))
    return (
        float(left_action["x"]) + (float(right_action["x"]) - float(left_action["x"])) * ratio,
        float(left_action["y"]) + (float(right_action["y"]) - float(left_action["y"])) * ratio,
    )


def main() -> None:
    args = parse_args()
    recording_path = args.recording.resolve()
    recording = json.loads(recording_path.read_text(encoding="utf-8"))
    frame_dir = recording_path.parent / "frames"
    width = int(recording["width"])
    height = int(recording["height"])
    actions = sorted(recording.get("actions", []), key=lambda item: float(item["t"]))
    radius = max(8, round(width / 96))

    for index, frame in enumerate(recording["frames"]):
        frame_path = frame_dir / str(frame["file"])
        x, y = cursor_position(float(frame["t"]), actions, width, height)
        with Image.open(frame_path) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.ellipse(
            (x - radius - 3, y - radius - 1, x + radius + 3, y + radius + 5),
            fill=(67, 91, 80),
        )
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(255, 255, 255),
            outline=(8, 127, 79),
            width=max(2, radius // 4),
        )
        image.save(frame_path, format="JPEG", quality=94, optimize=True)
        image.close()
        if index % 50 == 0:
            print(f"cursor {index}/{len(recording['frames'])}", flush=True)

    recording["cursor_burned_in"] = True
    recording_path.write_text(json.dumps(recording, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
