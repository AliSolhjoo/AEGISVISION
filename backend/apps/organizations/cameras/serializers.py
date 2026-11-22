from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .live_models import CameraLiveState
from .models import Camera


class CameraSerializer(serializers.ModelSerializer):
    # Stream endpoints and credentials are write-only; never disclose them.
    stream_url = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=2048)
    stream_username = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=160)
    stream_password = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=512, trim_whitespace=False)
    clear_credentials = serializers.BooleanField(write_only=True, required=False, default=False)
    has_stream_credentials = serializers.BooleanField(source="has_stream_credentials", read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = Camera
        fields = [
            "id", "name", "code", "description", "location", "source_type",
            "stream_url", "stream_username", "stream_password", "clear_credentials",
            "has_stream_credentials", "target_fps", "confidence_threshold",
            "status", "is_enabled", "last_seen_at", "created_by_email",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "has_stream_credentials", "status", "is_enabled", "last_seen_at",
            "created_by_email", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        candidate = self.instance or Camera()
        for field in ("source_type", "stream_url", "target_fps", "confidence_threshold"):
            if field in attrs:
                setattr(candidate, field, attrs[field])

        username = attrs.get("stream_username")
        password = attrs.get("stream_password")
        if (username is not None and password is None) or (password is not None and username is None):
            raise serializers.ValidationError({
                "stream_username": "Username and password must be supplied together."
            })
        if attrs.get("clear_credentials") and (username or password):
            raise serializers.ValidationError({
                "clear_credentials": "Do not send new credentials while clearing existing credentials."
            })

        organization = self.context.get("organization")
        code = attrs.get("code", getattr(self.instance, "code", None))
        if organization is not None and code:
            duplicate = Camera.objects.filter(organization=organization, code=code)
            if self.instance is not None:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError({
                    "code": "A camera with this code already exists in this organization."
                })

        try:
            candidate.clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc
        return attrs

    def create(self, validated_data):
        username = validated_data.pop("stream_username", "")
        password = validated_data.pop("stream_password", "")
        validated_data.pop("clear_credentials", None)
        camera = Camera(**validated_data)
        if username or password:
            camera.set_stream_credentials(username, password)
        camera.full_clean()
        camera.save()
        return camera

    def update(self, instance, validated_data):
        username = validated_data.pop("stream_username", None)
        password = validated_data.pop("stream_password", None)
        clear_credentials = validated_data.pop("clear_credentials", False)
        stream_changed = any(
            key in validated_data and getattr(instance, key) != validated_data[key]
            for key in ("stream_url", "source_type")
        ) or username is not None or clear_credentials

        for key, value in validated_data.items():
            setattr(instance, key, value)
        if clear_credentials:
            instance.clear_stream_credentials()
        elif username is not None and password is not None:
            instance.set_stream_credentials(username, password)
        instance.full_clean()
        instance.save()

        if stream_changed:
            CameraLiveState.objects.filter(camera=instance, is_requested=True).update(
                is_requested=False,
                status=CameraLiveState.Status.STOPPED,
                last_error="Camera source configuration changed. Start the live stream again.",
            )
        return instance
