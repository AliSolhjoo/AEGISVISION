from django.urls import path

from .views import (
    OrganizationListCreateView,
    OrganizationDetailView,
    OrganizationMembersView,
    MembershipDetailView,
    AcceptInvitationView,
)


from apps.organizations.cameras.views import CameraListCreateView, CameraDetailView

from apps.organizations.cameras.video_views import (
    VideoListCreateView,
    VideoDetailView,
    VideoReprocessView,
    VideoFrameListView,
    VideoFrameImageView,
)

from apps.organizations.cameras.detection_views import (
    DetectionRunListCreateView,
    DetectionRunDetailView,
    DetectionFrameListView,
    DetectionFrameImageView,
)

from apps.organizations.cameras.event_views import (
    EventRuleListCreateView,
    EventRuleDetailView,
    EventAnalysisView,
    OrganizationEventListView,
    SecurityEventStatusView,
    SecurityEventActivityView,
)

app_name = "organizations"

from apps.organizations.cameras.live_views import (
    LiveWorkerHealthView, CameraConnectionTestView, CameraLiveStateView,
    CameraLiveStartView, CameraLiveStopView, CameraLiveSnapshotView,
    CameraLiveEventListView, CameraLiveEventStatusView,
    CameraLiveRuleListCreateView, CameraLiveRuleDetailView,
)


from apps.organizations.cameras.soc_views import (
    SOCDashboardView,
    SOCEventListView,
    SOCAssigneesView,
    SOCExportCSVView,
)

from apps.organizations.cameras.tracking_views import (
    TrackingRunListCreateView,
    TrackingRunDetailView,
    ObjectTrackListView,
    ObjectTrackDetailView,
)

urlpatterns = [
    # AEGISVISION LIVE CAMERA INTELLIGENCE URLS
    path("<uuid:organization_id>/live-camera-worker/health/", LiveWorkerHealthView.as_view(), name="live-camera-worker-health"),
    path("<uuid:organization_id>/cameras/<int:camera_id>/test-connection/", CameraConnectionTestView.as_view(), name="camera-test-connection"),
    path("<uuid:organization_id>/cameras/<int:camera_id>/live/", CameraLiveStateView.as_view(), name="camera-live-state"),
    path("<uuid:organization_id>/cameras/<int:camera_id>/live/start/", CameraLiveStartView.as_view(), name="camera-live-start"),
    path("<uuid:organization_id>/cameras/<int:camera_id>/live/stop/", CameraLiveStopView.as_view(), name="camera-live-stop"),
    path("<uuid:organization_id>/cameras/<int:camera_id>/live/snapshot/", CameraLiveSnapshotView.as_view(), name="camera-live-snapshot"),
    path("<uuid:organization_id>/cameras/<int:camera_id>/event-rules/", CameraLiveRuleListCreateView.as_view(), name="camera-live-event-rules"),
    path("<uuid:organization_id>/cameras/<int:camera_id>/event-rules/<int:rule_id>/", CameraLiveRuleDetailView.as_view(), name="camera-live-event-rule-detail"),
    path("<uuid:organization_id>/cameras/<int:camera_id>/live/events/", CameraLiveEventListView.as_view(), name="camera-live-events"),
    path("<uuid:organization_id>/cameras/<int:camera_id>/live/events/<int:event_id>/", CameraLiveEventStatusView.as_view(), name="camera-live-event-status"),

    # AEGISVISION CAMERA MODULE URLS
    path(
        "<uuid:organization_id>/cameras/",
        CameraListCreateView.as_view(),
        name="cameras-list",
    ),
    path(
        "<uuid:organization_id>/cameras/<int:camera_id>/",
        CameraDetailView.as_view(),
        name="cameras-detail",
    ),


    path(
        "",
        OrganizationListCreateView.as_view(),
        name="list-create"
    ),

    path(
        "invitations/<uuid:membership_id>/accept/",
        AcceptInvitationView.as_view(),
        name="invitation-accept"
    ),

    path(
        "<uuid:organization_id>/",
        OrganizationDetailView.as_view(),
        name="detail"
    ),

    path(
        "<uuid:organization_id>/members/",
        OrganizationMembersView.as_view(),
        name="members"
    ),

    path(
        "<uuid:organization_id>/members/<uuid:membership_id>/",
        MembershipDetailView.as_view(),
        name="member-detail"
    ),


    # AEGISVISION VIDEO PROCESSING URLS
    path(
        "<uuid:organization_id>/videos/",
        VideoListCreateView.as_view(),
        name="videos-list",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/",
        VideoDetailView.as_view(),
        name="videos-detail",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/process/",
        VideoReprocessView.as_view(),
        name="video-process",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/frames/",
        VideoFrameListView.as_view(),
        name="video-frames",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/frames/<int:frame_id>/image/",
        VideoFrameImageView.as_view(),
        name="video-frame-image",
    ),

    # AEGISVISION OBJECT DETECTION URLS
    path(
        "<uuid:organization_id>/videos/<int:video_id>/detections/",
        DetectionRunListCreateView.as_view(),
        name="detection-runs",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/detections/<int:run_id>/",
        DetectionRunDetailView.as_view(),
        name="detection-run-detail",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/detections/<int:run_id>/frames/",
        DetectionFrameListView.as_view(),
        name="detection-frames",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/detections/<int:run_id>/frames/<int:detection_frame_id>/image/",
        DetectionFrameImageView.as_view(),
        name="detection-frame-image",
    ),

    # AEGISVISION OBJECT TRACKING URLS
    path(
        "<uuid:organization_id>/videos/<int:video_id>/detections/<int:run_id>/tracking/",
        TrackingRunListCreateView.as_view(),
        name="tracking-runs",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/detections/<int:run_id>/tracking/<int:tracking_id>/",
        TrackingRunDetailView.as_view(),
        name="tracking-run-detail",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/detections/<int:run_id>/tracking/<int:tracking_id>/tracks/",
        ObjectTrackListView.as_view(),
        name="tracking-tracks",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/detections/<int:run_id>/tracking/<int:tracking_id>/tracks/<int:track_id>/",
        ObjectTrackDetailView.as_view(),
        name="tracking-track-detail",
    ),

    # AEGISVISION SECURITY EVENT / ANALYTICS URLS
    path(
        "<uuid:organization_id>/videos/<int:video_id>/event-rules/",
        EventRuleListCreateView.as_view(),
        name="event-rules",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/event-rules/<int:rule_id>/",
        EventRuleDetailView.as_view(),
        name="event-rule-detail",
    ),
    path(
        "<uuid:organization_id>/videos/<int:video_id>/event-analysis/",
        EventAnalysisView.as_view(),
        name="event-analysis",
    ),
    path(
        "<uuid:organization_id>/events/",
        OrganizationEventListView.as_view(),
        name="security-events",
    ),
    path(
        "<uuid:organization_id>/events/<int:event_id>/",
        SecurityEventStatusView.as_view(),
        name="security-event-status",
    ),
    # AEGISVISION SECURITY OPERATIONS CENTER (SOC) URLS
    path(
        "<uuid:organization_id>/soc/dashboard/",
        SOCDashboardView.as_view(),
        name="soc-dashboard",
    ),
    path(
        "<uuid:organization_id>/soc/events/",
        SOCEventListView.as_view(),
        name="soc-events",
    ),
    path(
        "<uuid:organization_id>/soc/events/export.csv",
        SOCExportCSVView.as_view(),
        name="soc-events-export",
    ),
    path(
        "<uuid:organization_id>/soc/assignees/",
        SOCAssigneesView.as_view(),
        name="soc-assignees",
    ),
    path(
        "<uuid:organization_id>/events/<int:event_id>/activity/",
        SecurityEventActivityView.as_view(),
        name="security-event-activity",
    ),
]