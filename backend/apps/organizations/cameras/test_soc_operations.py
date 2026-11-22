from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.organizations.models import (
    DetectionRun,
    Membership,
    Organization,
    SecurityEvent,
    SecurityEventActivity,
    TrackingRun,
    VideoAsset,
)


class SecurityOperationsCenterApiTests(TestCase):
    password = "Strong-SOC-Test-Password-2026!"

    def setUp(self):
        self.owner = User.objects.create_user(
            email="soc-owner@example.test", password=self.password,
            first_name="SOC", last_name="Owner",
        )
        self.operator = User.objects.create_user(
            email="soc-operator@example.test", password=self.password,
            first_name="SOC", last_name="Operator",
        )
        self.organization = Organization.objects.create(
            name="SOC Test Organization",
            slug="soc-test-organization",
            created_by=self.owner,
        )
        Membership.objects.create(
            organization=self.organization, user=self.owner,
            role=Membership.Role.OWNER, status=Membership.Status.ACTIVE,
        )
        Membership.objects.create(
            organization=self.organization, user=self.operator,
            role=Membership.Role.OPERATOR, status=Membership.Status.ACTIVE,
        )
        self.asset = VideoAsset.objects.create(
            organization=self.organization,
            uploaded_by=self.owner,
            name="SOC sample",
            source_file="aegisvision/videos/soc-sample.mp4",
            original_filename="soc-sample.mp4",
            content_type="video/mp4",
            file_size=100,
            sha256="",
            status=VideoAsset.Status.COMPLETED,
        )
        detection = DetectionRun.objects.create(
            asset=self.asset,
            created_by=self.owner,
            status=DetectionRun.Status.COMPLETED,
        )
        tracking = TrackingRun.objects.create(
            detection_run=detection,
            created_by=self.owner,
            status=TrackingRun.Status.COMPLETED,
        )
        self.event = SecurityEvent.objects.create(
            organization=self.organization,
            asset=self.asset,
            tracking_run=tracking,
            rule_name="North gate intrusion",
            event_type="zone_intrusion",
            track_number=4,
            label="person",
            timestamp_seconds=12.5,
            frame_number=25,
            confidence=0.94,
            severity=SecurityEvent.Severity.CRITICAL,
            status=SecurityEvent.Status.NEW,
            details={"bounding_box": [10, 20, 40, 80]},
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)
        self.org_url = f"/api/organizations/{self.organization.pk}"

    def test_dashboard_returns_real_summary_and_seven_day_series(self):
        response = self.client.get(f"{self.org_url}/soc/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["total_events"], 1)
        self.assertEqual(response.data["summary"]["open_events"], 1)
        self.assertEqual(response.data["summary"]["critical_open"], 1)
        self.assertEqual(len(response.data["trend_7d"]), 7)
        self.assertEqual(response.data["recent_events"][0]["id"], self.event.pk)

    def test_event_list_filters_by_severity_and_status(self):
        response = self.client.get(
            f"{self.org_url}/soc/events/?severity=critical&status=new"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["severity"], "critical")

    def test_operator_can_investigate_assign_and_add_audit_note(self):
        self.client.force_authenticate(user=self.operator)
        response = self.client.patch(
            f"{self.org_url}/events/{self.event.pk}/",
            {
                "status": "investigating",
                "assigned_to_id": self.operator.pk,
                "note": "Operator reviewed the initial evidence.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "investigating")
        self.assertEqual(response.data["assigned_to_id"], self.operator.pk)
        self.assertEqual(
            SecurityEventActivity.objects.filter(event=self.event).count(), 2
        )
        self.assertTrue(
            SecurityEventActivity.objects.filter(
                event=self.event,
                action=SecurityEventActivity.Action.STATUS_CHANGED,
                note="Operator reviewed the initial evidence.",
            ).exists()
        )

    def test_activity_endpoint_is_organization_scoped(self):
        SecurityEventActivity.objects.create(
            organization=self.organization,
            event=self.event,
            actor=self.owner,
            action=SecurityEventActivity.Action.CREATED,
            to_status=self.event.status,
            note="Created in test.",
        )
        response = self.client.get(
            f"{self.org_url}/events/{self.event.pk}/activity/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["action"], "created")

    def test_assignees_only_include_active_operations_members(self):
        response = self.client.get(f"{self.org_url}/soc/assignees/")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data}
        self.assertIn(self.owner.pk, ids)
        self.assertIn(self.operator.pk, ids)

    def test_csv_export_is_excel_friendly(self):
        response = self.client.get(f"{self.org_url}/soc/events/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"North gate intrusion", response.content)

    def test_viewer_can_read_soc_but_cannot_manage_events(self):
        viewer = User.objects.create_user(
            email="soc-viewer@example.test", password=self.password,
            first_name="SOC", last_name="Viewer",
        )
        Membership.objects.create(
            organization=self.organization, user=viewer,
            role=Membership.Role.VIEWER, status=Membership.Status.ACTIVE,
        )
        self.client.force_authenticate(user=viewer)
        dashboard = self.client.get(f"{self.org_url}/soc/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertFalse(dashboard.data["permissions"]["can_manage_events"])
        update = self.client.patch(
            f"{self.org_url}/events/{self.event.pk}/",
            {"status": "investigating"},
            format="json",
        )
        self.assertEqual(update.status_code, 403)

    def test_csv_export_neutralizes_spreadsheet_formulas(self):
        self.event.rule_name = "=HYPERLINK(\"https://example.test\",\"click\")"
        self.event.save(update_fields=["rule_name"])
        response = self.client.get(f"{self.org_url}/soc/events/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"'=HYPERLINK", response.content)
