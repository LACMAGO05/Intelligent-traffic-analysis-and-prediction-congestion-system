"""
Gridlock forecasting for proactive alerts.

Hybrid strategy (chosen to balance cost and accuracy):

1. **History (cheap):** look at the collected ``TrafficRecord`` rows for this
   route at the target weekday+hour. If history doesn't suggest congestion, we
   stop here and spend no API quota.
2. **Live confirm (accurate):** only for routes history flags as risky, do a
   single live hybrid prediction for the target time to confirm before alerting.

A forecast is returned only when BOTH agree there's likely congestion ~1 hour
out, which keeps false alerts (and Google API spend) low.
"""
import logging

from django.db.models import Count, Q

from ..models import TrafficRecord
from .hybrid_prediction_service import HybridPredictionService

logger = logging.getLogger(__name__)

CONGESTED = ["Medium", "High"]
MIN_SAMPLES = 8           # need at least this much history to trust a pattern
HISTORY_THRESHOLD = 45    # % of historical records congested to flag as risky


def route_string(origin, destination):
    """Match the "Origin to Destination" form used in TrafficRecord.route."""
    return f"{origin} to {destination}"


def history_congestion_pct(route_str, weekday, hour):
    """% of historical records for this route/weekday/hour that were congested,
    or None when there isn't enough history to judge."""
    agg = (
        TrafficRecord.objects.filter(route=route_str, day_of_week=weekday, hour=hour)
        .aggregate(
            total=Count("id"),
            congested=Count("id", filter=Q(congestion__in=CONGESTED)),
        )
    )
    total = agg["total"] or 0
    if total < MIN_SAMPLES:
        return None
    return round(100 * agg["congested"] / total)


def forecast_gridlock(origin, destination, target_dt):
    """
    Decide whether a gridlock is likely on this route at ``target_dt``.

    Returns a dict describing the forecast when an alert is warranted, else None.
    """
    route_str = route_string(origin, destination)

    # Step 1 — history gate (no API spend).
    hist = history_congestion_pct(route_str, target_dt.weekday(), target_dt.hour)
    if hist is None or hist < HISTORY_THRESHOLD:
        return None

    # Step 2 — live confirmation for the target time.
    try:
        pred = HybridPredictionService().get_hybrid_prediction(
            origin, destination, int(target_dt.timestamp())
        )
    except Exception:
        logger.exception("Live confirm failed for %s", route_str)
        return None

    if "error" in pred:
        return None

    congestion = pred.get("congestion")
    if congestion not in CONGESTED:
        return None  # live data disagrees — don't cry wolf

    # Identify the worst choke point, if Google surfaced one.
    segments = pred.get("segments_delay") or []
    worst_point = None
    if segments:
        worst = max(segments, key=lambda s: s.get("delay", 0))
        worst_point = worst.get("point")

    return {
        "route": route_str,
        "origin": origin,
        "destination": destination,
        "target_dt": target_dt,
        "congestion": congestion,
        "history_pct": hist,
        "eta": pred.get("final_smart_eta") or pred.get("travel_time"),
        "worst_point": worst_point,
    }
