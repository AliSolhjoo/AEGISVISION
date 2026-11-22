from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.permissions import (
    CanAcknowledgeEvents,
    CanManageCameras,
    CanManageEventRules,
    CanViewAnalytics,
)
from .event_models import AnalyticsRule, SecurityEvent, SecurityEventActivity
from .event_services import EventAnalysisError, evaluate_tracking_run
from .tracking_models import TrackingRun
from .video_analytics import AnalyticsConfigError, validate_config
from .video_models import VideoAsset


def _asset_for_view(view, video_id):
    return get_object_or_404(VideoAsset, pk=video_id, organization=view.organization)


def _rule_payload(rule: AnalyticsRule) -> dict:
    return {
        "id": rule.pk,
        "asset_id": rule.asset_id,
        "camera_id": rule.camera_id,
        "scope": "camera" if rule.camera_id else "asset",
        "name": rule.name,
        "rule_type": rule.rule_type,
        "geometry": rule.geometry,
        "labels": rule.labels or [],
        "minimum_confidence": rule.minimum_confidence,
        "anchor": rule.anchor,
        "direction": rule.direction,
        "dwell_seconds": rule.dwell_seconds,
        "is_active": rule.is_active,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _clean_rule_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise AnalyticsConfigError("بدنه درخواست باید یک شیء JSON باشد.")
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 120:
        raise AnalyticsConfigError("نام قانون الزامی است و حداکثر ۱۲۰ نویسه دارد.")

    rule_type = str(data.get("rule_type", "")).strip().lower()
    scope = str(data.get("scope", "asset")).strip().lower()
    if scope not in {"asset", "camera"}:
        raise AnalyticsConfigError("scope must be asset or camera.")
    geometry = data.get("geometry") or {}
    if not isinstance(geometry, dict):
        raise AnalyticsConfigError("هندسه قانون معتبر نیست.")

    raw = {
        "id": "pending-rule",
        "name": name,
        "type": rule_type,
        "enabled": data.get("is_active", True),
        "labels": data.get("labels", []),
        "minimum_confidence": data.get("minimum_confidence", 0.0),
        "anchor": data.get("anchor", "bottom_center"),
    }
    # Only accept geometry keys that belong to the selected rule type.
    if rule_type in {AnalyticsRule.RuleType.ZONE_INTRUSION, AnalyticsRule.RuleType.LOITERING}:
        raw["polygon"] = geometry.get("polygon", data.get("polygon"))
    elif rule_type == AnalyticsRule.RuleType.LINE_CROSSING:
        raw["line"] = geometry.get("line", data.get("line"))
        raw["direction"] = data.get("direction", "both")
    if rule_type == AnalyticsRule.RuleType.LOITERING:
        raw["dwell_seconds"] = data.get("dwell_seconds", 10.0)

    clean = validate_config({"version": 1, "max_observation_gap_seconds": 3.0, "rules": [raw]})["rules"][0]
    clean_geometry = {}
    if rule_type in {AnalyticsRule.RuleType.ZONE_INTRUSION, AnalyticsRule.RuleType.LOITERING}:
        clean_geometry["polygon"] = [[float(x), float(y)] for x, y in clean["polygon"]]
    elif rule_type == AnalyticsRule.RuleType.LINE_CROSSING:
        clean_geometry["line"] = [[float(x), float(y)] for x, y in clean["line"]]

    return {
        "name": name,
        "rule_type": rule_type,
        "scope": scope,
        "geometry": clean_geometry,
        "labels": clean["labels"],
        "minimum_confidence": clean["minimum_confidence"],
        "anchor": clean["anchor"],
        "direction": clean.get("direction", "both"),
        "dwell_seconds": clean.get("dwell_seconds", 10.0),
        "is_active": clean["enabled"],
    }


def _event_payload(event: SecurityEvent) -> dict:
    return {
        "id": event.pk,
        "organization_id": str(event.organization_id),
        "asset_id": event.asset_id,
        "asset_name": event.asset.name,
        "tracking_run_id": event.tracking_run_id,
        "rule_id": event.rule_id,
        "rule_name": event.rule_name,
        "event_type": event.event_type,
        "track_number": event.track_number,
        "label": event.label,
        "timestamp_seconds": event.timestamp_seconds,
        "frame_number": event.frame_number,
        "confidence": event.confidence,
        "details": event.details,
        "status": event.status,
        "severity": event.severity,
        "assigned_to_id": event.assigned_to_id,
        "assigned_to": ({
            "id": event.assigned_to_id,
            "email": event.assigned_to.email,
            "full_name": event.assigned_to.full_name or event.assigned_to.email,
        } if event.assigned_to_id else None),
        "camera_id": event.asset.camera_id,
        "camera_name": event.asset.camera.name if event.asset.camera_id else None,
        "acknowledged_at": event.acknowledged_at,
        "resolved_at": event.resolved_at,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
    }


class EventRuleListCreateView(APIView):
    def get_permissions(self):
        permission = CanViewAnalytics if self.request.method == "GET" else CanManageEventRules
        return [permission()]

    def get(self, request, organization_id, video_id):
        asset = _asset_for_view(self, video_id)
        rule_scope = Q(asset=asset)
        if asset.camera_id:
            rule_scope |= Q(camera_id=asset.camera_id)
        rules = AnalyticsRule.objects.filter(
            organization=self.organization,
        ).filter(rule_scope).order_by("-created_at", "-id")
        return Response([_rule_payload(item) for item in rules])

    def post(self, request, organization_id, video_id):
        asset = _asset_for_view(self, video_id)
        try:
            clean = _clean_rule_payload(request.data)
        except (AnalyticsConfigError, TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        scope = clean.pop("scope")
        if scope == "camera" and not asset.camera_id:
            return Response({"detail": "این ویدئو به دوربین متصل نیست؛ قانون را برای همین ویدئو ذخیره کن."}, status=status.HTTP_400_BAD_REQUEST)
        rule = AnalyticsRule.objects.create(
            organization=self.organization,
            asset=asset if scope == "asset" else None,
            camera=asset.camera if scope == "camera" else None,
            created_by=request.user,
            **clean,
        )
        return Response(_rule_payload(rule), status=status.HTTP_201_CREATED)


class EventRuleDetailView(APIView):
    def get_permissions(self):
        permission = CanViewAnalytics if self.request.method == "GET" else CanManageEventRules
        return [permission()]

    def get_rule(self, organization_id, video_id, rule_id):
        asset = _asset_for_view(self, video_id)
        rule_scope = Q(asset=asset)
        if asset.camera_id:
            rule_scope |= Q(camera_id=asset.camera_id)
        return get_object_or_404(
            AnalyticsRule.objects.filter(organization=self.organization).filter(rule_scope),
            pk=rule_id,
        )

    def get(self, request, organization_id, video_id, rule_id):
        return Response(_rule_payload(self.get_rule(organization_id, video_id, rule_id)))

    def patch(self, request, organization_id, video_id, rule_id):
        rule = self.get_rule(organization_id, video_id, rule_id)
        asset = _asset_for_view(self, video_id)
        current = _rule_payload(rule)
        current.update(request.data)
        try:
            clean = _clean_rule_payload(current)
        except (AnalyticsConfigError, TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        scope = clean.pop("scope")
        if scope == "camera" and not asset.camera_id:
            return Response({"detail": "این ویدئو به دوربین متصل نیست."}, status=status.HTTP_400_BAD_REQUEST)
        rule.asset = asset if scope == "asset" else None
        rule.camera = asset.camera if scope == "camera" else None
        for field, value in clean.items():
            setattr(rule, field, value)
        rule.save()
        return Response(_rule_payload(rule))

    def delete(self, request, organization_id, video_id, rule_id):
        rule = self.get_rule(organization_id, video_id, rule_id)
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventAnalysisView(APIView):
    def get_permissions(self):
        permission = CanViewAnalytics if self.request.method == "GET" else CanManageCameras
        return [permission()]

    def get(self, request, organization_id, video_id):
        asset = _asset_for_view(self, video_id)
        latest_tracking = TrackingRun.objects.filter(
            detection_run__asset=asset,
            status=TrackingRun.Status.COMPLETED,
        ).order_by("-created_at", "-id").first()
        return Response({
            "asset_id": asset.pk,
            "tracking_ready": latest_tracking is not None,
            "tracking_run_id": latest_tracking.pk if latest_tracking else None,
            "tracking_run_status": latest_tracking.status if latest_tracking else None,
            "active_rules_count": AnalyticsRule.objects.filter(
                Q(asset=asset) | (Q(camera_id=asset.camera_id) if asset.camera_id else Q(pk__in=[])),
                organization=self.organization,
                is_active=True,
            ).count(),
            "events_count": SecurityEvent.objects.filter(
                organization=self.organization, asset=asset
            ).count(),
        })

    def post(self, request, organization_id, video_id):
        asset = _asset_for_view(self, video_id)
        requested_run_id = request.data.get("tracking_run_id")
        if requested_run_id not in (None, ""):
            try:
                requested_run_id = int(requested_run_id)
            except (TypeError, ValueError):
                return Response({"detail": "شناسه اجرای رهگیری معتبر نیست."}, status=status.HTTP_400_BAD_REQUEST)
        runs = TrackingRun.objects.filter(
            detection_run__asset=asset,
            detection_run__asset__organization=self.organization,
            status=TrackingRun.Status.COMPLETED,
        )
        if requested_run_id:
            tracking_run = get_object_or_404(runs, pk=requested_run_id)
        else:
            tracking_run = runs.order_by("-created_at", "-id").first()
        if tracking_run is None:
            return Response(
                {"detail": "ابتدا تحلیل و رهگیری ویدئو باید کامل شود."},
                status=status.HTTP_409_CONFLICT,
            )
        rule_scope = Q(asset=asset)
        if asset.camera_id:
            rule_scope |= Q(camera_id=asset.camera_id)
        rules = list(AnalyticsRule.objects.filter(
            organization=self.organization,
            is_active=True,
        ).filter(rule_scope).order_by("id"))
        try:
            report = evaluate_tracking_run(tracking_run, rules=rules)
        except EventAnalysisError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (AnalyticsConfigError, ValueError) as exc:
            return Response({"detail": f"تنظیمات قوانین معتبر نیست: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(report, status=status.HTTP_200_OK)


class OrganizationEventListView(APIView):
    permission_classes = [CanViewAnalytics]

    def get(self, request, organization_id):
        events = SecurityEvent.objects.filter(
            organization=self.organization,
        ).select_related("asset", "asset__camera", "rule", "tracking_run", "assigned_to").order_by("-created_at", "-id")
        video_id = request.query_params.get("video_id")
        event_status = request.query_params.get("status")
        event_type = request.query_params.get("type")
        if video_id:
            try:
                video_id = int(video_id)
            except (TypeError, ValueError):
                return Response({"detail": "شناسه ویدئو معتبر نیست."}, status=status.HTTP_400_BAD_REQUEST)
            events = events.filter(asset_id=video_id)
        if event_status:
            valid = {choice[0] for choice in SecurityEvent.Status.choices}
            if event_status not in valid:
                return Response({"detail": "وضعیت رویداد معتبر نیست."}, status=status.HTTP_400_BAD_REQUEST)
            events = events.filter(status=event_status)
        if event_type:
            events = events.filter(event_type=event_type)
        try:
            limit = min(500, max(1, int(request.query_params.get("limit", 200))))
        except (TypeError, ValueError):
            limit = 200
        return Response([_event_payload(item) for item in events[:limit]])


class SecurityEventStatusView(APIView):
    permission_classes = [CanAcknowledgeEvents]

    def patch(self, request, organization_id, event_id):
        from django.db import transaction
        from apps.organizations.models import Membership

        event = get_object_or_404(
            SecurityEvent.objects.select_related(
                "asset", "asset__camera", "rule", "tracking_run", "assigned_to"
            ),
            pk=event_id,
            organization=self.organization,
        )
        payload = request.data if isinstance(request.data, dict) else {}
        now = timezone.now()
        note = str(payload.get("note", "") or "").strip()
        if len(note) > 2000:
            return Response({"detail": "Note must be 2,000 characters or fewer."}, status=status.HTTP_400_BAD_REQUEST)

        allowed_statuses = {choice[0] for choice in SecurityEvent.Status.choices}
        new_status = payload.get("status", event.status)
        if new_status not in allowed_statuses:
            return Response({"detail": "Invalid event status."}, status=status.HTTP_400_BAD_REQUEST)

        allowed_severities = {choice[0] for choice in SecurityEvent.Severity.choices}
        new_severity = payload.get("severity", event.severity)
        if new_severity not in allowed_severities:
            return Response({"detail": "Invalid event severity."}, status=status.HTTP_400_BAD_REQUEST)

        assigned_to = event.assigned_to
        if "assigned_to_id" in payload:
            requested_assignee = payload.get("assigned_to_id")
            if requested_assignee in (None, ""):
                assigned_to = None
            else:
                try:
                    requested_assignee = int(requested_assignee)
                except (TypeError, ValueError):
                    return Response({"detail": "Invalid assignee."}, status=status.HTTP_400_BAD_REQUEST)
                membership = Membership.objects.filter(
                    organization=self.organization,
                    user_id=requested_assignee,
                    status=Membership.Status.ACTIVE,
                    role__in=[
                        Membership.Role.OWNER,
                        Membership.Role.ADMIN,
                        Membership.Role.OPERATOR,
                        Membership.Role.ANALYST,
                    ],
                    user__is_active=True,
                ).select_related("user").first()
                if membership is None:
                    return Response({"detail": "Assignee must be an active operations member of this workspace."}, status=status.HTTP_400_BAD_REQUEST)
                assigned_to = membership.user

        old_status = event.status
        old_severity = event.severity
        old_assignee = event.assigned_to
        with transaction.atomic():
            event.status = new_status
            event.severity = new_severity
            event.assigned_to = assigned_to
            if new_status == SecurityEvent.Status.NEW:
                event.acknowledged_by = None
                event.acknowledged_at = None
                event.resolved_by = None
                event.resolved_at = None
            elif new_status in {
                SecurityEvent.Status.ACKNOWLEDGED,
                SecurityEvent.Status.INVESTIGATING,
            }:
                if not event.acknowledged_at:
                    event.acknowledged_by = request.user
                    event.acknowledged_at = now
                event.resolved_by = None
                event.resolved_at = None
            elif new_status in {SecurityEvent.Status.RESOLVED, SecurityEvent.Status.FALSE_POSITIVE}:
                if not event.acknowledged_at:
                    event.acknowledged_by = request.user
                    event.acknowledged_at = now
                event.resolved_by = request.user
                event.resolved_at = now

            event.save(update_fields=[
                "status", "severity", "assigned_to", "acknowledged_by", "acknowledged_at",
                "resolved_by", "resolved_at", "updated_at",
            ])

            if old_status != new_status:
                SecurityEventActivity.objects.create(
                    organization=self.organization, event=event, actor=request.user,
                    action=SecurityEventActivity.Action.STATUS_CHANGED,
                    from_status=old_status, to_status=new_status, note=note,
                )
            if old_severity != new_severity:
                SecurityEventActivity.objects.create(
                    organization=self.organization, event=event, actor=request.user,
                    action=SecurityEventActivity.Action.SEVERITY_CHANGED,
                    from_severity=old_severity, to_severity=new_severity,
                )
            if old_assignee_id := (old_assignee.pk if old_assignee else None):
                assignee_changed = old_assignee_id != (assigned_to.pk if assigned_to else None)
            else:
                assignee_changed = assigned_to is not None
            if assignee_changed:
                SecurityEventActivity.objects.create(
                    organization=self.organization, event=event, actor=request.user,
                    action=SecurityEventActivity.Action.ASSIGNED,
                    from_assignee=old_assignee, to_assignee=assigned_to,
                )
            if note and old_status == new_status:
                SecurityEventActivity.objects.create(
                    organization=self.organization, event=event, actor=request.user,
                    action=SecurityEventActivity.Action.COMMENT, note=note,
                )
        event.refresh_from_db()
        event = SecurityEvent.objects.select_related("asset", "asset__camera", "assigned_to").get(pk=event.pk)
        return Response(_event_payload(event))


class SecurityEventActivityView(APIView):
    permission_classes = [CanViewAnalytics]

    def get(self, request, organization_id, event_id):
        event = get_object_or_404(SecurityEvent, pk=event_id, organization=self.organization)
        activities = SecurityEventActivity.objects.filter(
            event=event, organization=self.organization
        ).select_related("actor", "from_assignee", "to_assignee").order_by("created_at", "id")
        results = []
        for item in activities[:250]:
            results.append({
                "id": item.pk,
                "action": item.action,
                "actor": ({"id": item.actor_id, "email": item.actor.email, "full_name": item.actor.full_name or item.actor.email} if item.actor_id else None),
                "from_status": item.from_status,
                "to_status": item.to_status,
                "from_severity": item.from_severity,
                "to_severity": item.to_severity,
                "from_assignee": ({"id": item.from_assignee_id, "full_name": item.from_assignee.full_name or item.from_assignee.email} if item.from_assignee_id else None),
                "to_assignee": ({"id": item.to_assignee_id, "full_name": item.to_assignee.full_name or item.to_assignee.email} if item.to_assignee_id else None),
                "note": item.note,
                "created_at": item.created_at,
            })
        return Response(results)

