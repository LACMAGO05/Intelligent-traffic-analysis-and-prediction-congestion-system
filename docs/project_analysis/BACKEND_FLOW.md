# TrafficPro — Backend Flow

> **Status:** Understanding-only. No production code was modified.
> **Generated:** 2026-05-30
> **Scope:** Django request lifecycle, view-by-view behaviour, the prediction orchestration chain, and the background collector.

## 1. Purpose

This document traces how HTTP requests move through the Django backend — from middleware, through views and decorators, into the service layer, and out to persistence and external APIs. It also covers the background collection worker, which shares the same domain library.

## 2. Request Lifecycle

```
HTTP request
  → SecurityMiddleware (SSL/HSTS in prod)
  → WhiteNoiseMiddleware (static assets short-circuit here)
  → SessionMiddleware (DB-backed sessions)
  → CommonMiddleware
  → CsrfViewMiddleware (validates X-CSRFToken on POST)
  → AuthenticationMiddleware (request.user)
  → MessageMiddleware
  → XFrameOptionsMiddleware (DENY)
  → URLconf: TrafficPro/urls.py → TrafficApp/urls.py
  → View (function-based, + decorators)
  → Response (render(template) | JsonResponse)
```

Context processors `TrafficApp.rbac.role_context` and `TrafficApp.context_processors.contact_form` inject `{{ user_role }}` and a `ContactForm` into every template render.

## 3. URL → View Map

| URL | View | Access control | Purpose |
|---|---|---|---|
| `/` | `landing_view` | public (auth → redirect predict) | Marketing/landing page |
| `/login/` | `signin_view` | `@ratelimit 5/m IP` | Authenticate, redirect to predict |
| `/signup/` | `signup_view` | `@ratelimit 3/h IP` | Stash signup + OTP hash in session |
| `/otp/` | `verify_otp` | `@ratelimit 5/10m IP` | Verify OTP, create `User` |
| `/logout/` | `logout_view` | — | End session |
| `/predict/` | `predict_view` | `@ratelimit 30/m user` + `@role_required(Admin,Analyst,Commuter)` | Core hybrid prediction (GET page / POST JSON) |
| `/chat-history/` | `chat_history_view` | `@login_required` | List user threads (JSON) |
| `/chat-history/<uuid>/` | `thread_detail_view` | `@login_required` | Messages of one thread (JSON) |
| `/analytics/` | `analytics_view` | `@role_required(Admin,Analyst)` | Supabase aggregate dashboard |
| `/contact/` | `contact_view` | public (POST) | Send contact email via SendGrid |
| `/password_reset/` + 3 | `CustomPasswordResetView` + Django auth views | public | SendGrid-based password reset |

> **Routed-but-missing:** `static/index.js` calls `/transcribe/` and `/alerts/`, which are **not** in `urls.py` (the alerts route is commented out). These resolve to 404s.

## 4. Decorator Stack (cross-cutting)

- `@ratelimit(key=..., rate=..., block=True)` — django-ratelimit; throttles by IP (auth) or user (predict). **Note:** default cache backend is per-process, so limits are not shared across Gunicorn workers.
- `@role_required(*roles)` ([rbac.py](../../TrafficApp/rbac.py)) — wraps `@login_required`; superuser bypass; checks Django Group membership; returns `403 JSON` for `X-Requested-With=XMLHttpRequest`, else `403.html`.
- `@login_required` — standard Django redirect-to-login.

## 5. Core Flow — `predict_view` (POST)

```
predict_view(POST)
  1. sanitize_location(origin), sanitize_location(destination)   # strips tags/js, 200-char cap
  2. parse day/time → compute departure_time ("now" | unix ts)
     - get_next_weekday() resolves named weekday
     - past-time guard: rolls to tomorrow (now-day) or +7 days (named day)
  3. HybridPredictionService().get_hybrid_prediction(origin, destination, departure_time)
        ├─ GoogleMapsService.get_route_details()  → distance, normal/traffic duration, polyline, alternatives, segments_delay
        ├─ _gather_context(target_dt)             → weather + holiday + school + event + office indicators
        ├─ _prepare_ml_features()                 → feature dict (+ congestion + pressure score)
        ├─ ModelService.predict()                 → {congestion_level, probabilities, confidence}
        └─ _apply_hybrid_logic()                  → Smart ETA + risk + XAI reasoning JSON
  4. append row to google_traffic_data_v2.csv (7-col schema)
  5. resolve/create ChatThread; create ChatMessage(response=prediction JSON)
  6. JsonResponse(prediction + thread_id + thread_title)
  (errors → traceback.print_exc(); JsonResponse(error, 500))
```

Key behaviours:
- A **new `HybridPredictionService` is instantiated per request**, which re-loads the model + encoder from disk every time (see Risks).
- `departure_time == "now"` requests Google's live traffic; future timestamps request predicted traffic (`is_prediction=True`).
- The view writes to **two** stores synchronously: CSV file + Postgres.

## 6. Auth Flows

**Signup → OTP → user creation:**
```
POST /signup/  → password length >=12 check
               → generate_otp() (6 digits), sha256 hash
               → session['signup_data'] = {username, email,
                   password_hash=make_password(pw), otp_hash,
                   otp_created_at, otp_attempts=0}
POST /otp/     → load session data (else redirect signup)
               → expiry > 600s? attempts >= 5? → invalidate
               → compare sha256(entered) to otp_hash
               → success: User(username,email; password=stored hash).save()
               → clear session; redirect login
```
**Observation:** `send_verification_email` is imported but not invoked in `signup_view` as written — the OTP is generated/hashed but no delivery call is visible in the view, so the user has no obvious way to receive the code in this flow.

**Password reset:** `CustomPasswordResetForm.save()` builds `http(s)://{domain}/reset/{uid}/{token}/` and sends via SendGrid (`send_password_reset_email`), bypassing Django's SMTP backend. `use_https` defaults to `False`, so links are `http://` unless overridden.

## 7. Background Collector Flow

```
manage.py start_collector
  → TrafficScheduler.start()
       → schedule_next(): get_adaptive_interval()
            rush(6–9,16–20)=10min · night(22–6)=60min · else=30min
       → runs collect_all_routes() immediately, then on IntervalTrigger
       → run_and_reschedule(): re-evaluates interval band each tick
  → TrafficCollector.collect_all_routes()
       gather shared context once (weather/holiday/school/event/office)
       for each route in settings.TRAFFIC_ROUTES (~60 pairs):
          fetch_google_traffic() → Directions API
          CongestionIntelligence.classify() · PressureScoreCalculator.calculate()
          CSVManager.append_record()  (dedupe by timestamp+route, last 100 lines)
          time.sleep(1)  # crude rate-limit spacing
```

## 8. Interactions & Dependencies

- Views depend on: `services.hybrid_prediction_service`, `services.email_service`, `utils`, `forms`, `rbac`, `models`, and `supabase` (analytics).
- `HybridPredictionService` depends on `services.google_maps_service`, `services.model_service`, and **seven** `traffic_collector` modules — coupling the web path to the collector library.
- Both web and worker depend on the Google Directions API and the same context providers.

## 9. Risks

1. **Inline blocking I/O** — Google (10s) + OpenWeatherMap (10s) calls run sequentially inside the request, holding a worker for the duration; no timeouts budget for the combined chain.
2. **Per-request model load** — `ModelService.__init__` reloads `traffic_model.pkl` and `label_encoder.pkl` on every prediction (latency + GC churn).
3. **Rate limiting not shared across workers** — in-process cache makes `@ratelimit` ineffective under multi-worker deployment.
4. **Dual CSV writers / schema mismatch** — `predict_view` (7 cols) vs `CSVManager` (20 cols) against the same file.
5. **OTP delivery gap** — signup generates an OTP but the view does not appear to send it.
6. **Broad exception handling + `print`/`traceback.print_exc`** — debugging output to stdout rather than structured logging; error detail (`str(e)`) returned to clients in `predict_view`.
7. **`http://` reset links** by default (`use_https=False`).
8. **404 endpoints** referenced by the frontend (`/transcribe/`, `/alerts/`).

## 10. Scalability Concerns

- **Worker saturation:** blocking external calls + per-request model load cap throughput per Gunicorn worker; CPU/memory scale poorly.
- **No queue/cache:** email and prediction work that could be async stays synchronous; repeated context fetches aren't memoized.
- **Collector is single-process and stateful:** can't run multiple instances without duplicate collection; APScheduler state is in-memory only.
- **CSV append + duplicate scan** is not concurrency-safe and grows linearly; unsuitable as a shared write target at scale.
- **Sessions in DB** scale with managed Postgres but add a query per authenticated request; a cache-backed session store would reduce DB load.
