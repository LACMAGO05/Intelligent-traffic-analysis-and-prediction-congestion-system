# TrafficPro — System Architecture

> **Status:** Understanding-only. No production code was modified to produce this document.
> **Generated:** 2026-05-30
> **Companion docs:** [REPOSITORY_MAP.md](REPOSITORY_MAP.md) · [BACKEND_FLOW.md](BACKEND_FLOW.md) · [FRONTEND_FLOW.md](FRONTEND_FLOW.md) · [ML_PIPELINE.md](ML_PIPELINE.md) · [DATABASE_STRUCTURE.md](DATABASE_STRUCTURE.md) · [THIRD_PARTY_SERVICES.md](THIRD_PARTY_SERVICES.md)

## 1. Purpose

TrafficPro is a Django web application that predicts road congestion and travel time for Buea, Cameroon, by **fusing three independent signals** — Google Maps live/predicted routing, a trained gradient-boosted ML model, and local contextual intelligence (weather, holidays, school/office rush, recurring events). It serves three roles (Admin, Analyst, Commuter) through a chat-style prediction UI, persists conversations, and feeds an analytics dashboard.

This document describes the **whole-system shape**: the runtime processes, how they interact, what they depend on, and where the architectural risks and scaling limits lie.

## 2. High-Level Topology

```
                       ┌──────────────────────────────────────────────┐
                       │                   CLIENT                       │
                       │  Browser: Django templates + static/index.js   │
                       │  Google Maps JS SDK (Places) + Leaflet         │
                       └───────────────────────┬────────────────────────┘
                                                │ HTTPS (page loads + AJAX JSON)
                                                ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │                        WEB PROCESS (Gunicorn + WhiteNoise)                    │
   │                                                                              │
   │   Django middleware → URLconf → Views (TrafficApp.views)                     │
   │      auth/RBAC · predict · chat-history · analytics · contact                │
   │                              │                                               │
   │                              ▼                                               │
   │             HybridPredictionService (orchestrator)                           │
   │        ┌───────────────┬───────────────────┬──────────────────────┐         │
   │        ▼               ▼                   ▼                      ▼         │
   │  GoogleMapsService  ModelService    traffic_collector ctx libs   email_svc  │
   │   (Directions)      (.pkl + enc)    weather/holiday/school/event  (SendGrid) │
   └────────┬───────────────┬───────────────────┬──────────────┬─────────────────┘
            │               │                   │              │
            ▼               ▼                   ▼              ▼
     Google Maps API   model artifacts   OpenWeatherMap   SendGrid API
                       (local files)     holidays(CM lib)
            │
   ┌────────┴───────────────────────────────────────────────────────────────────┐
   │                     WORKER PROCESS (manage.py start_collector)                │
   │   APScheduler (adaptive interval) → TrafficCollector → same ctx libs          │
   │      → CSVManager → google_traffic_data_v2.csv                                │
   └───────────────────────────────────────────────────────────────────────────────┘

   PERSISTENCE:  PostgreSQL (chat, auth, sessions)   ·   CSV (training/log data)
                 Supabase (chat_history → analytics reads)
```

## 3. Logical Layers

| Layer | Modules | Role |
|---|---|---|
| **Presentation** | `templates/`, `static/index.js`, `static/js/*` | Server-rendered HTML + a vanilla-JS controller doing AJAX prediction/chat |
| **HTTP / routing** | `TrafficPro/urls.py`, `TrafficApp/urls.py`, middleware | Route resolution, CSRF, sessions, security headers, static serving |
| **Application / views** | `TrafficApp/views.py`, `rbac.py`, `forms.py` | Thin request handlers; auth, RBAC gating, rate limiting |
| **Domain / services** | `TrafficApp/services/*` | Prediction orchestration, Google client, model inference, email |
| **Context / collection library** | `traffic_collector/*` | Shared context providers + background data collection |
| **Persistence** | `models.py` + Postgres, CSV files, Supabase | Chat data (relational), training data (file), analytics (BaaS) |
| **Integrations** | Google Maps, OpenWeatherMap, SendGrid, Supabase, `holidays` | External capability providers |

The key architectural seam is the **service layer**: views never call external APIs or the model directly — they delegate to `HybridPredictionService`, which is the single composition point.

## 4. Runtime Processes

1. **Web process** — Gunicorn serving `TrafficPro.wsgi`; handles all user requests; static assets via WhiteNoise. Stateless apart from DB-backed sessions.
2. **Collector worker** — `python manage.py start_collector`; long-lived process running an in-memory APScheduler loop. **Not** started by the web dyno; must be a separate worker.
3. **Offline training** — `Model_training.ipynb`, run manually by a data scientist; consumes the CSV and emits model artifacts.

These three are loosely coupled and communicate only through shared stores (CSV, model files, DB).

## 5. Interactions

- **Synchronous request path:** Browser → view → `HybridPredictionService` → (Google Directions HTTP call + local model inference + context lookups, some of which make their own HTTP calls to OpenWeatherMap) → JSON response. The whole chain is blocking and inline within the web request.
- **Persistence on predict:** each successful prediction writes a CSV row *and* creates `ChatThread`/`ChatMessage` rows in Postgres.
- **Background path:** scheduler tick → collector → Google + context → CSV append (dedupe by timestamp+route).
- **Analytics path:** Admin/Analyst → `analytics_view` → Supabase `chat_history` SELECT → aggregate.

## 6. Dependencies

- **Framework:** Django 6.0.3, Gunicorn 23, WhiteNoise 6.9.
- **Data/ML:** pandas (unpinned), plus unlisted runtime imports `numpy`, `joblib`, the model library (XGBoost), `apscheduler`, `holidays`.
- **External services:** Google Maps Directions + JS/Places, OpenWeatherMap, SendGrid, Supabase. (See [THIRD_PARTY_SERVICES.md](THIRD_PARTY_SERVICES.md).)
- **Config:** `python-dotenv` + `.env`; Postgres via `dj-database-url`.

## 7. Architectural Risks

1. **Synchronous external calls inside the request** — a prediction blocks on Google Directions (10s timeout) *and* OpenWeatherMap (10s) sequentially. Any slow upstream directly inflates user latency and ties up a Gunicorn worker.
2. **No caching layer** — weather, holidays, and (largely static) route geometry are re-fetched on every prediction; django-ratelimit also defaults to in-memory/local cache, which is per-process and ineffective across multiple Gunicorn workers/dynos.
3. **In-memory scheduler state** — APScheduler runs in a single worker process with no persistence; a restart loses schedule state, and running >1 worker would double-collect.
4. **Dual write of the same CSV** — `predict_view` (7-col) and `CSVManager` (20-col) append to `google_traffic_data_v2.csv` with different schemas, risking a malformed training file. (See [ML_PIPELINE.md](ML_PIPELINE.md).)
5. **`DEBUG` referenced but never assigned** in `settings.py` (`if not DEBUG:` at line 145) — latent `NameError`/security-toggle ambiguity at startup.
6. **Model/format drift** — code and docs say "LightGBM"; artifacts are XGBoost; the loaded file is `traffic_model.pkl`. Operational confusion about which artifact is canonical.
7. **Tight web↔collector coupling** — the web request path imports `traffic_collector` modules; a change to the collection library can break inference.
8. **Secret hygiene** — `TrafficPro/.env` exists in the working tree; ensure it is git-ignored and rotated.

## 8. Scalability Concerns

- **Horizontal web scaling is constrained** by: (a) in-process rate-limit cache (needs shared Redis/Memcached); (b) the single-instance collector assumption; (c) local-file model + CSV reads, which don't exist on additional dynos with ephemeral filesystems.
- **Filesystem-backed training data** does not survive container restarts on PaaS (Render/Heroku ephemeral disk) — collected CSV rows can be silently lost; this should move to object storage or a table.
- **Model loaded per-request** — `ModelService.__init__` calls `joblib.load` every time `HybridPredictionService` is instantiated (once per prediction). Loading a ~1 MB model on every request adds avoidable latency and memory churn; a process-level singleton/cache is the standard remedy.
- **CSV duplicate check reads the file** (`csv_manager._is_duplicate` reads last 100 lines each append) — fine at small scale, but O(file) growth and not concurrency-safe across processes.
- **No async/queue** — long predictions and email sends happen inline; a task queue (Celery/RQ) would decouple latency-sensitive paths.
- **Database** is the most scalable component (managed Postgres), but chat history has no pagination/retention strategy and `ChatMessage.response` stores full prediction JSON blobs that will grow unbounded.
