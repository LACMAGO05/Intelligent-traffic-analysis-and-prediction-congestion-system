# Deployment overview

This guide describes the deployment behavior represented by the repository. It is not evidence that a live Render service, database, worker, or scheduled workflow is currently configured. See [DEPLOYMENT_CHECKLIST.md](../DEPLOYMENT_CHECKLIST.md) for an operational checklist and [CONFIGURATION.md](CONFIGURATION.md) for environment variable meanings.

## Render Blueprint in this repository

`render.yaml` declares one web service. Its configured build command installs `requirements.txt`, collects static assets, and applies Django migrations; its start command runs Gunicorn with `TrafficPro.wsgi`. It configures `/healthz/` as the health check and specifies Python 3.12. The Blueprint does not declare a worker, database, or Redis instance. Confirm that the necessary services and current plan are available and configured in the target Render account.

The health endpoint in `TrafficApp/views.py` checks database connectivity and returns an error status if the database is unavailable. A successful process start alone is not sufficient to establish a healthy deployment.

## Model artifacts

Inference expects `traffic_model.pkl` and `feature_schema.json` at the repository root. Startup and Django system checks warn if either is missing. The Render build command does not train, download, or otherwise provision these artifacts. `.gitignore` explicitly exempts the root `traffic_model.pkl` from the general pickle ignore rule, but that does not prove it is committed in the deployed revision. Confirm that both matching artifacts are present in the exact release and inspect startup logs for missing-artifact warnings. See [ML_PIPELINE.md](ML_PIPELINE.md).

## Background work: choose and verify the operating mode

The code has two relevant entry points:

| Mode | What runs | What it does not establish |
|---|---|---|
| GitHub Actions workflow `.github/workflows/scheduled-tasks.yml` | Every 20 minutes, posts to `/tasks/run/` with `CRON_SECRET`. The endpoint runs gridlock alert forecasting and processes the outbox. | It does not run `TrafficCollector` or populate new `TrafficRecord` observations. |
| Separate process running `python manage.py start_collector` | Starts APScheduler. It collects traffic records and schedules gridlock alerts and outbox processing. | The Render Blueprint does not declare this worker. Its live provisioning must be confirmed. |

The worker scheduler runs collection immediately on startup and then at adaptive intervals. It schedules gridlock-alert processing every 20 minutes and outbox processing every minute. If the worker is the selected path for alerts and outbox, do not also enable the GitHub scheduled workflow without intentionally handling concurrent execution. The outbox processor has no visible row-claim/locking step, so overlapping processors could process the same pending task. If the web-only plus GitHub Actions mode is selected, document that periodic traffic collection is not provided by the checked-in scheduled endpoint.

The cron endpoint requires `CRON_SECRET`; the workflow also requires repository secrets for the application URL and matching cron secret. Keep secret values in deployment secret stores. Do not put them in the repository or logs.

## Configuration and security

Use [CONFIGURATION.md](CONFIGURATION.md) for the application environment reference. At minimum, the web process needs the Django secret and database URL; usable live predictions need the Google Maps key and the model artifacts. Email, weather, push, Redis, Sentry, and cron settings are integration-dependent. The checked-in Blueprint uses `DEBUG=False`; production HTTPS, secure-cookie, and HSTS settings are conditional on debug being false. Restrict the browser-exposed Google Maps key and protect all private keys and service credentials.

## Release verification

After deployment, verify the actual build logs, migration result, `/healthz/` response, model artifact warnings, live route prediction, and whichever scheduled-work mode is selected. Verify email or push only if those integrations are configured. These checks require the target deployment and have not been performed as part of this documentation update.
