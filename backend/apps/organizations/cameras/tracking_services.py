from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .detection_models import DetectionFrame, DetectionRun
from .sort_tracker import associate_detections_sort
from .tracking_models import ObjectTrack, TrackObservation, TrackingRun


class TrackingProcessingError(Exception):
    """Raised when an object-tracking job cannot be completed safely."""


def intersection_over_union(box_a, box_b) -> float:
    """Calculate IoU for [x1, y1, x2, y2] pixel boxes."""
    if not isinstance(box_a, (list, tuple)) or not isinstance(box_b, (list, tuple)):
        return 0.0
    if len(box_a) != 4 or len(box_b) != 4:
        return 0.0
    try:
        ax1, ay1, ax2, ay2 = (float(value) for value in box_a)
        bx1, by1, bx2, by2 = (float(value) for value in box_b)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if ax2 <= ax1 or ay2 <= ay1 or bx2 <= bx1 or by2 <= by1:
        return 0.0

    intersection_width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    intersection_height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = intersection_width * intersection_height
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _normalize_detections(frame):
    """Normalize and validate one frame's detections for greedy IoU."""
    frame_number = int(frame["frame_number"])
    timestamp_seconds = float(frame.get("timestamp_seconds") or 0.0)
    normalized = []

    for detection in list(frame.get("detections") or []):
        box = detection.get("bounding_box")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        try:
            box = [float(value) for value in box]
            confidence = float(detection.get("confidence", 0.0))
            class_id = int(detection["class_id"])
            label = str(detection["label"])[:80]
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (
            box[2] <= box[0]
            or box[3] <= box[1]
            or not 0 <= confidence <= 1
        ):
            continue

        normalized.append(
            {
                "detection_id": detection.get("detection_id"),
                "source_frame_id": detection.get(
                    "source_frame_id", frame.get("source_frame_id")
                ),
                "frame_number": frame_number,
                "timestamp_seconds": timestamp_seconds,
                "class_id": class_id,
                "label": label,
                "confidence": confidence,
                "bounding_box": box,
            }
        )
    return normalized


def associate_detections(frame_records, iou_threshold=0.30, max_gap_frames=2):
    """Associate detections using the original class-aware greedy IoU tracker.

    Kept unchanged as ``greedy_iou_v1`` so previous behavior remains available.
    Track IDs are local to this tracking run; they are not identity labels.
    """
    if not 0.05 <= float(iou_threshold) <= 0.95:
        raise ValueError("IoU threshold must be between 0.05 and 0.95.")
    if not 0 <= int(max_gap_frames) <= 30:
        raise ValueError("Maximum gap must be between 0 and 30 frames.")

    tracks = {}
    next_track_number = 1
    observations_total = 0

    for sequence_index, frame in enumerate(frame_records):
        normalized = _normalize_detections(frame)
        frame_number = int(frame["frame_number"])
        timestamp_seconds = float(frame.get("timestamp_seconds") or 0.0)

        candidates = []
        for track_number, track in tracks.items():
            gap = sequence_index - track["last_sequence_index"] - 1
            if gap > max_gap_frames:
                continue
            for detection_index, detection in enumerate(normalized):
                if detection["class_id"] != track["class_id"]:
                    continue
                overlap = intersection_over_union(
                    track["last_box"], detection["bounding_box"]
                )
                if overlap >= iou_threshold:
                    candidates.append((overlap, track_number, detection_index))

        # Highest IoU wins; each previous track and current detection can match once.
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        assigned_tracks = set()
        assigned_detections = set()
        assignments = {}
        for overlap, track_number, detection_index in candidates:
            if track_number in assigned_tracks or detection_index in assigned_detections:
                continue
            assigned_tracks.add(track_number)
            assigned_detections.add(detection_index)
            assignments[detection_index] = track_number

        for detection_index, detection in enumerate(normalized):
            track_number = assignments.get(detection_index)
            if track_number is None:
                track_number = next_track_number
                next_track_number += 1
                tracks[track_number] = {
                    "track_number": track_number,
                    "class_id": detection["class_id"],
                    "label": detection["label"],
                    "first_frame_number": frame_number,
                    "last_frame_number": frame_number,
                    "first_timestamp_seconds": timestamp_seconds,
                    "last_timestamp_seconds": timestamp_seconds,
                    "last_sequence_index": sequence_index,
                    "last_box": detection["bounding_box"],
                    "observations": [],
                }

            track = tracks[track_number]
            track["last_frame_number"] = frame_number
            track["last_timestamp_seconds"] = timestamp_seconds
            track["last_sequence_index"] = sequence_index
            track["last_box"] = detection["bounding_box"]
            observation = {
                "track_number": track_number,
                "detection_id": detection["detection_id"],
                "source_frame_id": detection["source_frame_id"],
                "frame_number": frame_number,
                "timestamp_seconds": timestamp_seconds,
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


def run_association(frame_records, tracker_name, iou_threshold, max_gap_frames):
    """Dispatch a tracking run to its explicitly selected algorithm."""
    selected = (tracker_name or "greedy_iou_v1").strip().lower()
    if selected == "greedy_iou_v1":
        return associate_detections(
            frame_records,
            iou_threshold=iou_threshold,
            max_gap_frames=max_gap_frames,
        )
    if selected == "sort_v1":
        return associate_detections_sort(
            frame_records,
            iou_threshold=iou_threshold,
            max_gap_frames=max_gap_frames,
        )
    raise TrackingProcessingError(
        f"Unsupported tracker '{selected}'. Supported trackers: greedy_iou_v1, sort_v1."
    )


def _mark_failed(run, message: str):
    now = timezone.now()
    TrackingRun.objects.filter(pk=run.pk).update(
        status=TrackingRun.Status.FAILED,
        error_message=str(message)[:1000],
        finished_at=now,
        updated_at=now,
        frames_processed=0,
        tracks_count=0,
        observations_count=0,
    )
    run.refresh_from_db()
    return run


def process_tracking_run(tracking_run_id: int):
    """Process one queued tracking job and persist track observations."""
    run = TrackingRun.objects.select_related(
        "detection_run", "detection_run__asset", "detection_run__asset__organization"
    ).get(pk=tracking_run_id)
    if run.status != TrackingRun.Status.QUEUED:
        return run

    now = timezone.now()
    claimed = TrackingRun.objects.filter(
        pk=run.pk,
        status=TrackingRun.Status.QUEUED,
    ).update(
        status=TrackingRun.Status.PROCESSING,
        started_at=now,
        finished_at=None,
        error_message="",
        frames_processed=0,
        tracks_count=0,
        observations_count=0,
        updated_at=now,
    )
    if not claimed:
        run.refresh_from_db()
        return run
    run.refresh_from_db()

    try:
        detection_run = run.detection_run
        if detection_run.status != DetectionRun.Status.COMPLETED:
            raise TrackingProcessingError(
                "The source detection run must be completed first."
            )

        detection_frames = list(
            DetectionFrame.objects.filter(run=detection_run)
            .select_related("source_frame")
            .prefetch_related("detections")
            .order_by("source_frame__frame_number", "id")
        )
        if not detection_frames:
            raise TrackingProcessingError(
                "No completed detection frames are available for tracking."
            )

        frame_records = []
        for detection_frame in detection_frames:
            source_frame = detection_frame.source_frame
            frame_records.append(
                {
                    "source_frame_id": detection_frame.source_frame_id,
                    "frame_number": source_frame.frame_number,
                    "timestamp_seconds": source_frame.timestamp_seconds,
                    "detections": [
                        {
                            "detection_id": detection.pk,
                            "source_frame_id": detection_frame.source_frame_id,
                            "class_id": detection.class_id,
                            "label": detection.label,
                            "confidence": detection.confidence,
                            "bounding_box": detection.bounding_box,
                        }
                        for detection in detection_frame.detections.all()
                    ],
                }
            )

        result = run_association(
            frame_records,
            tracker_name=run.tracker_name,
            iou_threshold=run.iou_threshold,
            max_gap_frames=run.max_gap_frames,
        )

        with transaction.atomic():
            # Only rows belonging to this run are replaced. Other tracking runs
            # and all source detections remain untouched.
            ObjectTrack.objects.filter(tracking_run=run).delete()
            new_tracks = [
                ObjectTrack(
                    tracking_run=run,
                    track_number=item["track_number"],
                    class_id=item["class_id"],
                    label=item["label"],
                    status=ObjectTrack.Status.COMPLETED,
                    first_frame_number=item["first_frame_number"],
                    last_frame_number=item["last_frame_number"],
                    first_timestamp_seconds=item["first_timestamp_seconds"],
                    last_timestamp_seconds=item["last_timestamp_seconds"],
                    observations_count=item["observations_count"],
                )
                for item in result["tracks"]
            ]
            ObjectTrack.objects.bulk_create(new_tracks)
            persisted_tracks = {
                track.track_number: track
                for track in ObjectTrack.objects.filter(tracking_run=run)
            }
            observation_rows = []
            for track_data in result["tracks"]:
                track = persisted_tracks[track_data["track_number"]]
                for observation in track_data["observations"]:
                    observation_rows.append(
                        TrackObservation(
                            track=track,
                            detection_id=observation["detection_id"],
                            source_frame_id=observation["source_frame_id"],
                            frame_number=observation["frame_number"],
                            timestamp_seconds=observation["timestamp_seconds"],
                            confidence=observation["confidence"],
                            bounding_box=observation["bounding_box"],
                        )
                    )
            TrackObservation.objects.bulk_create(observation_rows)

            finished = timezone.now()
            TrackingRun.objects.filter(pk=run.pk).update(
                status=TrackingRun.Status.COMPLETED,
                frames_processed=len(detection_frames),
                tracks_count=result["tracks_count"],
                observations_count=result["observations_count"],
                error_message="",
                finished_at=finished,
                updated_at=finished,
            )

        run.refresh_from_db()
        return run
    except TrackingProcessingError as exc:
        ObjectTrack.objects.filter(tracking_run=run).delete()
        return _mark_failed(run, str(exc))
    except Exception:
        ObjectTrack.objects.filter(tracking_run=run).delete()
        return _mark_failed(
            run,
            "Object tracking failed because of an unexpected database or processing error.",
        )
