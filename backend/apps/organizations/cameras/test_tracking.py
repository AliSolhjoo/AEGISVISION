from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.organizations.models import Organization, Membership
from .detection_models import DetectionFrame, DetectionRun, ObjectDetection
from .tracking_models import ObjectTrack, TrackObservation, TrackingRun
from .tracking_services import associate_detections, intersection_over_union, process_tracking_run
from .video_models import VideoAsset, VideoFrame, VideoProcessingJob


class IoUAndAssociationTests(TestCase):
    def test_iou_for_identical_boxes_is_one(self):
        self.assertAlmostEqual(
            intersection_over_union([0, 0, 10, 10], [0, 0, 10, 10]),
            1.0,
        )

    def test_iou_for_non_overlapping_boxes_is_zero(self):
        self.assertEqual(
            intersection_over_union([0, 0, 10, 10], [20, 20, 30, 30]),
            0.0,
        )

    def test_invalid_boxes_return_zero(self):
        self.assertEqual(intersection_over_union([1, 1, 1, 5], [0, 0, 5, 5]), 0.0)
        self.assertEqual(intersection_over_union([0, 0, 1], [0, 0, 5, 5]), 0.0)

    def test_same_object_is_associated_across_adjacent_frames(self):
        frames = [
            {"frame_number": 10, "timestamp_seconds": 1.0, "detections": [
                {"class_id": 1, "label": "person", "confidence": 0.95, "bounding_box": [0, 0, 20, 30]},
            ]},
            {"frame_number": 20, "timestamp_seconds": 2.0, "detections": [
                {"class_id": 1, "label": "person", "confidence": 0.93, "bounding_box": [2, 1, 22, 31]},
            ]},
        ]
        result = associate_detections(frames, iou_threshold=0.3, max_gap_frames=0)
        self.assertEqual(result["tracks_count"], 1)
        self.assertEqual(result["observations_count"], 2)
        self.assertEqual(result["tracks"][0]["first_frame_number"], 10)
        self.assertEqual(result["tracks"][0]["last_frame_number"], 20)

    def test_different_classes_are_never_joined(self):
        frames = [
            {"frame_number": 1, "detections": [
                {"class_id": 1, "label": "person", "confidence": 0.9, "bounding_box": [0, 0, 10, 10]},
            ]},
            {"frame_number": 2, "detections": [
                {"class_id": 3, "label": "car", "confidence": 0.9, "bounding_box": [0, 0, 10, 10]},
            ]},
        ]
        result = associate_detections(frames, iou_threshold=0.3, max_gap_frames=2)
        self.assertEqual(result["tracks_count"], 2)

    def test_non_overlapping_objects_create_new_tracks(self):
        frames = [
            {"frame_number": 1, "detections": [
                {"class_id": 1, "label": "person", "confidence": 0.9, "bounding_box": [0, 0, 10, 10]},
            ]},
            {"frame_number": 2, "detections": [
                {"class_id": 1, "label": "person", "confidence": 0.9, "bounding_box": [30, 30, 40, 40]},
            ]},
        ]
        result = associate_detections(frames, iou_threshold=0.3, max_gap_frames=2)
        self.assertEqual(result["tracks_count"], 2)

    def test_track_can_bridge_configured_missing_frames(self):
        frames = [
            {"frame_number": 1, "detections": [
                {"class_id": 1, "label": "person", "confidence": 0.9, "bounding_box": [0, 0, 20, 20]},
            ]},
            {"frame_number": 2, "detections": []},
            {"frame_number": 3, "detections": [
                {"class_id": 1, "label": "person", "confidence": 0.9, "bounding_box": [1, 1, 21, 21]},
            ]},
        ]
        result = associate_detections(frames, iou_threshold=0.3, max_gap_frames=1)
        self.assertEqual(result["tracks_count"], 1)
        self.assertEqual(result["observations_count"], 2)

    def test_track_does_not_bridge_more_than_configured_gap(self):
        frames = [
            {"frame_number": 1, "detections": [
                {"class_id": 1, "label": "person", "confidence": 0.9, "bounding_box": [0, 0, 20, 20]},
            ]},
            {"frame_number": 2, "detections": []},
            {"frame_number": 3, "detections": []},
            {"frame_number": 4, "detections": [
                {"class_id": 1, "label": "person", "confidence": 0.9, "bounding_box": [1, 1, 21, 21]},
            ]},
        ]
        result = associate_detections(frames, iou_threshold=0.3, max_gap_frames=1)
        self.assertEqual(result["tracks_count"], 2)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            associate_detections([], iou_threshold=1.0, max_gap_frames=1)
        with self.assertRaises(ValueError):
            associate_detections([], iou_threshold=0.3, max_gap_frames=31)

    def test_empty_frames_produce_no_tracks(self):
        result = associate_detections([
            {"frame_number": 1, "detections": []},
            {"frame_number": 2, "detections": []},
        ])
        self.assertEqual(result["tracks_count"], 0)
        self.assertEqual(result["observations_count"], 0)


class TrackingServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tracking-service@example.test",
            password="A-Strong-Test-Password-2026!",
        )
        self.organization = Organization.objects.create(
            name="Tracking Service Org",
            slug="tracking-service-org",
            created_by=self.user,
        )
        self.asset = VideoAsset.objects.create(
            organization=self.organization,
            uploaded_by=self.user,
            name="Tracking sample",
            original_filename="tracking.mp4",
            content_type="video/mp4",
            file_size=2048,
            status=VideoAsset.Status.COMPLETED,
        )
        self.job = VideoProcessingJob.objects.create(
            asset=self.asset,
            created_by=self.user,
            status=VideoProcessingJob.Status.COMPLETED,
        )
        self.source_frames = [
            VideoFrame.objects.create(
                job=self.job,
                frame_number=frame_number,
                timestamp_seconds=timestamp,
                width=640,
                height=480,
                image=f"tracking-tests/frame-{frame_number}.jpg",
            )
            for frame_number, timestamp in [(0, 0.0), (25, 1.0)]
        ]
        self.detection_run = DetectionRun.objects.create(
            asset=self.asset,
            created_by=self.user,
            status=DetectionRun.Status.COMPLETED,
            frames_processed=2,
            detections_count=2,
        )
        self.detection_frames = []
        for source_frame in self.source_frames:
            detection_frame = DetectionFrame.objects.create(
                run=self.detection_run,
                source_frame=source_frame,
                annotated_image=f"tracking-tests/annotated-{source_frame.frame_number}.jpg",
                detections_count=1,
            )
            self.detection_frames.append(detection_frame)
        ObjectDetection.objects.create(
            detection_frame=self.detection_frames[0],
            class_id=1,
            label="person",
            confidence=0.95,
            bounding_box=[10, 10, 50, 80],
        )
        ObjectDetection.objects.create(
            detection_frame=self.detection_frames[1],
            class_id=1,
            label="person",
            confidence=0.92,
            bounding_box=[12, 11, 52, 81],
        )
        self.tracking_run = TrackingRun.objects.create(
            detection_run=self.detection_run,
            created_by=self.user,
            iou_threshold=0.3,
            max_gap_frames=1,
        )

    def test_service_persists_tracks_and_observations(self):
        result = process_tracking_run(self.tracking_run.pk)
        self.assertEqual(result.status, TrackingRun.Status.COMPLETED)
        self.assertEqual(result.frames_processed, 2)
        self.assertEqual(result.tracks_count, 1)
        self.assertEqual(result.observations_count, 2)
        self.assertEqual(ObjectTrack.objects.filter(tracking_run=result).count(), 1)
        self.assertEqual(TrackObservation.objects.filter(track__tracking_run=result).count(), 2)

    def test_service_refuses_uncompleted_detection_run(self):
        self.detection_run.status = DetectionRun.Status.PROCESSING
        self.detection_run.save(update_fields=["status"])
        result = process_tracking_run(self.tracking_run.pk)
        self.assertEqual(result.status, TrackingRun.Status.FAILED)
        self.assertIn("must be completed", result.error_message)


class TrackingAPITests(APITestCase):
    password = "A-Strong-Test-Password-2026!"

    def setUp(self):
        self.owner = User.objects.create_user(email="tracking-owner@example.test", password=self.password)
        self.operator = User.objects.create_user(email="tracking-operator@example.test", password=self.password)
        self.viewer = User.objects.create_user(email="tracking-viewer@example.test", password=self.password)
        self.outsider = User.objects.create_user(email="tracking-outsider@example.test", password=self.password)
        self.organization = Organization.objects.create(
            name="Tracking API Org", slug="tracking-api-org", created_by=self.owner
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
            name="API tracking video",
            original_filename="api-tracking.mp4",
            content_type="video/mp4",
            file_size=1024,
            status=VideoAsset.Status.COMPLETED,
        )
        self.detection_run = DetectionRun.objects.create(
            asset=self.asset,
            created_by=self.owner,
            status=DetectionRun.Status.COMPLETED,
        )
        self.job = VideoProcessingJob.objects.create(
            asset=self.asset,
            created_by=self.owner,
            status=VideoProcessingJob.Status.COMPLETED,
        )
        self.source_frame = VideoFrame.objects.create(
            job=self.job,
            frame_number=0,
            timestamp_seconds=0,
            width=100,
            height=100,
            image="tracking-tests/api-frame.jpg",
        )
        self.detection_frame = DetectionFrame.objects.create(
            run=self.detection_run,
            source_frame=self.source_frame,
            annotated_image="tracking-tests/api-annotated.jpg",
            detections_count=1,
        )
        self.detection = ObjectDetection.objects.create(
            detection_frame=self.detection_frame,
            class_id=1,
            label="person",
            confidence=0.9,
            bounding_box=[1, 1, 20, 30],
        )
        self.list_url = reverse(
            "organizations:tracking-runs",
            kwargs={
                "organization_id": self.organization.id,
                "video_id": self.asset.pk,
                "run_id": self.detection_run.pk,
            },
        )
        self.client.force_authenticate(user=self.owner)

    def test_owner_can_queue_tracking(self):
        response = self.client.post(
            self.list_url,
            {"iou_threshold": 0.35, "max_gap_frames": 2},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(TrackingRun.objects.count(), 1)
        self.assertEqual(TrackingRun.objects.get().status, TrackingRun.Status.QUEUED)

    def test_operator_can_queue_tracking(self):
        self.client.force_authenticate(user=self.operator)
        response = self.client.post(self.list_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_viewer_cannot_queue_tracking(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(self.list_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_list_tracking_runs(self):
        TrackingRun.objects.create(detection_run=self.detection_run, created_by=self.owner)
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_outsider_cannot_list_tracking_runs(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_iou_threshold_is_rejected(self):
        response = self.client.post(self.list_url, {"iou_threshold": 1.2}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tracking_runs_are_organization_scoped(self):
        other_organization = Organization.objects.create(
            name="Other Tracking Org", slug="other-tracking-org", created_by=self.owner
        )
        Membership.objects.create(
            organization=other_organization,
            user=self.owner,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )
        response = self.client.get(reverse(
            "organizations:tracking-runs",
            kwargs={
                "organization_id": other_organization.id,
                "video_id": self.asset.pk,
                "run_id": self.detection_run.pk,
            },
        ))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_completed_run_exposes_tracks(self):
        tracking_run = TrackingRun.objects.create(
            detection_run=self.detection_run,
            created_by=self.owner,
            status=TrackingRun.Status.COMPLETED,
        )
        track = ObjectTrack.objects.create(
            tracking_run=tracking_run,
            track_number=1,
            class_id=1,
            label="person",
            first_frame_number=0,
            last_frame_number=0,
            observations_count=1,
        )
        TrackObservation.objects.create(
            track=track,
            detection=self.detection,
            source_frame=self.source_frame,
            frame_number=0,
            timestamp_seconds=0,
            confidence=0.9,
            bounding_box=[1, 1, 20, 30],
        )
        response = self.client.get(reverse(
            "organizations:tracking-tracks",
            kwargs={
                "organization_id": self.organization.id,
                "video_id": self.asset.pk,
                "run_id": self.detection_run.pk,
                "tracking_id": tracking_run.pk,
            },
        ))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_track_detail_is_scoped_to_tracking_run(self):
        tracking_run = TrackingRun.objects.create(
            detection_run=self.detection_run,
            created_by=self.owner,
            status=TrackingRun.Status.COMPLETED,
        )
        track = ObjectTrack.objects.create(
            tracking_run=tracking_run,
            track_number=1,
            class_id=1,
            label="person",
            first_frame_number=0,
            last_frame_number=0,
        )
        response = self.client.get(reverse(
            "organizations:tracking-track-detail",
            kwargs={
                "organization_id": self.organization.id,
                "video_id": self.asset.pk,
                "run_id": self.detection_run.pk,
                "tracking_id": tracking_run.pk,
                "track_id": track.pk,
            },
        ))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["track_number"], 1)
        self.assertEqual(response.data["observations"], [])
