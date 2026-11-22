from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import TrackingRun, ObjectTrack, TrackObservation
from apps.organizations.cameras.video_analytics import (
    AnalyticsConfigError,
    analyze_tracking_data,
)


class Command(BaseCommand):
    help = "Create an analytics report (zone intrusion, line crossing, loitering) for a completed tracking run."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)
        parser.add_argument("--config", type=str, required=True, help="Path to the analytics rules JSON file.")
        parser.add_argument("--output", type=str, default=None, help="Output JSON path. Default: BASE_DIR/tracking_exports/analytics_run_ID.json")

    def handle(self, *args, **options):
        run_id = options["run_id"]
        try:
            run = TrackingRun.objects.get(pk=run_id)
        except TrackingRun.DoesNotExist as exc:
            raise CommandError(f"TrackingRun {run_id} was not found.") from exc
        if run.status != TrackingRun.Status.COMPLETED:
            raise CommandError(f"TrackingRun {run_id} must be completed (status={run.status}).")

        config_path = Path(options["config"]).expanduser()
        if not config_path.is_absolute():
            config_path = Path.cwd() / config_path
        if not config_path.is_file():
            raise CommandError(f"Analytics config file was not found: {config_path}")
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read analytics config: {exc}") from exc

        track_rows = list(ObjectTrack.objects.filter(tracking_run=run).order_by("track_number", "id"))
        serialized_tracks = []
        for track in track_rows:
            observations = TrackObservation.objects.filter(track=track).select_related("source_frame").order_by("timestamp_seconds", "frame_number", "id")
            serialized_observations = []
            for observation in observations:
                frame = observation.source_frame
                serialized_observations.append({
                    "frame_number": int(observation.frame_number),
                    "timestamp_seconds": float(observation.timestamp_seconds),
                    "confidence": float(observation.confidence),
                    "bounding_box": observation.bounding_box,
                    "width": int(frame.width),
                    "height": int(frame.height),
                })
            serialized_tracks.append({
                "track_number": int(track.track_number),
                "label": str(track.label),
                "observations": serialized_observations,
            })

        try:
            report = analyze_tracking_data(serialized_tracks, config)
        except (AnalyticsConfigError, TypeError, ValueError) as exc:
            raise CommandError(f"Invalid analytics input: {exc}") from exc

        report["tracking_run"] = {
            "id": run.pk,
            "tracker_name": run.tracker_name,
            "detection_run_id": run.detection_run_id,
            "frames_processed": run.frames_processed,
            "tracks_count": run.tracks_count,
            "observations_count": run.observations_count,
        }
        report["source_asset_id"] = run.detection_run.asset_id
        report["config_file"] = str(config_path)

        if options["output"]:
            output_path = Path(options["output"]).expanduser()
            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path
        else:
            output_path = Path(settings.BASE_DIR) / "tracking_exports" / f"analytics_run_{run.pk}.json"
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_name(output_path.name + ".partial")
        try:
            temp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(output_path)
        except OSError as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise CommandError(f"Could not write analytics report: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(
            f"Analytics completed | run={run.pk} | tracks={report['summary']['unique_tracks']} | "
            f"events={report['event_summary']['total_events']}"
        ))
        self.stdout.write(f"Report: {output_path}")
