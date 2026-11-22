from django.core.management.base import BaseCommand, CommandError

from apps.organizations.cameras.detection_models import DetectionRun
from apps.organizations.cameras.detection_services import process_detection_run


class Command(BaseCommand):
    help = "Run queued AEGISVISION object-detection jobs."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=1)
        parser.add_argument("--run-id", type=int, default=None)

    def handle(self, *args, **options):
        limit = options["limit"]
        run_id = options["run_id"]
        if limit < 1 or limit > 100:
            raise CommandError("--limit must be between 1 and 100.")

        queryset = DetectionRun.objects.filter(status=DetectionRun.Status.QUEUED)
        if run_id is not None:
            queryset = queryset.filter(pk=run_id)
            if not queryset.exists():
                raise CommandError(f"Queued detection run {run_id} was not found.")
            run_ids = list(queryset.values_list("pk", flat=True)[:1])
        else:
            run_ids = list(
                queryset.order_by("created_at", "id").values_list("pk", flat=True)[:limit]
            )

        if not run_ids:
            self.stdout.write(self.style.WARNING("No queued detection runs were found."))
            return

        for current_id in run_ids:
            run = process_detection_run(current_id)
            message = (
                f"Run {run.pk}: {run.status} | "
                f"frames={run.frames_processed} | detections={run.detections_count}"
            )
            if run.status == DetectionRun.Status.COMPLETED:
                self.stdout.write(self.style.SUCCESS(message))
            else:
                self.stdout.write(self.style.ERROR(f"{message} | {run.error_message}"))
