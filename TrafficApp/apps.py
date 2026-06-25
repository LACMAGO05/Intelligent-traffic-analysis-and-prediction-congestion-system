import logging
import os

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class TrafficappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "TrafficApp"

    def ready(self):
        # Register deploy-time system checks.
        from . import checks  # noqa: F401

        # Fail loudly at process startup (incl. under gunicorn) if the ML model
        # is missing, so a degraded deploy is obvious in the logs immediately.
        for fname in ("traffic_model.pkl", "feature_schema.json"):
            if not os.path.exists(os.path.join(settings.BASE_DIR, fname)):
                logger.warning(
                    "ML artifact '%s' is MISSING — predictions will be degraded.", fname
                )
