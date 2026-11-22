from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def live_frame_upload_to(instance, filename):
    token = uuid.uuid4().hex
    return (
        f"aegisvision/live/org_{instance.camera.organization_id}/"
        f"camera_{instance.camera_id}/{token}.jpg"
    )


class CameraLiveState(models.Model):
    class Status(models.TextChoices):
        STOPPED = "stopped", "Stopped"
        STARTING = "starting", "Starting"
        ONLINE = "online", "Online"
        RECONNECTING = "reconnecting", "Reconnecting"
        ERROR = "error", "Error"

    camera = models.OneToOneField(
        "organizations.Camera",
        on_delete=models.CASCADE,
        related_name="live_state",
    )
    is_requested = models.BooleanField(default=False, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.STOPPED, db_index=True)
    session_id = models.UUIDField(default=uuid.uuid4, editable=False)
    latest_frame = models.ImageField(upload_to=live_frame_upload_to, blank=True, max_length=500)
    latest_detections = models.JSONField(default=list, blank=True)
    last_error = models.CharField(max_length=1000, blank=True)
    frame_number = models.PositiveIntegerField(default=0)
    frames_processed = models.PositiveIntegerField(default=0)
    objects_count = models.PositiveIntegerField(default=0)
    tracks_count = models.PositiveIntegerField(default=0)
    fps_actual = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(120.0)])
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    session_started_at = models.DateTimeField(null=True, blank=True)
    last_frame_at = models.DateTimeField(null=True, blank=True)
    last_inference_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "organizations"
        indexes = [
            models.Index(fields=["status", "is_requested"], name="cam_live_requested_idx"),
        ]
        verbose_name = "Camera live state"
        verbose_name_plural = "Camera live states"

    def __str__(self):
        return f"Live {self.camera_id}: {self.status}"


class CameraWorkerHeartbeat(models.Model):
    """Singleton lease/heartbeat for the background camera manager process."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    process_id = models.PositiveIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=1000, blank=True)

    class Meta:
        app_label = "organizations"
        verbose_name = "Camera worker heartbeat"
        verbose_name_plural = "Camera worker heartbeat"

    def __str__(self):
        return f"Camera worker PID {self.process_id or 'stopped'}"


class CameraLiveEvent(models.Model):
    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critical"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    class Status(models.TextChoices):
        NEW = "new", "New"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        FALSE_POSITIVE = "false_positive", "False positive"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="camera_live_events"
    )
    camera = models.ForeignKey(
        "organizations.Camera", on_delete=models.CASCADE, related_name="live_events"
    )
    rule = models.ForeignKey(
        "organizations.AnalyticsRule", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="camera_live_events",
    )
    rule_name = models.CharField(max_length=120)
    event_type = models.CharField(max_length=24)
    session_id = models.UUIDField()
    track_number = models.PositiveIntegerField()
    label = models.CharField(max_length=80)
    timestamp_seconds = models.FloatField()
    frame_number = models.PositiveIntegerField()
    confidence = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    details = models.JSONField(default=dict, blank=True)
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.MEDIUM, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_camera_live_events",
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="acknowledged_camera_live_events",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="resolved_camera_live_events",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "organizations"
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["camera", "session_id", "rule", "track_number", "event_type", "frame_number"],
                name="uniq_camera_live_event_evidence",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status", "occurred_at"], name="cam_live_event_org_idx"),
            models.Index(fields=["camera", "occurred_at"], name="cam_live_event_cam_idx"),
        ]
        verbose_name = "Camera live event"
        verbose_name_plural = "Camera live events"

    def __str__(self):
        return f"{self.rule_name} — {self.camera.name} — Track #{self.track_number}"


class CameraLiveEventActivity(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        STATUS_CHANGED = "status_changed", "Status changed"
        ASSIGNED = "assigned", "Assigned"
        COMMENT = "comment", "Comment"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="camera_live_event_activities"
    )
    event = models.ForeignKey(
        CameraLiveEvent, on_delete=models.CASCADE, related_name="activities"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="camera_live_event_activities",
    )
    action = models.CharField(max_length=24, choices=Action.choices)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "organizations"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["organization", "created_at"], name="cam_live_act_org_idx")]

    def __str__(self):
        return f"{self.action} — live event #{self.event_id}"
