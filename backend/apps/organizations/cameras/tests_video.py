import importlib.util
import tempfile
from pathlib import Path
import unittest

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.organizations.models import Organization, Membership
from .video_models import VideoAsset, VideoProcessingJob, VideoFrame
from .video_services import calculate_sample_timestamps, process_video_job


class VideoSamplingTests(TestCase):
    def test_regular_sampling_includes_last_frame(self):
        timestamps, effective = calculate_sample_timestamps(12, 2, 20)
        self.assertEqual(timestamps, [0, 2, 4, 6, 8, 10, 12])
        self.assertEqual(effective, 2)

    def test_sampling_respects_maximum_frame_count(self):
        timestamps, effective = calculate_sample_timestamps(20, 1, 5)
        self.assertEqual(len(timestamps), 5)
        self.assertEqual(timestamps, [0, 5, 10, 15, 20])
        self.assertEqual(effective, 5)

    def test_zero_duration_returns_first_sample(self):
        timestamps, effective = calculate_sample_timestamps(0, 2, 10)
        self.assertEqual(timestamps, [0.0])
        self.assertEqual(effective, 2)


class VideoAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="video-owner@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        self.operator = User.objects.create_user(
            email="video-operator@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        self.viewer = User.objects.create_user(
            email="video-viewer@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        self.outsider = User.objects.create_user(
            email="video-outsider@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        self.organization = Organization.objects.create(
            name="Video Test Organization",
            slug="video-test-organization",
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
            "organizations:videos-list",
            kwargs={"organization_id": self.organization.id},
        )
        self.client.force_authenticate(user=self.owner)

    def upload_file(self, filename="sample.mp4", content_type="video/mp4"):
        return SimpleUploadedFile(
            filename,
            b"not-a-real-video-yet",
            content_type=content_type,
        )

    def upload_payload(self, **overrides):
        payload = {
            "name": "Loading Bay Recording",
            "source_file": self.upload_file(),
            "frame_interval_seconds": "2",
            "max_frames": "30",
        }
        payload.update(overrides)
        return payload

    def tearDown(self):
        for asset in VideoAsset.objects.all():
            if asset.source_file:
                asset.source_file.delete(save=False)
            for frame in VideoFrame.objects.filter(job__asset=asset):
                if frame.image:
                    frame.image.delete(save=False)
        super().tearDown()

    def test_owner_can_upload_video_and_job_is_queued(self):
        response = self.client.post(
            self.list_url,
            self.upload_payload(),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(VideoAsset.objects.count(), 1)
        asset = VideoAsset.objects.get()
        self.assertEqual(asset.status, VideoAsset.Status.QUEUED)
        self.assertEqual(asset.processing_job.status, VideoProcessingJob.Status.QUEUED)
        self.assertNotIn("source_file", response.data)
        self.assertNotIn("url", response.data)

    def test_operator_can_upload_video(self):
        self.client.force_authenticate(user=self.operator)
        response = self.client.post(
            self.list_url,
            self.upload_payload(),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_viewer_cannot_upload_video(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(
            self.list_url,
            self.upload_payload(),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_member_cannot_upload_or_list(self):
        self.client.force_authenticate(user=self.outsider)
        upload_response = self.client.post(
            self.list_url,
            self.upload_payload(),
            format="multipart",
        )
        list_response = self.client.get(self.list_url)
        self.assertEqual(upload_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unsupported_extension_is_rejected(self):
        response = self.client.post(
            self.list_url,
            self.upload_payload(source_file=self.upload_file("notes.txt", "text/plain")),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_video_content_type_is_rejected(self):
        response = self.client.post(
            self.list_url,
            self.upload_payload(source_file=self.upload_file("sample.mp4", "text/plain")),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_max_frames_is_validated(self):
        response = self.client.post(
            self.list_url,
            self.upload_payload(max_frames="1000"),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_viewer_can_list_videos(self):
        self.client.post(self.list_url, self.upload_payload(), format="multipart")
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_video_detail_is_scoped_to_organization(self):
        response = self.client.post(self.list_url, self.upload_payload(), format="multipart")
        video_id = response.data["id"]
        other_org = Organization.objects.create(
            name="Other Video Organization",
            slug="other-video-organization",
            created_by=self.owner,
        )
        other_url = reverse(
            "organizations:videos-detail",
            kwargs={"organization_id": other_org.id, "video_id": video_id},
        )
        denied = self.client.get(other_url)
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_frames_are_not_available_before_processing(self):
        response = self.client.post(self.list_url, self.upload_payload(), format="multipart")
        frames_url = reverse(
            "organizations:video-frames",
            kwargs={
                "organization_id": self.organization.id,
                "video_id": response.data["id"],
            },
        )
        frames_response = self.client.get(frames_url)
        self.assertEqual(frames_response.status_code, status.HTTP_409_CONFLICT)

    def test_failed_job_can_be_queued_again(self):
        response = self.client.post(self.list_url, self.upload_payload(), format="multipart")
        asset = VideoAsset.objects.get(pk=response.data["id"])
        job = asset.processing_job
        job.status = VideoProcessingJob.Status.FAILED
        job.error_message = "Decoder unavailable"
        job.save()
        asset.status = VideoAsset.Status.FAILED
        asset.save(update_fields=["status", "updated_at"])

        retry_url = reverse(
            "organizations:video-process",
            kwargs={
                "organization_id": self.organization.id,
                "video_id": asset.pk,
            },
        )
        retry = self.client.post(retry_url)
        self.assertEqual(retry.status_code, status.HTTP_202_ACCEPTED)
        job.refresh_from_db()
        asset.refresh_from_db()
        self.assertEqual(job.status, VideoProcessingJob.Status.QUEUED)
        self.assertEqual(asset.status, VideoAsset.Status.QUEUED)

    def test_viewer_cannot_requeue_video(self):
        response = self.client.post(self.list_url, self.upload_payload(), format="multipart")
        retry_url = reverse(
            "organizations:video-process",
            kwargs={
                "organization_id": self.organization.id,
                "video_id": response.data["id"],
            },
        )
        self.client.force_authenticate(user=self.viewer)
        denied = self.client.post(retry_url)
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)


class VideoProcessingIntegrationTests(TestCase):
    """Generate a tiny local AVI and exercise the actual extraction pipeline."""

    @unittest.skipUnless(importlib.util.find_spec("cv2"), "OpenCV is not installed.")
    def test_processing_pipeline_extracts_frames(self):
        import cv2
        import numpy as np

        owner = User.objects.create_user(
            email="processor-test@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        organization = Organization.objects.create(
            name="Processor Test Organization",
            slug="processor-test-organization",
            created_by=owner,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.avi"
            writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*"MJPG"),
                5.0,
                (64, 48),
            )
            if not writer.isOpened():
                self.skipTest("OpenCV MJPG video writer is unavailable.")
            for index in range(10):
                frame = np.full((48, 64, 3), index * 15, dtype=np.uint8)
                writer.write(frame)
            writer.release()

            with video_path.open("rb") as stream:
                uploaded = SimpleUploadedFile(
                    "sample.avi",
                    stream.read(),
                    content_type="video/x-msvideo",
                )

            asset = VideoAsset.objects.create(
                organization=organization,
                uploaded_by=owner,
                name="Pipeline Sample",
                source_file=uploaded,
                original_filename="sample.avi",
                content_type="video/x-msvideo",
                file_size=video_path.stat().st_size,
                status=VideoAsset.Status.QUEUED,
            )
            job = VideoProcessingJob.objects.create(
                asset=asset,
                created_by=owner,
                frame_interval_seconds=1,
                max_frames=10,
            )

            result = process_video_job(job.pk)
            asset.refresh_from_db()
            self.assertEqual(result.status, VideoProcessingJob.Status.COMPLETED)
            self.assertEqual(asset.status, VideoAsset.Status.COMPLETED)
            self.assertGreater(result.frame_count, 0)
            self.assertEqual(
                VideoFrame.objects.filter(job=result).count(),
                result.frame_count,
            )

            for frame in VideoFrame.objects.filter(job=result):
                frame.image.delete(save=False)
            asset.source_file.delete(save=False)
