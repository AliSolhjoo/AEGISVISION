from rest_framework import serializers
from rest_framework.reverse import reverse

from .detection_models import DetectionRun, DetectionFrame, ObjectDetection
from .video_models import VideoAsset


class DetectionRunCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetectionRun
        fields = ["confidence_threshold", "max_frames", "requested_device"]

    def validate(self, attrs):
        asset = self.context["asset"]
        if asset.status != VideoAsset.Status.COMPLETED:
            raise serializers.ValidationError(
                "The source video must finish frame extraction before object detection."
            )
        job = getattr(asset, "processing_job", None)
        if job is None or job.status != "completed" or not job.frames.exists():
            raise serializers.ValidationError(
                "No completed frame-extraction job with available frames was found."
            )
        return attrs

    def create(self, validated_data):
        return DetectionRun.objects.create(
            asset=self.context["asset"],
            created_by=self.context["request"].user,
            **validated_data,
        )


class DetectionRunSerializer(serializers.ModelSerializer):
    asset_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = DetectionRun
        fields = [
            "id", "asset_id", "status", "model_name",
            "confidence_threshold", "max_frames", "requested_device",
            "actual_device", "frames_processed", "detections_count",
            "error_message", "started_at", "finished_at",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class ObjectDetectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ObjectDetection
        fields = [
            "id", "class_id", "label", "confidence",
            "bounding_box", "created_at",
        ]
        read_only_fields = fields


class DetectionFrameSerializer(serializers.ModelSerializer):
    source_frame_number = serializers.IntegerField(
        source="source_frame.frame_number", read_only=True
    )
    timestamp_seconds = serializers.FloatField(
        source="source_frame.timestamp_seconds", read_only=True
    )
    detections = ObjectDetectionSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = DetectionFrame
        fields = [
            "id", "source_frame_number", "timestamp_seconds",
            "detections_count", "image_url", "detections", "created_at",
        ]
        read_only_fields = fields

    def get_image_url(self, obj):
        request = self.context.get("request")
        path = reverse(
            "organizations:detection-frame-image",
            kwargs={
                "organization_id": self.context["organization_id"],
                "video_id": self.context["video_id"],
                "run_id": obj.run_id,
                "detection_frame_id": obj.pk,
            },
            request=request,
        )
        return path
