import uuid

from django.conf import settings
from django.db import models


class Organization(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    name = models.CharField(max_length=150)

    slug = models.SlugField(
        max_length=150,
        unique=True
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_organizations"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self):
        return self.name


class Membership(models.Model):

    class Role(models.TextChoices):

        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        OPERATOR = "operator", "Operator"
        ANALYST = "analyst", "Analyst"
        VIEWER = "viewer", "Viewer"

    class Status(models.TextChoices):

        ACTIVE = "active", "Active"
        INVITED = "invited", "Invited"
        SUSPENDED = "suspended", "Suspended"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships"
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VIEWER
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invitations"
    )

    joined_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:

        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_organization_membership"
            )
        ]

        indexes = [
            models.Index(
                fields=["organization", "status"],
                name="membership_org_status_idx"
            ),
            models.Index(
                fields=["user", "status"],
                name="membership_user_status_idx"
            ),
        ]

        verbose_name = "Membership"
        verbose_name_plural = "Memberships"

    def __str__(self):
        return (
            f"{self.user.email} - "
            f"{self.organization.name} - "
            f"{self.role}"
        )

# AEGISVISION CAMERA MODULE MODEL REGISTRATION
from .cameras.models import Camera  # noqa: F401

# AEGISVISION VIDEO PROCESSING MODEL REGISTRATION
from .cameras.video_models import VideoAsset, VideoProcessingJob, VideoFrame  # noqa: F401

# AEGISVISION OBJECT DETECTION MODEL REGISTRATION
from .cameras.detection_models import DetectionRun, DetectionFrame, ObjectDetection  # noqa: F401

# AEGISVISION OBJECT TRACKING MODEL REGISTRATION
from .cameras.tracking_models import TrackingRun, ObjectTrack, TrackObservation  # noqa: F401

# AEGISVISION SECURITY EVENT MODELS
from .cameras.event_models import AnalyticsRule, SecurityEvent, SecurityEventActivity  # noqa: F401

# AEGISVISION LIVE CAMERA INTELLIGENCE MODELS
from .cameras.live_models import (  # noqa: F401
    CameraLiveState, CameraWorkerHeartbeat, CameraLiveEvent, CameraLiveEventActivity,
)
