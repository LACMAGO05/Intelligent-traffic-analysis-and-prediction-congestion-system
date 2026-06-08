"""
Recompute the event/market fields on existing TrafficRecord rows using the
new location-aware EventDetector (see traffic_context.event_detector).

The original collector stored a city-wide Fri/Sat/Sun "event" flag on every
route. This rewrites ``event_indicator / event_type / event_severity`` from each
row's timestamp + route so the real, location-specific market days appear in the
stored dataset.

Safe: writes a CSV backup of the three columns (keyed by row id) BEFORE touching
anything, so the change is fully reversible. Use --dry-run to preview counts.
"""
import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from TrafficApp.models import TrafficRecord
from traffic_context.event_detector import EventDetector


def _split_route(route):
    """'Origin to Destination' -> ('Origin', 'Destination')."""
    parts = str(route).split(" to ")
    if len(parts) >= 2:
        return parts[0].strip(), parts[-1].strip()
    return route, route


class Command(BaseCommand):
    help = "Backfill location-aware market/event fields on existing TrafficRecord rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backup",
            default=str(settings.BASE_DIR / "event_fields_backup.csv"),
            help="Where to write the reversible backup CSV.",
        )
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change without writing.")

    def handle(self, *args, **options):
        detector = EventDetector()
        rows = list(TrafficRecord.objects.all().only(
            "id", "timestamp", "route", "event_indicator", "event_type", "event_severity"
        ))
        self.stdout.write(f"Loaded {len(rows)} rows.")

        # ── reversible backup (always written, even on dry-run) ──────────
        backup_path = options["backup"]
        with open(backup_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "event_indicator", "event_type", "event_severity"])
            for r in rows:
                w.writerow([r.id, r.event_indicator, r.event_type, r.event_severity])
        self.stdout.write(f"Backup of current event fields written to {backup_path}")

        # ── recompute ───────────────────────────────────────────────────
        changed = []
        now_on = 0
        for r in rows:
            origin, destination = _split_route(r.route)
            info = detector.get_event_info(r.timestamp, origin, destination)
            if info["event_indicator"]:
                now_on += 1
            if (r.event_indicator != info["event_indicator"]
                    or r.event_type != info["event_type"]
                    or r.event_severity != info["event_severity"]):
                r.event_indicator = info["event_indicator"]
                r.event_type = info["event_type"]
                r.event_severity = info["event_severity"]
                changed.append(r)

        pct = (now_on / len(rows) * 100) if rows else 0
        self.stdout.write(
            f"{len(changed)} row(s) would change; after backfill {now_on}/{len(rows)} "
            f"({pct:.1f}%) rows carry an event/market flag."
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no rows updated."))
            return

        batch = options["batch_size"]
        for i in range(0, len(changed), batch):
            TrafficRecord.objects.bulk_update(
                changed[i:i + batch],
                ["event_indicator", "event_type", "event_severity"],
                batch_size=batch,
            )
            self.stdout.write(f"  ...updated {min(i + batch, len(changed))}/{len(changed)}")

        self.stdout.write(self.style.SUCCESS(
            f"Done. {len(changed)} row(s) updated. Restore with the backup CSV if needed."
        ))
