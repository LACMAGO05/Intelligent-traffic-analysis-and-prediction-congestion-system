import csv
import os
from django.conf import settings
from .logger import logger

class CSVManager:
    def __init__(self, filename="google_traffic_data_v2.csv"):
        self.filepath = os.path.join(settings.BASE_DIR, filename)
        self.fieldnames = [
            "timestamp", "route", "distance_km", "hour", "day", "day_of_week",
            "travel_time_mins", "speed_kmh", "congestion",
            "weather_condition", "rainfall_status", "holiday_indicator",
            "school_holiday_indicator", "school_hours_indicator",
            "working_hours_indicator", "office_rush_hour_indicator",
            "event_indicator", "event_type", "event_severity",
            "traffic_pressure_score"
        ]
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.isfile(self.filepath):
            try:
                with open(self.filepath, mode='w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                    writer.writeheader()
                logger.info(f"Created new CSV file at {self.filepath}")
            except Exception as e:
                logger.error(f"Failed to create CSV file: {e}")

    def append_record(self, record):
        """Appends a single record, ensuring no duplicates based on timestamp and route."""
        if self._is_duplicate(record):
            logger.debug(f"Duplicate record skipped: {record.get('timestamp')} - {record.get('route')}")
            return False

        try:
            # Filter record to match fieldnames
            filtered_record = {k: record[k] for k in self.fieldnames if k in record}
            
            with open(self.filepath, mode='a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writerow(filtered_record)
            return True
        except Exception as e:
            logger.error(f"Error appending to CSV: {e}")
            return False

    def _is_duplicate(self, record):
        """Simple duplicate check: check if the exact timestamp and route combination exists in the last few lines."""
        if not os.path.isfile(self.filepath):
            return False
            
        try:
            # For large files, we only check the last 100 lines for efficiency
            with open(self.filepath, 'r') as f:
                # This is a bit naive for very large files but works for typical append scenarios
                lines = f.readlines()
                last_lines = lines[-100:]
                
                target = f"{record['timestamp']},{record['route']}"
                for line in last_lines:
                    if line.startswith(target):
                        return True
        except Exception:
            pass
        return False
