"""
Lightweight background-task helper.

This decouples fire-and-forget work (e.g. non-critical emails) from the request
path without requiring a broker. It is intentionally minimal:

* When ``settings.TASK_ALWAYS_EAGER`` is true (tests / local debugging) the
  callable runs synchronously.
* Otherwise it is submitted to a small thread pool and the request returns
  immediately.

For production at scale this should be swapped for a real task queue
(Celery / RQ + Redis); ``run_async`` is the single seam to change. Only use it
for work whose failure is tolerable (the caller does not observe the result).
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bgtask")


def run_async(func, *args, **kwargs):
    """Run ``func(*args, **kwargs)`` off the request path (best-effort)."""
    name = getattr(func, "__name__", repr(func))

    if getattr(settings, "TASK_ALWAYS_EAGER", False):
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.exception("Eager background task %s failed", name)
            return None

    def _wrapped():
        try:
            func(*args, **kwargs)
        except Exception:
            logger.exception("Background task %s failed", name)

    _executor.submit(_wrapped)
    return None
