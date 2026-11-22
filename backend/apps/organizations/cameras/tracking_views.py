from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from .detection_models import DetectionRun
from .permissions import CanViewCameras, camera_permission_for_method
from .tracking_models import ObjectTrack, TrackingRun
from .tracking_serializers import (
    ObjectTrackDetailSerializer,
    ObjectTrackSerializer,
    TrackingRunCreateSerializer,
    TrackingRunSerializer,
)


class TrackingConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The requested tracking operation conflicts with the current state."
    default_code = "tracking_state_conflict"


class TrackingRunListCreateView(APIView):
    def get_permissions(self):
        return [camera_permission_for_method(self.request.method)()]

    def get_detection_run(self, organization_id, video_id, run_id):
        return get_object_or_404(
            DetectionRun.objects.select_related("asset", "asset__organization"),
            pk=run_id,
            asset_id=video_id,
            asset__organization=self.organization,
        )

    def get(self, request, organization_id, video_id, run_id):
        detection_run = self.get_detection_run(organization_id, video_id, run_id)
        runs = TrackingRun.objects.filter(detection_run=detection_run).order_by("-created_at", "-id")
        return Response(TrackingRunSerializer(runs, many=True).data)

    def post(self, request, organization_id, video_id, run_id):
        detection_run = self.get_detection_run(organization_id, video_id, run_id)
        serializer = TrackingRunCreateSerializer(
            data=request.data,
            context={"request": request, "detection_run": detection_run},
        )
        serializer.is_valid(raise_exception=True)
        tracking_run = serializer.save()
        return Response(
            TrackingRunSerializer(tracking_run).data,
            status=status.HTTP_202_ACCEPTED,
        )


class TrackingRunDetailView(APIView):
    permission_classes = [CanViewCameras]

    def get_tracking_run(self, organization_id, video_id, run_id, tracking_id):
        return get_object_or_404(
            TrackingRun.objects.select_related("detection_run", "detection_run__asset"),
            pk=tracking_id,
            detection_run_id=run_id,
            detection_run__asset_id=video_id,
            detection_run__asset__organization=self.organization,
        )

    def get(self, request, organization_id, video_id, run_id, tracking_id):
        tracking_run = self.get_tracking_run(organization_id, video_id, run_id, tracking_id)
        return Response(TrackingRunSerializer(tracking_run).data)


class ObjectTrackListView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, video_id, run_id, tracking_id):
        tracking_run = get_object_or_404(
            TrackingRun.objects.select_related("detection_run", "detection_run__asset"),
            pk=tracking_id,
            detection_run_id=run_id,
            detection_run__asset_id=video_id,
            detection_run__asset__organization=self.organization,
            status=TrackingRun.Status.COMPLETED,
        )
        tracks = ObjectTrack.objects.filter(tracking_run=tracking_run).order_by("track_number")
        return Response(ObjectTrackSerializer(tracks, many=True).data)


class ObjectTrackDetailView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, video_id, run_id, tracking_id, track_id):
        track = get_object_or_404(
            ObjectTrack.objects.select_related(
                "tracking_run", "tracking_run__detection_run", "tracking_run__detection_run__asset"
            ).prefetch_related("observations"),
            pk=track_id,
            tracking_run_id=tracking_id,
            tracking_run__detection_run_id=run_id,
            tracking_run__detection_run__asset_id=video_id,
            tracking_run__detection_run__asset__organization=self.organization,
            tracking_run__status=TrackingRun.Status.COMPLETED,
        )
        return Response(ObjectTrackDetailSerializer(track).data)
