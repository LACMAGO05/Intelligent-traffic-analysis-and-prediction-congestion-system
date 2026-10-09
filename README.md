# TrafficPro

TrafficPro is a Django application for route-based traffic analysis in Buea, Cameroon. It combines Google Maps route data, a LightGBM congestion classifier, and local context such as weather, school schedules, holidays, and events to present route estimates and traffic indicators.

The application also includes account and device verification flows, saved prediction history, analytics, and route alerts. The model predicts a binary congestion class; the UI's **High** classification comes from Google's live traffic data rather than the model.

## Project documentation

- [Local development setup](docs/SETUP.md)
- [Environment configuration](docs/CONFIGURATION.md)
- [Project overview](docs/PROJECT_OVERVIEW.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Database](docs/DATABASE.md)
- [Machine-learning pipeline](docs/ML_PIPELINE.md)
- [Deployment overview](docs/DEPLOYMENT.md)
- [Deployment checklist](DEPLOYMENT_CHECKLIST.md)
- [Current model card](ml_artifacts/MODEL_CARD.md)
- [Historical project analysis archive](docs/project_analysis/README.md)

## Repository landmarks

- `TrafficApp/` — Django views, models, templates, services, and management commands.
- `traffic_context/` — shared route, weather, calendar, and ML feature logic.
- `traffic_collector/` — traffic collection and scheduler implementation.
- `TrafficPro/` — Django project settings and entry points.
- `.github/workflows/` — CI checks and the scheduled-task endpoint trigger.

The linked deployment guide and checklist describe the current deployment materials. The scheduled-task workflow invokes gridlock alert forecasting and outbox processing; traffic collection is started separately by the collector command when a worker is configured.
