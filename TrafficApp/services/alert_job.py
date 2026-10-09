"""
Background job: send "leave earlier" gridlock alerts.

Runs on the existing traffic scheduler. For every active RouteWatch it forecasts
~1 hour ahead, and if a gridlock is likely (and the user hasn't already been
alerted for that window) it pushes a notification to their browsers.
"""
import datetime
import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import RouteWatch, TrafficAlert
from .forecast import forecast_gridlock, route_string
from .push_service import notify_user

logger = logging.getLogger(__name__)
ALERT_CLAIM_LEASE = timedelta(minutes=25)


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

        # Claim the unique delivery window before calling the push provider so
        # concurrent schedulers cannot both notify the same user and route.
        claim_token = uuid.uuid4()
        now = timezone.now()
        with transaction.atomic():
            claim, created = TrafficAlert.objects.get_or_create(
                user=watch.user,
                route=route,
                alert_for=alert_hour,
                defaults={
                    "route_watch": watch,
                    "status": TrafficAlert.STATUS_PENDING,
                    "claim_token": claim_token,
                    "lease_expires_at": now + ALERT_CLAIM_LEASE,
                },
            )
            if not created:
                claim = TrafficAlert.objects.select_for_update().get(pk=claim.pk)
                if claim.status == TrafficAlert.STATUS_SENT:
                    continue
                if claim.lease_expires_at and claim.lease_expires_at > now:
                    continue
                claim_token = uuid.uuid4()
                claim.status = TrafficAlert.STATUS_PENDING
                claim.claim_token = claim_token
                claim.lease_expires_at = now + ALERT_CLAIM_LEASE
                claim.route_watch = watch
                claim.save(update_fields=[
                    "status", "claim_token", "lease_expires_at", "route_watch"
                ])

        forecast = forecast_gridlock(watch.origin, watch.destination, target_dt)
        if not forecast:
            TrafficAlert.objects.filter(pk=claim.pk, claim_token=claim_token).delete()
            continue

        sent = notify_user(watch.user, _build_payload(forecast))
        if sent:
            TrafficAlert.objects.filter(pk=claim.pk, claim_token=claim_token).update(
                status=TrafficAlert.STATUS_SENT,
                sent_at=timezone.now(),
                claim_token=None,
                lease_expires_at=None,
            )
            sent_total += sent
            logger.info("Gridlock alert sent")
        else:
            # Allow the next scheduled pass to retry, but never overlap a slow
            # or still-running send attempt.
            TrafficAlert.objects.filter(pk=claim.pk, claim_token=claim_token).update(
                claim_token=None,
                lease_expires_at=timezone.now() + ALERT_CLAIM_LEASE,
            )

    return sent_total
