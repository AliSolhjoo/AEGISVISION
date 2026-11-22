from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class TrackingRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    detection_run = models.ForeignKey(
        "organizations.DetectionRun",
        on_delete=models.CASCADE,
        related_name="tracking_runs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tracking_runs",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    tracker_name = models.CharField(max_length=80, default="greedy_iou_v1")
    iou_threshold = models.FloatField(
        default=0.30,
        validators=[MinValueValidator(0.05), MaxValueValidator(0.95)],
    )
    # Number of consecutive detector frames a track may be absent and still match.
    max_gap_frames = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(30)],
    )
    frames_processed = models.PositiveIntegerField(default=0)
    tracks_count = models.PositiveIntegerField(default=0)
    observations_count = models.PositiveIntegerField(default=0)
    error_message = models.CharField(max_length=1000, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "organizations"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["detection_run", "status", "created_at"],
                name="trk_run_det_status_idx",
            ),
        ]
        verbose_name = "Tracking run"
        verbose_name_plural = "Tracking runs"

    def __str__(self):
        return f"Tracking {self.pk} — detection {self.detection_run_id} ({self.status})"


class ObjectTrack(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    tracking_run = models.ForeignKey(
        TrackingRun,
        on_delete=models.CASCADE,
        related_name="tracks",
    )
    track_number = models.PositiveIntegerField()
    class_id = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=80, db_index=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    first_frame_number = models.PositiveIntegerField()
    last_frame_number = models.PositiveIntegerField()
    first_timestamp_seconds = models.FloatField(default=0)
    last_timestamp_seconds = models.FloatField(default=0)
    observations_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "organizations"
        ordering = ["track_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["tracking_run", "track_number"],
                name="uniq_tracking_run_track_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tracking_run", "label"],
                name="obj_track_run_label_idx",
            ),
        ]
        verbose_name = "Object track"
        verbose_name_plural = "Object tracks"

    def __str__(self):
        return f"Track #{self.track_number} — {self.label}"


class TrackObservation(models.Model):
    track = models.ForeignKey(
        ObjectTrack,
        on_delete=models.CASCADE,
        related_name="observations",
    )
    detection = models.ForeignKey(
        "organizations.ObjectDetection",
        on_delete=models.CASCADE,
        related_name="track_observations",
    )
    source_frame = models.ForeignKey(
        "organizations.VideoFrame",
        on_delete=models.CASCADE,
        related_name="track_observations",
    )
    frame_number = models.PositiveIntegerField()
    timestamp_seconds = models.FloatField(default=0)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    # Snapshot of pixel coordinates [x1, y1, x2, y2] for stable API output.
    bounding_box = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "organizations"
        ordering = ["frame_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["track", "frame_number"],
                name="uniq_track_observation_frame",
            ),
        ]
        indexes = [
            models.Index(
                fields=["track", "frame_number"],
                name="trk_obs_track_frame_idx",
            ),
        ]
        verbose_name = "Track observation"
        verbose_name_plural = "Track observations"

    def __str__(self):
        return f"Track #{self.track.track_number} at frame {self.frame_number}"
