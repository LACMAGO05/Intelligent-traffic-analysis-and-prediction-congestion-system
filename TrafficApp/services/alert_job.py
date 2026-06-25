"""
Background job: send "leave earlier" gridlock alerts.

Runs on the existing traffic scheduler. For every active RouteWatch it forecasts
~1 hour ahead, and if a gridlock is likely (and the user hasn't already been
alerted for that window) it pushes a notification to their browsers.
"""
import datetime
import logging

from django.utils import timezone

from ..models import RouteWatch, TrafficAlert
from .forecast import forecast_gridlock, route_string
from .push_service import notify_user

logger = logging.getLogger(__name__)


def _watch_applies(watch, target_dt):
    """Respect the watch's day-of-week list and optional commute time window."""
    if watch.days:
        allowed = {int(d) for d in watch.days.split(",") if d.strip().isdigit()}
        if target_dt.weekday() not in allowed:
            return False
    if watch.window_start and watch.window_end:
        t = target_dt.time()
        if not (watch.window_start <= t <= watch.window_end):
            return False
    return True


def _build_payload(forecast):
    when = timezone.localtime(forecast["target_dt"]).strftime("%H:%M")
    where = f" near {forecast['worst_point']}" if forecast.get("worst_point") else ""
    body = (
        f"{forecast['congestion']} congestion likely{where} around {when}. "
        f"Leave earlier to beat it."
    )
    return {
        "title": f"🚦 Gridlock ahead: {forecast['origin']} → {forecast['destination']}",
        "body": body,
        "url": "/predict/",
        "tag": forecast["route"],
    }


def run_gridlock_alerts(lead_minutes=60):
    """Forecast every active watch ~lead_minutes ahead and alert when needed.
    Returns the number of push messages sent."""
    now = timezone.localtime()
    target_dt = now + datetime.timedelta(minutes=lead_minutes)
    alert_hour = target_dt.replace(minute=0, second=0, microsecond=0)
    sent_total = 0

    for watch in RouteWatch.objects.filter(active=True).select_related("user"):
        if not _watch_applies(watch, target_dt):
            continue

        route = route_string(watch.origin, watch.destination)

        # Dedup: already alerted this user for this route + hour window?
        if TrafficAlert.objects.filter(
            user=watch.user, route=route, alert_for=alert_hour
        ).exists():
            continue

        forecast = forecast_gridlock(watch.origin, watch.destination, target_dt)
        if not forecast:
            continue

        sent = notify_user(watch.user, _build_payload(forecast))
        if sent:
            TrafficAlert.objects.create(
                user=watch.user, route_watch=watch, route=route, alert_for=alert_hour
            )
            sent_total += sent
            logger.info("Gridlock alert sent to %s for %s", watch.user.username, route)

    return sent_total
