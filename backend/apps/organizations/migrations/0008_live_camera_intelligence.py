# Generated for AEGISVISION Live Camera Intelligence.
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


def live_frame_upload_to(instance, filename):
    token = uuid.uuid4().hex
    return f"aegisvision/live/org_{instance.camera.organization_id}/camera_{instance.camera_id}/{token}.jpg"


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0007_soc_operations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="camera",
            name="credentials_encrypted",
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="camera",
            name="target_fps",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text="Maximum AI inference frames per second for live processing.",
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)],
            ),
        ),
        migrations.AddField(
            model_name="camera",
            name="confidence_threshold",
            field=models.FloatField(
                default=0.55,
                validators=[django.core.validators.MinValueValidator(0.05), django.core.validators.MaxValueValidator(0.99)],
            ),
        ),
        migrations.CreateModel(
            name="CameraLiveState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_requested", models.BooleanField(db_index=True, default=False)),
                ("status", models.CharField(choices=[("stopped", "Stopped"), ("starting", "Starting"), ("online", "Online"), ("reconnecting", "Reconnecting"), ("error", "Error")], db_index=True, default="stopped", max_length=16)),
                ("session_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("latest_frame", models.ImageField(blank=True, max_length=500, upload_to=live_frame_upload_to)),
                ("latest_detections", models.JSONField(blank=True, default=list)),
                ("last_error", models.CharField(blank=True, max_length=1000)),
                ("frame_number", models.PositiveIntegerField(default=0)),
                ("frames_processed", models.PositiveIntegerField(default=0)),
                ("objects_count", models.PositiveIntegerField(default=0)),
                ("tracks_count", models.PositiveIntegerField(default=0)),
                ("fps_actual", models.FloatField(default=0.0, validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(120.0)])),
                ("width", models.PositiveIntegerField(blank=True, null=True)),
                ("height", models.PositiveIntegerField(blank=True, null=True)),
                ("session_started_at", models.DateTimeField(blank=True, null=True)),
                ("last_frame_at", models.DateTimeField(blank=True, null=True)),
                ("last_inference_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("camera", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="live_state", to="organizations.camera")),
            ],
            options={
                "verbose_name": "Camera live state",
                "verbose_name_plural": "Camera live states",
            },
        ),
        migrations.AddIndex(
            model_name="cameralivestate",
            index=models.Index(fields=["status", "is_requested"], name="cam_live_requested_idx"),
        ),
        migrations.CreateModel(
            name="CameraWorkerHeartbeat",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("process_id", models.PositiveIntegerField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("last_heartbeat", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=1000)),
            ],
            options={
                "verbose_name": "Camera worker heartbeat",
                "verbose_name_plural": "Camera worker heartbeat",
            },
        ),
        migrations.CreateModel(
            name="CameraLiveEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rule_name", models.CharField(max_length=120)),
                ("event_type", models.CharField(max_length=24)),
                ("session_id", models.UUIDField()),
                ("track_number", models.PositiveIntegerField()),
                ("label", models.CharField(max_length=80)),
                ("timestamp_seconds", models.FloatField()),
                ("frame_number", models.PositiveIntegerField()),
                ("confidence", models.FloatField(validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)])),
                ("details", models.JSONField(blank=True, default=dict)),
                ("severity", models.CharField(choices=[("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low")], db_index=True, default="medium", max_length=12)),
                ("status", models.CharField(choices=[("new", "New"), ("acknowledged", "Acknowledged"), ("investigating", "Investigating"), ("resolved", "Resolved"), ("false_positive", "False positive")], db_index=True, default="new", max_length=20)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("acknowledged_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="acknowledged_camera_live_events", to=settings.AUTH_USER_MODEL)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_camera_live_events", to=settings.AUTH_USER_MODEL)),
                ("camera", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="live_events", to="organizations.camera")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="camera_live_events", to="organizations.organization")),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_camera_live_events", to=settings.AUTH_USER_MODEL)),
                ("rule", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="camera_live_events", to="organizations.analyticsrule")),
            ],
            options={
                "verbose_name": "Camera live event",
                "verbose_name_plural": "Camera live events",
                "ordering": ["-occurred_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="cameraliveevent",
            constraint=models.UniqueConstraint(fields=("camera", "session_id", "rule", "track_number", "event_type", "frame_number"), name="uniq_camera_live_event_evidence"),
        ),
        migrations.AddIndex(
            model_name="cameraliveevent",
            index=models.Index(fields=["organization", "status", "occurred_at"], name="cam_live_event_org_idx"),
        ),
        migrations.AddIndex(
            model_name="cameraliveevent",
            index=models.Index(fields=["camera", "occurred_at"], name="cam_live_event_cam_idx"),
        ),
        migrations.CreateModel(
            name="CameraLiveEventActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("created", "Created"), ("status_changed", "Status changed"), ("assigned", "Assigned"), ("comment", "Comment")], max_length=24)),
                ("from_status", models.CharField(blank=True, max_length=20)),
                ("to_status", models.CharField(blank=True, max_length=20)),
                ("note", models.TextField(blank=True, max_length=2000)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="camera_live_event_activities", to=settings.AUTH_USER_MODEL)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="organizations.cameraliveevent")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="camera_live_event_activities", to="organizations.organization")),
            ],
            options={
                "verbose_name": "Camera live event activity",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="cameraliveeventactivity",
            index=models.Index(fields=["organization", "created_at"], name="cam_live_act_org_idx"),
        ),
    ]
