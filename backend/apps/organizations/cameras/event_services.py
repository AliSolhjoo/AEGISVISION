from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.db.models import Prefetch
from django.utils import timezone

from .event_models import AnalyticsRule, SecurityEvent, SecurityEventActivity
from .tracking_models import ObjectTrack, TrackObservation, TrackingRun
from .video_analytics import analyze_tracking_data


class EventAnalysisError(Exception):
    """Raised when a tracking run cannot be evaluated against security rules."""


def rule_to_engine_config(rule: AnalyticsRule) -> dict:
    config = {
        "id": str(rule.pk),
        "name": rule.name,
        "type": rule.rule_type,
        "enabled": bool(rule.is_active),
        "labels": rule.labels or [],
        "minimum_confidence": rule.minimum_confidence,
        "anchor": rule.anchor,
    }
    if rule.rule_type in {AnalyticsRule.RuleType.ZONE_INTRUSION, AnalyticsRule.RuleType.LOITERING}:
        config["polygon"] = (rule.geometry or {}).get("polygon", [])
    if rule.rule_type == AnalyticsRule.RuleType.LINE_CROSSING:
        config["line"] = (rule.geometry or {}).get("line", [])
        config["direction"] = rule.direction
    if rule.rule_type == AnalyticsRule.RuleType.LOITERING:
        config["dwell_seconds"] = rule.dwell_seconds
    return config


def build_tracking_payload(tracking_run: TrackingRun) -> list[dict]:
    observation_queryset = TrackObservation.objects.select_related("source_frame").order_by(
        "timestamp_seconds", "frame_number", "id"
    )
    tracks = ObjectTrack.objects.filter(tracking_run=tracking_run).prefetch_related(
        Prefetch("observations", queryset=observation_queryset)
    ).order_by("track_number")

    payload = []
    for track in tracks:
        observations = []
        for observation in track.observations.all():
            frame = observation.source_frame
            if not frame.width or not frame.height:
                continue
            observations.append({
                "frame_number": observation.frame_number,
                "timestamp_seconds": observation.timestamp_seconds,
                "confidence": observation.confidence,
                "bounding_box": observation.bounding_box,
                "width": frame.width,
                "height": frame.height,
            })
        if observations:
            payload.append({
                "track_number": track.track_number,
                "label": track.label,
                "observations": observations,
            })
    return payload


def evaluate_tracking_run(tracking_run: TrackingRun, rules=None) -> dict:
    """Evaluate active rules for one completed run and persist idempotent events.

    Re-evaluation updates/deletes stale generated rows but preserves the status
    and acknowledgement metadata of events whose evidence remains unchanged.
    """
    tracking_run = TrackingRun.objects.select_related(
        "detection_run", "detection_run__asset", "detection_run__asset__organization"
    ).get(pk=tracking_run.pk)
    if tracking_run.status != TrackingRun.Status.COMPLETED:
        raise EventAnalysisError("رهگیری ویدئو باید قبل از تحلیل رویدادها تکمیل شده باشد.")

    asset = tracking_run.detection_run.asset
    if rules is None:
        rule_scope = Q(asset=asset)
        if asset.camera_id:
            rule_scope |= Q(camera_id=asset.camera_id)
        rules = AnalyticsRule.objects.filter(
            organization=asset.organization,
            is_active=True,
        ).filter(rule_scope).order_by("id")
    rules = list(rules)
    if not rules:
        raise EventAnalysisError("برای این ویدئو هنوز هیچ قانون فعالی تعریف نشده است.")

    engine_rules = [rule_to_engine_config(rule) for rule in rules]
    config = {"version": 1, "max_observation_gap_seconds": 3.0, "rules": engine_rules}
    track_payload = build_tracking_payload(tracking_run)
    report = analyze_tracking_data(track_payload, config)
    rules_by_id = {str(rule.pk): rule for rule in rules}
    rule_ids = [rule.pk for rule in rules]

    retained_ids = []
    created_count = 0
    updated_count = 0
    with transaction.atomic():
        existing = list(SecurityEvent.objects.filter(
            tracking_run=tracking_run,
            rule_id__in=rule_ids,
        ))
        existing_by_key = {
            (str(item.rule_id), item.track_number, item.event_type, item.frame_number): item
            for item in existing
        }

        for item in report["events"]:
            rule_key = str(item["rule_id"])
            rule = rules_by_id.get(rule_key)
            if rule is None:
                continue
            key = (rule_key, int(item["track_number"]), item["event_type"], int(item["frame_number"]))
            severity_by_type = {
                AnalyticsRule.RuleType.ZONE_INTRUSION: SecurityEvent.Severity.HIGH,
                AnalyticsRule.RuleType.LINE_CROSSING: SecurityEvent.Severity.MEDIUM,
                AnalyticsRule.RuleType.LOITERING: SecurityEvent.Severity.MEDIUM,
            }
            defaults = {
                "organization": asset.organization,
                "asset": asset,
                "rule": rule,
                "rule_name": rule.name,
                "label": str(item["label"])[:80],
                "timestamp_seconds": float(item["timestamp_seconds"]),
                "confidence": float(item["confidence"]),
                "details": item,
                "updated_at": timezone.now(),
            }
            current = existing_by_key.get(key)
            if current:
                for field, value in defaults.items():
                    setattr(current, field, value)
                current.save(update_fields=list(defaults.keys()))
                retained_ids.append(current.pk)
                updated_count += 1
            else:
                created = SecurityEvent.objects.create(
                    tracking_run=tracking_run,
                    track_number=int(item["track_number"]),
                    event_type=item["event_type"],
                    frame_number=int(item["frame_number"]),
                    status=SecurityEvent.Status.NEW,
                    severity=severity_by_type.get(rule.rule_type, SecurityEvent.Severity.MEDIUM),
                    **defaults,
                )
                SecurityEventActivity.objects.create(
                    organization=asset.organization,
                    event=created,
                    actor=None,
                    action=SecurityEventActivity.Action.CREATED,
                    to_status=created.status,
                    to_severity=created.severity,
                    note="Generated automatically by the video analytics engine.",
                )
                retained_ids.append(created.pk)
                created_count += 1

        stale = SecurityEvent.objects.filter(
            tracking_run=tracking_run,
            rule_id__in=rule_ids,
        )
        if retained_ids:
            stale = stale.exclude(pk__in=retained_ids)
        stale.delete()

    report["persistence"] = {
        "created": created_count,
        "updated": updated_count,
        "total": len(report["events"]),
    }
    report["tracking_run_id"] = tracking_run.pk
    report["asset_id"] = asset.pk
    return report

