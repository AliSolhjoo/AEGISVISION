from pathlib import Path
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from django.core.validators import MinValueValidator, MaxValueValidator


@deconstructible
class DetectionMediaStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=None)

    @property
    def base_location(self):
        configured_root = getattr(settings, "MEDIA_ROOT", "")
        if configured_root:
            return str(configured_root)
        return str(Path(settings.BASE_DIR) / "media")


DETECTION_STORAGE = DetectionMediaStorage()


def annotated_frame_upload_to(instance, filename):
    asset = instance.run.asset
    safe_name = f"frame_{instance.source_frame_id}_{uuid.uuid4().hex[:8]}.jpg"
    return (
        f"aegisvision/detections/org_{asset.organization_id}/"
        f"video_{asset.pk}/run_{instance.run_id}/{safe_name}"
    )


class DetectionRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Device(models.TextChoices):
        AUTO = "auto", "Automatic"
        CPU = "cpu", "CPU"
        CUDA = "cuda", "CUDA"

    asset = models.ForeignKey(
        "organizations.VideoAsset",
        on_delete=models.CASCADE,
        related_name="detection_runs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_detection_runs",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    model_name = models.CharField(
        max_length=120,
        default="fasterrcnn_mobilenet_v3_large_320_fpn",
    )
    confidence_threshold = models.FloatField(
        default=0.50,
        validators=[MinValueValidator(0.05), MaxValueValidator(0.99)],
    )
    max_frames = models.PositiveSmallIntegerField(
        default=120,
        validators=[MinValueValidator(1), MaxValueValidator(300)],
    )
    requested_device = models.CharField(
        max_length=8,
        choices=Device.choices,
        default=Device.AUTO,
    )
    actual_device = models.CharField(max_length=16, blank=True)
    frames_processed = models.PositiveIntegerField(default=0)
    detections_count = models.PositiveIntegerField(default=0)
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
                fields=["asset", "status", "created_at"],
                name="det_run_asset_status_idx",
            ),
        ]
        verbose_name = "Detection run"
        verbose_name_plural = "Detection runs"

    def __str__(self):
        return f"Detection {self.pk} — {self.asset.name} ({self.status})"


class DetectionFrame(models.Model):
    run = models.ForeignKey(
        DetectionRun,
        on_delete=models.CASCADE,
        related_name="frames",
    )
    source_frame = models.ForeignKey(
        "organizations.VideoFrame",
        on_delete=models.CASCADE,
        related_name="detection_outputs",
    )
    annotated_image = models.ImageField(
        storage=DETECTION_STORAGE,
        upload_to=annotated_frame_upload_to,
        max_length=500,
    )
    detections_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "organizations"
        ordering = ["source_frame__frame_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "source_frame"],
                name="uniq_det_run_src_frame",
            ),
        ]
        indexes = [
            models.Index(
                fields=["run", "source_frame"],
                name="det_frame_run_source_idx",
            ),
        ]

    def __str__(self):
        return f"Detection frame {self.source_frame_id} / run {self.run_id}"


class ObjectDetection(models.Model):
    detection_frame = models.ForeignKey(
        DetectionFrame,
        on_delete=models.CASCADE,
        related_name="detections",
    )
    class_id = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=80, db_index=True)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    # Pixel coordinates in the stored source frame: [x1, y1, x2, y2].
    bounding_box = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "organizations"
        ordering = ["-confidence", "id"]
        indexes = [
            models.Index(
                fields=["detection_frame", "label"],
                name="obj_det_frame_label_idx",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.confidence:.2f})"
