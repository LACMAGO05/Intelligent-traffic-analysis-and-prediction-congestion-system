"""
Deploy-time system checks.

These surface in ``manage.py check`` and run on ``runserver`` startup, so a
deployment that is missing its ML artifacts is flagged loudly instead of
silently degrading every prediction (the regression we hit before, where
``traffic_model.pkl`` never reached the server).
"""
import os

from django.conf import settings
from django.core.checks import Warning, register


@register()
def model_artifacts_check(app_configs, **kwargs):
    issues = []
    for fname in ("traffic_model.pkl", "feature_schema.json"):
        path = os.path.join(settings.BASE_DIR, fname)
        if not os.path.exists(path):
            issues.append(
                Warning(
                    f"ML artifact '{fname}' is missing at {path}.",
                    hint="Predictions will be degraded ('Model not loaded'). Ensure the "
                         "file is committed and shipped to this environment.",
                    id="TrafficApp.W001",
                )
            )
    return issues
