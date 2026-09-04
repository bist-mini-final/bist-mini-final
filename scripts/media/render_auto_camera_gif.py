"""Render a smooth click-following product demo GIF from CDP screencast frames."""

from __future__ import annotations

import argparse
import bisect
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recording", type=Path, default=Path(".tmp/core-flow-recording/recording.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/assets/excel-rag-core-user-flow.gif"))
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--colors", type=int, default=64)
    return parser.parse_args()


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def build_time_map(source_anchors: list[float], fast_forward: list[dict[str, Any]]) -> list[float]:
    """Compress idle waits while retaining every real browser transition."""

    output_anchors = [0.0]
    for start, end in zip(source_anchors, source_anchors[1:]):
        source_gap = max(0.0, end - start)
        midpoint = (start + end) / 2
        fast_segment = next(
            (
                segment for segment in fast_forward
                if float(segment["start"]) <= midpoint <= float(segment["end"])
            ),
            None,
        )
        if fast_segment is not None:
            segment_duration = max(0.001, float(fast_segment["end"]) - float(fast_segment["start"]))
            output_gap = source_gap * (float(fast_segment["target_duration"]) / segment_duration)
        else:
            output_gap = max(0.42, min(1.35, source_gap * 0.50))
        output_anchors.append(output_anchors[-1] + output_gap)
    return output_anchors


def interpolate(value: float, xs: list[float], ys: list[float]) -> float:
    index = bisect.bisect_right(xs, value) - 1
    index = max(0, min(index, len(xs) - 2))
    span = xs[index + 1] - xs[index]
    ratio = 0.0 if span <= 0 else (value - xs[index]) / span
    return ys[index] + (ys[index + 1] - ys[index]) * ratio


def tracked_camera_state(
    output_time: float,
    actions: list[dict[str, Any]],
    width: int,
    height: int,
) -> tuple[float, float, float]:
    """Continuously follow successive focus points instead of pulsing to center."""

    center = (width / 2, height / 2, 1.0)
    if not actions:
        return center

    first = actions[0]
    first_time = float(first["output_t"])
    if output_time <= first_time:
        transition_start = max(0.0, first_time - 0.55)
        if output_time <= transition_start:
            return center
        ratio = smoothstep((output_time - transition_start) / max(0.001, first_time - transition_start))
        return (
            center[0] + (float(first["x"]) - center[0]) * ratio,
            center[1] + (float(first["y"]) - center[1]) * ratio,
            center[2] + (float(first.get("zoom", 1.16)) - center[2]) * ratio,
        )

    for current, following in zip(actions, actions[1:]):
        current_time = float(current["output_t"])
        following_time = float(following["output_t"])
        if output_time > following_time:
            continue

        gap = max(0.001, following_time - current_time)
        transition_duration = min(0.58, max(0.20, gap * 0.42))
        transition_start = max(current_time, following_time - transition_duration)
        if output_time <= transition_start:
            return (
                float(current["x"]),
                float(current["y"]),
                float(current.get("zoom", 1.16)),
            )
        ratio = smoothstep((output_time - transition_start) / max(0.001, following_time - transition_start))
        return (
            float(current["x"]) + (float(following["x"]) - float(current["x"])) * ratio,
            float(current["y"]) + (float(following["y"]) - float(current["y"])) * ratio,
            float(current.get("zoom", 1.16))
            + (float(following.get("zoom", 1.16)) - float(current.get("zoom", 1.16))) * ratio,
        )

    last = actions[-1]
    return float(last["x"]), float(last["y"]), float(last.get("zoom", 1.16))


def camera_state(
    output_time: float,
    actions: list[dict[str, Any]],
    width: int,
    height: int,
    mode: str = "pulse",
) -> tuple[float, float, float]:
    if mode == "track":
        return tracked_camera_state(output_time, actions, width, height)

    center_x = width / 2
    center_y = height / 2
    strongest_weight = 0.0
    selected: dict[str, Any] | None = None

    for action in actions:
        delta = output_time - action["output_t"]
        if -0.42 <= delta < 0:
            weight = smoothstep((delta + 0.42) / 0.42)
        elif 0 <= delta <= 0.34:
            weight = 1.0
        elif 0.34 < delta <= 0.88:
            weight = 1.0 - smoothstep((delta - 0.34) / 0.54)
        else:
            weight = 0.0
        if weight > strongest_weight:
            strongest_weight = weight
            selected = action

    if selected is None:
        return center_x, center_y, 1.0

    target_x = float(selected["x"])
    target_y = float(selected["y"])
    zoom = 1.0 + (float(selected.get("zoom", 1.16)) - 1.0) * strongest_weight
    return (
        center_x + (target_x - center_x) * strongest_weight,
        center_y + (target_y - center_y) * strongest_weight,
        zoom,
    )


def crop_camera(frame: Image.Image, center_x: float, center_y: float, zoom: float, width: int, height: int) -> Image.Image:
    crop_width = max(2, int(round(width / zoom)))
    crop_height = max(2, int(round(height / zoom)))
    half_width = crop_width / 2
    half_height = crop_height / 2
    center_x = max(half_width, min(width - half_width, center_x))
    center_y = max(half_height, min(height - half_height, center_y))
    left = int(round(center_x - half_width))
    top = int(round(center_y - half_height))
    right = min(width, left + crop_width)
    bottom = min(height, top + crop_height)
    left = max(0, right - crop_width)
    top = max(0, bottom - crop_height)
    return frame.crop((left, top, right, bottom)).resize((width, height), Image.Resampling.BICUBIC)


def load_blended_frame(frame_dir: Path, frames: list[dict[str, Any]], frame_times: list[float], source_time: float) -> Image.Image:
    right_index = bisect.bisect_left(frame_times, source_time)
    if right_index <= 0:
        return Image.open(frame_dir / frames[0]["file"]).convert("RGB")
    if right_index >= len(frames):
        return Image.open(frame_dir / frames[-1]["file"]).convert("RGB")

    left_index = right_index - 1
    left_time = frame_times[left_index]
    right_time = frame_times[right_index]
    span = right_time - left_time
    alpha = 0.0 if span <= 0 else (source_time - left_time) / span
    with Image.open(frame_dir / frames[left_index]["file"]) as left_image:
        left = left_image.convert("RGB")
    if alpha < 0.08:
        return left
    with Image.open(frame_dir / frames[right_index]["file"]) as right_image:
        right = right_image.convert("RGB")
    if alpha > 0.92:
        return right
    return Image.blend(left, right, alpha)


def load_nearest_frame(
    frame_dir: Path,
    frames: list[dict[str, Any]],
    frame_times: list[float],
    source_time: float,
) -> Image.Image:
    """Select the nearest captured frame without washing out UI accent colors."""

    right_index = bisect.bisect_left(frame_times, source_time)
    if right_index <= 0:
        selected_index = 0
    elif right_index >= len(frames):
        selected_index = len(frames) - 1
    else:
        left_index = right_index - 1
        selected_index = (
            left_index
            if source_time - frame_times[left_index] <= frame_times[right_index] - source_time
            else right_index
        )
    return Image.open(frame_dir / frames[selected_index]["file"]).convert("RGB")


def load_source_frame(
    frame_dir: Path,
    frames: list[dict[str, Any]],
    frame_times: list[float],
    source_time: float,
    sampling: str,
) -> Image.Image:
    if sampling == "nearest":
        return load_nearest_frame(frame_dir, frames, frame_times, source_time)
    return load_blended_frame(frame_dir, frames, frame_times, source_time)


def build_palette(sample_frames: list[Image.Image], colors: int) -> Image.Image:
    tile_width, tile_height = 480, 270
    sheet_width = tile_width * 4
    sample_height = tile_height * 4
    accent_height = tile_height
    sheet = Image.new("RGB", (sheet_width, sample_height + accent_height), "white")
    accent_pixels: list[tuple[int, int, int]] = []
    for index, frame in enumerate(sample_frames[:16]):
        tile = frame.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
        sheet.paste(tile, ((index % 4) * tile_width, (index // 4) * tile_height))
        # White canvas pixels dominate this product. Replicate real saturated
        # pixels so small rose, violet, blue, and amber module accents retain
        # dedicated entries in the shared GIF palette.
        accent_pixels.extend(
            pixel for pixel in tile.get_flattened_data()
            if max(pixel) - min(pixel) >= 18 and min(pixel) < 242
        )
    if accent_pixels:
        target_count = sheet_width * accent_height
        step = max(1, len(accent_pixels) // target_count)
        sampled = accent_pixels[::step]
        repeated = (sampled * math.ceil(target_count / len(sampled)))[:target_count]
        accent_strip = Image.new("RGB", (sheet_width, accent_height))
        accent_strip.putdata(repeated)
        sheet.paste(accent_strip, (0, sample_height))
    return sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)


def main() -> None:
    args = parse_args()
    recording_path = args.recording.resolve()
    recording = json.loads(recording_path.read_text(encoding="utf-8"))
    frame_dir = recording_path.parent / "frames"
    frames = recording["frames"]
    actions = recording["actions"]
    fast_forward = recording.get("fast_forward", [])
    width = int(recording["width"])
    height = int(recording["height"])
    duration = float(recording["duration"])
    camera_mode = str(recording.get("camera_mode", "pulse"))
    frame_sampling = str(recording.get("frame_sampling", "nearest"))
    frame_times = [float(frame["t"]) for frame in frames]

    source_anchors = [
        0.0,
        *[float(action["t"]) for action in actions],
        *[float(segment["start"]) for segment in fast_forward],
        *[float(segment["end"]) for segment in fast_forward],
        duration,
    ]
    source_anchors = sorted(set(source_anchors))
    output_anchors = build_time_map(source_anchors, fast_forward)
    output_duration = output_anchors[-1]
    output_count = max(2, math.ceil(output_duration * args.fps))

    for action in actions:
        action["output_t"] = interpolate(float(action["t"]), source_anchors, output_anchors)

    sample_frames: list[Image.Image] = []
    for index in range(16):
        output_time = output_duration * index / 15
        source_time = interpolate(output_time, output_anchors, source_anchors)
        frame = load_source_frame(frame_dir, frames, frame_times, source_time, frame_sampling)
        camera = camera_state(output_time, actions, width, height, camera_mode)
        sample_frames.append(crop_camera(frame, *camera, width, height))
    palette = build_palette(sample_frames, args.colors)
    for sample in sample_frames:
        sample.close()

    rendered: list[Image.Image] = []
    for index in range(output_count):
        output_time = index / args.fps
        source_time = interpolate(output_time, output_anchors, source_anchors)
        source_frame = load_source_frame(frame_dir, frames, frame_times, source_time, frame_sampling)
        camera = camera_state(output_time, actions, width, height, camera_mode)
        camera_frame = crop_camera(source_frame, *camera, width, height)
        source_frame.close()
        quantized = camera_frame.quantize(palette=palette, dither=Image.Dither.NONE)
        camera_frame.close()
        rendered.append(quantized)
        if index % args.fps == 0:
            print(f"rendered {index}/{output_count}", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # GIF stores delays in centiseconds. Round cumulative presentation times
    # instead of every frame independently, so rates such as 24 fps become a
    # stable 40/50 ms cadence with the correct long-run average.
    durations: list[int] = []
    previous_end = 0
    for index in range(output_count):
        rounded_end = round(((index + 1) * 1000 / args.fps) / 10) * 10
        durations.append(max(10, rounded_end - previous_end))
        previous_end = rounded_end
    rendered[0].save(
        args.output,
        save_all=True,
        append_images=rendered[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=1,
    )
    for frame in rendered:
        frame.close()

    print(json.dumps({
        "source_frames": len(frames),
        "output_frames": output_count,
        "source_duration": round(duration, 3),
        "output_duration": round(sum(durations) / 1000, 3),
        "fps": args.fps,
        "width": width,
        "height": height,
        "colors": args.colors,
        "camera_mode": camera_mode,
        "frame_sampling": frame_sampling,
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
