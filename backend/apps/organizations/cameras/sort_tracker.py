"""SORT-style multi-object tracking with a Kalman filter and Hungarian assignment.

This module is deliberately independent from Django so its association logic can
be tested without loading the project settings.

Track IDs are local to one tracking run. They are not identity labels.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment


_INVALID_COST = 1_000_000.0


def _valid_box(box: Any) -> list[float] | None:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        values = [float(value) for value in box]
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        return None
    return values


def _box_to_measurement(box: list[float]) -> np.ndarray:
    x1, y1, x2, y2 = box
    return np.asarray(
        [
            (x1 + x2) / 2.0,
            (y1 + y2) / 2.0,
            x2 - x1,
            y2 - y1,
        ],
        dtype=float,
    )


def _measurement_to_box(measurement: np.ndarray) -> list[float]:
    cx, cy, width, height = (float(value) for value in measurement[:4])
    width = max(width, 1.0)
    height = max(height, 1.0)
    return [
        cx - width / 2.0,
        cy - height / 2.0,
        cx + width / 2.0,
        cy + height / 2.0,
    ]


def _iou(box_a: list[float], box_b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    intersection_width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    intersection_height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = intersection_width * intersection_height
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _normalized_center_distance(box_a: list[float], box_b: list[float]) -> float:
    a = _box_to_measurement(box_a)
    b = _box_to_measurement(box_b)
    distance = math.hypot(float(a[0] - b[0]), float(a[1] - b[1]))
    scale_a = math.hypot(float(a[2]), float(a[3]))
    scale_b = math.hypot(float(b[2]), float(b[3]))
    return distance / max(scale_a, scale_b, 1.0)


class _KalmanBoxFilter:
    """Constant-velocity Kalman filter for box center and size.

    State: [cx, cy, width, height, vx, vy, vwidth, vheight].
    Measurement: [cx, cy, width, height].
    """

    def __init__(self, box: list[float], timestamp_seconds: float):
        self.state = np.zeros((8, 1), dtype=float)
        self.state[:4, 0] = _box_to_measurement(box)

        # High initial velocity uncertainty lets the first matched movement
        # establish velocity instead of forcing a near-stationary prediction.
        self.covariance = np.diag(
            [25.0, 25.0, 64.0, 64.0, 400.0, 400.0, 100.0, 100.0]
        )
        self.observation_matrix = np.zeros((4, 8), dtype=float)
        self.observation_matrix[:4, :4] = np.eye(4, dtype=float)
        self.measurement_noise = np.diag([16.0, 16.0, 36.0, 36.0])
        self.timestamp_seconds = float(timestamp_seconds)

    def predict(self, timestamp_seconds: float) -> list[float]:
        timestamp = float(timestamp_seconds)
        delta = timestamp - self.timestamp_seconds
        if not math.isfinite(delta) or delta <= 0:
            delta = 1.0
        # Prevent unstable jumps if malformed input contains a very large gap.
        delta = min(delta, 10.0)

        transition = np.eye(8, dtype=float)
        for index in range(4):
            transition[index, index + 4] = delta

        process_noise = np.diag(
            [
                2.0 * delta * delta,
                2.0 * delta * delta,
                3.0 * delta * delta,
                3.0 * delta * delta,
                12.0 * delta,
                12.0 * delta,
                8.0 * delta,
                8.0 * delta,
            ]
        )

        self.state = transition @ self.state
        self.covariance = (
            transition @ self.covariance @ transition.T + process_noise
        )
        self.state[2, 0] = max(self.state[2, 0], 1.0)
        self.state[3, 0] = max(self.state[3, 0], 1.0)
        self.timestamp_seconds = timestamp
        return _measurement_to_box(self.state[:, 0])

    def update(self, box: list[float]) -> None:
        measurement = _box_to_measurement(box).reshape(4, 1)
        innovation = measurement - self.observation_matrix @ self.state
        innovation_covariance = (
            self.observation_matrix
            @ self.covariance
            @ self.observation_matrix.T
            + self.measurement_noise
        )
        kalman_gain = np.linalg.solve(
            innovation_covariance,
            self.observation_matrix @ self.covariance,
        ).T

        self.state = self.state + kalman_gain @ innovation

        # Joseph-form covariance update is more numerically stable.
        identity = np.eye(8, dtype=float)
        residual = identity - kalman_gain @ self.observation_matrix
        self.covariance = (
            residual @ self.covariance @ residual.T
            + kalman_gain @ self.measurement_noise @ kalman_gain.T
        )
        self.state[2, 0] = max(self.state[2, 0], 1.0)
        self.state[3, 0] = max(self.state[3, 0], 1.0)


def _normalize_frame_detections(frame: dict[str, Any]) -> list[dict[str, Any]]:
    frame_number = int(frame["frame_number"])
    timestamp = float(frame.get("timestamp_seconds") or 0.0)
    if not math.isfinite(timestamp):
        timestamp = 0.0

    normalized = []
    for detection in list(frame.get("detections") or []):
        box = _valid_box(detection.get("bounding_box"))
        if box is None:
            continue
        try:
            confidence = float(detection.get("confidence", 0.0))
            class_id = int(detection["class_id"])
            label = str(detection["label"])[:80]
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            continue
        normalized.append(
            {
                "detection_id": detection.get("detection_id"),
                "source_frame_id": detection.get(
                    "source_frame_id", frame.get("source_frame_id")
                ),
                "frame_number": frame_number,
                "timestamp_seconds": timestamp,
                "class_id": class_id,
                "label": label,
                "confidence": confidence,
                "bounding_box": box,
            }
        )
    return normalized


def associate_detections_sort(
    frame_records,
    iou_threshold: float = 0.30,
    max_gap_frames: int = 2,
    max_center_distance: float = 1.25,
):
    """Associate detections using Kalman prediction + Hungarian assignment.

    Matching is class-aware. A pair is eligible when its predicted boxes have
    enough IoU OR their center distance is within ``max_center_distance`` box
    diagonals. The Hungarian algorithm then chooses a globally optimal
    one-to-one assignment for the current frame.

    ``max_gap_frames`` is the number of consecutive sampled frames a track may
    miss before it is retired. This is not an appearance/re-identification
    model; after long occlusions or crossings, identity switches remain possible.
    """
    iou_threshold = float(iou_threshold)
    max_gap_frames = int(max_gap_frames)
    max_center_distance = float(max_center_distance)

    if not 0.05 <= iou_threshold <= 0.95:
        raise ValueError("IoU threshold must be between 0.05 and 0.95.")
    if not 0 <= max_gap_frames <= 30:
        raise ValueError("Maximum gap must be between 0 and 30 frames.")
    if not 0.25 <= max_center_distance <= 5.0:
        raise ValueError("Maximum center distance must be between 0.25 and 5.0.")

    tracks: dict[int, dict[str, Any]] = {}
    next_track_number = 1
    observations_total = 0

    for sequence_index, frame in enumerate(frame_records):
        frame_number = int(frame["frame_number"])
        timestamp = float(frame.get("timestamp_seconds") or 0.0)
        if not math.isfinite(timestamp):
            timestamp = 0.0
        detections = _normalize_frame_detections(frame)

        active_track_numbers = []
        predicted_boxes = []
        for track_number, track in tracks.items():
            missed_frames = sequence_index - track["last_detection_sequence_index"] - 1
            if missed_frames > max_gap_frames:
                continue
            predicted_boxes.append(track["kalman"].predict(timestamp))
            active_track_numbers.append(track_number)

        assignments: dict[int, int] = {}
        if active_track_numbers and detections:
            cost_matrix = np.full(
                (len(active_track_numbers), len(detections)),
                _INVALID_COST,
                dtype=float,
            )

            for track_index, track_number in enumerate(active_track_numbers):
                track = tracks[track_number]
                predicted_box = predicted_boxes[track_index]
                for detection_index, detection in enumerate(detections):
                    if detection["class_id"] != track["class_id"]:
                        continue

                    detection_box = detection["bounding_box"]
                    overlap = _iou(predicted_box, detection_box)
                    center_distance = _normalized_center_distance(
                        predicted_box, detection_box
                    )

                    # Permit a low-IoU match when the Kalman-predicted center
                    # remains spatially plausible. This handles fast motion.
                    if (
                        overlap < iou_threshold
                        and center_distance > max_center_distance
                    ):
                        continue

                    normalized_distance = min(
                        center_distance / max_center_distance, 1.0
                    )
                    cost = 0.70 * (1.0 - overlap) + 0.30 * normalized_distance
                    cost_matrix[track_index, detection_index] = cost

            row_indices, column_indices = linear_sum_assignment(cost_matrix)
            for track_index, detection_index in zip(row_indices, column_indices):
                if cost_matrix[track_index, detection_index] >= _INVALID_COST:
                    continue
                track_number = active_track_numbers[track_index]
                assignments[int(detection_index)] = track_number

        for detection_index, detection in enumerate(detections):
            track_number = assignments.get(detection_index)
            if track_number is None:
                track_number = next_track_number
                next_track_number += 1
                tracks[track_number] = {
                    "track_number": track_number,
                    "class_id": detection["class_id"],
                    "label": detection["label"],
                    "first_frame_number": detection["frame_number"],
                    "last_frame_number": detection["frame_number"],
                    "first_timestamp_seconds": detection["timestamp_seconds"],
                    "last_timestamp_seconds": detection["timestamp_seconds"],
                    "last_detection_sequence_index": sequence_index,
                    "kalman": _KalmanBoxFilter(
                        detection["bounding_box"], detection["timestamp_seconds"]
                    ),
                    "observations": [],
                }
            else:
                tracks[track_number]["kalman"].update(detection["bounding_box"])

            track = tracks[track_number]
            track["last_frame_number"] = detection["frame_number"]
            track["last_timestamp_seconds"] = detection["timestamp_seconds"]
            track["last_detection_sequence_index"] = sequence_index
            observation = {
                "track_number": track_number,
                "detection_id": detection["detection_id"],
                "source_frame_id": detection["source_frame_id"],
                "frame_number": frame_number,
                "timestamp_seconds": detection["timestamp_seconds"],
                "confidence": detection["confidence"],
                "bounding_box": detection["bounding_box"],
            }
            track["observations"].append(observation)
            observations_total += 1

    results = []
    for track_number in sorted(tracks):
        track = tracks[track_number]
        results.append(
            {
                "track_number": track_number,
                "class_id": track["class_id"],
                "label": track["label"],
                "first_frame_number": track["first_frame_number"],
                "last_frame_number": track["last_frame_number"],
                "first_timestamp_seconds": track["first_timestamp_seconds"],
                "last_timestamp_seconds": track["last_timestamp_seconds"],
                "observations_count": len(track["observations"]),
                "observations": track["observations"],
            }
        )

    return {
        "tracks": results,
        "tracks_count": len(results),
        "observations_count": observations_total,
    }


class LiveSORTTracker:
    """Incremental SORT tracker for unbounded live streams.

    The batch functions above remain unchanged for recorded-video analysis.
    This class only keeps active Kalman states and emits current-frame matches.
    """

    def __init__(
        self,
        iou_threshold: float = 0.30,
        max_gap_frames: int = 8,
        max_center_distance: float = 1.25,
    ):
        self.iou_threshold = float(iou_threshold)
        self.max_gap_frames = int(max_gap_frames)
        self.max_center_distance = float(max_center_distance)
        if not 0.05 <= self.iou_threshold <= 0.95:
            raise ValueError("IoU threshold must be between 0.05 and 0.95.")
        if not 0 <= self.max_gap_frames <= 120:
            raise ValueError("Live max_gap_frames must be between 0 and 120.")
        if not 0.25 <= self.max_center_distance <= 5.0:
            raise ValueError("Maximum center distance must be between 0.25 and 5.0.")
        self._tracks: dict[int, dict[str, Any]] = {}
        self._next_track_number = 1
        self._sequence_index = -1

    def reset(self):
        self._tracks.clear()
        self._next_track_number = 1
        self._sequence_index = -1

    def update(self, detections, frame_number: int, timestamp_seconds: float):
        """Associate detections for one live inference frame.

        Input detections use the same class_id/label/confidence/bounding_box
        structure as ``infer_live_image``. Output is one item per detection with
        a stable ``track_number`` within this camera session.
        """
        self._sequence_index += 1
        timestamp = float(timestamp_seconds)
        frame = {
            "frame_number": int(frame_number),
            "timestamp_seconds": timestamp,
            "detections": detections,
        }
        normalized = _normalize_frame_detections(frame)

        active_numbers = []
        predicted_boxes = []
        retired = []
        for number, track in self._tracks.items():
            missed = self._sequence_index - track["last_sequence_index"] - 1
            if missed > self.max_gap_frames:
                retired.append(number)
                continue
            predicted_boxes.append(track["kalman"].predict(timestamp))
            active_numbers.append(number)
        for number in retired:
            self._tracks.pop(number, None)

        assignments: dict[int, int] = {}
        if active_numbers and normalized:
            cost_matrix = np.full((len(active_numbers), len(normalized)), _INVALID_COST, dtype=float)
            for track_index, number in enumerate(active_numbers):
                track = self._tracks[number]
                predicted = predicted_boxes[track_index]
                for detection_index, detection in enumerate(normalized):
                    if detection["class_id"] != track["class_id"]:
                        continue
                    candidate = detection["bounding_box"]
                    overlap = _iou(predicted, candidate)
                    distance = _normalized_center_distance(predicted, candidate)
                    if overlap < self.iou_threshold and distance > self.max_center_distance:
                        continue
                    cost_matrix[track_index, detection_index] = (
                        0.70 * (1.0 - overlap)
                        + 0.30 * min(distance / self.max_center_distance, 1.0)
                    )
            rows, columns = linear_sum_assignment(cost_matrix)
            for row, column in zip(rows, columns):
                if cost_matrix[row, column] < _INVALID_COST:
                    assignments[int(column)] = active_numbers[int(row)]

        current = []
        for detection_index, detection in enumerate(normalized):
            number = assignments.get(detection_index)
            if number is None:
                number = self._next_track_number
                self._next_track_number += 1
                self._tracks[number] = {
                    "class_id": detection["class_id"],
                    "label": detection["label"],
                    "kalman": _KalmanBoxFilter(detection["bounding_box"], timestamp),
                    "last_sequence_index": self._sequence_index,
                    "first_frame_number": int(frame_number),
                }
            else:
                track = self._tracks[number]
                track["kalman"].update(detection["bounding_box"])
                track["last_sequence_index"] = self._sequence_index

            current.append({
                **detection,
                "track_number": number,
                "predicted_box": _measurement_to_box(self._tracks[number]["kalman"].state[:, 0]),
            })
        return current

    @property
    def active_track_count(self) -> int:
        return len(self._tracks)
