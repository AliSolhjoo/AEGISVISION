"""Incremental evaluation of camera-scoped AnalyticsRule objects."""
from __future__ import annotations

from .video_analytics import _line_crossing, box_anchor, point_in_polygon


class LiveRuleEvaluator:
    def __init__(self, rules=None):
        self.rules = list(rules or [])
        self._states: dict[tuple[int, int], dict] = {}

    def set_rules(self, rules):
        self.rules = list(rules or [])
        active_ids = {int(rule.pk) for rule in self.rules}
        self._states = {
            key: value for key, value in self._states.items() if key[1] in active_ids
        }

    def evaluate(self, tracked_detections, width: int, height: int, timestamp: float, frame_number: int):
        emitted = []
        for detection in tracked_detections:
            track_number = int(detection["track_number"])
            label = str(detection["label"]).lower()
            confidence = float(detection["confidence"])
            point = box_anchor(
                detection["bounding_box"],
                width,
                height,
                "bottom_center",
            )

            for rule in self.rules:
                if not rule.is_active:
                    continue
                if rule.labels and label not in {str(item).lower() for item in rule.labels}:
                    continue
                if confidence < float(rule.minimum_confidence):
                    continue

                key = (track_number, int(rule.pk))
                state = self._states.setdefault(
                    key,
                    {
                        "previous_point": None,
                        "was_inside": False,
                        "inside_since": None,
                        "loitering_emitted": False,
                    },
                )
                event = None
                geometry = rule.geometry or {}

                if rule.rule_type in {"zone_intrusion", "loitering"}:
                    polygon = geometry.get("polygon") or []
                    if len(polygon) < 3:
                        continue
                    inside = point_in_polygon(point, [tuple(p) for p in polygon])

                    if rule.rule_type == "zone_intrusion":
                        if inside and not state["was_inside"]:
                            event = {
                                "event_type": "zone_intrusion",
                                "details": {
                                    "point": [round(point[0], 6), round(point[1], 6)],
                                    "initial_observation": state["previous_point"] is None,
                                },
                            }
                    else:
                        if inside:
                            if state["inside_since"] is None:
                                state["inside_since"] = float(timestamp)
                                state["loitering_emitted"] = False
                            dwell = max(0.0, float(timestamp) - float(state["inside_since"]))
                            if dwell >= float(rule.dwell_seconds) and not state["loitering_emitted"]:
                                state["loitering_emitted"] = True
                                event = {
                                    "event_type": "loitering",
                                    "details": {
                                        "point": [round(point[0], 6), round(point[1], 6)],
                                        "dwell_seconds": round(dwell, 3),
                                    },
                                }
                        else:
                            state["inside_since"] = None
                            state["loitering_emitted"] = False
                    state["was_inside"] = inside

                elif rule.rule_type == "line_crossing":
                    line = geometry.get("line") or []
                    previous = state["previous_point"]
                    if len(line) == 2 and previous is not None:
                        crossing = _line_crossing(previous, point, [tuple(p) for p in line])
                        if crossing:
                            direction, ratio, crossing_point = crossing
                            if rule.direction == "both" or rule.direction == direction:
                                event = {
                                    "event_type": "line_crossing",
                                    "details": {
                                        "direction": direction,
                                        "crossing_point": [round(crossing_point[0], 6), round(crossing_point[1], 6)],
                                    },
                                }

                state["previous_point"] = point
                if event:
                    emitted.append({
                        "rule": rule,
                        "rule_id": int(rule.pk),
                        "rule_name": rule.name,
                        "event_type": event["event_type"],
                        "track_number": track_number,
                        "label": label,
                        "confidence": confidence,
                        "frame_number": int(frame_number),
                        "timestamp_seconds": float(timestamp),
                        "details": event["details"],
                    })
        return emitted
