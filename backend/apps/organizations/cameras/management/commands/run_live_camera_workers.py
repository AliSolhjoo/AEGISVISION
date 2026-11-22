import time

from django.core.management.base import BaseCommand, CommandError

from apps.organizations.cameras.live_stream_services import run_live_camera_manager


class Command(BaseCommand):
    help = "Run the background manager that consumes requested RTSP camera streams."

    def add_arguments(self, parser):
        parser.add_argument("--poll-seconds", type=float, default=2.0)

    def handle(self, *args, **options):
        poll_seconds = float(options["poll_seconds"])
        if not 0.5 <= poll_seconds <= 10:
            raise CommandError("--poll-seconds must be between 0.5 and 10.")
        self.stdout.write(self.style.SUCCESS("AEGISVISION live camera worker manager is starting."))
        try:
            run_live_camera_manager(poll_seconds=poll_seconds)
        except KeyboardInterrupt:
            self.stdout.write("Stopping live camera workers...")
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            self.stdout.write(self.style.WARNING("AEGISVISION live camera worker manager stopped."))
