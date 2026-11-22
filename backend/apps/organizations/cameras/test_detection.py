from unittest.mock import patch
from io import BytesIO

from PIL import Image

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.organizations.models import Organization, Membership
from .detection_models import DetectionRun
from .detection_services import select_frames
from .video_models import VideoAsset, VideoProcessingJob, VideoFrame


class FrameSelectionTests(TestCase):
    def test_select_frames_returns_all_when_under_limit(self):
        values = list(range(5))
        self.assertEqual(select_frames(values, 10), values)

    def test_select_frames_is_evenly_spread_and_bounded(self):
        values = list(range(101))
        result = select_frames(values, 5)
        self.assertEqual(result, [0, 25, 50, 75, 100])

    def test_select_one_frame_returns_first(self):
        self.assertEqual(select_frames([10, 20, 30], 1), [10])

    def test_empty_frame_collection_returns_empty(self):
        self.assertEqual(select_frames([], 10), [])


class DetectionAPITests(APITestCase):
    password = "A-Strong-Test-Password-2026!"

    def setUp(self):
        self.owner = User.objects.create_user(
            email="detect-owner@example.test", password=self.password
        )
        self.operator = User.objects.create_user(
            email="detect-operator@example.test", password=self.password
        )
        self.viewer = User.objects.create_user(
            email="detect-viewer@example.test", password=self.password
        )
        self.outsider = User.objects.create_user(
            email="detect-outsider@example.test", password=self.password
        )
        self.organization = Organization.objects.create(
            name="Detection Test Organization",
            slug="detection-test-organization",
            created_by=self.owner,
        )
        for user, role in [
            (self.owner, Membership.Role.OWNER),
            (self.operator, Membership.Role.OPERATOR),
            (self.viewer, Membership.Role.VIEWER),
        ]:
            Membership.objects.create(
                organization=self.organization,
                user=user,
                role=role,
                status=Membership.Status.ACTIVE,
            )
        self.asset = VideoAsset.objects.create(
            organization=self.organization,
            uploaded_by=self.owner,
            name="Completed sample video",
            original_filename="sample.mp4",
            content_type="video/mp4",
            file_size=1234,
            status=VideoAsset.Status.COMPLETED,
            duration_seconds=12.0,
            width=640,
            height=480,
            fps=25.0,
        )
        self.job = VideoProcessingJob.objects.create(
            asset=self.asset,
            created_by=self.owner,
            status=VideoProcessingJob.Status.COMPLETED,
            frame_count=1,
        )
        self.frame = VideoFrame.objects.create(
            job=self.job,
            frame_number=0,
            timestamp_seconds=0.0,
            width=640,
            height=480,
            image="placeholder-frame.jpg",
        )
        self.url = reverse(
            "organizations:detection-runs",
            kwargs={
                "organization_id": self.organization.id,
                "video_id": self.asset.pk,
            },
        )
        self.client.force_authenticate(user=self.owner)

    def test_owner_can_queue_detection_run(self):
        response = self.client.post(
            self.url,
            {"confidence_threshold": 0.6, "max_frames": 1, "requested_device": "cpu"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(DetectionRun.objects.count(), 1)
        self.assertEqual(DetectionRun.objects.get().status, DetectionRun.Status.QUEUED)

    def test_operator_can_queue_detection_run(self):
        self.client.force_authenticate(user=self.operator)
        response = self.client.post(self.url, {"requested_device": "cpu"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_viewer_cannot_queue_detection_run(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(self.url, {"requested_device": "cpu"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_list_detection_runs(self):
        DetectionRun.objects.create(
            asset=self.asset, created_by=self.owner, requested_device="cpu"
        )
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_non_member_cannot_list_detection_runs(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detection_rejected_for_unprocessed_video(self):
        self.asset.status = VideoAsset.Status.QUEUED
        self.asset.save(update_fields=["status", "updated_at"])
        response = self.client.post(self.url, {"requested_device": "cpu"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_confidence_is_rejected(self):
        response = self.client.post(
            self.url,
            {"confidence_threshold": 1.5, "requested_device": "cpu"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_run_is_scoped_to_organization(self):
        run = DetectionRun.objects.create(
            asset=self.asset, created_by=self.owner, requested_device="cpu"
        )
        other_org = Organization.objects.create(
            name="Other Detection Org", slug="other-detection-org", created_by=self.owner
        )
        Membership.objects.create(
            organization=other_org, user=self.owner,
            role=Membership.Role.OWNER, status=Membership.Status.ACTIVE,
        )
        detail_url = reverse(
            "organizations:detection-run-detail",
            kwargs={
                "organization_id": other_org.id,
                "video_id": self.asset.pk,
                "run_id": run.pk,
            },
        )
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DetectionServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="service-owner@example.test", password="A-Strong-Test-Password-2026!"
        )
        self.organization = Organization.objects.create(
            name="Service Detection Org", slug="service-detection-org", created_by=self.owner
        )
        self.asset = VideoAsset.objects.create(
            organization=self.organization,
            uploaded_by=self.owner,
            name="Service sample",
            original_filename="sample.mp4",
            content_type="video/mp4",
            file_size=100,
            status=VideoAsset.Status.COMPLETED,
        )
        self.job = VideoProcessingJob.objects.create(
            asset=self.asset, created_by=self.owner,
            status=VideoProcessingJob.Status.COMPLETED,
        )
        self.frame = VideoFrame.objects.create(
            job=self.job, frame_number=0, timestamp_seconds=0,
            width=32, height=32, image="test-frame.jpg",
        )
        self.run = DetectionRun.objects.create(
            asset=self.asset, created_by=self.owner, requested_device="cpu", max_frames=1
        )

    def tearDown(self):
        from .detection_models import DetectionFrame
        for output in DetectionFrame.objects.all():
            if output.annotated_image:
                output.annotated_image.delete(save=False)
        for frame in VideoFrame.objects.all():
            if frame.image:
                frame.image.delete(save=False)
        super().tearDown()

    @patch("apps.organizations.cameras.detection_services.infer_frame")
    @patch("apps.organizations.cameras.detection_services.resolve_device", return_value="cpu")
    def test_detection_service_persists_detection_results(self, mocked_device, mocked_infer):
        from .detection_services import process_detection_run
        from django.core.files.base import ContentFile
        from .detection_models import DetectionFrame, ObjectDetection

        # Generate a tiny valid JPEG so the FileField exposes a real local path.
        buffer = BytesIO()
        Image.new("RGB", (32, 32), color=(30, 40, 50)).save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()
        self.frame.image.save("service-frame.jpg", ContentFile(image_bytes), save=True)
        mocked_infer.return_value = (
            [{"class_id": 1, "label": "person", "confidence": 0.93, "bounding_box": [1, 2, 20, 30]}],
            image_bytes,
        )

        result = process_detection_run(self.run.pk)
        self.assertEqual(result.status, DetectionRun.Status.COMPLETED)
        self.assertEqual(result.frames_processed, 1)
        self.assertEqual(result.detections_count, 1)
        self.assertEqual(DetectionFrame.objects.count(), 1)
        self.assertEqual(ObjectDetection.objects.get().label, "person")
        mocked_device.assert_called_once_with("cpu")
        mocked_infer.assert_called_once()
