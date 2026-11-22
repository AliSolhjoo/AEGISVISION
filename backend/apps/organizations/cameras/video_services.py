from __future__ import annotations

import math
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from django.core.files.base import ContentFile

from .video_models import (
    MAX_VIDEO_DURATION_SECONDS,
    VideoAsset,
    VideoFrame,
    VideoProcessingJob,
)


class VideoProcessingError(Exception):
    """Raised when an uploaded video cannot be safely processed."""


def calculate_sample_timestamps(duration_seconds, interval_seconds, max_frames):
    """Return evenly bounded sample timestamps and the effective interval."""
    duration = max(0.0, float(duration_seconds or 0.0))
    interval = max(1.0, float(interval_seconds))
    frame_limit = max(2, int(max_frames))

    regular_count = int(duration // interval) + 1
    timestamps = [round(i * interval, 3) for i in range(regular_count)]

    if timestamps[-1] < duration and len(timestamps) < frame_limit:
        if duration - timestamps[-1] >= min(interval * 0.25, 0.5):
            timestamps.append(round(duration, 3))

    if len(timestamps) > frame_limit:
        effective = duration / (frame_limit - 1) if duration else interval
        timestamps = [round(i * effective, 3) for i in range(frame_limit)]
    else:
        effective = interval

    if not timestamps:
        timestamps = [0.0]

    return timestamps, round(float(effective), 3)


def delete_generated_frames(job):
    for frame in job.frames.all():
        if frame.image:
            frame.image.delete(save=False)
        frame.delete()


def _mark_failed(job, message):
    delete_generated_frames(job)
    now = timezone.now()
    VideoProcessingJob.objects.filter(pk=job.pk).update(
        status=VideoProcessingJob.Status.FAILED,
        error_message=str(message)[:1000],
        finished_at=now,
        updated_at=now,
        frame_count=0,
    )
    VideoAsset.objects.filter(pk=job.asset_id).update(
        status=VideoAsset.Status.FAILED,
        updated_at=now,
    )
    job.refresh_from_db()
    return job


def process_video_job(job_id):
    """Extract sampled JPEG frames from one queued video job.

    This function is intentionally invoked by a management command rather
    than inside the upload request, keeping large-video work out of HTTP.
    """
    job = VideoProcessingJob.objects.select_related("asset", "asset__organization").get(
        pk=job_id
    )
    if job.status not in {VideoProcessingJob.Status.QUEUED, VideoProcessingJob.Status.PROCESSING}:
        return job

    now = timezone.now()
    VideoProcessingJob.objects.filter(pk=job.pk).update(
        status=VideoProcessingJob.Status.PROCESSING,
        started_at=job.started_at or now,
        finished_at=None,
        error_message="",
        updated_at=now,
    )
    VideoAsset.objects.filter(pk=job.asset_id).update(
        status=VideoAsset.Status.PROCESSING,
        updated_at=now,
    )
    job.refresh_from_db()
    delete_generated_frames(job)

    capture = None
    try:
        try:
            import cv2
        except ImportError as exc:
            raise VideoProcessingError(
                "OpenCV is not installed. Install requirements.txt before processing videos."
            ) from exc

        asset = job.asset
        if not asset.source_file:
            raise VideoProcessingError("The uploaded video file is missing.")

        try:
            source_path = Path(asset.source_file.path)
        except (NotImplementedError, ValueError) as exc:
            raise VideoProcessingError(
                "The configured file storage does not expose a local file path."
            ) from exc

        if not source_path.is_file():
            raise VideoProcessingError("The uploaded video file was not found on disk.")
        if source_path.stat().st_size > 250 * 1024 * 1024:
            raise VideoProcessingError("The video exceeds the 250 MB processing limit.")

        capture = cv2.VideoCapture(str(source_path))
        if not capture.isOpened():
            raise VideoProcessingError(
                "The file could not be decoded as a supported video. Check its format and codec."
            )

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        if (
            not math.isfinite(fps)
            or fps <= 0
            or source_frame_count <= 0
            or width <= 0
            or height <= 0
        ):
            raise VideoProcessingError("The video metadata is incomplete or invalid.")
        if width > 8192 or height > 8192 or width * height > 50_000_000:
            raise VideoProcessingError("The video resolution exceeds the safe processing limit.")

        duration = source_frame_count / fps
        if not math.isfinite(duration) or duration <= 0 or duration > MAX_VIDEO_DURATION_SECONDS:
            raise VideoProcessingError("Video duration must be between 1 second and 20 minutes.")

        timestamps, effective_interval = calculate_sample_timestamps(
            duration,
            job.frame_interval_seconds,
            job.max_frames,
        )
        frames_created = 0
        for output_number, timestamp in enumerate(timestamps):
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
            success, frame = capture.read()
            if not success or frame is None:
                continue

            frame_height, frame_width = frame.shape[:2]
            max_dimension = max(frame_width, frame_height)
            if max_dimension > 1280:
                scale = 1280.0 / max_dimension
                target_size = (
                    max(1, int(frame_width * scale)),
                    max(1, int(frame_height * scale)),
                )
                frame = cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)
                frame_height, frame_width = frame.shape[:2]

            encoded_ok, encoded = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), 88],
            )
            if not encoded_ok:
                continue

            frame_record = VideoFrame(
                job=job,
                frame_number=output_number,
                timestamp_seconds=timestamp,
                width=frame_width,
                height=frame_height,
            )
            frame_record.image.save(
                f"frame_{output_number:05d}.jpg",
                ContentFile(encoded.tobytes()),
                save=True,
            )
            frames_created += 1
        capture.release()
        capture = None

        if frames_created == 0:
            raise VideoProcessingError("No readable frames could be extracted from this video.")

        finished = timezone.now()
        with transaction.atomic():
            VideoProcessingJob.objects.filter(pk=job.pk).update(
                status=VideoProcessingJob.Status.COMPLETED,
                effective_interval_seconds=effective_interval,
                frame_count=frames_created,
                error_message="",
                finished_at=finished,
                updated_at=finished,
            )
            VideoAsset.objects.filter(pk=asset.pk).update(
                status=VideoAsset.Status.COMPLETED,
                duration_seconds=round(duration, 3),
                width=width,
                height=height,
                fps=round(fps, 3),
                updated_at=finished,
            )
        job.refresh_from_db()
        return job

    except Exception as exc:
        safe_message = str(exc) if isinstance(exc, VideoProcessingError) else (
            "Video processing failed due to an unexpected decoder or storage error."
        )
        return _mark_failed(job, safe_message)
    finally:
        if capture is not None:
            capture.release()
