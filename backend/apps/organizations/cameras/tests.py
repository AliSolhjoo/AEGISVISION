from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.organizations.models import Organization, Membership
from .models import Camera


class CameraAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="camera-owner@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        self.operator = User.objects.create_user(
            email="camera-operator@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        self.viewer = User.objects.create_user(
            email="camera-viewer@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        self.outsider = User.objects.create_user(
            email="camera-outsider@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        self.organization = Organization.objects.create(
            name="Camera Test Organization",
            slug="camera-test-organization",
            created_by=self.owner,
        )
        Membership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )
        Membership.objects.create(
            organization=self.organization,
            user=self.operator,
            role=Membership.Role.OPERATOR,
            status=Membership.Status.ACTIVE,
        )
        Membership.objects.create(
            organization=self.organization,
            user=self.viewer,
            role=Membership.Role.VIEWER,
            status=Membership.Status.ACTIVE,
        )
        self.list_url = reverse(
            "organizations:cameras-list",
            kwargs={"organization_id": self.organization.id},
        )
        self.client.force_authenticate(user=self.owner)

    def camera_payload(self, **overrides):
        payload = {
            "name": "Loading Bay Camera",
            "code": "loading-bay-01",
            "description": "North loading bay entrance",
            "location": "Building A / North gate",
            "source_type": "rtsp",
            "stream_url": "rtsp://192.168.10.20:554/stream1",
        }
        payload.update(overrides)
        return payload

    def test_owner_can_register_camera(self):
        response = self.client.post(
            self.list_url,
            self.camera_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Camera.objects.count(), 1)
        self.assertNotIn("stream_url", response.data)
        self.assertEqual(
            Camera.objects.get().organization_id,
            self.organization.id,
        )

    def test_operator_can_register_camera(self):
        self.client.force_authenticate(user=self.operator)
        response = self.client.post(
            self.list_url,
            self.camera_payload(code="operator-camera"),
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_viewer_can_list_but_cannot_create(self):
        Camera.objects.create(
            organization=self.organization,
            created_by=self.owner,
            name="Existing Camera",
            code="existing-camera",
            source_type=Camera.SourceType.RTSP,
            stream_url="rtsp://192.168.10.21:554/stream1",
        )
        self.client.force_authenticate(user=self.viewer)
        list_response = self.client.get(self.list_url)
        create_response = self.client.post(
            self.list_url,
            self.camera_payload(code="viewer-camera"),
            format="json",
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(create_response.status_code, 403)

    def test_outsider_cannot_list_cameras(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_camera_code_is_unique_per_organization(self):
        self.client.post(self.list_url, self.camera_payload(), format="json")
        response = self.client.post(
            self.list_url,
            self.camera_payload(name="Duplicate code"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_credentials_in_stream_url_are_rejected(self):
        response = self.client.post(
            self.list_url,
            self.camera_payload(
                stream_url="rtsp://admin:secret@192.168.10.20:554/stream1"
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_query_string_in_stream_url_is_rejected(self):
        response = self.client.post(
            self.list_url,
            self.camera_payload(
                stream_url="rtsp://192.168.10.20:554/stream1?token=secret"
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_stream_scheme_must_match_source_type(self):
        response = self.client.post(
            self.list_url,
            self.camera_payload(
                source_type="rtsps",
                stream_url="rtsp://192.168.10.20:554/stream1",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_browser_camera_does_not_accept_server_stream_url(self):
        response = self.client.post(
            self.list_url,
            self.camera_payload(
                source_type="browser",
                stream_url="rtsp://192.168.10.20:554/stream1",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_camera_delete_is_soft_disable(self):
        camera = Camera.objects.create(
            organization=self.organization,
            created_by=self.owner,
            name="Soft Delete Camera",
            code="soft-delete-camera",
            source_type=Camera.SourceType.RTSP,
            stream_url="rtsp://192.168.10.22:554/stream1",
        )
        url = reverse(
            "organizations:cameras-detail",
            kwargs={
                "organization_id": self.organization.id,
                "camera_id": camera.id,
            },
        )
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        camera.refresh_from_db()
        self.assertFalse(camera.is_enabled)
        self.assertEqual(camera.status, Camera.Status.DISABLED)

    def test_camera_detail_is_scoped_to_organization(self):
        camera = Camera.objects.create(
            organization=self.organization,
            created_by=self.owner,
            name="Scoped Camera",
            code="scoped-camera",
            source_type=Camera.SourceType.RTSP,
            stream_url="rtsp://192.168.10.23:554/stream1",
        )
        another_org = Organization.objects.create(
            name="Another Organization",
            slug="another-camera-organization",
            created_by=self.owner,
        )
        url = reverse(
            "organizations:cameras-detail",
            kwargs={
                "organization_id": another_org.id,
                "camera_id": camera.id,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
