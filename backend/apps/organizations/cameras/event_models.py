from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class AnalyticsRule(models.Model):
    class RuleType(models.TextChoices):
        ZONE_INTRUSION = "zone_intrusion", "Zone intrusion"
        LINE_CROSSING = "line_crossing", "Line crossing"
        LOITERING = "loitering", "Loitering"

    class Anchor(models.TextChoices):
        BOTTOM_CENTER = "bottom_center", "Bottom center"
        CENTER = "center", "Center"

    class Direction(models.TextChoices):
        BOTH = "both", "Both directions"
        NEGATIVE_TO_POSITIVE = "negative_to_positive", "Negative to positive"
        POSITIVE_TO_NEGATIVE = "positive_to_negative", "Positive to negative"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="analytics_rules",
    )
    # A rule may be attached to one recording or reused by every recording
    # ingested from one camera. Exactly one target is required.
    asset = models.ForeignKey(
        "organizations.VideoAsset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="analytics_rules",
    )
    camera = models.ForeignKey(
        "organizations.Camera",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="analytics_rules",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_analytics_rules",
    )
    name = models.CharField(max_length=120)
    rule_type = models.CharField(max_length=24, choices=RuleType.choices)
    # Normalized geometry, e.g. {"polygon": [[0.1, 0.2], ...]} or {"line": [...]}
    geometry = models.JSONField(default=dict)
    labels = models.JSONField(default=list, blank=True)
    minimum_confidence = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    anchor = models.CharField(max_length=20, choices=Anchor.choices, default=Anchor.BOTTOM_CENTER)
    direction = models.CharField(max_length=24, choices=Direction.choices, default=Direction.BOTH)
    dwell_seconds = models.FloatField(
        default=10.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(86400.0)],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "organizations"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(asset__isnull=False, camera__isnull=True) | Q(asset__isnull=True, camera__isnull=False)),
                name="analytics_rule_one_target",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "asset", "is_active"], name="analytics_rule_scope_idx"),
            models.Index(fields=["organization", "camera", "is_active"], name="analytics_camera_scope_idx"),
        ]
        verbose_name = "Analytics rule"
        verbose_name_plural = "Analytics rules"

    def __str__(self):
        return f"{self.name} ({self.get_rule_type_display()})"


class SecurityEvent(models.Model):
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
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="security_events",
    )
    asset = models.ForeignKey(
        "organizations.VideoAsset",
        on_delete=models.CASCADE,
        related_name="security_events",
    )
    tracking_run = models.ForeignKey(
        "organizations.TrackingRun",
        on_delete=models.CASCADE,
        related_name="security_events",
    )
    rule = models.ForeignKey(
        AnalyticsRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    # Snapshot retained if an administrator later removes the rule.
    rule_name = models.CharField(max_length=120)
    event_type = models.CharField(max_length=24)
    track_number = models.PositiveIntegerField()
    label = models.CharField(max_length=80)
    timestamp_seconds = models.FloatField()
    frame_number = models.PositiveIntegerField()
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    details = models.JSONField(default=dict, blank=True)
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.MEDIUM, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_security_events",
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_security_events",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_security_events",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "organizations"
        ordering = ["-timestamp_seconds", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tracking_run", "rule", "track_number", "event_type", "frame_number"],
                name="uniq_security_event_evidence",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status", "created_at"], name="sec_event_org_status_idx"),
            models.Index(fields=["asset", "timestamp_seconds"], name="sec_event_asset_time_idx"),
            models.Index(fields=["tracking_run", "event_type"], name="sec_event_run_type_idx"),
        ]
        verbose_name = "Security event"
        verbose_name_plural = "Security events"

    def __str__(self):
        return f"{self.rule_name} — Track #{self.track_number} ({self.status})"


class SecurityEventActivity(models.Model):
    """Immutable audit entry for SOC actions performed on a security event."""

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        STATUS_CHANGED = "status_changed", "Status changed"
        ASSIGNED = "assigned", "Assigned"
        SEVERITY_CHANGED = "severity_changed", "Severity changed"
        COMMENT = "comment", "Comment"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="security_event_activities",
    )
    event = models.ForeignKey(
        SecurityEvent,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="security_event_activities",
    )
    action = models.CharField(max_length=24, choices=Action.choices)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    from_severity = models.CharField(max_length=12, blank=True)
    to_severity = models.CharField(max_length=12, blank=True)
    from_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="security_event_activity_from_assignments",
    )
    to_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="security_event_activity_to_assignments",
    )
    note = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "organizations"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="sec_activity_org_time_idx"),
            models.Index(fields=["event", "created_at"], name="sec_activity_event_time_idx"),
        ]
        verbose_name = "Security event activity"
        verbose_name_plural = "Security event activities"

    def __str__(self):
        return f"{self.get_action_display()} — Event #{self.event_id}"
