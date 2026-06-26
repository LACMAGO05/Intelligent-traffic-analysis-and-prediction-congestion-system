# TrafficPro — Repository Map

> **Status:** Understanding-only architecture map. No application code was modified to produce this document.
> **Generated:** 2026-05-30
> **Project:** AI-powered hybrid traffic prediction system for Buea, Cameroon.

TrafficPro predicts road congestion and travel time for routes in Buea by **fusing three signals**:

1. **Google Maps Directions API** — live/predicted route duration, distance, polyline, per-segment delays.
2. **A trained gradient-boosted model** — congestion class (Low/Medium/High) + probabilities.
3. **Local contextual intelligence** — weather, public/school holidays, school & office rush hours, recurring local events.

These are combined by a **Hybrid Prediction Service** that applies expert "ETA adjustment" rules and produces an explainable result (the "Smart ETA", a traffic-pressure score, risk level, and human-readable reasoning).

---

## 1. Top-Level Folder Structure

```
TrafficPro/                          # repo root (also the Django BASE_DIR)
├── manage.py                        # Django entry point
├── Procfile                         # Render/Heroku: `web: gunicorn TrafficPro.wsgi`
├── pythonanywhere_wsgi.py           # Alternate WSGI bootstrap (PythonAnywhere)
├── requirements.txt                 # Python dependencies
├── db.sqlite3                       # Local SQLite (DB is actually Postgres via DATABASE_URL)
│
├── TrafficPro/                      # Django PROJECT (settings / urls / wsgi / asgi)
│   ├── settings.py                  # Central config, route catalogue, security, logging
│   ├── urls.py                      # Root URLconf → admin + TrafficApp
│   ├── wsgi.py / asgi.py            # Server entry points
│   └── .env                         # Secrets (NOT for production source control)
│
├── TrafficApp/                      # Django APP (the web application)
│   ├── views.py                     # All HTTP views (auth, predict, chat, analytics, contact)
│   ├── urls.py                      # App URL routes
│   ├── models.py                    # ChatThread, ChatMessage (ORM)
│   ├── forms.py                     # ContactForm, CustomPasswordResetForm
│   ├── rbac.py                      # Role-based access control (Groups + decorator)
│   ├── utils.py                     # OTP gen + direct Google Directions helpers
│   ├── context_processors.py        # Injects contact form into all templates
│   ├── data_collector.py            # LEGACY standalone collector (Distance Matrix API)
│   ├── admin.py / apps.py / tests.py
│   ├── management/commands/
│   │   └── start_collector.py       # `manage.py start_collector` → runs scheduler
│   ├── services/                    # Prediction-time service layer
│   │   ├── hybrid_prediction_service.py   # ORCHESTRATOR
│   │   ├── google_maps_service.py         # Directions API client (route details)
│   │   ├── model_service.py               # Loads .pkl model + label encoder, predicts
│   │   └── email_service.py               # SendGrid email (verify/welcome/reset/contact)
│   ├── migrations/                  # 0001_initial, 0002 chat models
│   ├── static/                      # index.js, loader/ui-enhancements js+css, images
│   └── templates/                   # landing, sign_in/up, otp, predict, analytics, 403,
│                                    #   includes/*, registration/* (password reset)
│
├── traffic_collector/              # BACKGROUND data-collection + context PIPELINE
│   ├── scheduler.py                 # APScheduler adaptive interval scheduler
│   ├── collector.py                 # TrafficCollector: fetch + enrich + persist
│   ├── csv_manager.py               # Append rows to google_traffic_data_v2.csv
│   ├── weather_service.py           # OpenWeatherMap client
│   ├── holiday_service.py           # `holidays` lib (Cameroon)
│   ├── school_service.py            # School holiday / rush-hour rules
│   ├── event_detector.py            # Weekly/fixed events + office rush rules
│   ├── congestion.py                # Ratio → Low/Medium/High classifier
│   ├── pressure_score.py            # 0–100 "traffic pressure" composite score
│   ├── feature_engineering.py       # Cyclical hour, weekend, peak-hour features
│   └── logger.py                    # Shared file/console logger
│
├── Model_training.ipynb            # Offline model training notebook
├── traffic_model.pkl               # Model loaded at runtime by ModelService
├── model_XGBoost.pkl               # XGBoost model artifact
├── traffic_xgb_model.json          # XGBoost model (JSON/booster export)
├── label_encoder.pkl               # Encodes congestion classes (Low/Medium/High)
├── google_traffic_data_v2.csv      # Collected + prediction-time training/log data
│
├── staticfiles/                    # `collectstatic` output (WhiteNoise-served)
├── logs/                           # collector.log, django.log
└── docs/                           # Existing docs + this project_analysis/ folder
```

---

## 2. Major Modules / Components

| Component | Location | Responsibility |
|---|---|---|
| **Django project config** | `TrafficPro/` | Settings, routing, WSGI/ASGI, security, route catalogue, logging |
| **Web app (views & routing)** | `TrafficApp/views.py`, `urls.py` | Request handling for auth, prediction, chat history, analytics, contact |
| **Auth & RBAC** | `views.py`, `rbac.py`, `forms.py` | Signup w/ OTP, login/logout, password reset, role gating |
| **Prediction service layer** | `TrafficApp/services/` | Orchestrates Google + ML + context into a hybrid prediction |
| **ML model service** | `services/model_service.py` | Loads pickle model + encoder, builds feature vector, predicts congestion |
| **Context/collection pipeline** | `traffic_collector/` | Background data collection + reusable context providers (weather/holiday/school/event) |
| **Persistence** | `models.py`, Postgres, `*.csv` | Chat threads/messages in DB; raw traffic rows in CSV; analytics in Supabase |
| **Frontend** | `templates/`, `static/index.js` | Server-rendered pages + AJAX chat-style prediction UI, Google Places autocomplete, maps |
| **Email** | `services/email_service.py` | SendGrid transactional email |
| **External analytics store** | Supabase (`views.analytics_view`) | Reads `chat_history` table for analytics dashboard |

---

## 3. Backend Architecture

**Framework:** Django 6.0.3 (project name `TrafficPro`, single app `TrafficApp`).

**Request lifecycle (server-rendered + AJAX hybrid):**

```
Browser ──HTTP──> WhiteNoise/Gunicorn ──> Django MIDDLEWARE stack ──> URLconf ──> View
                                                                                   │
                          ┌────────────────────────────────────────────────────────┤
                          │                                                          │
                   (page render)                                              (JSON / AJAX)
                   render(template)                                    JsonResponse(prediction)
```

**Middleware (order, from `settings.py`):**
`SecurityMiddleware → WhiteNoise → Sessions → Common → CSRF → Authentication → Messages → XFrameOptions`.

**View layer (`TrafficApp/views.py`):** function-based views (+ one CBV for password reset). Cross-cutting concerns are applied via decorators:
- `@ratelimit` (django-ratelimit) — per-IP/per-user throttling on auth & predict.
- `@role_required(...)` / `@login_required` — access control (see §6).

**Service layer (`TrafficApp/services/`):** the views stay thin and delegate prediction work to `HybridPredictionService`, which composes the Google Maps client, the ML model service, and the `traffic_collector` context providers. This is the core architectural seam — see §10.

**Notable backend observations (understanding-only, not fixes):**
- `settings.py` line 145 references `if not DEBUG:` but `DEBUG` is **never assigned** in `settings.py` (it exists in `.env` but is not read via `os.getenv`). This is a latent `NameError` risk at startup depending on environment.
- `ModelService` loads `traffic_model.pkl` and the code/docstrings call it a **"LightGBM"** model, while the artifacts present are **XGBoost** (`model_XGBoost.pkl`, `traffic_xgb_model.json`). Naming is inconsistent across code, docs, and artifacts.
- Frontend (`static/index.js`) calls `/transcribe/` and `/alerts/`, but **no matching routes exist** in `urls.py` (alerts/predict-alert routes are commented out). These are dead/aspirational endpoints.
- `requirements.txt` does not pin several runtime imports used by the code: `joblib`, `numpy`, the model lib (`xgboost`/`lightgbm`), `apscheduler`, `holidays`. (`pandas` is present, unpinned.)
- `signup_view` stores OTP hash in the session but does **not** appear to send the OTP email in the view itself (`send_verification_email` is imported but not invoked in the shown flow).

---

## 4. Frontend Architecture

**Style:** Server-side rendered Django templates + a single vanilla-JS controller; no SPA framework.

```
templates/
├── base.html                 # Shared shell; includes header/footer/loader/bottom_nav
├── landing.html              # Public marketing/landing page
├── sign_in.html / sign_up.html / otp.html
├── predict.html              # Main app screen (chat-style prediction UI + map)
├── analytics.html            # Admin/Analyst dashboard
├── 403.html                  # Permission denied
├── includes/                 # header, footer, bottom_nav, loader, progress_bar,
│                             #   skeletons, contact
└── registration/             # Django password-reset templates + reset email
```

**Static / behaviour (`static/index.js`, 742 lines):**
- `predictTraffic()` — gathers origin/destination/day/time, `fetch("/predict/", POST)` with `X-CSRFToken`, renders the bot reply via `constructBotReply()`.
- Chat history: `loadChatThreads()` → `GET /chat-history/`; `loadThread(id)` → `GET /chat-history/<uuid>/`; `startNewAnalysis()`.
- `initAutocomplete()` — Google Maps **Places Autocomplete** biased to Buea (lat 4.1522, lng 9.2314); map/polyline rendering uses the Google JS SDK (API key injected by `predict_view`).
- Helpers: `getCookie`/`getCSRFToken` for CSRF; `displayMessage`; voice-input stubs (`startRecording`/`sendAudioToDjango` → `/transcribe/`, currently unrouted); `fetchAlerts()` polling `/alerts/` every 120s (currently unrouted).
- UI polish: `static/js/loader.js`, `static/js/ui-enhancements.js`, matching CSS. Templates use Tailwind utility classes (see form widget classes in `forms.py`).

**CSRF model:** Django CSRF cookie read in JS and sent as `X-CSRFToken` header on POST `fetch` calls.

---

## 5. Machine Learning Pipeline

### Training (offline)
- `Model_training.ipynb` trains a gradient-boosted classifier on `google_traffic_data_v2.csv`.
- Output artifacts: `traffic_model.pkl` / `model_XGBoost.pkl` / `traffic_xgb_model.json` + `label_encoder.pkl` (encodes `Low/Medium/High`).

### Inference (runtime — `services/model_service.py`)
```
features_dict ──> pd.DataFrame([...]) ──> one-hot expand categoricals
              ──> add derived (is_weekend, is_morning_rush, prev_hour_speed default)
              ──> reindex to fixed `feature_names` order (fill_value=0)
              ──> model.predict(X) -> class probabilities
              ──> argmax + label_encoder.inverse_transform
              ──> {congestion_level, probabilities{}, confidence, status}
```

**Expected feature schema (`ModelService.feature_names`):**
`distance_km, hour, day_of_week, holiday_indicator, school_holiday_indicator, school_hours_indicator, working_hours_indicator, office_rush_hour_indicator, event_indicator, event_severity, is_weekend, is_morning_rush, prev_hour_speed`, plus one-hot route columns (`route_Malingo to UB Junction`, `route_Mile 17 to Malingo`, `route_UB Junction to Check Point`), weather one-hots (`weather_condition_{Clouds,Drizzle,Rain,Thunderstorm}`), `rainfall_status_Rain`, `event_type_Market Activity`.

> The training routes encoded in the model (3 one-hot routes) are far narrower than the ~60-route catalogue the collector polls (`settings.TRAFFIC_ROUTES`). Unknown routes simply fall to all-zero one-hots (`fill_value=0`).

### Hybrid fusion (`services/hybrid_prediction_service.py`)
The model output is **not** returned directly. `HybridPredictionService` blends it with Google's live duration and contextual rules:

```
get_hybrid_prediction(origin, destination, departure_time):
  1. GoogleMapsService.get_route_details()      → distance, normal/traffic duration, polyline, alternatives
  2. _gather_context(target_dt)                 → weather + holiday + school + event + office indicators
  3. _prepare_ml_features(route, context)       → feature dict (+ congestion + pressure score)
  4. ModelService.predict(features)             → {congestion_level, probabilities, confidence}
  5. _apply_hybrid_logic(google, model, context):
       - Smart ETA Adjustment Engine: additive minute deltas for
         model-vs-Google disagreement, rainfall, school rush, office rush;
         small reduction when pressure is very low.
       - PressureScoreCalculator → 0–100 score → risk level / stability.
       - Builds XAI "ai_reasoning", "smart_recommendation", "adjustment_reasons".
  → rich JSON: travel_time (smart ETA), congestion, confidence, probabilities,
    pressure score/level/trend, context_analysis, risk_analysis, polyline, segments_delay.
```

---

## 6. Authentication & Authorization Flow

**Identity:** Django's built-in `User` model (no custom user model).

**Signup (`signup_view` + `verify_otp`):**
```
POST /signup/  → validate password length (>=12)
               → generate 6-digit OTP, sha256-hash it
               → stash {username, email, password_hash(make_password),
                        otp_hash, otp_created_at, otp_attempts} in SESSION
POST /otp/     → expiry check (>600s), attempt cap (>=5),
               → compare sha256(entered_otp) to stored hash
               → on success: create User(password=stored hash) → redirect login
```
Rate limited: signup `3/h` per IP, OTP `5/10m` per IP. (OTP delivery email path noted in §3.)

**Login/logout:** `signin_view` (`authenticate`/`login`, `5/m` per IP) → redirect `predict`; `logout_view` → `landing`.

**Password reset:** `CustomPasswordResetView` + `CustomPasswordResetForm.save()` builds a `uid/token` link and sends it via **SendGrid** (`send_password_reset_email`), bypassing Django's SMTP email path. Confirm/done handled by Django's built-in auth views + `registration/` templates.

**RBAC (`rbac.py`) — Django Groups:**
| Role | Capabilities |
|---|---|
| **Admin** | Full access (predict, analytics, user mgmt, retrain) |
| **Analyst** | Analytics + prediction |
| **Commuter** | Prediction only (default for new users) |

- `@role_required(*roles)` wraps `@login_required`; superusers bypass; AJAX requests get `403 JSON`, page requests get `403.html`.
- `get_user_role()` + `role_context()` context processor expose `{{ user_role }}` to every template for nav show/hide.
- Gating in views: `predict_view` → Admin/Analyst/Commuter; `analytics_view` → Admin/Analyst; chat views → `@login_required`.

---

## 7. Database Structure

**Engine:** PostgreSQL in deployment via `dj_database_url.parse(os.getenv("DATABASE_URL"))`. `db.sqlite3` present for local dev (SQLite block in settings is commented out). `TIME_ZONE=Africa/Douala`, `USE_TZ=True`.

**App models (`TrafficApp/models.py`):**
```
ChatThread
  id          UUID (pk)
  user        FK → auth.User (related_name=chat_threads, CASCADE)
  title       Char(255)
  created_at  DateTime (auto)

ChatMessage
  id          BigAuto (pk)
  thread      FK → ChatThread (related_name=messages, nullable, CASCADE)
  user        FK → auth.User (related_name=chat_messages, CASCADE)
  message     Text          # human prompt e.g. "From X to Y"
  response    JSONField     # full hybrid prediction JSON
  timestamp   DateTime (auto)
```
Plus all standard Django tables (auth user/group/permission, sessions, admin log, contenttypes). Migrations: `0001_initial`, `0002_chatthread_chatmessage_thread`.

**Non-relational / file stores:**
- **CSV** `google_traffic_data_v2.csv` — written by both the background collector (`csv_manager.py`, full feature schema) and by `predict_view` (a *narrower* 7-column schema: `route, distance, hour, day, travel_time, speed, congestion`). The two writers use **different column sets** against the same file.
- **Supabase** `chat_history` table — read by `analytics_view` for aggregate counts (High/Medium/Low). (Write path to Supabase not present in the reviewed views.)

---

## 8. Traffic Collection Pipeline

Run manually/as a worker via `python manage.py start_collector`.

```
start_collector (mgmt command)
        │
        ▼
TrafficScheduler (APScheduler BackgroundScheduler)
   ├─ get_adaptive_interval():  rush 6–9 & 16–20 → 10min · night 22–6 → 60min · else 30min
   ├─ runs collector.collect_all_routes() immediately, then on interval
   └─ reschedules itself when the interval band changes
        │
        ▼
TrafficCollector.collect_all_routes()
   ├─ gather shared context once per cycle:
   │     WeatherService (OpenWeatherMap) · HolidayService (holidays/CM)
   │     SchoolService · EventDetector (events + office rush)
   └─ for each route in settings.TRAFFIC_ROUTES (~60 Buea route pairs):
         fetch_google_traffic() → Directions API → distance/duration/traffic/speed
         CongestionIntelligence.classify() → Low/Medium/High
         PressureScoreCalculator.calculate() → 0–100
         CSVManager.append_record() → google_traffic_data_v2.csv  (dedupe by timestamp+route)
```

**Legacy/duplicate collector:** `TrafficApp/data_collector.py` is an older standalone script using the **Distance Matrix** API (not Directions), 3 hardcoded routes, writing `google_traffic_data.csv`. It is not wired into the scheduler and appears superseded by `traffic_collector/`.

**Reuse:** the same context providers (`weather/holiday/school/event/pressure/congestion/feature_engineering`) are imported by `HybridPredictionService` at prediction time — collection and inference share one context library.

---

## 9. Deployment Structure

| Concern | Configuration |
|---|---|
| **App server** | Gunicorn (`Procfile`: `web: gunicorn TrafficPro.wsgi`) |
| **Platform** | Render (CSRF trusted origin `https://traffik237.onrender.com`); PythonAnywhere bootstrap also present (`pythonanywhere_wsgi.py`) |
| **Static files** | WhiteNoise + `CompressedManifestStaticFilesStorage`; `collectstatic` → `staticfiles/` |
| **Database** | Postgres via `DATABASE_URL` (`dj-database-url`, `psycopg[binary]`) |
| **Config/secrets** | `python-dotenv` loads `.env`; `SECRET_KEY` required (crashes if missing); `ALLOWED_HOSTS` from env |
| **Security (prod, `if not DEBUG`)** | SSL redirect, secure+httponly session cookie, secure CSRF cookie, HSTS 1y w/ preload+subdomains, 8h session age, expire-at-browser-close. Always-on: XSS filter, nosniff, `X_FRAME_OPTIONS=DENY` |
| **Background worker** | `manage.py start_collector` (must run as a separate process/worker; not started by the web dyno) |
| **Logging** | Console handlers via `LOGGING`; `traffic_collector/logger.py` also writes `logs/collector.log`; `logs/django.log` present |

**Env vars required:** `DJANGO_SECRET_KEY, DATABASE_URL, ALLOWED_HOSTS, DEBUG, GOOGLE_MAPS_API_KEY, OPENWEATHER_API_KEY, SENDGRID_API_KEY, DEFAULT_FROM_EMAIL, SUPABASE_URL, SUPABASE_KEY`.

---

## 10. Third-Party Integrations

| Service | Used by | Purpose |
|---|---|---|
| **Google Maps Directions API** | `google_maps_service.py`, `utils.py`, `collector.py` | Route distance/duration, traffic duration, polyline, alternatives, per-step delays |
| **Google Maps Distance Matrix API** | `data_collector.py` (legacy) | Older route metric collection |
| **Google Maps JS + Places** | `static/index.js`, `predict.html` | Map render, polyline, origin/destination autocomplete (Buea-biased) |
| **OpenWeatherMap** | `weather_service.py` | Current Buea weather → `weather_condition`, `rainfall_status` |
| **SendGrid** | `email_service.py`, `forms.py` | Verification, welcome, password-reset, contact emails |
| **Supabase** | `views.analytics_view` | Reads `chat_history` for analytics aggregates |
| **`holidays` (PyPI)** | `holiday_service.py` | Cameroon public-holiday calendar |
| **APScheduler** | `scheduler.py` | Adaptive background scheduling of collection |
| **django-ratelimit** | `views.py` | Per-IP / per-user throttling |
| **WhiteNoise** | middleware/static storage | Static file serving |

---

## 11. Service Interactions & Dependency Relationships

```
                              ┌──────────────────────────────┐
                              │           Browser             │
                              │ templates + static/index.js  │
                              └───────────────┬──────────────┘
                                              │ HTTPS (page + AJAX JSON)
                                              ▼
        ┌─────────────────────────────────────────────────────────────────┐
        │                    Django (TrafficApp.views)                      │
        │  landing · signin/signup/otp · predict · chat-history · analytics │
        │  decorators: @ratelimit · @login_required · @role_required(rbac)  │
        └───┬───────────────┬───────────────────┬────────────────┬─────────┘
            │               │                   │                │
   (auth/reset)      (predict POST)        (chat read)     (analytics)
            │               │                   │                │
            ▼               ▼                   ▼                ▼
   email_service     HybridPredictionService  models.ChatThread  Supabase
   (SendGrid)               │                  /ChatMessage (PG)  (chat_history)
                            │
        ┌───────────────────┼─────────────────────────────────────┐
        ▼                   ▼                                       ▼
 GoogleMapsService     ModelService                     traffic_collector context libs
 (Directions API)   (*.pkl + encoder)        weather · holiday · school · event ·
        │                   │                 pressure_score · congestion · feature_eng
        ▼                   ▼                                       │
  Google Maps API     pandas/numpy + model          OpenWeatherMap · holidays(CM)

  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
  Background worker (separate process):
    manage.py start_collector → TrafficScheduler(APScheduler)
       → TrafficCollector → GoogleDirections + same context libs
       → CSVManager → google_traffic_data_v2.csv → (offline) Model_training.ipynb → *.pkl
```

**Key dependency facts:**
- `services/hybrid_prediction_service.py` is the single integration hub — it imports both `services/*` and `traffic_collector/*`, coupling the web request path to the collector library.
- Both the **web app** (prediction time) and the **collector** (background) depend on the same context modules and on the Google Directions API.
- The ML training loop is **file-mediated**: collector → CSV → notebook → pickle → `ModelService`. There is no online/automatic retraining wired in.

---

## 12. Primary Data Flows

**A. Prediction (user-facing):**
```
User form (origin, destination, day, time)
  → POST /predict/ (sanitize_location, compute departure_time)
  → HybridPredictionService.get_hybrid_prediction()
       → Google route details + context + model probs → fused JSON
  → append row to google_traffic_data_v2.csv (7-col schema)
  → persist ChatThread + ChatMessage(response=JSON) in Postgres
  → JsonResponse → index.js constructBotReply() renders ETA, congestion,
    pressure, reasoning, map polyline
```

**B. Background collection (training data):**
```
Scheduler tick → for each route: Google Directions + context
  → classify congestion + pressure score
  → CSVManager.append_record() (full 20-col schema, dedupe) → CSV
```

**C. Analytics:**
```
Admin/Analyst → GET /analytics/ → Supabase chat_history SELECT *
  → aggregate counts (High/Medium/Low) → analytics.html
```

**D. Chat history:**
```
GET /chat-history/           → user's ChatThread list (JSON)
GET /chat-history/<uuid>/    → messages of one thread (message + stored JSON response)
```

---

## 13. Cross-Cutting Observations (for future work — no changes made)

1. **Model naming/format drift** — code & docstrings say *LightGBM*; artifacts are *XGBoost*; runtime loads `traffic_model.pkl`. Reconcile naming and confirm which artifact is canonical.
2. **`DEBUG` not defined in `settings.py`** — referenced at line 145 but never assigned from env; potential startup `NameError`.
3. **Unrouted frontend endpoints** — `/transcribe/` and `/alerts/` are fetched by `index.js` but absent from `urls.py` (alerts route commented out).
4. **Two collectors** — `traffic_collector/` (active, Directions API) vs `TrafficApp/data_collector.py` (legacy, Distance Matrix API, different CSV). Clarify ownership.
5. **CSV schema split** — `predict_view` and `CSVManager` write the same logical dataset with different column sets; downstream training should account for this.
6. **Route coverage gap** — model encodes 3 routes; collector polls ~60. Most routes hit all-zero one-hot encodings at inference.
7. **Dependency pinning** — several runtime imports (`joblib`, `numpy`, model lib, `apscheduler`, `holidays`) are not in `requirements.txt`.
8. **Secrets** — `TrafficPro/.env` is tracked in the working tree; ensure it is git-ignored and rotated as needed.

> These are recorded for awareness only. Per the task scope, **no application code was modified.**
