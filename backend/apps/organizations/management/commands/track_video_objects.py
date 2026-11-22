from django.core.management.base import BaseCommand, CommandError

from apps.organizations.cameras.tracking_models import TrackingRun
from apps.organizations.cameras.tracking_services import process_tracking_run


class Command(BaseCommand):
    help = "Run queued AEGISVISION object-tracking jobs."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=1)
        parser.add_argument("--run-id", type=int, default=None)

    def handle(self, *args, **options):
        limit = options["limit"]
        run_id = options["run_id"]
        if limit < 1 or limit > 100:
            raise CommandError("--limit must be between 1 and 100.")

        queryset = TrackingRun.objects.filter(status=TrackingRun.Status.QUEUED)
        if run_id is not None:
            queryset = queryset.filter(pk=run_id)
            if not queryset.exists():
                raise CommandError(f"Queued tracking run {run_id} was not found.")
            run_ids = list(queryset.values_list("pk", flat=True)[:1])
        else:
            run_ids = list(
                queryset.order_by("created_at", "id").values_list("pk", flat=True)[:limit]
            )

        if not run_ids:
            self.stdout.write(self.style.WARNING("No queued tracking runs were found."))
            return

        for current_id in run_ids:
            run = process_tracking_run(current_id)
            message = (
                f"Tracking run {run.pk}: {run.status} | "
                f"frames={run.frames_processed} | tracks={run.tracks_count} | "
                f"observations={run.observations_count}"
            )
            if run.status == TrackingRun.Status.COMPLETED:
                self.stdout.write(self.style.SUCCESS(message))
            else:
                self.stdout.write(self.style.ERROR(f"{message} | {run.error_message}"))
