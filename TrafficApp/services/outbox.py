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

from django.conf import settings
from django.utils import timezone

from ..models import TaskOutbox
from .email_service import send_welcome_email, send_new_device_login_alert

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5

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
    """Run up to ``limit`` pending tasks. Returns (processed, failed_or_retried)."""
    processed = failed = 0
    rows = TaskOutbox.objects.filter(status=TaskOutbox.STATUS_PENDING).order_by("created_at")[:limit]
    for row in rows:
        func = TASK_REGISTRY.get(row.task)
        if func is None:
            row.status = TaskOutbox.STATUS_FAILED
            row.last_error = "Unknown task"
            row.processed_at = timezone.now()
            row.save(update_fields=["status", "last_error", "processed_at"])
            failed += 1
            continue

        row.attempts += 1
        try:
            if func(**row.payload) is False:
                raise RuntimeError("task reported failure")
            row.status = TaskOutbox.STATUS_DONE
            row.processed_at = timezone.now()
            row.save(update_fields=["status", "attempts", "processed_at"])
            processed += 1
        except Exception as exc:
            row.last_error = str(exc)[:500]
            if row.attempts >= MAX_ATTEMPTS:
                row.status = TaskOutbox.STATUS_FAILED
                row.processed_at = timezone.now()
            row.save(update_fields=["status", "attempts", "last_error", "processed_at"])
            failed += 1
            logger.warning("Outbox task %s failed (attempt %s): %s", row.task, row.attempts, exc)
    return processed, failed
