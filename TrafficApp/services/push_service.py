"""
Web Push delivery.

Sends a notification to a user's browsers via the Push API + VAPID, using
``pywebpush``. Dead subscriptions (HTTP 404/410 from the push service) are
pruned automatically so we don't keep trying to reach uninstalled browsers.
"""
import json
import logging

from django.conf import settings
from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)


def _vapid_claims():
    return {"sub": settings.VAPID_SUBJECT}


def send_push_to_subscription(subscription, payload):
    """
    Push ``payload`` (a dict) to one PushSubscription row.

    Returns True on success. On 404/410 the subscription is deleted (the browser
    unsubscribed/was removed) and False is returned.
    """
    if not settings.VAPID_PRIVATE_KEY:
        logger.warning("VAPID_PRIVATE_KEY not configured; cannot send push.")
        return False
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims=_vapid_claims(),
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            logger.info("Pruning dead push subscription %s (status %s)", subscription.pk, status)
            subscription.delete()
        else:
            logger.warning("Web push failed for sub %s: %s", subscription.pk, exc)
        return False
    except Exception:
        logger.exception("Unexpected error sending web push")
        return False


def notify_user(user, payload):
    """Send a notification to every browser the user has subscribed. Returns count sent."""
    sent = 0
    for sub in user.push_subscriptions.all():
        if send_push_to_subscription(sub, payload):
            sent += 1
    return sent
