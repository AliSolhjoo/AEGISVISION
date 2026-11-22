from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.organizations.cameras.video_models import VideoAsset, VideoProcessingJob
from apps.organizations.cameras.video_services import process_video_job


class Command(BaseCommand):
    help = "Process queued AEGISVISION video uploads and extract sampled frames."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=1,
            help="Maximum number of queued jobs to process (default: 1).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1 or limit > 100:
            raise CommandError("--limit must be between 1 and 100.")

        processed = 0
        while processed < limit:
            with transaction.atomic():
                job = (
                    VideoProcessingJob.objects.select_for_update()
                    .select_related("asset")
                    .filter(status=VideoProcessingJob.Status.QUEUED)
                    .order_by("created_at", "id")
                    .first()
                )
                if job is None:
                    break
                now = timezone.now()
                job.status = VideoProcessingJob.Status.PROCESSING
                job.started_at = now
                job.error_message = ""
                job.save(update_fields=["status", "started_at", "error_message", "updated_at"])
                VideoAsset.objects.filter(pk=job.asset_id).update(
                    status=VideoAsset.Status.PROCESSING,
                    updated_at=now,
                )

            result = process_video_job(job.pk)
            processed += 1
            if result.status == VideoProcessingJob.Status.COMPLETED:
                self.stdout.write(self.style.SUCCESS(
                    f"Completed job {result.pk}: {result.frame_count} frames extracted."
                ))
            else:
                self.stderr.write(self.style.ERROR(
                    f"Failed job {result.pk}: {result.error_message}"
                ))

        if processed == 0:
            self.stdout.write("No queued video jobs found.")
        else:
            self.stdout.write(f"Processed {processed} video job(s).")
