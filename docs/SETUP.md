# Local development setup

This guide describes a local Ubuntu development setup based on the current Django settings and dependency file. It has not been executed as part of this documentation change; verify it in your environment and report any missing prerequisites.

## Prerequisites

- Ubuntu with Python 3.12 or newer. The checked-in deployment configuration and CI workflow use Python 3.12; Django 6 requires a compatible Python version.
- PostgreSQL available locally, or a PostgreSQL-compatible database URL you are authorized to use.
- Git and a shell.

Google Maps credentials are needed for live route predictions and traffic collection. Weather uses OpenWeatherMap when configured and returns an unknown-weather fallback when its key is absent. Email and push functionality require their respective provider configuration; the core project can be explored without configuring every integration.

## Create the environment

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create a local PostgreSQL database and role using your local PostgreSQL administration workflow. Put the connection URL and a development-only Django secret in a root `.env` file. `TrafficPro/settings.py` loads that file with `python-dotenv`, and `.gitignore` excludes `.env` files. Use the variable reference in [CONFIGURATION.md](CONFIGURATION.md); never commit real credentials.

For local development, set `DEBUG=True` and include `localhost` and `127.0.0.1` in `ALLOWED_HOSTS`. Use the actual local database URL in `DATABASE_URL`. A Google Maps API key is needed for live route predictions; restrict that key according to the Google Cloud project’s usage because the application exposes it to the browser map client.

## Initialize and start Django

With the virtual environment active and required local settings configured:

```bash
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open the local address printed by Django. The health endpoint is `/healthz/`; it checks the database connection as well as application responsiveness. The project’s current model files are `traffic_model.pkl` and `feature_schema.json` at the repository root. Startup checks warn if either is missing; prediction quality and availability depend on those artifacts and the external Google Maps service.

## Optional local processes

- Run `python manage.py start_collector` only when you intend to collect traffic data and have configured its database and external API dependencies. It runs a persistent scheduler and is separate from `runserver`.
- The `/tasks/run/` endpoint is for secret-authenticated scheduled gridlock-alert forecasting and outbox processing. It does not start or run the traffic collector.
- Additional model lifecycle commands are described in [ML_PIPELINE.md](ML_PIPELINE.md). Training requires an input dataset; the default CSV path in the command may not be present in every checkout.

## Quality checks

The repository’s CI workflow documents the checks used in automation: migration consistency, Django system checks, migrations, and the test suite. See [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). These commands have not been run as part of this guide’s preparation.
