# TrafficPro project overview

TrafficPro is a Django application for route-based traffic analysis in Buea, Cameroon. It combines Google Maps route and traffic data with a LightGBM congestion classifier and local context to present route estimates and traffic indicators. The system is intended for people planning trips around Buea, including commuters, drivers, students, and local businesses.

## What the application provides

- Route analysis with Google Maps traffic information and a traffic pressure score.
- Context signals from weather, school schedules, holidays, and local events.
- A prediction interface with saved history and an analytics view.
- Account, device verification, and route-alert flows.

The classifier predicts **Free-flow** or **Congested**. It does not predict the UI's **High** category; that category is surfaced from Google's live traffic data. The model is one input to the hybrid prediction service, not an independent guarantee of travel time or congestion accuracy.

## Implementation at a glance

- **Web application:** Django, server-rendered templates, and JavaScript.
- **Persistence:** PostgreSQL through `DATABASE_URL`; Django models store application records, including prediction logs and collected traffic records.
- **Prediction:** Google Maps Directions data, a binary LightGBM model, and shared context providers in `traffic_context/`.
- **Collection and scheduled work:** `traffic_collector/` contains the collector and APScheduler implementation. The checked-in GitHub Actions workflow calls `/tasks/run/` for gridlock alert forecasting and outbox processing; that endpoint does not run traffic collection.
- **External services:** Google Maps, OpenWeatherMap, and SendGrid integrations are configured in `TrafficPro/settings.py`. Redis, Sentry, and VAPID settings are also supported/configured there. Supabase settings remain in the code, but this overview does not assign them an active runtime role.

## Further reading

See the repository [README](../README.md) for the documentation index. Start with [local setup](SETUP.md) and [environment configuration](CONFIGURATION.md); the architecture, database, ML, and deployment guides cover their respective areas. Historical analysis and phase notes are indexed in the [project analysis archive](project_analysis/README.md); use them as records of prior investigations and changes, not as the authoritative description of the current implementation.
