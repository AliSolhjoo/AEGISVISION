from pathlib import Path
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


# Respect MEDIA_ROOT dynamically. If it is not configured, store files in
# backend/media. The deconstructible storage keeps migrations portable and
# avoids embedding an absolute developer-specific path in migration files.
@deconstructible
class AegisMediaStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=None)

    @property
    def base_location(self):
        configured_root = getattr(settings, "MEDIA_ROOT", "")
        if configured_root:
            return str(configured_root)
        return str(Path(settings.BASE_DIR) / "media")


VIDEO_STORAGE = AegisMediaStorage()


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
MAX_VIDEO_SIZE_BYTES = 250 * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = 20 * 60


def video_source_upload_to(instance, filename):
    suffix = Path(filename.replace("\\", "/")).suffix.lower()
    return f"aegisvision/videos/org_{instance.organization_id}/{uuid.uuid4().hex}{suffix}"


def video_frame_upload_to(instance, filename):
    return (
        f"aegisvision/frames/org_{instance.job.asset.organization_id}/"
        f"video_{instance.job.asset_id}/job_{instance.job_id}/{filename}"
    )


class VideoAsset(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="video_assets",
    )
    camera = models.ForeignKey(
        "organizations.Camera",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="video_assets",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_video_assets",
    )
    name = models.CharField(max_length=150)
    source_file = models.FileField(
        storage=VIDEO_STORAGE,
        upload_to=video_source_upload_to,
        max_length=500,
    )
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    file_size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, blank=True)

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    duration_seconds = models.FloatField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    fps = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "organizations"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "status", "created_at"],
                name="video_org_status_created_idx",
            ),
        ]
        verbose_name = "Video asset"
        verbose_name_plural = "Video assets"

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class VideoProcessingJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    asset = models.OneToOneField(
        VideoAsset,
        on_delete=models.CASCADE,
        related_name="processing_job",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_video_jobs",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    frame_interval_seconds = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )
    max_frames = models.PositiveSmallIntegerField(
        default=180,
        validators=[MinValueValidator(2), MaxValueValidator(300)],
    )
    effective_interval_seconds = models.FloatField(null=True, blank=True)
    frame_count = models.PositiveIntegerField(default=0)
    error_message = models.CharField(max_length=1000, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "organizations"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="video_job_status_created_idx",
            ),
        ]
        verbose_name = "Video processing job"
        verbose_name_plural = "Video processing jobs"

    def __str__(self):
        return f"Job {self.pk} — {self.asset.name} ({self.status})"


class VideoFrame(models.Model):
    job = models.ForeignKey(
        VideoProcessingJob,
        on_delete=models.CASCADE,
        related_name="frames",
    )
    frame_number = models.PositiveIntegerField()
    timestamp_seconds = models.FloatField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    image = models.ImageField(
        storage=VIDEO_STORAGE,
        upload_to=video_frame_upload_to,
        max_length=500,
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "organizations"
        ordering = ["frame_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "frame_number"],
                name="unique_video_job_frame_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["job", "frame_number"],
                name="video_frame_job_number_idx",
            ),
        ]
        verbose_name = "Video frame"
        verbose_name_plural = "Video frames"

    def __str__(self):
        return f"Frame {self.frame_number} / Job {self.job_id}"
