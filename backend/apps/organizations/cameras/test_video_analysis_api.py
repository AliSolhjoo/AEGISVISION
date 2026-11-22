from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import APITestCase, override_settings
from rest_framework import status

from apps.accounts.models import User
from apps.organizations.models import (
    Membership,
    Organization,
    VideoAsset,
    VideoProcessingJob,
)


class AutomaticVideoAnalysisApiTests(APITestCase):
    password = "A-Strong-Test-Password-2026!"

    def setUp(self):
        self.temp_directory = TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        media_root = Path(self.temp_directory.name) / "media"
        self.settings_override = override_settings(
            BASE_DIR=Path(self.temp_directory.name),
            MEDIA_ROOT=media_root,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.owner = User.objects.create_user(
            email="auto-analysis-owner@example.test",
            password=self.password,
        )
        self.organization = Organization.objects.create(
            name="Automatic Analysis Test",
            slug="automatic-analysis-test",
            created_by=self.owner,
        )
        Membership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )
        self.client.force_authenticate(user=self.owner)

    @patch(
        "apps.organizations.cameras.video_analysis_api.spawn_analysis_worker",
        return_value=43210,
    )
    def test_upload_creates_asset_job_and_starts_background_worker(self, spawn_worker):
        upload = SimpleUploadedFile(
            "sample.mp4",
            b"fake-mp4-payload-for-api-test",
            content_type="video/mp4",
        )
        response = self.client.post(
            "/api/video-analysis/upload/",
            {
                "video": upload,
                "organization_id": str(self.organization.pk),
                "name": "Automatic sample",
                "frame_interval_seconds": "1",
                "max_frames": "300",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        asset = VideoAsset.objects.get(pk=response.data["asset_id"])
        job = VideoProcessingJob.objects.get(asset=asset)
        self.assertEqual(asset.name, "Automatic sample")
        self.assertEqual(job.status, VideoProcessingJob.Status.QUEUED)
        self.assertEqual(job.frame_interval_seconds, 1)
        self.assertEqual(job.max_frames, 300)
        spawn_worker.assert_called_once_with(asset.pk)

    @patch(
        "apps.organizations.cameras.video_analysis_api.spawn_analysis_worker",
        return_value=43211,
    )
    def test_existing_queued_library_asset_can_start_automatic_analysis(self, spawn_worker):
        asset = VideoAsset.objects.create(
            organization=self.organization,
            uploaded_by=self.owner,
            name="Queued library video",
            source_file="aegisvision/videos/existing.mp4",
            original_filename="existing.mp4",
            content_type="video/mp4",
            file_size=100,
            status=VideoAsset.Status.QUEUED,
        )
        VideoProcessingJob.objects.create(
            asset=asset,
            created_by=self.owner,
            status=VideoProcessingJob.Status.QUEUED,
            frame_interval_seconds=1,
            max_frames=300,
        )

        response = self.client.post(
            f"/api/video-analysis/assets/{asset.pk}/start/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["asset_id"], asset.pk)
        spawn_worker.assert_called_once_with(asset.pk)

    @patch(
        "apps.organizations.cameras.video_analysis_api.spawn_analysis_worker",
        return_value=43212,
    )
    def test_upload_rejects_user_without_organization_membership(self, spawn_worker):
        outsider = User.objects.create_user(
            email="auto-analysis-outsider@example.test",
            password=self.password,
        )
        self.client.force_authenticate(user=outsider)
        upload = SimpleUploadedFile("sample.mp4", b"data", content_type="video/mp4")

        response = self.client.post(
            "/api/video-analysis/upload/",
            {
                "video": upload,
                "organization_id": str(self.organization.pk),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        spawn_worker.assert_not_called()

    def test_upload_rejects_invalid_frame_options(self):
        upload = SimpleUploadedFile("sample.mp4", b"data", content_type="video/mp4")
        response = self.client.post(
            "/api/video-analysis/upload/",
            {
                "video": upload,
                "organization_id": str(self.organization.pk),
                "frame_interval_seconds": "0",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
