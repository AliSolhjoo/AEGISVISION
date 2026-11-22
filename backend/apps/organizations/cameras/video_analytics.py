from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any


class AnalyticsConfigError(ValueError):
    """Raised when an analytics rule configuration is invalid."""


def _number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalyticsConfigError(f"{field} must be a number.") from exc
    if not math.isfinite(result):
        raise AnalyticsConfigError(f"{field} must be finite.")
    return result


def _point(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise AnalyticsConfigError(f"{field} must be [x, y].")
    x = _number(value[0], f"{field}[0]")
    y = _number(value[1], f"{field}[1]")
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise AnalyticsConfigError(f"{field} coordinates must be normalized between 0 and 1.")
    return x, y


def validate_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise AnalyticsConfigError("Configuration root must be a JSON object.")
    rules = config.get("rules", [])
    if not isinstance(rules, list):
        raise AnalyticsConfigError("'rules' must be a list.")

    max_gap = _number(config.get("max_observation_gap_seconds", 3.0), "max_observation_gap_seconds")
    if not 0.0 < max_gap <= 3600.0:
        raise AnalyticsConfigError("max_observation_gap_seconds must be between 0 and 3600.")

    clean_rules = []
    seen_ids = set()
    valid_types = {"zone_intrusion", "line_crossing", "loitering"}
    for index, raw in enumerate(rules):
        prefix = f"rules[{index}]"
        if not isinstance(raw, dict):
            raise AnalyticsConfigError(f"{prefix} must be an object.")
        rule_id = str(raw.get("id", "")).strip()
        name = str(raw.get("name", rule_id)).strip()
        rule_type = str(raw.get("type", "")).strip().lower()
        if not rule_id:
            raise AnalyticsConfigError(f"{prefix}.id is required.")
        if rule_id in seen_ids:
            raise AnalyticsConfigError(f"Duplicate rule id: {rule_id}.")
        seen_ids.add(rule_id)
        if rule_type not in valid_types:
            raise AnalyticsConfigError(
                f"{prefix}.type must be one of: {', '.join(sorted(valid_types))}."
            )
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise AnalyticsConfigError(f"{prefix}.enabled must be boolean.")

        labels = raw.get("labels", [])
        if not isinstance(labels, list) or any(not isinstance(item, str) for item in labels):
            raise AnalyticsConfigError(f"{prefix}.labels must be a list of strings.")
        labels = sorted({item.strip().lower() for item in labels if item.strip()})

        minimum_confidence = _number(raw.get("minimum_confidence", 0.0), f"{prefix}.minimum_confidence")
        if not 0.0 <= minimum_confidence <= 1.0:
            raise AnalyticsConfigError(f"{prefix}.minimum_confidence must be between 0 and 1.")

        rule = {
            "id": rule_id,
            "name": name or rule_id,
            "type": rule_type,
            "enabled": enabled,
            "labels": labels,
            "minimum_confidence": minimum_confidence,
            "anchor": str(raw.get("anchor", "bottom_center")).lower(),
        }
        if rule["anchor"] not in {"bottom_center", "center"}:
            raise AnalyticsConfigError(f"{prefix}.anchor must be bottom_center or center.")

        if rule_type in {"zone_intrusion", "loitering"}:
            polygon_raw = raw.get("polygon")
            if not isinstance(polygon_raw, list) or len(polygon_raw) < 3:
                raise AnalyticsConfigError(f"{prefix}.polygon must contain at least 3 normalized points.")
            rule["polygon"] = [
                _point(item, f"{prefix}.polygon[{point_index}]")
                for point_index, item in enumerate(polygon_raw)
            ]
        if rule_type == "line_crossing":
            line_raw = raw.get("line")
            if not isinstance(line_raw, list) or len(line_raw) != 2:
                raise AnalyticsConfigError(f"{prefix}.line must contain exactly 2 normalized points.")
            line = [
                _point(item, f"{prefix}.line[{point_index}]")
                for point_index, item in enumerate(line_raw)
            ]
            if line[0] == line[1]:
                raise AnalyticsConfigError(f"{prefix}.line endpoints must be different.")
            rule["line"] = line
            direction = str(raw.get("direction", "both")).lower()
            if direction not in {"both", "negative_to_positive", "positive_to_negative"}:
                raise AnalyticsConfigError(f"{prefix}.direction is invalid.")
            rule["direction"] = direction
        if rule_type == "loitering":
            dwell = _number(raw.get("dwell_seconds", 10.0), f"{prefix}.dwell_seconds")
            if not 0.0 < dwell <= 86400.0:
                raise AnalyticsConfigError(f"{prefix}.dwell_seconds must be between 0 and 86400.")
            rule["dwell_seconds"] = dwell

        clean_rules.append(rule)

    return {
        "version": int(config.get("version", 1)),
        "max_observation_gap_seconds": max_gap,
        "rules": clean_rules,
    }


def box_anchor(box: list | tuple, width: int, height: int, mode: str = "bottom_center") -> tuple[float, float]:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise ValueError("Bounding box must contain [x1, y1, x2, y2].")
    x1, y1, x2, y2 = (_number(value, "bounding_box") for value in box)
    if x2 <= x1 or y2 <= y1 or width <= 0 or height <= 0:
        raise ValueError("Bounding box or frame dimensions are invalid.")
    if mode == "center":
        x, y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    else:
        x, y = (x1 + x2) / 2.0, y2
    return min(1.0, max(0.0, x / width)), min(1.0, max(0.0, y / height))


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test; boundary points count as inside."""
    x, y = point
    inside = False
    eps = 1e-10
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) <= eps and min(x1, x2) - eps <= x <= max(x1, x2) + eps and min(y1, y2) - eps <= y <= max(y1, y2) + eps:
            return True
        intersects = (y1 > y) != (y2 > y)
        if intersects:
            x_intersection = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_intersection:
                inside = not inside
    return inside


def _cross(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _segments_intersect(p1, p2, q1, q2) -> bool:
    eps = 1e-10
    d1, d2 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    d3, d4 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    return (d1 * d2 <= eps) and (d3 * d4 <= eps)


def _line_crossing(previous: tuple[float, float], current: tuple[float, float], line: list[tuple[float, float]]):
    start, end = line
    side_before = _cross(start, end, previous)
    side_after = _cross(start, end, current)
    if abs(side_before) < 1e-10 or abs(side_after) < 1e-10:
        return None
    if side_before * side_after >= 0:
        return None
    if not _segments_intersect(previous, current, start, end):
        return None
    direction = "negative_to_positive" if side_before < 0 < side_after else "positive_to_negative"
    ratio = abs(side_before) / (abs(side_before) + abs(side_after))
    crossing_point = (
        previous[0] + ratio * (current[0] - previous[0]),
        previous[1] + ratio * (current[1] - previous[1]),
    )
    return direction, ratio, crossing_point


def _matches_rule(observation: dict, rule: dict, label: str) -> bool:
    if rule["labels"] and label.lower() not in rule["labels"]:
        return False
    return observation["confidence"] >= rule["minimum_confidence"]


def _event(rule: dict, track: dict, observation: dict, timestamp: float, event_type: str, **extra) -> dict:
    return {
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "event_type": event_type,
        "track_number": track["track_number"],
        "label": track["label"],
        "timestamp_seconds": round(float(timestamp), 3),
        "frame_number": observation["frame_number"],
        "confidence": round(float(observation["confidence"]), 5),
        **extra,
    }


def _summarize_tracks(tracks: list[dict]) -> dict:
    by_label = Counter(track["label"] for track in tracks)
    total_observations = sum(len(track["observations"]) for track in tracks)
    summaries = []
    for track in tracks:
        observations = track["observations"]
        first = observations[0]
        last = observations[-1]
        duration = max(0.0, last["timestamp_seconds"] - first["timestamp_seconds"])
        path_length = 0.0
        for left, right in zip(observations, observations[1:]):
            dx = right["point"][0] - left["point"][0]
            dy = right["point"][1] - left["point"][1]
            path_length += math.hypot(dx, dy)
        summaries.append({
            "track_number": track["track_number"],
            "label": track["label"],
            "observations": len(observations),
            "first_frame": first["frame_number"],
            "last_frame": last["frame_number"],
            "start_seconds": round(first["timestamp_seconds"], 3),
            "end_seconds": round(last["timestamp_seconds"], 3),
            "observed_span_seconds": round(duration, 3),
            "normalized_path_length": round(path_length, 6),
        })
    return {
        "unique_tracks": len(tracks),
        "total_observations": total_observations,
        "tracks_by_label": dict(sorted(by_label.items())),
        "track_details": summaries,
    }


def analyze_tracking_data(tracks: list[dict], config: dict) -> dict:
    """Analyze serialized tracks and return deterministic rule events + metrics.

    Each observation requires frame_number, timestamp_seconds, confidence,
    bounding_box, width and height. Bounding boxes use pixel coordinates;
    rule geometry uses normalized [0, 1] coordinates.
    """
    clean_config = validate_config(config)
    max_gap = clean_config["max_observation_gap_seconds"]
    prepared_tracks = []

    for raw_track in tracks:
        label = str(raw_track.get("label", "unknown"))[:80]
        try:
            track_number = int(raw_track["track_number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Each track must have an integer track_number.") from exc
        prepared_observations = []
        for raw in raw_track.get("observations", []):
            try:
                timestamp = _number(raw["timestamp_seconds"], "timestamp_seconds")
                frame_number = int(raw["frame_number"])
                confidence = _number(raw.get("confidence", 0.0), "confidence")
                width = int(raw["width"])
                height = int(raw["height"])
                box = raw["bounding_box"]
                point = box_anchor(box, width, height, "bottom_center")
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if not 0.0 <= confidence <= 1.0:
                continue
            prepared_observations.append({
                "frame_number": frame_number,
                "timestamp_seconds": timestamp,
                "confidence": confidence,
                "bounding_box": [float(value) for value in box],
                "width": width,
                "height": height,
                "point": point,
            })
        prepared_observations.sort(key=lambda item: (item["timestamp_seconds"], item["frame_number"]))
        if prepared_observations:
            prepared_tracks.append({
                "track_number": track_number,
                "label": label,
                "observations": prepared_observations,
            })

    prepared_tracks.sort(key=lambda item: item["track_number"])
    metrics = _summarize_tracks(prepared_tracks)
    events = []
    rule_totals = defaultdict(int)

    for rule in clean_config["rules"]:
        if not rule["enabled"]:
            continue
        for track in prepared_tracks:
            observations = [item for item in track["observations"] if _matches_rule(item, rule, track["label"])]
            if not observations:
                continue

            if rule["type"] == "zone_intrusion":
                was_inside = False
                last_seen = None
                for observation in observations:
                    timestamp = observation["timestamp_seconds"]
                    if last_seen is not None and timestamp - last_seen > max_gap:
                        was_inside = False
                    point = box_anchor(
                        observation["bounding_box"], observation["width"],
                        observation["height"], rule["anchor"],
                    )
                    inside = point_in_polygon(point, rule["polygon"])
                    if inside and not was_inside:
                        events.append(_event(
                            rule, track, observation, timestamp,
                            "zone_intrusion", point=[round(point[0], 6), round(point[1], 6)],
                        ))
                    was_inside = inside
                    last_seen = timestamp

            elif rule["type"] == "line_crossing":
                for previous, current in zip(observations, observations[1:]):
                    gap = current["timestamp_seconds"] - previous["timestamp_seconds"]
                    if gap <= 0 or gap > max_gap:
                        continue
                    previous_point = box_anchor(
                        previous["bounding_box"], previous["width"], previous["height"], rule["anchor"]
                    )
                    current_point = box_anchor(
                        current["bounding_box"], current["width"], current["height"], rule["anchor"]
                    )
                    crossing = _line_crossing(previous_point, current_point, rule["line"])
                    if crossing is None:
                        continue
                    direction, ratio, crossing_point = crossing
                    if rule["direction"] != "both" and direction != rule["direction"]:
                        continue
                    event_time = previous["timestamp_seconds"] + ratio * gap
                    events.append(_event(
                        rule, track, current, event_time, "line_crossing",
                        direction=direction, point=[round(crossing_point[0], 6), round(crossing_point[1], 6)],
                    ))

            elif rule["type"] == "loitering":
                entry_time = None
                last_inside_time = None
                emitted = False
                for observation in observations:
                    timestamp = observation["timestamp_seconds"]
                    point = box_anchor(
                        observation["bounding_box"], observation["width"],
                        observation["height"], rule["anchor"],
                    )
                    inside = point_in_polygon(point, rule["polygon"])
                    if not inside:
                        entry_time = None
                        last_inside_time = None
                        emitted = False
                        continue
                    if last_inside_time is None or timestamp - last_inside_time > max_gap:
                        entry_time = timestamp
                        emitted = False
                    last_inside_time = timestamp
                    if entry_time is not None and not emitted and timestamp - entry_time >= rule["dwell_seconds"]:
                        trigger_time = entry_time + rule["dwell_seconds"]
                        events.append(_event(
                            rule, track, observation, trigger_time, "loitering",
                            dwell_seconds=round(rule["dwell_seconds"], 3),
                            zone_entry_seconds=round(entry_time, 3),
                        ))
                        emitted = True

    events.sort(key=lambda item: (item["timestamp_seconds"], item["rule_id"], item["track_number"], item["event_type"]))
    for item in events:
        rule_totals[item["rule_id"]] += 1

    return {
        "schema_version": 1,
        "summary": metrics,
        "event_summary": {
            "total_events": len(events),
            "events_by_type": dict(sorted(Counter(item["event_type"] for item in events).items())),
            "events_by_rule": dict(sorted(rule_totals.items())),
        },
        "events": events,
    }
