"""
Durable task outbox.

``enqueue(name, **payload)`` persists a unit of fire-and-forget work; the
background worker calls ``process_outbox()`` on a schedule to run it with
retries. This is the production-grade replacement for the in-process thread pool
(``tasks.run_async``) for work whose loss matters, e.g. transactional emails.

Only tasks registered in ``TASK_REGISTRY`` can run, and payloads must be
JSON-serialisable, so a restart can fully reconstruct the job from the DB.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import TaskOutbox
from .email_service import send_welcome_email, send_new_device_login_alert

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
LOCK_TIMEOUT = timedelta(minutes=15)

# Named, JSON-serialisable tasks. Each returns truthy on success (the email
# helpers return True/False), which the processor uses to decide retry.
TASK_REGISTRY = {
    "send_welcome_email": send_welcome_email,
    "send_new_device_login_alert": send_new_device_login_alert,
}


def enqueue(task, **payload):
    """Queue a task. Runs inline when TASK_ALWAYS_EAGER (tests/local), else persists."""
    if task not in TASK_REGISTRY:
        raise ValueError(f"Unknown outbox task: {task}")
    if getattr(settings, "TASK_ALWAYS_EAGER", False):
        try:
            return TASK_REGISTRY[task](**payload)
        except Exception:
            logger.exception("Eager outbox task %s failed", task)
            return None
    return TaskOutbox.objects.create(task=task, payload=payload)


def process_outbox(limit=20):
    """Claim and run tasks at least once; external sends can repeat after a crash."""
    processed = failed = 0
    now = timezone.now()
    stale_before = now - LOCK_TIMEOUT

    # Claims are short database transactions. skip_locked lets separate worker
    # processes take different rows without holding locks during network calls.
    with transaction.atomic():
        stale = Q(status=TaskOutbox.STATUS_PROCESSING) & (
            Q(locked_at__isnull=True) | Q(locked_at__lt=stale_before)
        )
        failed += TaskOutbox.objects.filter(stale, attempts__gte=MAX_ATTEMPTS).update(
            status=TaskOutbox.STATUS_FAILED,
            processed_at=now,
            locked_at=None,
            last_error="Processing lease expired after maximum attempts",
        )
        rows = list(
            TaskOutbox.objects.filter(
                Q(status=TaskOutbox.STATUS_PENDING)
                | (stale & Q(attempts__lt=MAX_ATTEMPTS))
            )
            .order_by("created_at")
            .select_for_update(skip_locked=True)[:limit]
        )
        for row in rows:
            row.status = TaskOutbox.STATUS_PROCESSING
            row.locked_at = now
            row.attempts += 1
            row.save(update_fields=["status", "locked_at", "attempts"])

    for row in rows:
        func = TASK_REGISTRY.get(row.task)
        if func is None:
            row.status = TaskOutbox.STATUS_FAILED
            row.last_error = "Unknown task"
            row.processed_at = timezone.now()
            row.locked_at = None
            row.save(update_fields=["status", "last_error", "processed_at", "locked_at"])
            failed += 1
            continue

        try:
            if func(**row.payload) is False:
                raise RuntimeError("task reported failure")
            row.status = TaskOutbox.STATUS_DONE
            row.processed_at = timezone.now()
            row.locked_at = None
            row.last_error = ""
            row.save(update_fields=["status", "processed_at", "locked_at", "last_error"])
            processed += 1
        except Exception as exc:
            row.last_error = f"{type(exc).__name__}: task failed"
            if row.attempts >= MAX_ATTEMPTS:
                row.status = TaskOutbox.STATUS_FAILED
                row.processed_at = timezone.now()
            else:
                row.status = TaskOutbox.STATUS_PENDING
            row.locked_at = None
            row.save(update_fields=["status", "last_error", "processed_at", "locked_at"])
            failed += 1
            logger.warning("Outbox task %s failed (attempt %s; %s)", row.task, row.attempts, type(exc).__name__)
    return processed, failed
