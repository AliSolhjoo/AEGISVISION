from __future__ import annotations

import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import ObjectTrack, TrackingRun, TrackObservation

from apps.organizations.cameras.tracking_video_render import (
    interpolate_track_observation,
    scale_box,
    track_color,
)


class Command(BaseCommand):
    help = (
        "Render a completed tracking run onto its original source video, "
        "including interpolated boxes and Track IDs."
    )

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Output MP4 path. Default: BASE_DIR/tracking_exports/tracking_run_ID.mp4",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace an existing MP4/JSON export.",
        )

    def handle(self, *args, **options):
        run_id = options["run_id"]
        try:
            run = TrackingRun.objects.select_related(
                "detection_run", "detection_run__asset"
            ).get(pk=run_id)
        except TrackingRun.DoesNotExist as exc:
            raise CommandError(f"TrackingRun {run_id} was not found.") from exc

        if run.status != TrackingRun.Status.COMPLETED:
            raise CommandError(
                f"TrackingRun {run_id} must be completed first (status={run.status})."
            )

        asset = run.detection_run.asset
        if not asset.source_file:
            raise CommandError("The source video file is missing from this VideoAsset.")
        try:
            source_path = Path(asset.source_file.path)
        except (AttributeError, NotImplementedError, ValueError) as exc:
            raise CommandError(
                "The configured storage does not expose a local source-video path."
            ) from exc
        if not source_path.is_file():
            raise CommandError(f"Source video was not found: {source_path}")

        track_rows = list(
            ObjectTrack.objects.filter(tracking_run=run).order_by("track_number", "id")
        )
        # A completed detector run may legitimately contain zero objects.
        # Still export a playable copy of the source with the AEGISVISION HUD.
        tracks = []
        observation_total = 0
        for track in track_rows:
            rows = list(
                TrackObservation.objects.filter(track=track)
                .select_related("source_frame")
                .order_by("frame_number", "id")
            )
            if not rows:
                continue

            sample_width = int(rows[0].source_frame.width or 0)
            sample_height = int(rows[0].source_frame.height or 0)
            if sample_width <= 0 or sample_height <= 0:
                raise CommandError(
                    f"Track {track.track_number} references a frame with invalid dimensions."
                )

            points = []
            for row in rows:
                box = row.bounding_box
                if not isinstance(box, (list, tuple)) or len(box) != 4:
                    continue
                try:
                    numeric_box = [float(value) for value in box]
                    timestamp = float(row.timestamp_seconds)
                    confidence = float(row.confidence)
                except (TypeError, ValueError, OverflowError):
                    continue
                points.append(
                    {
                        "frame_number": int(row.frame_number),
                        "timestamp_seconds": timestamp,
                        "confidence": confidence,
                        "bounding_box": numeric_box,
                    }
                )
            if not points:
                continue

            tracks.append(
                {
                    "track_number": int(track.track_number),
                    "label": str(track.label),
                    "observations": points,
                    "sample_width": sample_width,
                    "sample_height": sample_height,
                    "observations_count": len(points),
                }
            )
            observation_total += len(points)

        if not tracks:
            self.stdout.write(self.style.WARNING(
                "No valid track observations were found; exporting the source video without object boxes."
            ))

        if options["output"]:
            output_path = Path(options["output"]).expanduser()
            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path
        else:
            output_path = (
                Path(settings.BASE_DIR)
                / "tracking_exports"
                / f"tracking_run_{run.pk}.mp4"
            )
        output_path = output_path.resolve()
        metadata_path = output_path.with_suffix(".json")

        if not options["overwrite"] and (output_path.exists() or metadata_path.exists()):
            raise CommandError(
                f"Export already exists: {output_path}. Use --overwrite to replace it."
            )

        try:
            import cv2
        except ImportError as exc:
            raise CommandError(
                "OpenCV is required. Install the project's requirements before exporting."
            ) from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_video = output_path.with_name(output_path.stem + ".partial" + output_path.suffix)
        temp_json = metadata_path.with_name(metadata_path.name + ".partial")
        for temporary in (temp_video, temp_json):
            if temporary.exists():
                temporary.unlink()

        capture = cv2.VideoCapture(str(source_path))
        if not capture.isOpened():
            raise CommandError("OpenCV could not open the source video.")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if fps <= 0 or width <= 0 or height <= 0:
            capture.release()
            raise CommandError("The source video has invalid FPS or dimensions.")

        writer = cv2.VideoWriter(
            str(temp_video),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            capture.release()
            writer.release()
            raise CommandError(
                "OpenCV could not initialize the MP4 writer (mp4v codec)."
            )

        frame_index = 0
        frames_with_overlay = 0
        max_gap_frames = int(run.max_gap_frames)
        font = cv2.FONT_HERSHEY_SIMPLEX

        try:
            while True:
                ok, frame = capture.read()
                if not ok or frame is None:
                    break

                timestamp = frame_index / fps
                frame_height, frame_width = frame.shape[:2]
                drew_any = False

                for track in tracks:
                    match = interpolate_track_observation(
                        track["observations"],
                        timestamp,
                        fps,
                        max_gap_frames,
                    )
                    if match is None:
                        continue

                    box, confidence = match
                    scale_x = frame_width / track["sample_width"]
                    scale_y = frame_height / track["sample_height"]
                    x1, y1, x2, y2 = scale_box(box, scale_x, scale_y)

                    x1 = max(0, min(frame_width - 1, int(round(x1))))
                    y1 = max(0, min(frame_height - 1, int(round(y1))))
                    x2 = max(0, min(frame_width - 1, int(round(x2))))
                    y2 = max(0, min(frame_height - 1, int(round(y2))))
                    if x2 <= x1 or y2 <= y1:
                        continue

                    color = track_color(track["track_number"])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    label = (
                        f"{track['label']} ID:{track['track_number']} "
                        f"{confidence * 100:.1f}%"
                    )
                    (text_width, text_height), baseline = cv2.getTextSize(
                        label, font, 0.55, 2
                    )
                    label_top = max(0, y1 - text_height - baseline - 7)
                    label_bottom = label_top + text_height + baseline + 7
                    label_right = min(frame_width - 1, x1 + text_width + 8)
                    cv2.rectangle(
                        frame,
                        (x1, label_top),
                        (label_right, label_bottom),
                        color,
                        -1,
                    )
                    cv2.putText(
                        frame,
                        label,
                        (x1 + 4, label_bottom - baseline - 3),
                        font,
                        0.55,
                        (0, 0, 0),
                        2,
                        cv2.LINE_AA,
                    )
                    drew_any = True

                # Small timestamp/run marker for quick review.
                hud = f"AEGISVISION | SORT run #{run.pk} | {timestamp:06.2f}s"
                cv2.putText(
                    frame,
                    hud,
                    (12, 25),
                    font,
                    0.6,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                writer.write(frame)
                if drew_any:
                    frames_with_overlay += 1
                frame_index += 1
        except Exception:
            capture.release()
            writer.release()
            if temp_video.exists():
                temp_video.unlink()
            raise
        finally:
            capture.release()
            writer.release()

        if frame_index == 0 or not temp_video.is_file() or temp_video.stat().st_size == 0:
            if temp_video.exists():
                temp_video.unlink()
            raise CommandError("No video frames were written; export was not created.")

        summary = {
            "tracking_run_id": run.pk,
            "tracker_name": run.tracker_name,
            "source_asset_id": asset.pk,
            "source_video": str(source_path),
            "output_video": str(output_path),
            "fps": fps,
            "width": width,
            "height": height,
            "source_frame_count_metadata": source_frame_count,
            "frames_written": frame_index,
            "frames_with_tracking_overlay": frames_with_overlay,
            "tracks_rendered": len(tracks),
            "observations_rendered": observation_total,
            "max_gap_frames_for_interpolation": max_gap_frames,
            "audio": "not copied by OpenCV VideoWriter",
            "tracks": [
                {
                    "track_number": track["track_number"],
                    "label": track["label"],
                    "observations_count": track["observations_count"],
                    "first_timestamp_seconds": track["observations"][0]["timestamp_seconds"],
                    "last_timestamp_seconds": track["observations"][-1]["timestamp_seconds"],
                }
                for track in tracks
            ],
        }

        try:
            temp_json.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp_video, output_path)
            os.replace(temp_json, metadata_path)
        except Exception:
            for temporary in (temp_video, temp_json):
                if temporary.exists():
                    temporary.unlink()
            raise

        self.stdout.write(self.style.SUCCESS("Tracking video export completed."))
        self.stdout.write(f"Video: {output_path}")
        self.stdout.write(f"Metadata: {metadata_path}")
        self.stdout.write(f"Frames written: {frame_index}")
        self.stdout.write(f"Frames with overlays: {frames_with_overlay}")
        self.stdout.write(f"Tracks rendered: {len(tracks)}")
        self.stdout.write(
            self.style.WARNING(
                "Note: OpenCV export does not copy the source video's audio."
            )
        )
