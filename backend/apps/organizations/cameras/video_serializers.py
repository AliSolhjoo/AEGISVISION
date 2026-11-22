import hashlib
import os
from pathlib import PurePosixPath

from rest_framework import serializers

from .models import Camera
from .video_models import (
    ALLOWED_VIDEO_EXTENSIONS,
    MAX_VIDEO_SIZE_BYTES,
    VideoAsset,
    VideoFrame,
    VideoProcessingJob,
)


class VideoUploadSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False, allow_blank=False)
    source_file = serializers.FileField(write_only=True, allow_empty_file=False)
    camera_id = serializers.PrimaryKeyRelatedField(
        source="camera",
        queryset=Camera.objects.none(),
        required=False,
        allow_null=True,
    )
    frame_interval_seconds = serializers.IntegerField(
        min_value=1,
        max_value=60,
        required=False,
        default=2,
    )
    max_frames = serializers.IntegerField(
        min_value=2,
        max_value=300,
        required=False,
        default=180,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context.get("organization")
        if organization is not None:
            self.fields["camera_id"].queryset = Camera.objects.filter(
                organization=organization,
                is_enabled=True,
            )

    def validate_source_file(self, uploaded_file):
        filename = uploaded_file.name.replace("\\", "/").split("/")[-1]
        suffix = PurePosixPath(filename).suffix.lower()
        if suffix not in ALLOWED_VIDEO_EXTENSIONS:
            raise serializers.ValidationError(
                "Unsupported video extension. Allowed: mp4, mov, mkv, avi, webm."
            )
        if uploaded_file.size <= 0:
            raise serializers.ValidationError("The uploaded file is empty.")
        if uploaded_file.size > MAX_VIDEO_SIZE_BYTES:
            raise serializers.ValidationError(
                "The video exceeds the 250 MB upload limit."
            )
        supplied_type = (getattr(uploaded_file, "content_type", "") or "").lower()
        if supplied_type and not (
            supplied_type.startswith("video/")
            or supplied_type == "application/octet-stream"
        ):
            raise serializers.ValidationError(
                "The uploaded file must have a video content type."
            )
        return uploaded_file

    def validate(self, attrs):
        organization = self.context["organization"]
        camera = attrs.get("camera")
        if camera is not None and camera.organization_id != organization.pk:
            raise serializers.ValidationError({
                "camera_id": "The selected camera does not belong to this organization."
            })
        return attrs

    def create(self, validated_data):
        from django.db import transaction
        from .video_models import VideoAsset, VideoProcessingJob

        request = self.context["request"]
        organization = self.context["organization"]
        uploaded_file = validated_data.pop("source_file")
        camera = validated_data.pop("camera", None)
        interval = validated_data.pop("frame_interval_seconds", 2)
        max_frames = validated_data.pop("max_frames", 180)

        original_filename = os.path.basename(
            uploaded_file.name.replace("\\", "/")
        )[:255]
        name = validated_data.get("name") or PurePosixPath(original_filename).stem[:150]
        if not name:
            name = "Uploaded video"

        digest = hashlib.sha256()
        uploaded_file.seek(0)
        for chunk in uploaded_file.chunks():
            digest.update(chunk)
        uploaded_file.seek(0)

        asset = None
        try:
            with transaction.atomic():
                asset = VideoAsset.objects.create(
                    organization=organization,
                    camera=camera,
                    uploaded_by=request.user,
                    name=name,
                    source_file=uploaded_file,
                    original_filename=original_filename,
                    content_type=getattr(uploaded_file, "content_type", "") or "",
                    file_size=uploaded_file.size,
                    sha256=digest.hexdigest(),
                    status=VideoAsset.Status.QUEUED,
                )
                VideoProcessingJob.objects.create(
                    asset=asset,
                    created_by=request.user,
                    frame_interval_seconds=interval,
                    max_frames=max_frames,
                    status=VideoProcessingJob.Status.QUEUED,
                )
        except Exception:
            if asset is not None and asset.source_file:
                asset.source_file.delete(save=False)
            raise
        return asset


class VideoProcessingJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoProcessingJob
        fields = [
            "id",
            "status",
            "frame_interval_seconds",
            "max_frames",
            "effective_interval_seconds",
            "frame_count",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class VideoAssetSerializer(serializers.ModelSerializer):
    camera_id = serializers.IntegerField(read_only=True, allow_null=True)
    uploaded_by_email = serializers.EmailField(source="uploaded_by.email", read_only=True)
    processing_job = VideoProcessingJobSerializer(read_only=True)
    frames_count = serializers.IntegerField(source="processing_job.frame_count", read_only=True)

    class Meta:
        model = VideoAsset
        fields = [
            "id",
            "name",
            "camera_id",
            "original_filename",
            "content_type",
            "file_size",
            "sha256",
            "status",
            "duration_seconds",
            "width",
            "height",
            "fps",
            "uploaded_by_email",
            "processing_job",
            "frames_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class VideoFrameSerializer(serializers.ModelSerializer):
    image_endpoint = serializers.SerializerMethodField()

    class Meta:
        model = VideoFrame
        fields = [
            "id",
            "frame_number",
            "timestamp_seconds",
            "width",
            "height",
            "image_endpoint",
            "created_at",
        ]

    def get_image_endpoint(self, obj):
        from django.urls import reverse

        return reverse(
            "organizations:video-frame-image",
            kwargs={
                "organization_id": self.context["organization_id"],
                "video_id": obj.job.asset_id,
                "frame_id": obj.pk,
            },
        )
