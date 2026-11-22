from __future__ import annotations

import csv
from datetime import date, timedelta
from io import StringIO

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Membership
from apps.organizations.permissions import CanViewAnalytics
from .event_models import SecurityEvent
from .event_views import _event_payload


OPEN_STATUSES = [
    SecurityEvent.Status.NEW,
    SecurityEvent.Status.ACKNOWLEDGED,
    SecurityEvent.Status.INVESTIGATING,
]
SEVERITY_ORDER = [
    SecurityEvent.Severity.CRITICAL,
    SecurityEvent.Severity.HIGH,
    SecurityEvent.Severity.MEDIUM,
    SecurityEvent.Severity.LOW,
]


def scoped_events(organization):
    return SecurityEvent.objects.filter(organization=organization).select_related(
        "asset", "asset__camera", "rule", "tracking_run", "assigned_to"
    )


def filtered_events(request, organization):
    events = scoped_events(organization)
    params = request.query_params
    status_value = params.get("status")
    severity = params.get("severity")
    camera_id = params.get("camera_id")
    query = (params.get("q") or "").strip()
    date_from = params.get("date_from")
    date_to = params.get("date_to")

    if status_value and status_value != "all":
        events = events.filter(status=status_value)
    if severity and severity != "all":
        events = events.filter(severity=severity)
    if camera_id:
        try:
            events = events.filter(asset__camera_id=int(camera_id))
        except (TypeError, ValueError):
            return events.none()
    if query:
        events = events.filter(
            Q(rule_name__icontains=query)
            | Q(label__icontains=query)
            | Q(asset__name__icontains=query)
            | Q(asset__original_filename__icontains=query)
            | Q(assigned_to__email__icontains=query)
            | Q(asset__camera__name__icontains=query)
        )
    if date_from:
        try:
            date_from = date.fromisoformat(date_from)
        except (TypeError, ValueError):
            return events.none()
        events = events.filter(created_at__date__gte=date_from)
    if date_to:
        try:
            date_to = date.fromisoformat(date_to)
        except (TypeError, ValueError):
            return events.none()
        events = events.filter(created_at__date__lte=date_to)
    return events


class SOCDashboardView(APIView):
    permission_classes = [CanViewAnalytics]

    def get(self, request, organization_id):
        events = scoped_events(self.organization)
        today = timezone.localdate()
        seven_days_ago = today - timedelta(days=6)
        open_events = events.filter(status__in=OPEN_STATUSES)

        severity_counts_raw = dict(
            events.values("severity")
            .annotate(total=Count("id"))
            .values_list("severity", "total")
        )
        status_counts_raw = dict(
            events.values("status")
            .annotate(total=Count("id"))
            .values_list("status", "total")
        )
        trend_raw = {
            item["day"].isoformat(): item["total"]
            for item in events.filter(created_at__date__gte=seven_days_ago)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(total=Count("id"))
            .order_by("day")
        }
        trend = []
        for offset in range(7):
            day = seven_days_ago + timedelta(days=offset)
            trend.append({"date": day.isoformat(), "count": trend_raw.get(day.isoformat(), 0)})

        camera_rows = list(
            events.filter(asset__camera__isnull=False)
            .values("asset__camera_id", "asset__camera__name")
            .annotate(total=Count("id"))
            .order_by("-total", "asset__camera__name")[:6]
        )
        recent = events.order_by("-created_at", "-id")[:10]

        return Response({
            "generated_at": timezone.now(),
            "permissions": {
                "can_manage_events": self.membership.role in {
                    Membership.Role.OWNER,
                    Membership.Role.ADMIN,
                    Membership.Role.OPERATOR,
                },
                "can_export": True,
            },
            "summary": {
                "total_events": events.count(),
                "open_events": open_events.count(),
                "critical_open": open_events.filter(severity=SecurityEvent.Severity.CRITICAL).count(),
                "high_open": open_events.filter(severity=SecurityEvent.Severity.HIGH).count(),
                "new_today": events.filter(status=SecurityEvent.Status.NEW, created_at__date=today).count(),
                "resolved_today": events.filter(status=SecurityEvent.Status.RESOLVED, resolved_at__date=today).count(),
                "unassigned_open": open_events.filter(assigned_to__isnull=True).count(),
                "investigating": events.filter(status=SecurityEvent.Status.INVESTIGATING).count(),
            },
            "by_severity": {key: severity_counts_raw.get(key, 0) for key in SEVERITY_ORDER},
            "by_status": {key: status_counts_raw.get(key, 0) for key, _ in SecurityEvent.Status.choices},
            "trend_7d": trend,
            "top_cameras": [
                {
                    "camera_id": row["asset__camera_id"],
                    "camera_name": row["asset__camera__name"],
                    "events": row["total"],
                }
                for row in camera_rows
            ],
            "recent_events": [_event_payload(item) for item in recent],
        })


class SOCEventListView(APIView):
    permission_classes = [CanViewAnalytics]

    def get(self, request, organization_id):
        events = filtered_events(request, self.organization).order_by("-created_at", "-id")
        total = events.count()
        try:
            limit = min(250, max(1, int(request.query_params.get("limit", 100))))
            offset = max(0, int(request.query_params.get("offset", 0)))
        except (TypeError, ValueError):
            limit, offset = 100, 0
        page = events[offset:offset + limit]
        return Response({
            "count": total,
            "offset": offset,
            "limit": limit,
            "results": [_event_payload(item) for item in page],
        })


class SOCAssigneesView(APIView):
    permission_classes = [CanViewAnalytics]

    def get(self, request, organization_id):
        members = Membership.objects.filter(
            organization=self.organization,
            status=Membership.Status.ACTIVE,
            role__in=[
                Membership.Role.OWNER,
                Membership.Role.ADMIN,
                Membership.Role.OPERATOR,
                Membership.Role.ANALYST,
            ],
            user__is_active=True,
        ).select_related("user").order_by("user__first_name", "user__last_name", "user__email")
        return Response([{
            "id": item.user_id,
            "email": item.user.email,
            "full_name": item.user.full_name or item.user.email,
            "role": item.role,
        } for item in members])


def _safe_csv_cell(value):
    """Prevent spreadsheet formula execution from user-controlled CSV values."""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


class SOCExportCSVView(APIView):
    permission_classes = [CanViewAnalytics]

    def get(self, request, organization_id):
        events = filtered_events(request, self.organization).order_by("-created_at", "-id")[:5000]
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "Event ID", "Created at", "Severity", "Status", "Event type", "Rule",
            "Camera", "Video", "Object", "Track ID", "Timestamp (seconds)",
            "Frame", "Confidence", "Assigned to",
        ])
        for item in events:
            writer.writerow([_safe_csv_cell(value) for value in [
                item.pk,
                item.created_at.isoformat(),
                item.severity,
                item.status,
                item.event_type,
                item.rule_name,
                item.asset.camera.name if item.asset.camera_id else "",
                item.asset.name,
                item.label,
                item.track_number,
                item.timestamp_seconds,
                item.frame_number,
                item.confidence,
                item.assigned_to.email if item.assigned_to_id else "",
            ]])
        response = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="aegisvision_soc_{timezone.localdate().isoformat()}.csv"'
        response["Cache-Control"] = "no-store"
        return response
