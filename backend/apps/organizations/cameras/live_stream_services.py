from __future__ import annotations

import os
import threading
import time
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import close_old_connections
from django.utils import timezone

from .detection_services import infer_live_image, resolve_device
from .event_models import AnalyticsRule
from .live_models import (
    CameraLiveEvent,
    CameraLiveEventActivity,
    CameraLiveState,
    CameraWorkerHeartbeat,
)
from .live_rule_engine import LiveRuleEvaluator
from .models import Camera
from .sort_tracker import LiveSORTTracker


_STOP = threading.Event()
_INFERENCE_LOCK = threading.RLock()


def _now():
    return timezone.now()


def _set_state(camera_id: int, **values):
    values["updated_at"] = _now()
    CameraLiveState.objects.filter(camera_id=camera_id).update(**values)


def _open_capture(cv2, stream_url):
    capture = cv2.VideoCapture()
    try:
        parameters = []
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            parameters.extend([int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC), 7000])
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            parameters.extend([int(cv2.CAP_PROP_READ_TIMEOUT_MSEC), 5000])
        opened = capture.open(stream_url, cv2.CAP_FFMPEG, parameters) if parameters else capture.open(stream_url, cv2.CAP_FFMPEG)
    except Exception:
        opened = False
    if not opened:
        capture.release()
        # Fallback helps OpenCV builds that do not expose FFmpeg timeout params.
        capture = cv2.VideoCapture(stream_url)
    try:
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return capture


def _draw_live_overlay(cv2, frame, camera_name, detections, rules, timestamp):
    height, width = frame.shape[:2]
    output = frame.copy()

    for rule in rules:
        geometry = rule.geometry or {}
        if rule.rule_type in {"zone_intrusion", "loitering"}:
            polygon = geometry.get("polygon") or []
            if len(polygon) >= 3:
                points = [
                    (int(round(float(x) * width)), int(round(float(y) * height)))
                    for x, y in polygon
                ]
                import numpy as np
                cv2.polylines(output, [np.asarray(points, dtype="int32")], True, (40, 70, 240), 2, cv2.LINE_AA)
                cv2.putText(output, str(rule.name)[:36], points[0], cv2.FONT_HERSHEY_SIMPLEX, 0.52, (40, 70, 240), 2, cv2.LINE_AA)
        elif rule.rule_type == "line_crossing":
            line = geometry.get("line") or []
            if len(line) == 2:
                p1 = (int(float(line[0][0]) * width), int(float(line[0][1]) * height))
                p2 = (int(float(line[1][0]) * width), int(float(line[1][1]) * height))
                cv2.line(output, p1, p2, (0, 190, 255), 3, cv2.LINE_AA)
                cv2.putText(output, str(rule.name)[:36], p1, cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 190, 255), 2, cv2.LINE_AA)

    for item in detections:
        x1, y1, x2, y2 = [int(round(value)) for value in item["bounding_box"]]
        number = int(item["track_number"])
        # Deterministic BGR color; avoids random flicker between frames.
        color = (
            60 + (number * 47) % 170,
            60 + (number * 83) % 170,
            60 + (number * 29) % 170,
        )
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        title = f'{item["label"]} | ID {number} | {float(item["confidence"]):.2f}'
        text_y = max(18, y1 - 7)
        cv2.putText(output, title[:72], (x1, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2, cv2.LINE_AA)

    cv2.rectangle(output, (0, 0), (width, 32), (18, 24, 34), -1)
    header = f"LIVE  |  {camera_name[:42]}  |  {len(detections)} objects  |  {timestamp:.1f}s"
    cv2.putText(output, header, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 240, 247), 1, cv2.LINE_AA)
    return output


def _persist_live_events(camera, state, events):
    for item in events:
        rule = item["rule"]
        if item["event_type"] == "zone_intrusion":
            severity = CameraLiveEvent.Severity.HIGH
        elif item["event_type"] == "line_crossing":
            severity = CameraLiveEvent.Severity.MEDIUM
        else:
            severity = CameraLiveEvent.Severity.HIGH

        event, created = CameraLiveEvent.objects.get_or_create(
            camera=camera,
            session_id=state.session_id,
            rule=rule,
            track_number=item["track_number"],
            event_type=item["event_type"],
            frame_number=item["frame_number"],
            defaults={
                "organization": camera.organization,
                "rule_name": item["rule_name"],
                "label": item["label"],
                "timestamp_seconds": item["timestamp_seconds"],
                "confidence": item["confidence"],
                "details": item["details"],
                "severity": severity,
                "occurred_at": _now(),
            },
        )
        if created:
            CameraLiveEventActivity.objects.create(
                organization=camera.organization,
                event=event,
                action=CameraLiveEventActivity.Action.CREATED,
                to_status=event.status,
                note="Automatically generated by live camera analytics.",
            )


def _save_snapshot(state, jpeg_bytes, detections, frame_number, width, height, timestamp, fps):
    old_name = state.latest_frame.name if state.latest_frame else ""
    file_name = f"live_{state.camera_id}_{uuid.uuid4().hex}.jpg"
    state.latest_frame.save(file_name, ContentFile(jpeg_bytes), save=False)
    state.latest_detections = [
        {
            "track_number": int(item["track_number"]),
            "label": str(item["label"]),
            "class_id": int(item["class_id"]),
            "confidence": float(item["confidence"]),
            "bounding_box": [int(round(value)) for value in item["bounding_box"]],
        }
        for item in detections[:100]
    ]
    state.frame_number = int(frame_number)
    state.frames_processed += 1
    state.objects_count = len(detections)
    state.tracks_count = len({int(item["track_number"]) for item in detections})
    state.fps_actual = round(float(fps), 2)
    state.width = int(width)
    state.height = int(height)
    state.last_frame_at = _now()
    state.last_inference_at = state.last_frame_at
    state.last_error = ""
    state.status = CameraLiveState.Status.ONLINE
    state.save(update_fields=[
        "latest_frame", "latest_detections", "frame_number", "frames_processed",
        "objects_count", "tracks_count", "fps_actual", "width", "height",
        "last_frame_at", "last_inference_at", "last_error", "status", "updated_at",
    ])
    if old_name and old_name != state.latest_frame.name:
        try:
            default_storage.delete(old_name)
        except Exception:
            pass


def _load_rules(camera):
    return list(
        AnalyticsRule.objects.filter(
            organization=camera.organization,
            camera=camera,
            is_active=True,
        ).order_by("id")
    )


def _camera_requested(camera_id: int) -> bool:
    close_old_connections()
    state = CameraLiveState.objects.filter(camera_id=camera_id).values("is_requested").first()
    camera_enabled = Camera.objects.filter(pk=camera_id).values_list("is_enabled", flat=True).first()
    close_old_connections()
    return bool(state and state["is_requested"] and camera_enabled)


def _mark_camera_stopped(camera_id: int, camera_status=None):
    CameraLiveState.objects.filter(camera_id=camera_id).update(
        is_requested=False,
        status=CameraLiveState.Status.STOPPED,
        fps_actual=0.0,
        last_error="",
        updated_at=_now(),
    )
    if camera_status:
        # A concurrent camera disable must not be overwritten with OFFLINE.
        Camera.objects.filter(pk=camera_id, is_enabled=True).update(
            status=camera_status,
            updated_at=_now(),
        )
    close_old_connections()


def run_one_camera(camera_id: int, inference_lock: threading.RLock, stop_event: threading.Event):
    """Reconnect-safe camera loop; one thread per requested RTSP camera."""
    import cv2

    close_old_connections()
    try:
        camera = Camera.objects.select_related("organization").get(pk=camera_id)
        state, _ = CameraLiveState.objects.get_or_create(camera=camera)
        state.session_id = uuid.uuid4()
        state.status = CameraLiveState.Status.STARTING
        state.last_error = ""
        state.session_started_at = _now()
        state.frame_number = 0
        state.frames_processed = 0
        state.objects_count = 0
        state.tracks_count = 0
        state.fps_actual = 0.0
        state.save(update_fields=[
            "session_id", "status", "last_error", "session_started_at", "frame_number",
            "frames_processed", "objects_count", "tracks_count", "fps_actual", "updated_at",
        ])
        camera_status = Camera.Status.PENDING
        failure_count = 0
        device = resolve_device("auto")
        tracker = LiveSORTTracker(iou_threshold=0.30, max_gap_frames=max(3, camera.target_fps * 3))
        evaluator = LiveRuleEvaluator()
        cached_rules = []
        rules_loaded_at = 0.0
        frame_index = 0
        session_monotonic = time.monotonic()
        next_inference_at = 0.0
        last_health_update = 0.0
        fps_samples = []
        last_fps_measure = time.monotonic()

        while not stop_event.is_set() and _camera_requested(camera_id):
            try:
                camera.refresh_from_db()
                state.refresh_from_db()
                stream_url = camera.build_connection_url()
            except Exception as exc:
                _set_state(camera_id, status=CameraLiveState.Status.ERROR, last_error=str(exc)[:1000], is_requested=False)
                Camera.objects.filter(pk=camera_id).update(status=Camera.Status.ERROR, updated_at=_now())
                return

            _set_state(camera_id, status=CameraLiveState.Status.STARTING, last_error="")
            capture = _open_capture(cv2, stream_url)
            if not capture.isOpened():
                capture.release()
                failure_count += 1
                camera_status = Camera.Status.OFFLINE
                _set_state(
                    camera_id,
                    status=CameraLiveState.Status.RECONNECTING,
                    last_error="RTSP stream could not be opened. Check camera network, stream path and credentials.",
                )
                Camera.objects.filter(pk=camera_id).update(status=camera_status, updated_at=_now())
                if not _wait_or_stop(stop_event, min(30.0, max(2.0, 2.0 ** min(failure_count, 4))), camera_id):
                    break
                continue

            failure_count = 0
            camera_status = Camera.Status.ONLINE
            Camera.objects.filter(pk=camera_id).update(status=Camera.Status.ONLINE, last_seen_at=_now(), updated_at=_now())
            _set_state(camera_id, status=CameraLiveState.Status.ONLINE, last_error="")
            tracker.reset()
            evaluator = LiveRuleEvaluator()
            consecutive_read_failures = 0
            rules_loaded_at = 0.0
            next_inference_at = 0.0

            try:
                last_control_check = 0.0
                while not stop_event.is_set():
                    loop_time = time.monotonic()
                    if loop_time - last_control_check >= 1.0:
                        if not _camera_requested(camera_id):
                            break
                        last_control_check = loop_time
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        consecutive_read_failures += 1
                        if consecutive_read_failures < 3:
                            time.sleep(0.05)
                            continue
                        _set_state(
                            camera_id,
                            status=CameraLiveState.Status.RECONNECTING,
                            last_error="Camera stream stopped delivering frames; reconnecting.",
                        )
                        Camera.objects.filter(pk=camera_id).update(status=Camera.Status.OFFLINE, updated_at=_now())
                        break
                    consecutive_read_failures = 0
                    moment = time.monotonic()
                    period = 1.0 / max(1, min(10, int(camera.target_fps or 2)))
                    if moment < next_inference_at:
                        continue
                    next_inference_at = moment + period

                    height, width = frame.shape[:2]
                    if max(width, height) > 1280:
                        scale = 1280.0 / max(width, height)
                        frame = cv2.resize(
                            frame,
                            (max(1, int(width * scale)), max(1, int(height * scale))),
                            interpolation=cv2.INTER_AREA,
                        )
                        height, width = frame.shape[:2]
                    timestamp = max(0.0, moment - session_monotonic)
                    with inference_lock:
                        detections = infer_live_image(frame, camera.confidence_threshold, device)
                    frame_index += 1
                    tracked = tracker.update(detections, frame_index, timestamp)

                    if moment - rules_loaded_at >= 10.0:
                        cached_rules = _load_rules(camera)
                        evaluator.set_rules(cached_rules)
                        rules_loaded_at = moment
                    events = evaluator.evaluate(tracked, width, height, timestamp, frame_index)
                    _persist_live_events(camera, state, events)

                    annotated = _draw_live_overlay(cv2, frame, camera.name, tracked, cached_rules, timestamp)
                    encoded_ok, encoded = cv2.imencode(
                        ".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 82]
                    )
                    if not encoded_ok:
                        continue

                    fps_samples.append(moment)
                    fps_samples = [sample for sample in fps_samples if moment - sample <= 5.0]
                    measured_fps = len(fps_samples) / max(1.0, min(5.0, moment - last_fps_measure))
                    _save_snapshot(
                        state,
                        encoded.tobytes(),
                        tracked,
                        frame_index,
                        width,
                        height,
                        timestamp,
                        min(120.0, measured_fps),
                    )

                    if moment - last_health_update >= 5.0:
                        Camera.objects.filter(pk=camera_id).update(
                            status=Camera.Status.ONLINE,
                            last_seen_at=_now(),
                            updated_at=_now(),
                        )
                        last_health_update = moment
            finally:
                capture.release()

            if not _camera_requested(camera_id):
                break
            failure_count += 1
            if not _wait_or_stop(stop_event, min(30.0, max(1.0, 2.0 ** min(failure_count, 4))), camera_id):
                break

        _mark_camera_stopped(camera_id, Camera.Status.OFFLINE if camera_status == Camera.Status.ONLINE else camera_status)
    except Exception as exc:
        safe_message = str(exc) if exc.__class__.__name__ in {"DetectionProcessingError", "RuntimeError"} else "Live camera worker stopped because of an unexpected processing error."
        _set_state(camera_id, status=CameraLiveState.Status.ERROR, last_error=safe_message[:1000], is_requested=False, fps_actual=0.0)
        Camera.objects.filter(pk=camera_id).update(status=Camera.Status.ERROR, updated_at=_now())
    finally:
        close_old_connections()


def _wait_or_stop(stop_event, seconds: float, camera_id: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if stop_event.is_set() or not _camera_requested(camera_id):
            return False
        time.sleep(0.25)
    return True


def _process_is_running(pid: int) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import subprocess
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return f'"{pid}"' in result.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def run_live_camera_manager(poll_seconds: float = 2.0):
    """Long-running manager shared by all RTSP cameras in the organization(s)."""
    close_old_connections()
    heartbeat, _ = CameraWorkerHeartbeat.objects.get_or_create(pk=1)
    heartbeat.refresh_from_db()
    if (
        heartbeat.process_id
        and heartbeat.process_id != os.getpid()
        and heartbeat.last_heartbeat
        and (_now() - heartbeat.last_heartbeat).total_seconds() < 20
        and _process_is_running(heartbeat.process_id)
    ):
        raise RuntimeError(f"Live camera manager is already running (PID {heartbeat.process_id}).")

    CameraWorkerHeartbeat.objects.filter(pk=1).update(
        process_id=os.getpid(), started_at=_now(), last_heartbeat=_now(), last_error=""
    )
    _STOP.clear()
    threads: dict[int, threading.Thread] = {}
    inference_lock = threading.RLock()
    try:
        while not _STOP.is_set():
            close_old_connections()
            wanted = list(
                CameraLiveState.objects.filter(
                    is_requested=True,
                    camera__is_enabled=True,
                    camera__source_type__in=[Camera.SourceType.RTSP, Camera.SourceType.RTSPS],
                ).values_list("camera_id", flat=True)
            )
            wanted_set = set(wanted)
            for camera_id in wanted:
                thread = threads.get(camera_id)
                if thread is None or not thread.is_alive():
                    worker = threading.Thread(
                        target=run_one_camera,
                        args=(camera_id, inference_lock, _STOP),
                        name=f"aegis-live-camera-{camera_id}",
                        daemon=True,
                    )
                    threads[camera_id] = worker
                    worker.start()
            for camera_id, thread in list(threads.items()):
                if camera_id not in wanted_set and not thread.is_alive():
                    threads.pop(camera_id, None)
            CameraWorkerHeartbeat.objects.filter(pk=1).update(last_heartbeat=_now())
            _STOP.wait(max(0.5, min(10.0, float(poll_seconds))))
    finally:
        _STOP.set()
        for thread in list(threads.values()):
            thread.join(timeout=8.0)
        requested_ids = list(
            CameraLiveState.objects.filter(is_requested=True).values_list("camera_id", flat=True)
        )
        CameraLiveState.objects.filter(is_requested=True).update(
            is_requested=False,
            status=CameraLiveState.Status.STOPPED,
            fps_actual=0.0,
            updated_at=_now(),
        )
        if requested_ids:
            Camera.objects.filter(pk__in=requested_ids, is_enabled=True).update(
                status=Camera.Status.OFFLINE,
                updated_at=_now(),
            )
        CameraWorkerHeartbeat.objects.filter(pk=1).update(
            process_id=None, last_heartbeat=None, last_error=""
        )
        close_old_connections()
