# Deployment overview

This guide describes the deployment behavior represented by the repository. It is not evidence that a live Render service, database, worker, or scheduled workflow is currently configured. See [DEPLOYMENT_CHECKLIST.md](../DEPLOYMENT_CHECKLIST.md) for an operational checklist and [CONFIGURATION.md](CONFIGURATION.md) for environment variable meanings.

## Render Blueprint in this repository

`render.yaml` declares one web service. Its configured build command installs `requirements.txt`, collects static assets, and applies Django migrations; its start command runs Gunicorn with `TrafficPro.wsgi`. It configures `/healthz/` as the health check and specifies Python 3.12. The Blueprint does not declare a worker, database, or Redis instance. Confirm that the necessary services and current plan are available and configured in the target Render account.

The health endpoint in `TrafficApp/views.py` checks database connectivity and returns an error status if the database is unavailable. A successful process start alone is not sufficient to establish a healthy deployment.

## Model artifacts

Inference reads the matching model and schema release named in `ml_artifacts/current.json`; if the manifest is absent, it falls back to the checked-in root `traffic_model.pkl` and `feature_schema.json`. Startup and Django system checks warn if the selected pair is missing or its schema version does not match the manifest. The Render build command does not train, download, or otherwise provision these artifacts. Confirm that the manifest and its complete release directory are present in the exact deployed revision and inspect startup logs for artifact warnings. See [ML_PIPELINE.md](ML_PIPELINE.md).

## Background work: choose and verify the operating mode

The code has two relevant entry points:

| Mode | What runs | What it does not establish |
|---|---|---|
| GitHub Actions workflow `.github/workflows/scheduled-tasks.yml` | Every 20 minutes, posts to `/tasks/run/` with `CRON_SECRET`. The endpoint runs gridlock alert forecasting and processes the outbox. | It does not run `TrafficCollector` or populate new `TrafficRecord` observations. |
| Separate process running `python manage.py start_collector` | Starts APScheduler. It collects traffic records and schedules gridlock alerts and outbox processing. | The Render Blueprint does not declare this worker. Its live provisioning must be confirmed. |

The worker scheduler runs collection immediately on startup and then at adaptive intervals. It schedules gridlock-alert processing every 20 minutes and outbox processing every minute. The GitHub scheduled workflow serializes its own invocations; database claims prevent concurrent workers from processing the same outbox row or alert window. Email delivery remains at-least-once: a process crash after a provider accepts a message but before the database records success can lead to a retry. If the web-only plus GitHub Actions mode is selected, document that periodic traffic collection is not provided by the checked-in scheduled endpoint.

The cron endpoint requires a POST with `CRON_SECRET` in the `X-Cron-Secret` header; query-string tokens are rejected. The workflow also requires repository secrets for the application URL and matching cron secret, and serializes its own runs. Keep secret values in deployment secret stores. Do not put them in the repository or logs.

## Configuration and security

Use [CONFIGURATION.md](CONFIGURATION.md) for the application environment reference. At minimum, the web process needs the Django secret and database URL; usable live predictions need the Google Maps key and the model artifacts. Email, weather, push, Redis, Sentry, and cron settings are integration-dependent. The checked-in Blueprint uses `DEBUG=False`; production HTTPS, secure-cookie, and HSTS settings are conditional on debug being false. Restrict the browser-exposed Google Maps key and protect all private keys and service credentials.

## Release verification

After deployment, verify the actual build logs, migration result, `/healthz/` response, model artifact warnings, live route prediction, and whichever scheduled-work mode is selected. Verify email or push only if those integrations are configured. These checks require the target deployment and have not been performed as part of this documentation update.
