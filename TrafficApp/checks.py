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
from .services.artifact_manifest import resolve_artifact_paths


@register()
def model_artifacts_check(app_configs, **kwargs):
    issues = []
    try:
        model_path, schema_path, release_version = resolve_artifact_paths(settings.BASE_DIR)
    except Exception as exc:
        return [
            Warning(
                f"ML artifact manifest is invalid ({type(exc).__name__}).",
                hint="Check ml_artifacts/current.json and its versioned model/schema release.",
                id="TrafficApp.W002",
            )
        ]
    expected_version = release_version
    for path in (model_path, schema_path):
        if not os.path.exists(path):
            issues.append(
                Warning(
                    f"ML artifact is missing at {path}.",
                    hint="Predictions will be degraded ('Model not loaded'). Ensure the "
                         "matching artifact release is committed and shipped to this environment.",
                    id="TrafficApp.W001",
                )
            )
    if expected_version and os.path.exists(schema_path):
        try:
            import json
            with open(schema_path, encoding="utf-8") as schema_file:
                schema = json.load(schema_file)
            if schema.get("version") != expected_version:
                issues.append(
                    Warning(
                        "Active model artifact manifest and schema versions do not match.",
                        hint="Promote a matching model and schema release.",
                        id="TrafficApp.W003",
                    )
                )
        except (OSError, ValueError):
            issues.append(
                Warning(
                    "Active model feature schema cannot be read.",
                    hint="Check the schema JSON in the active model release.",
                    id="TrafficApp.W004",
                )
            )
    return issues
