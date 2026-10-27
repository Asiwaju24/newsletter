import time

from django.core.management.base import BaseCommand

from newsletters import services


class Command(BaseCommand):
    help = "Send every issue that is due (scheduled in the past, or a send that stalled)."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running instead of exiting after one pass.")
        parser.add_argument("--interval", type=int, default=60, help="Seconds between passes with --loop (default 60).")

    def handle(self, *args, **options):
        while True:
            self._run_once()
            if not options["loop"]:
                return
            time.sleep(options["interval"])

    def _run_once(self):
        for issue in services.due_issues().select_related("newsletter__owner"):
            result = services.send_issue(issue)
            if result is None:
                continue  # another worker claimed it
            self.stdout.write(
                f"“{issue.subject}”: {result.sent} sent, {result.failed} failed, {result.skipped} skipped"
            )
