from django.contrib import admin

from .models import Organization, Membership


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "slug",
        "created_by",
        "is_active",
        "created_at",
    )

    search_fields = (
        "name",
        "slug",
        "created_by__email",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    prepopulated_fields = {
        "slug": ("name",)
    }

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change):

        is_new = obj.pk is None

        super().save_model(request, obj, form, change)

        if is_new:
            Membership.objects.get_or_create(
                organization=obj,
                user=obj.created_by,
                defaults={
                    "role": Membership.Role.OWNER,
                    "status": Membership.Status.ACTIVE,
                }
            )


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "organization",
        "role",
        "status",
        "created_at",
    )

    search_fields = (
        "user__email",
        "organization__name",
    )

    list_filter = (
        "role",
        "status",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

# AEGISVISION CAMERA MODULE ADMIN REGISTRATION
from .cameras.models import Camera


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = (
        "name", "code", "organization", "source_type",
        "status", "is_enabled", "created_at",
    )
    list_filter = ("source_type", "status", "is_enabled")
    search_fields = ("name", "code", "organization__name")
    readonly_fields = ("id", "created_at", "updated_at", "last_seen_at")
    exclude = ("stream_url",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

# AEGISVISION VIDEO PROCESSING ADMIN REGISTRATION
from .cameras.video_models import VideoAsset, VideoProcessingJob


@admin.register(VideoAsset)
class VideoAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "camera", "status", "file_size", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "original_filename", "organization__name")
    readonly_fields = (
        "id", "organization", "camera", "uploaded_by", "name",
        "source_file", "original_filename", "content_type", "file_size",
        "sha256", "status", "duration_seconds", "width", "height", "fps",
        "created_at", "updated_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VideoProcessingJob)
class VideoProcessingJobAdmin(admin.ModelAdmin):
    list_display = ("id", "asset", "status", "frame_count", "created_at", "finished_at")
    list_filter = ("status", "created_at")
    search_fields = ("asset__name", "asset__organization__name")
    readonly_fields = tuple(field.name for field in VideoProcessingJob._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

# AEGISVISION OBJECT DETECTION ADMIN REGISTRATION
from .cameras.detection_models import DetectionRun, DetectionFrame, ObjectDetection


@admin.register(DetectionRun)
class DetectionRunAdmin(admin.ModelAdmin):
    list_display = (
        "id", "asset", "status", "model_name", "frames_processed",
        "detections_count", "actual_device", "created_at",
    )
    list_filter = ("status", "model_name", "requested_device", "actual_device")
    search_fields = ("asset__name", "asset__organization__name", "created_by__email")
    readonly_fields = tuple(field.name for field in DetectionRun._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DetectionFrame)
class DetectionFrameAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "source_frame", "detections_count", "created_at")
    list_filter = ("created_at",)
    readonly_fields = tuple(field.name for field in DetectionFrame._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ObjectDetection)
class ObjectDetectionAdmin(admin.ModelAdmin):
    list_display = ("id", "label", "class_id", "confidence", "detection_frame")
    list_filter = ("label",)
    search_fields = ("label",)
    readonly_fields = tuple(field.name for field in ObjectDetection._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

# AEGISVISION OBJECT TRACKING ADMIN REGISTRATION
from .cameras.tracking_models import TrackingRun, ObjectTrack, TrackObservation


@admin.register(TrackingRun)
class TrackingRunAdmin(admin.ModelAdmin):
    list_display = (
        "id", "detection_run", "status", "tracker_name", "tracks_count",
        "observations_count", "created_at",
    )
    list_filter = ("status", "tracker_name", "created_at")
    search_fields = (
        "detection_run__asset__name",
        "detection_run__asset__organization__name",
        "created_by__email",
    )
    readonly_fields = tuple(field.name for field in TrackingRun._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ObjectTrack)
class ObjectTrackAdmin(admin.ModelAdmin):
    list_display = (
        "id", "tracking_run", "track_number", "label", "status", "observations_count",
    )
    list_filter = ("label", "status")
    search_fields = ("label", "tracking_run__detection_run__asset__name")
    readonly_fields = tuple(field.name for field in ObjectTrack._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TrackObservation)
class TrackObservationAdmin(admin.ModelAdmin):
    list_display = (
        "id", "track", "frame_number", "timestamp_seconds", "confidence",
    )
    list_filter = ("frame_number",)
    search_fields = ("track__label", "track__tracking_run__detection_run__asset__name")
    readonly_fields = tuple(field.name for field in TrackObservation._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



# AEGISVISION SECURITY ANALYTICS AND SOC ADMINISTRATION
from .cameras.event_models import AnalyticsRule, SecurityEvent, SecurityEventActivity


@admin.register(AnalyticsRule)
class AnalyticsRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "rule_type", "organization", "asset", "camera", "is_active", "created_at")
    list_filter = ("rule_type", "is_active", "created_at")
    search_fields = ("name", "asset__name", "camera__name", "organization__name")
    readonly_fields = tuple(field.name for field in AnalyticsRule._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ("id", "rule_name", "severity", "status", "assigned_to", "asset", "created_at")
    list_filter = ("severity", "status", "event_type", "created_at")
    search_fields = ("rule_name", "label", "asset__name", "assigned_to__email")
    readonly_fields = tuple(field.name for field in SecurityEvent._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

@admin.register(SecurityEventActivity)
class SecurityEventActivityAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "action", "actor", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("event__rule_name", "note", "actor__email")
    readonly_fields = tuple(field.name for field in SecurityEventActivity._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

from .cameras.live_models import CameraLiveState, CameraWorkerHeartbeat, CameraLiveEvent, CameraLiveEventActivity

admin.site.register(CameraLiveState)
admin.site.register(CameraWorkerHeartbeat)
admin.site.register(CameraLiveEvent)
admin.site.register(CameraLiveEventActivity)

# AEGISVISION LIVE CAMERA INTELLIGENCE ADMIN
from .cameras.live_models import (
    CameraLiveState,
    CameraWorkerHeartbeat,
    CameraLiveEvent,
    CameraLiveEventActivity,
)


@admin.register(CameraLiveState)
class CameraLiveStateAdmin(admin.ModelAdmin):
    list_display = ("camera", "status", "is_requested", "fps_actual", "objects_count", "tracks_count", "last_frame_at")
    list_filter = ("status", "is_requested")
    search_fields = ("camera__name", "camera__code", "camera__organization__name")
    readonly_fields = tuple(field.name for field in CameraLiveState._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CameraWorkerHeartbeat)
class CameraWorkerHeartbeatAdmin(admin.ModelAdmin):
    list_display = ("id", "process_id", "started_at", "last_heartbeat")
    readonly_fields = tuple(field.name for field in CameraWorkerHeartbeat._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CameraLiveEvent)
class CameraLiveEventAdmin(admin.ModelAdmin):
    list_display = ("id", "camera", "rule_name", "label", "severity", "status", "occurred_at")
    list_filter = ("severity", "status", "event_type", "occurred_at")
    search_fields = ("camera__name", "rule_name", "label")
    readonly_fields = tuple(field.name for field in CameraLiveEvent._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(CameraLiveEventActivity)
class CameraLiveEventActivityAdmin(admin.ModelAdmin):
    list_display = ("event", "action", "actor", "created_at")
    list_filter = ("action", "created_at")
    readonly_fields = tuple(field.name for field in CameraLiveEventActivity._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
