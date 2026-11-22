from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.permissions import CanManageCameras
from .permissions import CanViewCameras
from .video_models import VideoAsset, VideoFrame, VideoProcessingJob
from .video_serializers import (
    VideoAssetSerializer,
    VideoFrameSerializer,
    VideoUploadSerializer,
)
from .video_services import delete_generated_frames


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The requested operation conflicts with the current video state."
    default_code = "video_state_conflict"


class VideoListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        permission_class = CanViewCameras if self.request.method in SAFE_METHODS else CanManageCameras
        return [permission_class()]

    def get(self, request, organization_id):
        videos = VideoAsset.objects.filter(
            organization=self.organization
        ).select_related("camera", "uploaded_by", "processing_job")
        status_filter = request.query_params.get("status")
        if status_filter:
            valid_statuses = {choice[0] for choice in VideoAsset.Status.choices}
            if status_filter not in valid_statuses:
                return Response({"status": "Invalid video status."}, status=400)
            videos = videos.filter(status=status_filter)
        camera_id = request.query_params.get("camera_id")
        if camera_id:
            try:
                camera_id = int(camera_id)
            except (TypeError, ValueError):
                return Response({"camera_id": "Must be a valid integer."}, status=400)
            videos = videos.filter(camera_id=camera_id)
        return Response(VideoAssetSerializer(videos, many=True).data)

    def post(self, request, organization_id):
        serializer = VideoUploadSerializer(
            data=request.data,
            context={"request": request, "organization": self.organization},
        )
        serializer.is_valid(raise_exception=True)
        asset = serializer.save()
        return Response(
            VideoAssetSerializer(asset).data,
            status=status.HTTP_202_ACCEPTED,
        )


class VideoDetailView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, video_id):
        asset = get_object_or_404(
            VideoAsset.objects.select_related("camera", "uploaded_by", "processing_job"),
            pk=video_id,
            organization=self.organization,
        )
        return Response(VideoAssetSerializer(asset).data)


class VideoReprocessView(APIView):
    permission_classes = [CanManageCameras]

    def post(self, request, organization_id, video_id):
        with transaction.atomic():
            asset = get_object_or_404(
                VideoAsset.objects.select_for_update(),
                pk=video_id,
                organization=self.organization,
            )
            job = get_object_or_404(
                VideoProcessingJob.objects.select_for_update(),
                asset=asset,
            )
            if job.status == VideoProcessingJob.Status.QUEUED:
                return Response(
                    {"message": "The video is already queued.", "status": job.status},
                    status=status.HTTP_202_ACCEPTED,
                )
            if job.status == VideoProcessingJob.Status.PROCESSING:
                raise Conflict("The video is currently being processed.")
            if job.status == VideoProcessingJob.Status.COMPLETED:
                raise Conflict("The video has already been processed successfully.")

            delete_generated_frames(job)
            job.status = VideoProcessingJob.Status.QUEUED
            job.frame_count = 0
            job.error_message = ""
            job.started_at = None
            job.finished_at = None
            job.effective_interval_seconds = None
            job.save()
            asset.status = VideoAsset.Status.QUEUED
            asset.save(update_fields=["status", "updated_at"])

        return Response(
            {"message": "The video has been queued for processing.", "status": job.status},
            status=status.HTTP_202_ACCEPTED,
        )


class VideoFrameListView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, video_id):
        asset = get_object_or_404(
            VideoAsset,
            pk=video_id,
            organization=self.organization,
        )
        if asset.status != VideoAsset.Status.COMPLETED:
            raise Conflict("Frames are available after processing is completed.")
        frames = VideoFrame.objects.filter(
            job__asset=asset
        ).select_related("job", "job__asset")
        serializer = VideoFrameSerializer(
            frames,
            many=True,
            context={"organization_id": organization_id},
        )
        return Response(serializer.data)


class VideoFrameImageView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, video_id, frame_id):
        frame = get_object_or_404(
            VideoFrame.objects.select_related("job", "job__asset"),
            pk=frame_id,
            job__asset_id=video_id,
            job__asset__organization=self.organization,
            job__status=VideoProcessingJob.Status.COMPLETED,
        )
        try:
            image_file = frame.image.open("rb")
        except (FileNotFoundError, OSError, ValueError):
            raise APIException("The extracted frame file is unavailable.")
        response = FileResponse(image_file, content_type="image/jpeg")
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
