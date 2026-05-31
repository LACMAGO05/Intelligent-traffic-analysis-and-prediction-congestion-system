"""
Durable, database-backed store for collected traffic records.

Replaces the file-based :class:`CSVManager` as the runtime source of truth.
De-duplication is delegated to the database via the unique ``(timestamp, route)``
constraint on :class:`TrafficApp.models.TrafficRecord`, which is concurrency-safe
(unlike scanning the tail of a CSV) and survives process/host restarts.
"""
from datetime import datetime

from django.db import IntegrityError
from django.utils import timezone

from .logger import logger

# Fields copied straight from the collected ``record`` dict into the model.
# ``timestamp`` and ``route`` are handled separately (they form the unique key).
_DEFAULT_FIELDS = [
    "distance_km", "hour", "day", "day_of_week",
    "travel_time_mins", "speed_kmh", "congestion",
    "weather_condition", "rainfall_status", "holiday_indicator",
    "school_holiday_indicator", "school_hours_indicator",
    "working_hours_indicator", "office_rush_hour_indicator",
    "event_indicator", "event_type", "event_severity",
    "traffic_pressure_score",
]


def _parse_timestamp(value):
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None
    # The collector produces naive local timestamps; make them timezone-aware
    # so they are stored unambiguously while USE_TZ is active.
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


class TrafficRecordStore:
    """Persists a collected traffic ``record`` dict to the database."""

    def append_record(self, record):
        """
        Insert a record, skipping duplicates.

        Returns ``True`` if a new row was created, ``False`` if it was a
        duplicate or could not be stored.
        """
        # Imported lazily so this module is importable before the app registry
        # is ready (e.g. at settings/collector import time).
        from TrafficApp.models import TrafficRecord

        ts = _parse_timestamp(record.get("timestamp"))
        route = record.get("route")
        if ts is None or not route:
            logger.error("Skipping traffic record with missing timestamp/route: %s", record.get("route"))
            return False

        defaults = {
            field: record[field]
            for field in _DEFAULT_FIELDS
            if field in record and record[field] is not None
        }

        try:
            _, created = TrafficRecord.objects.get_or_create(
                timestamp=ts, route=route, defaults=defaults
            )
            if not created:
                logger.debug("Duplicate traffic record skipped: %s - %s", ts, route)
            return created
        except IntegrityError:
            # Raced with a concurrent writer on the unique constraint.
            logger.debug("Duplicate traffic record (integrity): %s - %s", ts, route)
            return False
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error storing traffic record for %s: %s", route, exc)
            return False
