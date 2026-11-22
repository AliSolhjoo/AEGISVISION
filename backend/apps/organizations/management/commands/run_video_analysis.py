from __future__ import annotations

import traceback

from django.db.models import Q

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.organizations.models import (
    DetectionRun,
    TrackingRun,
    VideoAsset,
    VideoProcessingJob,
    AnalyticsRule,
)
from apps.organizations.cameras.video_services import process_video_job
from apps.organizations.cameras.detection_services import process_detection_run
from apps.organizations.cameras.tracking_services import process_tracking_run
from apps.organizations.cameras.video_analysis_workflow import write_state


class Command(BaseCommand):
    help = "Run the complete AEGISVISION video pipeline in the background."

    def add_arguments(self, parser):
        parser.add_argument("--asset-id", type=int, required=True)

    def handle(self, *args, **options):
        asset_id = options["asset_id"]
        asset = VideoAsset.objects.select_related("organization", "uploaded_by").get(pk=asset_id)
        job = VideoProcessingJob.objects.get(asset=asset)

        try:
            write_state(asset_id, phase="extracting", status="processing")
            job = process_video_job(job.pk)
            if job.status != VideoProcessingJob.Status.COMPLETED:
                raise RuntimeError(job.error_message or "استخراج فریم‌ها ناموفق بود.")

            # Keep the asset in PROCESSING until detection, tracking and rendering finish.
            VideoAsset.objects.filter(pk=asset.pk).update(
                status=VideoAsset.Status.PROCESSING,
                updated_at=timezone.now(),
            )

            write_state(asset_id, phase="detecting", status="processing")
            detection = DetectionRun.objects.create(
                asset=asset,
                created_by=asset.uploaded_by,
                confidence_threshold=0.55,
                max_frames=300,
                requested_device="auto",
            )
            write_state(
                asset_id,
                phase="detecting",
                status="processing",
                detection_run_id=detection.pk,
            )
            # Process only this run. Never consume another organization's queued runs.
            detection = process_detection_run(detection.pk)
            if detection.status != DetectionRun.Status.COMPLETED:
                raise RuntimeError(detection.error_message or f"DetectionRun {detection.pk} با موفقیت تمام نشد.")

            write_state(
                asset_id,
                phase="tracking",
                status="processing",
                detection_run_id=detection.pk,
                detections_count=detection.detections_count,
                frames_detected=detection.frames_processed,
            )
            tracking = TrackingRun.objects.create(
                detection_run=detection,
                created_by=asset.uploaded_by,
                tracker_name="sort_v1",
                iou_threshold=0.30,
                max_gap_frames=2,
                error_message="",
            )
            write_state(
                asset_id,
                phase="tracking",
                status="processing",
                detection_run_id=detection.pk,
                tracking_run_id=tracking.pk,
                detections_count=detection.detections_count,
            )
            tracking = process_tracking_run(tracking.pk)
            if tracking.status != TrackingRun.Status.COMPLETED:
                raise RuntimeError(tracking.error_message or f"TrackingRun {tracking.pk} با موفقیت تمام نشد.")

            # Evaluate configured security rules automatically after SORT.
            # Event evaluation is additive: a malformed optional rule must not
            # invalidate the core detection/tracking output.
            events_count = 0
            event_analysis_error = ""
            rule_scope = Q(asset=asset)
            if asset.camera_id:
                rule_scope |= Q(camera_id=asset.camera_id)
            active_rules = AnalyticsRule.objects.filter(
                organization=asset.organization,
                is_active=True,
            ).filter(rule_scope)
            write_state(
                asset_id,
                phase="event_analysis",
                status="processing",
                detection_run_id=detection.pk,
                tracking_run_id=tracking.pk,
                detections_count=detection.detections_count,
                tracks_count=tracking.tracks_count,
                observations_count=tracking.observations_count,
            )
            if active_rules.exists():
                try:
                    from apps.organizations.cameras.event_services import evaluate_tracking_run
                    event_report = evaluate_tracking_run(tracking, rules=list(active_rules))
                    events_count = event_report["event_summary"]["total_events"]
                except Exception as event_exc:
                    event_analysis_error = str(event_exc)[:500] or event_exc.__class__.__name__

            write_state(
                asset_id,
                phase="rendering",
                status="processing",
                detection_run_id=detection.pk,
                tracking_run_id=tracking.pk,
                detections_count=detection.detections_count,
                tracks_count=tracking.tracks_count,
                observations_count=tracking.observations_count,
                events_count=events_count,
                event_analysis_error=event_analysis_error,
            )
            call_command("export_tracking_video", run_id=tracking.pk, overwrite=True)

            from pathlib import Path
            from django.conf import settings
            output = Path(settings.BASE_DIR) / "tracking_exports" / f"tracking_run_{tracking.pk}.mp4"
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("ویدئوی خروجی ساخته نشد.")

            VideoAsset.objects.filter(pk=asset.pk).update(
                status=VideoAsset.Status.COMPLETED,
                updated_at=timezone.now(),
            )
            write_state(
                asset_id,
                phase="completed",
                status="completed",
                detection_run_id=detection.pk,
                tracking_run_id=tracking.pk,
                detections_count=detection.detections_count,
                tracks_count=tracking.tracks_count,
                observations_count=tracking.observations_count,
                events_count=events_count,
                event_analysis_error=event_analysis_error,
                output_file=output.name,
            )
            self.stdout.write(self.style.SUCCESS(
                f"Video analysis completed: asset={asset_id}, detection={detection.pk}, tracking={tracking.pk}"
            ))
        except Exception as exc:
            message = str(exc)[:1000] or exc.__class__.__name__
            VideoAsset.objects.filter(pk=asset.pk).update(
                status=VideoAsset.Status.FAILED,
                updated_at=timezone.now(),
            )
            VideoProcessingJob.objects.filter(pk=job.pk).update(
                error_message=message,
                updated_at=timezone.now(),
            )
            write_state(
                asset_id,
                phase="failed",
                status="failed",
                error=message,
                traceback=traceback.format_exc()[-6000:],
            )
            self.stderr.write(self.style.ERROR(f"Video analysis failed for asset {asset_id}: {message}"))
            raise
