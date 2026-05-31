from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from TrafficApp.models import ChatThread, PredictionLog


class Command(BaseCommand):
    help = (
        "Retention: delete chat threads (with their messages, via cascade) and "
        "prediction logs older than N days."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=180,
            help="Delete records older than this many days (default: 180).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=days)

        old_threads = ChatThread.objects.filter(created_at__lt=cutoff)
        old_logs = PredictionLog.objects.filter(created_at__lt=cutoff)

        thread_count = old_threads.count()
        log_count = old_logs.count()

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"[dry-run] Would delete {thread_count} thread(s) and {log_count} "
                f"prediction log(s) older than {days} days (before {cutoff:%Y-%m-%d})."
            ))
            return

        old_threads.delete()
        old_logs.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Deleted {thread_count} thread(s) and {log_count} prediction log(s) "
            f"older than {days} days."
        ))
