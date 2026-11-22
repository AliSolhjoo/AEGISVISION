from __future__ import annotations

from datetime import timedelta

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Membership
from apps.organizations.permissions import CanAcknowledgeEvents, CanManageCameras
from .live_models import (
    CameraLiveEvent,
    CameraLiveEventActivity,
    CameraLiveState,
    CameraWorkerHeartbeat,
)
from .models import Camera
from .permissions import CanViewCameras


def _camera_for_view(view, camera_id):
    return get_object_or_404(
        Camera.objects.select_related("organization"),
        pk=camera_id,
        organization=view.organization,
    )


def _worker_online():
    heartbeat = CameraWorkerHeartbeat.objects.filter(pk=1).first()
    if not heartbeat or not heartbeat.process_id or not heartbeat.last_heartbeat:
        return False, heartbeat
    age = (timezone.now() - heartbeat.last_heartbeat).total_seconds()
    if age > 15:
        return False, heartbeat
    try:
        import os
        if os.name == "nt":
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {heartbeat.process_id}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return f'"{heartbeat.process_id}"' in result.stdout, heartbeat
        os.kill(int(heartbeat.process_id), 0)
        return True, heartbeat
    except Exception:
        return False, heartbeat


def _state_payload(camera, state, worker_online):
    state = state or CameraLiveState(camera=camera)
    return {
        "camera_id": camera.pk,
        "camera_name": camera.name,
        "status": state.status,
        "is_requested": state.is_requested,
        "worker_online": worker_online,
        "session_id": str(state.session_id),
        "frame_number": state.frame_number,
        "frames_processed": state.frames_processed,
        "objects_count": state.objects_count,
        "tracks_count": state.tracks_count,
        "fps_actual": state.fps_actual,
        "width": state.width,
        "height": state.height,
        "latest_detections": state.latest_detections or [],
        "last_error": state.last_error,
        "session_started_at": state.session_started_at,
        "last_frame_at": state.last_frame_at,
        "last_inference_at": state.last_inference_at,
        "snapshot_available": bool(state.latest_frame),
        "updated_at": state.updated_at,
    }


def _event_payload(event):
    return {
        "id": event.pk,
        "camera_id": event.camera_id,
        "camera_name": event.camera.name,
        "rule_id": event.rule_id,
        "rule_name": event.rule_name,
        "event_type": event.event_type,
        "track_number": event.track_number,
        "label": event.label,
        "timestamp_seconds": event.timestamp_seconds,
        "frame_number": event.frame_number,
        "confidence": event.confidence,
        "details": event.details,
        "severity": event.severity,
        "status": event.status,
        "assigned_to_id": event.assigned_to_id,
        "assigned_to": ({
            "id": event.assigned_to_id,
            "email": event.assigned_to.email,
            "full_name": event.assigned_to.full_name or event.assigned_to.email,
        } if event.assigned_to_id else None),
        "occurred_at": event.occurred_at,
        "created_at": event.created_at,
    }


class LiveWorkerHealthView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id):
        online, heartbeat = _worker_online()
        cameras = CameraLiveState.objects.filter(
            camera__organization=self.organization,
            camera__is_enabled=True,
        )
        return Response({
            "online": online,
            "process_id": heartbeat.process_id if heartbeat else None,
            "last_heartbeat": heartbeat.last_heartbeat if heartbeat else None,
            "total": cameras.count(),
            "online_cameras": cameras.filter(status=CameraLiveState.Status.ONLINE).count(),
            "requested_cameras": cameras.filter(is_requested=True).count(),
        })


class CameraConnectionTestView(APIView):
    permission_classes = [CanManageCameras]

    def post(self, request, organization_id, camera_id):
        camera = _camera_for_view(self, camera_id)
        if camera.source_type == Camera.SourceType.BROWSER:
            return Response({
                "ok": False,
                "detail": "Browser camera sources are captured by the browser and cannot be tested by the server RTSP probe.",
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            import cv2
            from .live_stream_services import _open_capture
            stream_url = camera.build_connection_url()
            capture = _open_capture(cv2, stream_url)
            try:
                if not capture.isOpened():
                    return Response({
                        "ok": False,
                        "detail": "RTSP connection failed. Verify the camera IP, stream path, credentials and LAN reachability.",
                    }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
                ok, frame = capture.read()
                if not ok or frame is None:
                    return Response({
                        "ok": False,
                        "detail": "The stream opened but no video frame could be read.",
                    }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
                height, width = frame.shape[:2]
                fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
                Camera.objects.filter(pk=camera.pk).update(
                    status=Camera.Status.ONLINE,
                    last_seen_at=timezone.now(),
                    updated_at=timezone.now(),
                )
                return Response({
                    "ok": True,
                    "width": width,
                    "height": height,
                    "fps": round(fps, 2) if fps > 0 else None,
                    "detail": "RTSP stream connected and a frame was received.",
                })
            finally:
                capture.release()
        except Exception as exc:
            # Never return or log the internal URL because it can contain credentials.
            return Response({
                "ok": False,
                "detail": str(exc)[:300] if exc.__class__.__name__ == "RuntimeError" else "The RTSP connection test failed. Verify OpenCV FFmpeg support and camera settings.",
            }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)


class CameraLiveStateView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, camera_id):
        camera = _camera_for_view(self, camera_id)
        state = CameraLiveState.objects.filter(camera=camera).first()
        worker_online, _ = _worker_online()
        return Response(_state_payload(camera, state, worker_online))


class CameraLiveStartView(APIView):
    permission_classes = [CanManageCameras]

    def post(self, request, organization_id, camera_id):
        camera = _camera_for_view(self, camera_id)
        if not camera.is_enabled:
            return Response({"detail": "Disabled cameras cannot be started."}, status=status.HTTP_409_CONFLICT)
        if camera.source_type == Camera.SourceType.BROWSER:
            return Response({"detail": "Browser cameras do not provide a server-side RTSP stream. Use an RTSP/RTSPS source for server-side AI processing."}, status=status.HTTP_400_BAD_REQUEST)
        online, _ = _worker_online()
        if not online:
            return Response({
                "detail": "The background live-camera worker is not running. Restart AEGISVISION with Start_AEGISVISION.bat.",
                "worker_online": False,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        state, _ = CameraLiveState.objects.get_or_create(camera=camera)
        if state.is_requested and state.status in {CameraLiveState.Status.STARTING, CameraLiveState.Status.ONLINE, CameraLiveState.Status.RECONNECTING}:
            return Response(_state_payload(camera, state, online), status=status.HTTP_200_OK)
        state.is_requested = True
        state.status = CameraLiveState.Status.STARTING
        state.last_error = ""
        state.save(update_fields=["is_requested", "status", "last_error", "updated_at"])
        Camera.objects.filter(pk=camera.pk).update(status=Camera.Status.PENDING, updated_at=timezone.now())
        return Response(_state_payload(camera, state, online), status=status.HTTP_202_ACCEPTED)


class CameraLiveStopView(APIView):
    permission_classes = [CanManageCameras]

    def post(self, request, organization_id, camera_id):
        camera = _camera_for_view(self, camera_id)
        state = CameraLiveState.objects.filter(camera=camera).first()
        if state:
            state.is_requested = False
            state.status = CameraLiveState.Status.STOPPED
            state.save(update_fields=["is_requested", "status", "updated_at"])
        Camera.objects.filter(pk=camera.pk).update(
            status=Camera.Status.OFFLINE if camera.is_enabled else Camera.Status.DISABLED,
            updated_at=timezone.now(),
        )
        return Response({"camera_id": camera.pk, "status": "stopped"}, status=status.HTTP_202_ACCEPTED)


class CameraLiveSnapshotView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, camera_id):
        camera = _camera_for_view(self, camera_id)
        state = CameraLiveState.objects.filter(camera=camera).first()
        if not state or not state.latest_frame:
            return Response({"detail": "No live frame is available yet."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(state.latest_frame.open("rb"), content_type="image/jpeg")
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class CameraLiveEventListView(APIView):
    permission_classes = [CanViewCameras]

    def get(self, request, organization_id, camera_id):
        camera = _camera_for_view(self, camera_id)
        events = CameraLiveEvent.objects.filter(
            organization=self.organization,
            camera=camera,
        ).select_related("camera", "assigned_to")[:100]
        return Response([_event_payload(event) for event in events])


class CameraLiveEventStatusView(APIView):
    def get_permissions(self):
        permission = CanViewCameras if self.request.method == "GET" else CanAcknowledgeEvents
        return [permission()]

    def patch(self, request, organization_id, camera_id, event_id):
        camera = _camera_for_view(self, camera_id)
        event = get_object_or_404(
            CameraLiveEvent.objects.select_related("camera", "assigned_to"),
            pk=event_id,
            camera=camera,
            organization=self.organization,
        )
        new_status = str(request.data.get("status", event.status)).strip()
        valid = {value for value, _ in CameraLiveEvent.Status.choices}
        if new_status not in valid:
            return Response({"status": "Invalid event status."}, status=status.HTTP_400_BAD_REQUEST)
        old_status = event.status
        if new_status != old_status:
            event.status = new_status
            if new_status == CameraLiveEvent.Status.ACKNOWLEDGED:
                event.acknowledged_by = request.user
                event.acknowledged_at = timezone.now()
            if new_status == CameraLiveEvent.Status.RESOLVED:
                event.resolved_by = request.user
                event.resolved_at = timezone.now()
            event.save(update_fields=["status", "acknowledged_by", "acknowledged_at", "resolved_by", "resolved_at", "updated_at"])
            CameraLiveEventActivity.objects.create(
                organization=self.organization,
                event=event,
                actor=request.user,
                action=CameraLiveEventActivity.Action.STATUS_CHANGED,
                from_status=old_status,
                to_status=new_status,
            )
        return Response(_event_payload(event))


class CameraLiveRuleListCreateView(APIView):
    def get_permissions(self):
        from apps.organizations.permissions import CanManageEventRules, CanViewAnalytics
        permission = CanViewAnalytics if self.request.method == "GET" else CanManageEventRules
        return [permission()]

    def get(self, request, organization_id, camera_id):
        from .event_models import AnalyticsRule
        from .event_views import _rule_payload
        camera = _camera_for_view(self, camera_id)
        rules = AnalyticsRule.objects.filter(
            organization=self.organization,
            camera=camera,
        ).order_by("-created_at", "-id")
        return Response([_rule_payload(rule) for rule in rules])

    def post(self, request, organization_id, camera_id):
        from .event_models import AnalyticsRule
        from .event_views import _clean_rule_payload, _rule_payload
        from .video_analytics import AnalyticsConfigError
        camera = _camera_for_view(self, camera_id)
        payload = request.data.copy()
        payload["scope"] = "camera"
        try:
            clean = _clean_rule_payload(payload)
        except (AnalyticsConfigError, TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        clean.pop("scope", None)
        rule = AnalyticsRule.objects.create(
            organization=self.organization,
            camera=camera,
            asset=None,
            created_by=request.user,
            **clean,
        )
        return Response(_rule_payload(rule), status=status.HTTP_201_CREATED)


class CameraLiveRuleDetailView(APIView):
    def get_permissions(self):
        from apps.organizations.permissions import CanManageEventRules, CanViewAnalytics
        permission = CanViewAnalytics if self.request.method == "GET" else CanManageEventRules
        return [permission()]

    def get_rule(self, camera, rule_id):
        from .event_models import AnalyticsRule
        return get_object_or_404(
            AnalyticsRule.objects.filter(organization=self.organization, camera=camera),
            pk=rule_id,
        )

    def get(self, request, organization_id, camera_id, rule_id):
        from .event_views import _rule_payload
        camera = _camera_for_view(self, camera_id)
        return Response(_rule_payload(self.get_rule(camera, rule_id)))

    def patch(self, request, organization_id, camera_id, rule_id):
        from .event_views import _clean_rule_payload, _rule_payload
        from .video_analytics import AnalyticsConfigError
        camera = _camera_for_view(self, camera_id)
        rule = self.get_rule(camera, rule_id)
        current = _rule_payload(rule)
        current.update(request.data)
        current["scope"] = "camera"
        try:
            clean = _clean_rule_payload(current)
        except (AnalyticsConfigError, TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        clean.pop("scope", None)
        for field, value in clean.items():
            setattr(rule, field, value)
        rule.save()
        return Response(_rule_payload(rule))

    def delete(self, request, organization_id, camera_id, rule_id):
        camera = _camera_for_view(self, camera_id)
        rule = self.get_rule(camera, rule_id)
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
