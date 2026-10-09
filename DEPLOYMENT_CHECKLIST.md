# Deployment checklist

Use this checklist with [the deployment overview](docs/DEPLOYMENT.md) and [the environment reference](docs/CONFIGURATION.md). It describes repository requirements; it does not confirm the state of a live deployment. Keep secrets in the platform’s secret manager and never commit or paste their values into this checklist.

## 1. Select the background-work mode

Choose deliberately based on the services available in the target environment:

- [ ] **Web service plus GitHub Actions scheduled endpoint:** configure the GitHub workflow secrets for the application URL and the same `CRON_SECRET` set on the web service. The checked-in workflow calls `/tasks/run/` every 20 minutes for gridlock alert forecasting and outbox processing. This mode does **not** run the traffic collector.
- [ ] **Separate worker running `python manage.py start_collector`:** configure a persistent worker with the application’s database and integration environment. This runs traffic collection plus scheduler-side gridlock alerts and outbox processing. If selecting this mode, avoid running the GitHub scheduled endpoint at the same time unless overlapping alert/outbox processing is addressed.
- [ ] Confirm the selected services and plan in the deployment provider; `render.yaml` declares a web service only and does not create a worker, database, or Redis instance.

## 2. Configure the database and application

- [ ] Provision or identify a PostgreSQL database and configure `DATABASE_URL` in the web service and any worker.
- [ ] Configure a unique production `DJANGO_SECRET_KEY` and set `DEBUG=False`.
- [ ] Set `ALLOWED_HOSTS` to the real deployment hostnames. Confirm HTTPS and CSRF behavior for the actual public domain.
- [ ] Configure `REDIS_URL` if a shared cache/rate-limit store is required. Without it, the application uses local-memory caching.
- [ ] Review [CONFIGURATION.md](docs/CONFIGURATION.md) and configure only the integrations needed for the selected deployment.
- [ ] Confirm backups and recovery for the PostgreSQL database with the chosen provider. Backup availability is provider/plan-specific and is not established by this repository.

## 3. Confirm ML artifacts are in the release

- [ ] Confirm `traffic_model.pkl` and `feature_schema.json` are both present in the exact deployed revision at the repository root.
- [ ] Confirm their version/schema correspondence using the model card and artifact metadata.
- [ ] Review build and startup logs for missing-artifact warnings. The Blueprint does not train or fetch model artifacts during build.

## 4. Configure external integrations as needed

- [ ] **Google Maps:** set the API key and restrict it to the required APIs and browser referrers. The key is rendered into browser code; restriction is important.
- [ ] **Weather:** configure the OpenWeatherMap key if weather context is required.
- [ ] **Email:** configure SendGrid credentials and a sender address accepted by the provider; verify the configured sender in that provider.
- [ ] **Push alerts:** configure the VAPID public/private key pair and contact subject if browser push is enabled.
- [ ] **Monitoring:** configure Sentry only if it is part of the deployment’s monitoring plan.

## 5. Deploy and verify

- [ ] Review `render.yaml`: the declared web build installs dependencies, collects static files, and runs migrations; the start command launches Gunicorn.
- [ ] Apply the Blueprint or equivalent configuration in the provider. The repository does not confirm that an external database, worker, Redis, or secrets are provisioned.
- [ ] Confirm build completion and migration success in provider logs.
- [ ] Request `/healthz/` and confirm the response indicates success; this endpoint checks the database connection.
- [ ] Confirm startup logs contain no missing ML artifact warning.
- [ ] Submit a route prediction and verify the response in the deployed application.
- [ ] Trigger the selected scheduled-work mode and inspect its logs/result. For the GitHub Actions mode, run the workflow manually and confirm it can reach `/tasks/run/` using configured secrets. Do not infer that collection is running from a successful scheduled endpoint call.
- [ ] Verify email, push, and monitoring only if configured; use non-sensitive test accounts and avoid logging credentials.

## Repository configuration references

- Render web service: [`render.yaml`](render.yaml)
- CI checks: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
- Scheduled endpoint workflow: [`.github/workflows/scheduled-tasks.yml`](.github/workflows/scheduled-tasks.yml)
- Django configuration: [`TrafficPro/settings.py`](TrafficPro/settings.py)
- Collector process: [`TrafficApp/management/commands/start_collector.py`](TrafficApp/management/commands/start_collector.py)
