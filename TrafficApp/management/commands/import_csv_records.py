"""
One-off / idempotent importer that loads collected traffic rows from a CSV
(e.g. the legacy ``google_traffic_data_v2.csv``) into the ``TrafficRecord``
table — i.e. into Supabase when ``DATABASE_URL`` points there.

Safe to re-run: the unique ``(timestamp, route)`` constraint means existing
rows are skipped via ``bulk_create(ignore_conflicts=True)``, so you never get
duplicates. Timestamp parsing mirrors the collector's ``record_store`` so the
imported rows are stored timezone-aware exactly like freshly collected ones.
"""
import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from TrafficApp.models import TrafficRecord
from traffic_collector.record_store import _parse_timestamp

# Nullable numeric columns -> empty cell becomes NULL.
_NULLABLE_INT = {"hour", "day_of_week"}
_NULLABLE_FLOAT = {"distance_km", "travel_time_mins", "speed_kmh", "traffic_pressure_score"}
# Non-nullable integer flags -> empty cell becomes 0 (matches model defaults).
_FLAG_INT = {
    "holiday_indicator", "school_holiday_indicator", "school_hours_indicator",
    "working_hours_indicator", "office_rush_hour_indicator", "event_indicator",
}
# Everything else copied as a trimmed string.
_STR = {
    "route", "day", "congestion", "weather_condition", "rainfall_status",
    "event_type", "event_severity",
}


def _coerce(field, raw):
    value = (raw or "").strip()
    if field in _NULLABLE_INT:
        return int(float(value)) if value != "" else None
    if field in _NULLABLE_FLOAT:
        return float(value) if value != "" else None
    if field in _FLAG_INT:
        return int(float(value)) if value != "" else 0
    return value  # string columns


class Command(BaseCommand):
    help = "Import traffic rows from a CSV into the TrafficRecord table (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default=str(settings.BASE_DIR / "google_traffic_data_v2.csv"),
            help="Path to the source CSV (default: BASE_DIR/google_traffic_data_v2.csv).",
        )
        parser.add_argument(
            "--batch-size", type=int, default=1000,
            help="Rows per bulk_create batch (default: 1000).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and report counts without writing to the database.",
        )

    def handle(self, *args, **options):
        path = options["csv"]
        if not os.path.exists(path):
            raise CommandError(f"CSV not found: {path}")

        before = TrafficRecord.objects.count()
        objs = []
        read = skipped_bad = skipped_corrupt = 0

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                read += 1
                ts = _parse_timestamp(row.get("timestamp"))
                route = (row.get("route") or "").strip()
                if ts is None or not route:
                    skipped_bad += 1
                    continue
                try:
                    fields = {"timestamp": ts}
                    for col in reader.fieldnames:
                        if col == "timestamp":
                            continue
                        fields[col] = _coerce(col, row.get(col))
                except (ValueError, TypeError):
                    # Column-shift corruption in the legacy CSV: a cell holds a
                    # value of the wrong type for its column. Skip the whole row.
                    skipped_corrupt += 1
                    continue
                objs.append(TrafficRecord(**fields))

        self.stdout.write(
            f"Read {read} row(s); {skipped_bad} skipped (bad timestamp/route); "
            f"{skipped_corrupt} skipped (corrupt/type-mismatch); "
            f"{len(objs)} ready to import."
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — nothing written."))
            return

        batch = options["batch_size"]
        for i in range(0, len(objs), batch):
            TrafficRecord.objects.bulk_create(
                objs[i:i + batch], ignore_conflicts=True, batch_size=batch
            )
            self.stdout.write(f"  ...processed {min(i + batch, len(objs))}/{len(objs)}")

        after = TrafficRecord.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Done. New rows inserted: {after - before} "
            f"(table went {before} -> {after}; duplicates skipped)."
        ))
