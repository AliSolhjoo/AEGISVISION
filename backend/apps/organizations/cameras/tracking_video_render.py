"""Pure helpers for rendering persisted tracking observations on source video."""
from __future__ import annotations

from bisect import bisect_right
from colorsys import hsv_to_rgb
from math import isfinite
from typing import Any


def interpolate_track_observation(
    observations: list[dict[str, Any]],
    timestamp_seconds: float,
    fps: float,
    max_gap_frames: int,
):
    """Return (box, confidence) at a video timestamp, or None.

    Interpolation is only performed between two observed points when the
    number of missing sampled frames does not exceed max_gap_frames. A
    one-point track is drawn only on the nearest source-video frame.
    """
    if not observations or fps <= 0 or not isfinite(timestamp_seconds):
        return None

    points = sorted(observations, key=lambda item: (item["timestamp_seconds"], item["frame_number"]))
    times = [float(item["timestamp_seconds"]) for item in points]

    if len(points) == 1:
        point = points[0]
        tolerance = 0.5 / fps + 1e-9
        if abs(timestamp_seconds - times[0]) <= tolerance:
            return list(point["bounding_box"]), float(point["confidence"])
        return None

    if timestamp_seconds < times[0] - 1e-9 or timestamp_seconds > times[-1] + 1e-9:
        return None

    right_index = bisect_right(times, timestamp_seconds)
    if right_index == 0:
        return None
    if right_index >= len(points):
        point = points[-1]
        if abs(timestamp_seconds - times[-1]) <= 1e-7:
            return list(point["bounding_box"]), float(point["confidence"])
        return None

    left = points[right_index - 1]
    right = points[right_index]
    left_time = float(left["timestamp_seconds"])
    right_time = float(right["timestamp_seconds"])

    if abs(timestamp_seconds - left_time) <= 1e-7:
        return list(left["bounding_box"]), float(left["confidence"])
    if right_time <= left_time:
        return None

    missing_frames = int(right["frame_number"]) - int(left["frame_number"]) - 1
    if missing_frames < 0 or missing_frames > int(max_gap_frames):
        return None

    ratio = (timestamp_seconds - left_time) / (right_time - left_time)
    ratio = max(0.0, min(1.0, ratio))
    left_box = [float(value) for value in left["bounding_box"]]
    right_box = [float(value) for value in right["bounding_box"]]
    if len(left_box) != 4 or len(right_box) != 4:
        return None

    box = [a + (b - a) * ratio for a, b in zip(left_box, right_box)]
    confidence = float(left["confidence"]) + (
        float(right["confidence"]) - float(left["confidence"])
    ) * ratio
    return box, confidence


def scale_box(box, scale_x: float, scale_y: float):
    """Scale an [x1, y1, x2, y2] box to source-video dimensions."""
    if len(box) != 4:
        raise ValueError("Bounding boxes must contain exactly four coordinates.")
    return [
        float(box[0]) * scale_x,
        float(box[1]) * scale_y,
        float(box[2]) * scale_x,
        float(box[3]) * scale_y,
    ]


def track_color(track_number: int):
    """Return a stable, readable OpenCV BGR color for a track number."""
    hue = (int(track_number) * 0.618033988749895) % 1.0
    red, green, blue = hsv_to_rgb(hue, 0.82, 1.0)
    return int(blue * 255), int(green * 255), int(red * 255)
