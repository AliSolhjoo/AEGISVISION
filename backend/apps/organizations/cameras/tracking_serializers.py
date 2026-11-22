from rest_framework import serializers

from .detection_models import DetectionFrame, DetectionRun
from .tracking_models import ObjectTrack, TrackObservation, TrackingRun


class TrackingRunCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingRun
        fields = ["iou_threshold", "max_gap_frames"]

    def validate(self, attrs):
        detection_run = self.context["detection_run"]
        if detection_run.status != DetectionRun.Status.COMPLETED:
            raise serializers.ValidationError(
                "The source detection run must be completed before tracking can start."
            )
        if not DetectionFrame.objects.filter(run=detection_run).exists():
            raise serializers.ValidationError(
                "No detection frames are available for this tracking run."
            )
        return attrs

    def create(self, validated_data):
        return TrackingRun.objects.create(
            detection_run=self.context["detection_run"],
            created_by=self.context["request"].user,
            **validated_data,
        )


class TrackingRunSerializer(serializers.ModelSerializer):
    detection_run_id = serializers.IntegerField(read_only=True)
    video_id = serializers.IntegerField(source="detection_run.asset_id", read_only=True)

    class Meta:
        model = TrackingRun
        fields = [
            "id", "detection_run_id", "video_id", "status", "tracker_name",
            "iou_threshold", "max_gap_frames", "frames_processed", "tracks_count",
            "observations_count", "error_message", "started_at", "finished_at",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class TrackObservationSerializer(serializers.ModelSerializer):
    detection_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = TrackObservation
        fields = [
            "id", "detection_id", "frame_number", "timestamp_seconds",
            "confidence", "bounding_box", "created_at",
        ]
        read_only_fields = fields


class ObjectTrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = ObjectTrack
        fields = [
            "id", "track_number", "class_id", "label", "status",
            "first_frame_number", "last_frame_number",
            "first_timestamp_seconds", "last_timestamp_seconds",
            "observations_count", "created_at",
        ]
        read_only_fields = fields


class ObjectTrackDetailSerializer(ObjectTrackSerializer):
    observations = TrackObservationSerializer(many=True, read_only=True)

    class Meta(ObjectTrackSerializer.Meta):
        fields = ObjectTrackSerializer.Meta.fields + ["observations"]
