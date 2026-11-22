from django.http import FileResponse
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from .detection_models import DetectionRun, DetectionFrame
from .detection_serializers import (
    DetectionFrameSerializer,
    DetectionRunCreateSerializer,
    DetectionRunSerializer,
)
from .permissions import CanViewCameras
from .permissions import camera_permission_for_method
from .video_models import VideoAsset


class DetectionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The requested detection operation conflicts with the current state."
    default_code = "detection_state_conflict"


class DetectionRunListCreateView(APIView):
    def get_permissions(self):
        permission_class = camera_permission_for_method(self.request.method)
        return [permission_class()]

    def get_asset(self, organization_id, video_id):
        return get_object_or_404(
            VideoAsset,
            pk=video_id,
            organization=self.organization,
        )

    def get(self, request, organization_id, video_id):
        asset = self.get_asset(organization_id, video_id)
        runs = DetectionRun.objects.filter(asset=asset).order_by("-created_at", "-id")
        return Response(DetectionRunSerializer(runs, many=True).data)

    def post(self, request, organization_id, video_id):
        asset = self.get_asset(organization_id, video_id)
        serializer = DetectionRunCreateSerializer(
            data=request.data,
            context={"request": request, "asset": asset},
        )
        serializer.is_valid(raise_exception=True)
        run = serializer.save()
        return Response(
            DetectionRunSerializer(run).data,
            status=status.HTTP_202_ACCEPTED,
        )


class DetectionRunDetailView(APIView):
    permission_classes = [CanViewCameras]

    def get_run(self, organization_id, video_id, run_id):
        return get_object_or_404(
            DetectionRun.objects.select_related("asset", "asset__organization"),
            pk=run_id,
            asset_id=video_id,
            asset__organization=self.organization,
        )

    def get(self, request, organization_id, video_id, run_id):
        run = self.get_run(organization_id, video_id, run_id)
        return Response(DetectionRunSerializer(run).data)


class DetectionFrameListView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, video_id, run_id):
        run = get_object_or_404(
            DetectionRun,
            pk=run_id,
            asset_id=video_id,
            asset__organization=self.organization,
        )
        if run.status != DetectionRun.Status.COMPLETED:
            raise DetectionConflict("Detection results are available after the run is completed.")
        frames = DetectionFrame.objects.filter(run=run).select_related(
            "source_frame", "run"
        ).prefetch_related("detections")
        serializer = DetectionFrameSerializer(
            frames,
            many=True,
            context={
                "request": request,
                "organization_id": organization_id,
                "video_id": video_id,
            },
        )
        return Response(serializer.data)


class DetectionFrameImageView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, video_id, run_id, detection_frame_id):
        detection_frame = get_object_or_404(
            DetectionFrame.objects.select_related("run", "run__asset"),
            pk=detection_frame_id,
            run_id=run_id,
            run__asset_id=video_id,
            run__asset__organization=self.organization,
            run__status=DetectionRun.Status.COMPLETED,
        )
        try:
            image_file = detection_frame.annotated_image.open("rb")
        except (FileNotFoundError, OSError, ValueError):
            raise APIException("The annotated image is unavailable.")
        response = FileResponse(image_file, content_type="image/jpeg")
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
