# Generated for AEGISVISION SOC operations.
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0006_analyticsrule_securityevent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="securityevent",
            name="severity",
            field=models.CharField(choices=[("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low")], db_index=True, default="medium", max_length=12),
        ),
        migrations.AddField(
            model_name="securityevent",
            name="assigned_to",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_security_events", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="securityevent",
            name="status",
            field=models.CharField(choices=[("new", "New"), ("acknowledged", "Acknowledged"), ("investigating", "Investigating"), ("resolved", "Resolved"), ("false_positive", "False positive")], db_index=True, default="new", max_length=20),
        ),
        migrations.CreateModel(
            name="SecurityEventActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("created", "Created"), ("status_changed", "Status changed"), ("assigned", "Assigned"), ("severity_changed", "Severity changed"), ("comment", "Comment")], max_length=24)),
                ("from_status", models.CharField(blank=True, max_length=20)),
                ("to_status", models.CharField(blank=True, max_length=20)),
                ("from_severity", models.CharField(blank=True, max_length=12)),
                ("to_severity", models.CharField(blank=True, max_length=12)),
                ("note", models.TextField(blank=True, max_length=2000)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="security_event_activities", to=settings.AUTH_USER_MODEL)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="organizations.securityevent")),
                ("from_assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="security_event_activity_from_assignments", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="security_event_activities", to="organizations.organization")),
                ("to_assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="security_event_activity_to_assignments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Security event activity",
                "verbose_name_plural": "Security event activities",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="securityeventactivity",
            index=models.Index(fields=["organization", "created_at"], name="sec_activity_org_time_idx"),
        ),
        migrations.AddIndex(
            model_name="securityeventactivity",
            index=models.Index(fields=["event", "created_at"], name="sec_activity_event_time_idx"),
        ),
    ]
