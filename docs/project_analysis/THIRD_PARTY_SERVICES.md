# TrafficPro — Third-Party Services

> **Status:** Understanding-only. No production code or credentials were modified.
> **Generated:** 2026-05-30
> **Scope:** External APIs/SDKs and libraries the system depends on, how they are used, and the associated risks.

## 1. Purpose

TrafficPro composes several external services to deliver predictions. This document inventories each integration, where it is used, what it depends on, and the operational/security risks it introduces.

## 2. Integration Inventory

| Service | Used by | Auth / config | Purpose |
|---|---|---|---|
| **Google Maps Directions API** | `services/google_maps_service.py`, `utils.py`, `traffic_collector/collector.py` | `GOOGLE_CLIENT_SECRET` (query param `key`) | Route distance, duration, traffic duration, polyline, alternatives, per-step delays |
| **Google Maps Distance Matrix API** | `TrafficApp/data_collector.py` (legacy) | `GOOGLE_CLIENT_SECRET` | Older route-metric collection (superseded) |
| **Google Maps JS SDK + Places** | `predict.html`, `static/index.js` | same key, embedded in page | Map render + origin/destination autocomplete (Buea-biased) |
| **OpenWeatherMap** | `traffic_collector/weather_service.py` | `OPENWEATHER_API_KEY` | Current Buea weather → `weather_condition`, `rainfall_status` |
| **SendGrid** | `services/email_service.py`, `forms.py` | `SENDGRID_API_KEY`, `DEFAULT_FROM_EMAIL` | Verification, welcome, password-reset, contact emails |
| **Supabase** | `views.analytics_view` | `SUPABASE_URL`, `SUPABASE_KEY` | Read `chat_history` for analytics aggregates |
| **`holidays` (PyPI)** | `traffic_collector/holiday_service.py` | none | Cameroon public-holiday calendar |
| **APScheduler** | `traffic_collector/scheduler.py` | none | Adaptive background scheduling of collection |
| **django-ratelimit** | `views.py` | cache backend | Per-IP / per-user request throttling |
| **WhiteNoise** | middleware / static storage | none | Static file serving |
| **Leaflet (unpkg CDN)** | `predict.html` | none | Map rendering library |

## 3. Per-Service Detail

### Google Maps (Directions + JS/Places)
- **Server:** `requests.get` to `directions/json` with `traffic_model=best_guess`, `alternatives=True`, 10s (service) / 15s (collector) timeout. Locations are normalized to append `, Buea, Cameroon`.
- **Client:** SDK loaded with the key inlined into `predict.html` (`?key={{ google_maps_api_key }}`), which comes from `GOOGLE_CLIENT_SECRET`.
- **Dependency:** all prediction and collection flows hard-depend on this API and a valid, billing-enabled key.

### OpenWeatherMap
- `weather_service.py` calls `data/2.5/weather?q=Buea,CM`. Handles 401 (returns `"Unauthorized"`) and missing key (returns `"Unknown"`) gracefully rather than failing the prediction.

### SendGrid
- `_send_email_safe()` wraps the SendGrid v3 client; `os.getenv("SENDGRID_API_KEY")` read at call time. Used for the OTP/verification, welcome, password-reset, and contact flows. Replaces Django's SMTP backend for transactional mail.

### Supabase
- Client created at **module import** in `views.py` from `settings.SUPABASE_URL/KEY`. Only a **read** (`select("*")`) is observed; no writer found in the reviewed code (see [DATABASE_STRUCTURE.md](DATABASE_STRUCTURE.md) §5).

### Libraries
- `holidays` (Cameroon), `apscheduler` (scheduler), `django-ratelimit` (throttle), `whitenoise` (static), `pandas`/`numpy`/`joblib`/XGBoost (ML), `dj-database-url`, `python-dotenv`, `cryptography`, `PyJWT`. Several ML libs are **not pinned** in `requirements.txt`.

## 4. Configuration Surface (env vars)

`DJANGO_SECRET_KEY, DATABASE_URL, ALLOWED_HOSTS, DEBUG, GOOGLE_CLIENT_SECRET, OPENWEATHER_API_KEY, SENDGRID_API_KEY, DEFAULT_FROM_EMAIL, SUPABASE_URL, SUPABASE_KEY, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD` — loaded from `.env` via `python-dotenv`. `DJANGO_SECRET_KEY` is mandatory (crashes if absent); `DEBUG` is in `.env` but **not read** into `settings.py`.

## 5. Interactions & Dependencies

```
predict request ──> GoogleMapsService (Google Directions) ──┐
              └────> context: WeatherService (OpenWeatherMap)│──> fused prediction
                            HolidayService (holidays lib)     │
auth/contact   ──> SendGrid                                   │
analytics      ──> Supabase (read)                            │
collector tick ──> Google Directions + OpenWeatherMap ──> CSV ┘
client page    ──> Google Maps JS/Places + Leaflet (CDN)
```

- The **synchronous prediction path** touches Google + OpenWeatherMap inline (blocking).
- The **client** depends on Google's CDN/SDK and unpkg (Leaflet CDN).
- **Single shared Google key** is used across Directions (server) and JS/Places (client).

## 6. Risks

1. **Exposed Google key with confusing name** — `GOOGLE_CLIENT_SECRET` is actually a Maps **API key** rendered into client HTML. It must be **HTTP-referrer + API restricted** in the Google console or it can be scraped and abused (billing exposure). The misleading variable name invites mishandling.
2. **No retry/circuit-breaker/cache** on external calls — a Google or OpenWeatherMap outage/slowness directly fails or stalls predictions; weather/holiday data are re-fetched every request.
3. **Quota & billing exposure** — Directions API is metered; the collector hits ~60 routes per cycle (as often as every 10 min in rush hours) plus per-user predictions, with no observed quota guard or cost cap.
4. **Secrets in `.env` in working tree** — ensure git-ignored and rotated; keys for Google, SendGrid, OpenWeatherMap, Supabase all present.
5. **`.env` `DEBUG` not honored** — security toggles in `settings.py` gate on an undefined `DEBUG`, risking either a `NameError` or unintended dev posture in production.
6. **Module-import-time Supabase client** — a bad key breaks the entire `views` import, not just analytics.
7. **CDN supply chain** — `unpkg.com/leaflet` without version pin or SRI.
8. **Email deliverability single point** — all transactional mail depends on SendGrid; failures are logged but not surfaced/retried.

## 7. Scalability Concerns

- **Third-party rate limits/quotas** are the primary scaling ceiling: Google Directions and OpenWeatherMap costs grow with both prediction volume and collector frequency × route count (~60). Caching context (weather per ~10 min, holidays per day, route geometry) would cut calls dramatically.
- **No shared cache backend** — django-ratelimit and any future response cache need Redis/Memcached to work across multiple workers/dynos.
- **Synchronous fan-out** to external services per request limits per-worker throughput; moving collection and email to a task queue, and adding response caching, would decouple user latency from upstream APIs.
- **Single region/city assumption** — Buea-specific normalization and a single weather city; multi-city scaling multiplies external-call volume and requires parameterization.
- **Collector politeness** is a fixed `time.sleep(1)` between routes rather than adaptive backoff; under quota pressure this neither protects quota effectively nor scales to larger route sets.
