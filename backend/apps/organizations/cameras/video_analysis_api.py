from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import (
    Camera,
    DetectionRun,
    Membership,
    Organization,
    TrackingRun,
    VideoAsset,
    VideoProcessingJob,
)

from .video_analysis_workflow import (
    is_worker_running,
    read_state,
    spawn_analysis_worker,
    write_state,
)

MAX_UPLOAD_BYTES = 250 * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
DEFAULT_FRAME_INTERVAL_SECONDS = 1
DEFAULT_MAX_FRAMES = 300


def _membership_exists(user, organization_id) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return Membership.objects.filter(
        organization_id=organization_id,
        user_id=user.pk,
        status=Membership.Status.ACTIVE,
    ).exists()


def _get_accessible_asset(user, asset_id: int):
    try:
        asset = VideoAsset.objects.select_related("organization", "uploaded_by").get(pk=asset_id)
    except VideoAsset.DoesNotExist:
        return None
    if getattr(user, "is_superuser", False) or asset.uploaded_by_id == user.pk:
        return asset
    if _membership_exists(user, asset.organization_id):
        return asset
    return None


def _latest_runs(asset):
    detection = DetectionRun.objects.filter(asset=asset).order_by("-created_at", "-id").first()
    tracking = None
    if detection:
        tracking = TrackingRun.objects.filter(detection_run=detection).order_by("-created_at", "-id").first()
    return detection, tracking


def _output_path(tracking_id: int) -> Path:
    return Path(settings.BASE_DIR) / "tracking_exports" / f"tracking_run_{tracking_id}.mp4"


def _status_payload(request, asset):
    job = VideoProcessingJob.objects.filter(asset=asset).first()
    state = read_state(asset.pk)
    state_status = state.get("status")
    if state_status in {"queued", "processing"}:
        detection_id = state.get("detection_run_id")
        tracking_id = state.get("tracking_run_id")
        detection = (
            DetectionRun.objects.filter(pk=detection_id, asset=asset).first()
            if detection_id else None
        )
        tracking = (
            TrackingRun.objects.filter(pk=tracking_id, detection_run__asset=asset).first()
            if tracking_id else None
        )
    else:
        detection, tracking = _latest_runs(asset)

    labels = {
        "queued": (0, "در صف اجرا"),
        "extracting": (10, "استخراج فریم‌ها"),
        "detecting": (35, "تشخیص اشیا با هوش مصنوعی"),
        "tracking": (65, "رهگیری اشیا با SORT"),
        "event_analysis": (78, "تحلیل رویدادهای امنیتی"),
        "rendering": (90, "ساخت ویدئوی تحلیل‌شده"),
        "failed": (100, "تحلیل با خطا متوقف شد"),
        "completed": (100, "تحلیل کامل شد"),
    }

    # The workflow state is authoritative while a new run is in progress.
    # This avoids stale DetectionRun/TrackingRun records from an older run
    # making the UI report a false failure before the new run is created.
    state_status = state.get("status")
    if state_status in {"queued", "processing"}:
        phase = state.get("phase", "queued")
        if phase not in labels:
            phase = "queued"
        progress, message = labels[phase]
        # Use the persisted extraction job for a more accurate early status.
        if phase == "queued" and job and job.status == VideoProcessingJob.Status.PROCESSING:
            phase = "extracting"
            progress, message = labels[phase]
    elif state_status == "failed":
        phase = "failed"
        progress, message = labels[phase]
    elif state_status == "completed":
        phase = "completed"
        progress, message = labels[phase]
    else:
        # Fallback for assets that pre-date automatic workflow state files.
        if job and job.status == VideoProcessingJob.Status.QUEUED:
            phase = "queued"
        elif job and job.status == VideoProcessingJob.Status.PROCESSING:
            phase = "extracting"
        elif not detection:
            phase = "queued"
        elif detection.status in {DetectionRun.Status.QUEUED, DetectionRun.Status.PROCESSING}:
            phase = "detecting"
        elif detection.status == DetectionRun.Status.FAILED:
            phase = "failed"
        elif not tracking:
            phase = "tracking"
        elif tracking.status in {TrackingRun.Status.QUEUED, TrackingRun.Status.PROCESSING}:
            phase = "tracking"
        elif tracking.status == TrackingRun.Status.FAILED:
            phase = "failed"
        else:
            phase = "rendering"
        progress, message = labels.get(phase, (5, "در حال پردازش"))

    result_exists = False
    result_url = None
    if tracking and tracking.status == TrackingRun.Status.COMPLETED:
        expected = _output_path(tracking.pk)
        result_exists = expected.is_file() and expected.stat().st_size > 0
        if result_exists:
            result_url = request.build_absolute_uri(
                f"/api/video-analysis/assets/{asset.pk}/result/"
            )

    completed = bool(state_status == "completed" and result_exists)
    state_failed = bool(state_status == "failed" or phase == "failed")
    if completed:
        phase, progress, message = "completed", 100, labels["completed"][1]
    elif state_status == "completed" and not result_exists:
        phase, progress, message = "failed", 100, "فایل خروجی تحلیل پیدا نشد"
        state_failed = True

    error = (
        state.get("error")
        or (detection.error_message if detection and detection.status == DetectionRun.Status.FAILED else "")
        or (tracking.error_message if tracking and tracking.status == TrackingRun.Status.FAILED else "")
    )
    if state_failed and not error:
        error = message

    return {
        "asset_id": asset.pk,
        "asset_name": asset.name,
        "status": "completed" if completed else ("failed" if state_failed else "processing"),
        "phase": phase,
        "progress": (
            int(state.get("progress", progress))
            if state_status in {"queued", "processing"} and state.get("phase") == phase
            else progress
        ),
        "message": (
            state.get("message", message)
            if state_status in {"queued", "processing"} and state.get("phase") == phase
            else message
        ),
        "frames_extracted": job.frame_count if job else 0,
        "frames_detected": detection.frames_processed if detection else 0,
        "detections_count": detection.detections_count if detection else 0,
        "tracking_run_id": tracking.pk if tracking else None,
        "tracks_count": tracking.tracks_count if tracking else 0,
        "observations_count": tracking.observations_count if tracking else 0,
        "events_count": int(state.get("events_count", 0) or 0),
        "event_analysis_error": state.get("event_analysis_error", ""),
        "result_ready": result_exists,
        "result_url": result_url,
        "error": error,
    }


def _parse_int_field(data, field_name, default, minimum, maximum):
    raw = data.get(field_name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} باید عدد صحیح باشد.")
    if not minimum <= value <= maximum:
        raise ValueError(f"{field_name} باید بین {minimum} و {maximum} باشد.")
    return value


def _start_existing_asset(asset, request):
    """Queue/resume automatic analysis for an already-uploaded VideoAsset."""
    current = read_state(asset.pk)
    current_pid = current.get("worker_pid")
    if current.get("status") in {"queued", "processing"} and current_pid:
        try:
            current_pid = int(current_pid)
        except (TypeError, ValueError):
            current_pid = 0
        if current_pid and is_worker_running(current_pid):
            return current_pid, True

    with transaction.atomic():
        locked_asset = VideoAsset.objects.select_for_update().get(pk=asset.pk)
        job = VideoProcessingJob.objects.select_for_update().filter(asset=locked_asset).first()
        if job is None:
            job = VideoProcessingJob.objects.create(
                asset=locked_asset,
                created_by=locked_asset.uploaded_by,
                frame_interval_seconds=DEFAULT_FRAME_INTERVAL_SECONDS,
                max_frames=DEFAULT_MAX_FRAMES,
            )
        elif job.status == VideoProcessingJob.Status.FAILED:
            job.status = VideoProcessingJob.Status.QUEUED
            job.started_at = None
            job.finished_at = None
            job.frame_count = 0
            job.error_message = ""
            job.effective_interval_seconds = None
            job.save(update_fields=[
                "status", "started_at", "finished_at", "frame_count",
                "error_message", "effective_interval_seconds", "updated_at",
            ])

        VideoAsset.objects.filter(pk=locked_asset.pk).update(
            status=VideoAsset.Status.QUEUED,
            updated_at=timezone.now(),
        )
        write_state(locked_asset.pk, phase="queued", status="queued")

    pid = spawn_analysis_worker(asset.pk)
    return pid, False


class VideoAnalysisUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uploaded = request.FILES.get("video")
        organization_id = request.data.get("organization_id")
        if uploaded is None:
            return Response({"detail": "فایل ویدئو ارسال نشده است."}, status=status.HTTP_400_BAD_REQUEST)
        if not organization_id:
            return Response({"detail": "organization_id الزامی است."}, status=status.HTTP_400_BAD_REQUEST)

        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return Response({"detail": "فرمت ویدئو پشتیبانی نمی‌شود."}, status=status.HTTP_400_BAD_REQUEST)
        if uploaded.size <= 0 or uploaded.size > MAX_UPLOAD_BYTES:
            return Response({"detail": "حجم ویدئو باید بین ۱ بایت تا ۲۵۰ مگابایت باشد."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            frame_interval = _parse_int_field(
                request.data, "frame_interval_seconds", DEFAULT_FRAME_INTERVAL_SECONDS, 1, 60
            )
            max_frames = _parse_int_field(request.data, "max_frames", DEFAULT_MAX_FRAMES, 2, 300)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            organization = Organization.objects.get(pk=organization_id)
        except (Organization.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "سازمان معتبر نیست."}, status=status.HTTP_404_NOT_FOUND)
        if not _membership_exists(request.user, organization.pk):
            return Response({"detail": "به این سازمان دسترسی ندارید."}, status=status.HTTP_403_FORBIDDEN)

        camera = None
        camera_id = request.data.get("camera_id")
        if camera_id:
            try:
                camera = Camera.objects.get(pk=int(camera_id), organization=organization)
            except (Camera.DoesNotExist, ValueError, TypeError):
                return Response({"detail": "دوربین انتخاب‌شده معتبر نیست."}, status=status.HTTP_400_BAD_REQUEST)

        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        uploaded.seek(0)
        filename = os.path.basename(uploaded.name)
        name = (request.data.get("name") or Path(filename).stem).strip()[:150] or Path(filename).stem[:150]

        asset = VideoAsset(
            organization=organization,
            camera=camera,
            uploaded_by=request.user,
            name=name,
            original_filename=filename[:255],
            content_type=uploaded.content_type or mimetypes.guess_type(filename)[0] or "video/mp4",
            file_size=uploaded.size,
            sha256=digest.hexdigest(),
            status=VideoAsset.Status.QUEUED,
        )
        try:
            with transaction.atomic():
                asset.source_file.save(filename, uploaded, save=False)
                asset.save()
                VideoProcessingJob.objects.create(
                    asset=asset,
                    created_by=request.user,
                    frame_interval_seconds=frame_interval,
                    max_frames=max_frames,
                )
                write_state(asset.pk, phase="queued", status="queued")
        except Exception:
            if asset.pk and asset.source_file:
                asset.source_file.delete(save=False)
            raise

        try:
            pid = spawn_analysis_worker(asset.pk)
        except Exception as exc:
            write_state(asset.pk, phase="failed", status="failed", error=str(exc)[:1000])
            VideoAsset.objects.filter(pk=asset.pk).update(
                status=VideoAsset.Status.FAILED,
                updated_at=timezone.now(),
            )
            return Response(
                {"detail": "شروع پردازش پس‌زمینه ممکن نشد.", "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "asset_id": asset.pk,
                "worker_pid": pid,
                "status": "queued",
                "status_url": f"/api/video-analysis/assets/{asset.pk}/status/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class VideoAnalysisStartView(APIView):
    """Start/resume the complete AI pipeline for a video already in the library."""

    permission_classes = [IsAuthenticated]

    def post(self, request, asset_id: int):
        asset = _get_accessible_asset(request.user, asset_id)
        if asset is None:
            return Response({"detail": "ویدئو پیدا نشد یا دسترسی ندارید."}, status=status.HTTP_404_NOT_FOUND)
        if not asset.source_file:
            return Response({"detail": "فایل اصلی ویدئو موجود نیست."}, status=status.HTTP_400_BAD_REQUEST)

        state = read_state(asset.pk)
        _, latest_tracking = _latest_runs(asset)
        if state.get("status") == "completed" and latest_tracking and latest_tracking.status == TrackingRun.Status.COMPLETED:
            existing_output = _output_path(latest_tracking.pk)
            if existing_output.is_file() and existing_output.stat().st_size > 0:
                return Response(_status_payload(request, asset), status=status.HTTP_200_OK)

        try:
            pid, already_running = _start_existing_asset(asset, request)
        except Exception as exc:
            write_state(asset.pk, phase="failed", status="failed", error=str(exc)[:1000])
            return Response(
                {"detail": "شروع تحلیل خودکار ممکن نشد.", "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "asset_id": asset.pk,
                "worker_pid": pid,
                "status": "processing" if already_running else "queued",
                "status_url": f"/api/video-analysis/assets/{asset.pk}/status/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class VideoAnalysisStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, asset_id: int):
        asset = _get_accessible_asset(request.user, asset_id)
        if asset is None:
            return Response({"detail": "ویدئو پیدا نشد یا دسترسی ندارید."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_status_payload(request, asset))


class VideoAnalysisResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, asset_id: int):
        asset = _get_accessible_asset(request.user, asset_id)
        if asset is None:
            return Response({"detail": "ویدئو پیدا نشد یا دسترسی ندارید."}, status=status.HTTP_404_NOT_FOUND)
        _, tracking = _latest_runs(asset)
        if not tracking or tracking.status != TrackingRun.Status.COMPLETED:
            return Response({"detail": "ویدئوی تحلیل‌شده هنوز آماده نیست."}, status=status.HTTP_409_CONFLICT)

        path = _output_path(tracking.pk)
        if not path.is_file():
            return Response({"detail": "فایل خروجی پیدا نشد."}, status=status.HTTP_404_NOT_FOUND)

        file_size = path.stat().st_size
        if file_size <= 0:
            return Response({"detail": "فایل خروجی خالی است."}, status=status.HTTP_404_NOT_FOUND)

        range_header = request.headers.get("Range")
        start, end = 0, file_size - 1
        response_status = 200
        if range_header:
            try:
                unit, value = range_header.split("=", 1)
                if unit.strip().lower() != "bytes":
                    raise ValueError
                first, last = value.split("-", 1)
                if first:
                    start = int(first)
                    end = int(last) if last else file_size - 1
                else:
                    suffix_length = int(last)
                    if suffix_length <= 0:
                        raise ValueError
                    start = max(0, file_size - suffix_length)
                    end = file_size - 1
                if start < 0 or end < start or start >= file_size:
                    raise ValueError
                end = min(end, file_size - 1)
                response_status = 206
            except (ValueError, TypeError):
                response = Response(status=416)
                response["Content-Range"] = f"bytes */{file_size}"
                return response

        length = end - start + 1

        def file_iterator():
            with path.open("rb") as file_handle:
                file_handle.seek(start)
                remaining = length
                while remaining:
                    chunk = file_handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        response = StreamingHttpResponse(file_iterator(), status=response_status, content_type="video/mp4")
        response["Accept-Ranges"] = "bytes"
        response["Content-Length"] = str(length)
        response["Content-Disposition"] = f'inline; filename="tracking_run_{tracking.pk}.mp4"'
        response["Cache-Control"] = "private, no-store"
        if response_status == 206:
            response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        return response
