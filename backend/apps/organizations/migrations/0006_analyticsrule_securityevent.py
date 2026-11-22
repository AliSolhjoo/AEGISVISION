# Generated for AEGISVISION event intelligence models.
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0005_trackingrun_objecttrack_trackobservation_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AnalyticsRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("rule_type", models.CharField(choices=[("zone_intrusion", "Zone intrusion"), ("line_crossing", "Line crossing"), ("loitering", "Loitering")], max_length=24)),
                ("geometry", models.JSONField(default=dict)),
                ("labels", models.JSONField(blank=True, default=list)),
                ("minimum_confidence", models.FloatField(default=0.0, validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)])),
                ("anchor", models.CharField(choices=[("bottom_center", "Bottom center"), ("center", "Center")], default="bottom_center", max_length=20)),
                ("direction", models.CharField(choices=[("both", "Both directions"), ("negative_to_positive", "Negative to positive"), ("positive_to_negative", "Positive to negative")], default="both", max_length=24)),
                ("dwell_seconds", models.FloatField(default=10.0, validators=[django.core.validators.MinValueValidator(0.1), django.core.validators.MaxValueValidator(86400.0)])),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="analytics_rules", to="organizations.videoasset")),
                ("camera", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="analytics_rules", to="organizations.camera")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_analytics_rules", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="analytics_rules", to="organizations.organization")),
            ],
            options={
                "verbose_name": "Analytics rule",
                "verbose_name_plural": "Analytics rules",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="SecurityEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rule_name", models.CharField(max_length=120)),
                ("event_type", models.CharField(max_length=24)),
                ("track_number", models.PositiveIntegerField()),
                ("label", models.CharField(max_length=80)),
                ("timestamp_seconds", models.FloatField()),
                ("frame_number", models.PositiveIntegerField()),
                ("confidence", models.FloatField(validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)])),
                ("details", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("new", "New"), ("acknowledged", "Acknowledged"), ("resolved", "Resolved"), ("false_positive", "False positive")], db_index=True, default="new", max_length=20)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("acknowledged_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="acknowledged_security_events", to=settings.AUTH_USER_MODEL)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="security_events", to="organizations.videoasset")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="security_events", to="organizations.organization")),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_security_events", to=settings.AUTH_USER_MODEL)),
                ("rule", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="events", to="organizations.analyticsrule")),
                ("tracking_run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="security_events", to="organizations.trackingrun")),
            ],
            options={
                "verbose_name": "Security event",
                "verbose_name_plural": "Security events",
                "ordering": ["-timestamp_seconds", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="analyticsrule",
            index=models.Index(fields=["organization", "asset", "is_active"], name="analytics_rule_scope_idx"),
        ),
        migrations.AddIndex(
            model_name="analyticsrule",
            index=models.Index(fields=["organization", "camera", "is_active"], name="analytics_camera_scope_idx"),
        ),
        migrations.AddConstraint(
            model_name="analyticsrule",
            constraint=models.CheckConstraint(condition=(Q(asset__isnull=False, camera__isnull=True) | Q(asset__isnull=True, camera__isnull=False)), name="analytics_rule_one_target"),
        ),
        migrations.AddConstraint(
            model_name="securityevent",
            constraint=models.UniqueConstraint(fields=("tracking_run", "rule", "track_number", "event_type", "frame_number"), name="uniq_security_event_evidence"),
        ),
        migrations.AddIndex(
            model_name="securityevent",
            index=models.Index(fields=["organization", "status", "created_at"], name="sec_event_org_status_idx"),
        ),
        migrations.AddIndex(
            model_name="securityevent",
            index=models.Index(fields=["asset", "timestamp_seconds"], name="sec_event_asset_time_idx"),
        ),
        migrations.AddIndex(
            model_name="securityevent",
            index=models.Index(fields=["tracking_run", "event_type"], name="sec_event_run_type_idx"),
        ),
    ]
