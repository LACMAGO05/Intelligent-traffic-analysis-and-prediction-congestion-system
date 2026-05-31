import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from TrafficApp.models import TrafficRecord

FIELDNAMES = [
    "timestamp", "route", "distance_km", "hour", "day", "day_of_week",
    "travel_time_mins", "speed_kmh", "congestion",
    "weather_condition", "rainfall_status", "holiday_indicator",
    "school_holiday_indicator", "school_hours_indicator",
    "working_hours_indicator", "office_rush_hour_indicator",
    "event_indicator", "event_type", "event_severity",
    "traffic_pressure_score",
]


class Command(BaseCommand):
    help = "Export collected TrafficRecord rows to a clean CSV for ML training."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=None,
            help="Output CSV path (default: BASE_DIR/traffic_training_export.csv).",
        )

    def handle(self, *args, **options):
        output = options["output"] or os.path.join(settings.BASE_DIR, "traffic_training_export.csv")

        count = 0
        with open(output, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            for record in TrafficRecord.objects.all().order_by("timestamp").iterator():
                row = {field: getattr(record, field) for field in FIELDNAMES}
                row["timestamp"] = record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow(row)
                count += 1

        self.stdout.write(self.style.SUCCESS(f"Exported {count} record(s) to {output}"))
