# TrafficPro — Engineering Audit

> **Status:** Audit only. No fixes were implemented. No production code was modified.
> **Generated:** 2026-05-30
> **Auditor scope:** Architecture, Security, Django Backend, Frontend, Database, ML Pipeline, Traffic Collection, Deployment, DevOps, Performance, Scalability, Product Readiness.
> **Companion docs:** [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) · [BACKEND_FLOW.md](BACKEND_FLOW.md) · [FRONTEND_FLOW.md](FRONTEND_FLOW.md) · [ML_PIPELINE.md](ML_PIPELINE.md) · [DATABASE_STRUCTURE.md](DATABASE_STRUCTURE.md) · [THIRD_PARTY_SERVICES.md](THIRD_PARTY_SERVICES.md) · [REPOSITORY_MAP.md](REPOSITORY_MAP.md)

---

## Severity Classification

| Severity | Meaning |
|---|---|
| **Critical** | Breaks production, causes data loss, or is a directly exploitable security hole. Fix before any production release. |
| **High** | Serious correctness, security, or reliability defect that will bite under real usage. Fix soon. |
| **Medium** | Quality/maintainability/performance issue that degrades the system but has workarounds. |
| **Low** | Cleanup, polish, or hardening; low blast radius. |

## Executive Summary

| # | Issue | Area | Severity |
|---|---|---|---|
| C1 | `DEBUG` referenced but never defined in `settings.py` | Backend/Deploy | **Critical** |
| C2 | Model/data artifacts are git-ignored — not shipped with deploy | Deployment/ML | **Critical** |
| C3 | No automated tests / no CI | DevOps | **Critical** |
| C4 | Signup OTP generated but never delivered | Backend/Product | **Critical** |
| H1 | Per-request model + service load (no caching) | Performance | **High** |
| H2 | Synchronous blocking external calls inside the request | Performance/Scalability | **High** |
| H3 | Rate limiting uses per-process cache → ineffective multi-worker | Security/Scalability | **High** |
| H4 | Google Maps API key exposed client-side under misleading name | Security | **High** |
| H5 | Dual-schema writes to the same training CSV | ML/Data | **High** |
| H6 | Train/serve skew (`prev_hour_speed`=20.0, 3-route one-hots vs ~60) | ML | **High** |
| H7 | Ephemeral filesystem — CSV/SQLite data loss on PaaS restart | Deployment/Data | **High** |
| H8 | Error detail (`str(e)`) leaked to clients; `print`/traceback to stdout | Security/Observability | **High** |
| M1 | Dead frontend endpoints (`/transcribe/`, `/alerts/` polled 120s) | Frontend | **Medium** |
| M2 | Unpinned / missing runtime dependencies | DevOps/Deploy | **Medium** |
| M3 | In-memory APScheduler; single-instance collector assumption | Scalability | **Medium** |
| M4 | No DB indexes / pagination / retention for chat data | Database/Perf | **Medium** |
| M5 | Supabase analytics read with no observed writer | Data/Product | **Medium** |
| M6 | Two parallel collectors (legacy `data_collector.py`) | Architecture | **Medium** |
| M7 | Password reset links default to `http://` | Security | **Medium** |
| M8 | Web↔collector tight coupling via shared imports | Architecture | **Medium** |
| M9 | Module-import-time Supabase client breaks all views on bad key | Backend | **Medium** |
| L1 | Model naming drift ("LightGBM" vs XGBoost) | ML/Docs | **Low** |
| L2 | CDN deps without version pin / SRI (Leaflet via unpkg) | Frontend/Security | **Low** |
| L3 | `db.sqlite3` & `.idea/` artifacts in working tree | DevOps | **Low** |
| L4 | Duplicated Google-fetch logic across 3 modules | Maintainability | **Low** |
| L5 | Broad `except Exception` / bare `except:` swallowing errors | Backend | **Low** |

---

## 1. Architecture

### M6 — Two parallel traffic collectors — *Medium*
- **Explanation:** `traffic_collector/` (active, APScheduler, Directions API, 20-col CSV) coexists with the legacy `TrafficApp/data_collector.py` (Distance Matrix API, 3 hardcoded routes, different `google_traffic_data.csv`). Both implement Google fetching independently.
- **Impact:** Confusion over the source of truth, divergent congestion logic, dead code that can be accidentally run or maintained.
- **Solution:** Designate `traffic_collector/` as canonical; delete or quarantine `data_collector.py`.
- **Implementation:** Move `data_collector.py` to an `archive/` folder or remove it; add a module docstring to `traffic_collector/` marking it canonical.

### M8 — Web request path tightly coupled to the collector library — *Medium*
- **Explanation:** `HybridPredictionService` imports seven `traffic_collector` modules; the synchronous web path and the background worker share the same code.
- **Impact:** A change intended for collection can break live predictions; hard to evolve the two independently.
- **Solution:** Extract the shared context providers (weather/holiday/school/event/pressure/congestion/features) into a neutral `context/` package consumed by both, leaving `traffic_collector/` only the scheduling/IO concern.
- **Implementation:** Introduce `trafficpro/context/` with the pure providers; have both `services/` and `traffic_collector/` depend on it. Pure refactor, no behavior change.

### L4 — Duplicated Google Directions logic — *Low*
- **Explanation:** Near-identical fetch/parse code exists in `google_maps_service.py`, `utils.get_realtime_traffic`, and `collector.fetch_google_traffic`.
- **Impact:** Bug fixes must be applied in three places; drift already exists (different congestion ratio thresholds).
- **Solution:** Consolidate into a single Directions client.
- **Implementation:** Make `GoogleMapsService` the one client; refactor the other two call sites to use it.

---

## 2. Security

### H3 — Rate limiting is per-process; ineffective across workers — *High*
- **Explanation:** `django-ratelimit` uses Django's default cache (per-process `LocMemCache` unless configured otherwise). With multiple Gunicorn workers/dynos, each holds its own counter, multiplying effective limits.
- **Impact:** Auth brute-force / OTP-guessing and predict-abuse protections are far weaker than the configured `5/m`, `3/h`, `5/10m`, `30/m` suggest.
- **Solution:** Back the cache with a shared store (Redis/Memcached).
- **Implementation:** Configure `CACHES` with Redis and set `RATELIMIT_USE_CACHE`; verify limits hold across workers in a load test.

### H4 — Google Maps key exposed client-side — *High* (name resolved)
- **Explanation:** `GOOGLE_MAPS_API_KEY` is a Maps **API key**, rendered into `predict.html` for the JS SDK. (The old misleading name `GOOGLE_CLIENT_SECRET` has been removed.)
- **Impact:** A scraped, unrestricted key can be abused → billing/quota theft.
- **Solution:** Apply HTTP-referrer + API restrictions in the Google Cloud console; consider separate keys for server (IP-restricted) vs browser (referrer-restricted).
- **Implementation:** Variable renamed to `GOOGLE_MAPS_API_KEY` (done). Remaining hardening: optionally split into browser- vs server-restricted keys.

### H8 — Internal error detail leaked to clients; stdout debugging — *High*
- **Explanation:** `predict_view` returns `JsonResponse({"error": str(e)}, 500)` and uses `print(...)` / `traceback.print_exc()` throughout instead of structured logging.
- **Impact:** Exception messages may disclose internals (paths, library errors); no centralized, queryable logs for incident response.
- **Solution:** Return a generic client error; log full detail server-side via the `logging` framework.
- **Implementation:** Replace `print`/`traceback.print_exc` with `logger.exception(...)`; return `{"error": "Prediction failed, please try again."}`; wire a log aggregator.

### M7 — Password reset links default to `http://` — *Medium*
- **Explanation:** `CustomPasswordResetForm.save()` builds the link with `use_https=False` by default.
- **Impact:** Reset tokens could traverse plaintext if the link is generated as `http://`.
- **Solution:** Force HTTPS in production.
- **Implementation:** Pass `use_https=True` (or derive from `request.is_secure()`/settings) when building the reset URL.

### (Verified-good security posture — noted, not issues)
- `.env`, `db.sqlite3`, `*.pkl`, and CSVs are correctly listed in `.gitignore` (secrets/data are **not** committed).
- Production security headers are configured (HSTS, secure cookies, nosniff, `X_FRAME_OPTIONS=DENY`, SSL redirect) — **but gated behind the broken `DEBUG` check (see C1)**.
- Passwords hashed via `make_password`; OTP stored as sha256 hash with expiry + attempt cap; signup enforces ≥12-char passwords; CSRF enabled; `sanitize_location()` strips tags/script.

---

## 3. Django Backend

### C1 — `DEBUG` referenced but never assigned in `settings.py` — *Critical*
- **Explanation:** `settings.py:145` evaluates `if not DEBUG:` to gate all production security settings, but `DEBUG` is never defined in `settings.py` (it exists only in `.env`, which is not read via `os.getenv`).
- **Impact:** At minimum a `NameError` crashing startup; if a `DEBUG` ever leaks into module scope, the entire production security block (SSL redirect, secure cookies, HSTS) may silently not apply.
- **Solution:** Define `DEBUG` explicitly from the environment.
- **Implementation:** `DEBUG = os.getenv("DEBUG", "False").lower() == "true"` near the top of `settings.py`; add a startup assertion that security settings apply when `DEBUG` is false.

### C4 — Signup OTP generated but never delivered — *Critical*
- **Explanation:** `signup_view` generates an OTP, hashes it, and stores it in the session, but does not call `send_verification_email` (imported but unused in the view). `verify_otp` then expects a code the user never received.
- **Impact:** Account registration is effectively broken end-to-end — no user can complete signup.
- **Solution:** Send the OTP via the existing email service during signup.
- **Implementation:** Call `send_verification_email(email, username, otp)` after stashing session data; handle send failure (surface error, allow resend). Add an integration test for the full signup→OTP→login path.

### M9 — Module-import-time Supabase client — *Medium*
- **Explanation:** `supabase = create_client(...)` runs at `views.py` import. A bad/missing key fails the import of the entire views module → every route 500s, not just analytics.
- **Impact:** A single misconfigured integration takes down the whole app.
- **Solution:** Lazily construct the client inside `analytics_view` (or a cached accessor).
- **Implementation:** Move client creation into a `get_supabase()` helper with try/except; degrade analytics gracefully.

### L5 — Broad/bare exception handling — *Low*
- **Explanation:** Multiple `except Exception` and a bare `except:` (e.g. time parsing in `predict_view`) swallow errors silently.
- **Impact:** Real failures masked; debugging harder.
- **Solution:** Catch specific exceptions; log the rest.
- **Implementation:** Replace bare `except:` with targeted handling; log unexpected paths.

---

## 4. Frontend

### M1 — Dead endpoints wired to the UI — *Medium*
- **Explanation:** `static/index.js` posts voice to `/transcribe/` and polls `/alerts/` every 120s; neither route exists in `urls.py` (alerts is commented out).
- **Impact:** Continuous 404 traffic (one per tab every 2 min), broken mic feature, console noise, wasted requests.
- **Solution:** Either implement the endpoints or remove/guard the client calls.
- **Implementation:** Short-term: disable `fetchAlerts()`/mic wiring behind a feature flag. Long-term: implement routes or delete the code.

### L2 — CDN dependencies without pin/SRI — *Low*
- **Explanation:** Leaflet loaded from `unpkg.com/leaflet` (unversioned, no Subresource Integrity).
- **Impact:** CDN outage or compromised asset affects the app; supply-chain exposure.
- **Solution:** Pin exact versions + add SRI hashes, or self-host via static files.
- **Implementation:** Use `leaflet@1.9.x` with `integrity`/`crossorigin`, or vendor into `static/`.

### (Frontend note) — AJAX 403 content-type mismatch — *Low*
- The RBAC decorator returns JSON only when `X-Requested-With: XMLHttpRequest` is set, which the `fetch` calls do not send → forbidden AJAX gets `403.html` (HTML) while the client expects JSON. Add the header client-side or standardize on JSON 403 for `/api`-style routes.

---

## 5. Database Design

### H7 — Ephemeral filesystem causes data loss — *High*
- **Explanation:** On Render/Heroku the disk is ephemeral. `google_traffic_data_v2.csv` (training data) and `db.sqlite3` live on it; the active DB is Postgres but CSV-based ML data is not durable.
- **Impact:** Collected training rows and prediction logs vanish on every restart/redeploy — the ML dataset silently erodes.
- **Solution:** Persist ML data in durable storage.
- **Implementation:** Write collection rows to a Postgres table (or S3-compatible object storage / Parquet); treat the CSV as a local cache only.

### H5 — Dual-schema writes to the same CSV — *High*
- **Explanation:** `predict_view` appends 7-column rows; `CSVManager` writes 20-column rows; both target `google_traffic_data_v2.csv`.
- **Impact:** Ragged file → misaligned columns on `read_csv`, corrupt or dropped training rows.
- **Solution:** Separate the prediction log from the collection dataset, or unify the schema.
- **Implementation:** Route prediction logs to their own table/file; standardize collector schema as the single training source.

### M4 — No indexes, pagination, or retention for chat data — *Medium*
- **Explanation:** `ChatThread` is filtered by `user` and ordered by `created_at`; `ChatMessage.response` stores full prediction JSON with no cap; no pagination on history endpoints.
- **Impact:** Listing/scanning degrades as data grows; table bloat from unbounded JSON.
- **Solution:** Add indexes, paginate, define retention.
- **Implementation:** `Meta.indexes` on `ChatThread(user, created_at)` and `ChatMessage(thread)`; paginate `/chat-history/`; add a retention/archival job; consider trimming stored `response` to needed fields.

### M5 — Supabase analytics read with no observed writer — *Medium*
- **Explanation:** `analytics_view` reads `chat_history` from Supabase, but no code path writes to it.
- **Impact:** Dashboard may be empty/stale; data lineage split across Postgres + Supabase + CSV is confusing.
- **Solution:** Consolidate analytics onto Postgres (the data already exists in `ChatMessage`), or implement/clarify the Supabase write path.
- **Implementation:** Re-point `analytics_view` to aggregate from `ChatMessage.response`, removing the Supabase dependency.

---

## 6. ML Pipeline

### C2 — Model/data artifacts are git-ignored — *Critical (deployment)*
- **Explanation:** `.gitignore` excludes `*.pkl` and the CSVs. `ModelService` loads `traffic_model.pkl` from `BASE_DIR` at runtime; if artifacts aren't shipped via another mechanism, `model` is `None` → `predict()` returns `{"error": "Model not loaded"}`.
- **Impact:** Predictions silently fall back to error/Google-only on a clean deploy; the core feature is non-functional unless artifacts are manually placed.
- **Solution:** Ship artifacts via a controlled channel (model registry, object storage, or release asset) with an integrity check.
- **Implementation:** Add a deploy step that fetches versioned artifacts to `BASE_DIR`; fail fast on startup if the model is missing; record model version.

### H6 — Train/serve skew — *High*
- **Explanation:** `prev_hour_speed` is hardcoded to `20.0` at inference; `is_weekend`/`is_morning_rush` recomputed in two places; the model encodes only 3 routes as one-hots while the collector polls ~60 (unknown routes → all-zero features).
- **Impact:** Degraded, possibly misleading predictions for most routes; the model's temporal/route signal is effectively neutralized in production.
- **Solution:** Align serving features with training; expand route encoding or use a generalizable route representation.
- **Implementation:** Compute `prev_hour_speed` from recent data; centralize feature derivation in one shared function used by training and serving; re-train with the full route set or switch routes to embeddings/target-encoding.

### L1 — Model naming/format drift — *Low*
- **Explanation:** Code/docs say "LightGBM"; artifacts are XGBoost (`model_XGBoost.pkl`, `traffic_xgb_model.json`); the loaded file is `traffic_model.pkl`.
- **Impact:** Operational confusion about the canonical artifact.
- **Solution:** Standardize naming and document the canonical artifact + version.
- **Implementation:** Rename to a versioned scheme (e.g. `congestion_xgb_v3.pkl`), update docstrings, record in a model card.

### (ML note) — No model validation/versioning/monitoring — *Medium*
- A bad retrain ships with no metrics gate, schema check, or drift detection. Add a validation step (holdout metrics threshold), pin a feature-schema contract, and log prediction distributions for drift.

---

## 7. Traffic Collection Pipeline

### M3 — In-memory scheduler; single-instance assumption — *Medium*
- **Explanation:** APScheduler `BackgroundScheduler` state is in-process; running >1 collector instance double-collects, and a restart loses schedule state. Collector politeness is a fixed `time.sleep(1)`.
- **Impact:** Can't scale or run HA; restart gaps in data; quota risk under fan-out (~60 routes × up to every 10 min).
- **Solution:** Use a durable scheduler/queue; add adaptive backoff and quota guards.
- **Implementation:** Move to Celery Beat / cron-triggered management command with a DB lock; add retry/backoff and a per-cycle call budget.

### (Collection note) — Duplicate detection is O(file) and not concurrency-safe — *Medium*
- `CSVManager._is_duplicate` reads the last 100 lines per append. Tie into H5/H7: move to a table with a unique constraint on `(timestamp, route)`.

---

## 8. Deployment

### C1 / C2 (cross-listed) — broken `DEBUG` gate and missing artifacts are the two release blockers.

### H7 (cross-listed) — ephemeral storage of ML data.

### M2 — Unpinned / missing runtime dependencies — *Medium*
- **Explanation:** `requirements.txt` omits `numpy`, `joblib`, the model lib (xgboost/lightgbm), `apscheduler`, and `holidays`; `pandas` and `psycopg[binary]` are unpinned.
- **Impact:** Clean deploys can fail at import (ModelService, scheduler, holiday service) or pull incompatible versions.
- **Solution:** Pin every runtime import.
- **Implementation:** Generate from a clean venv (`pip freeze`) or adopt `pip-tools`/Poetry with a lockfile; add a CI job that builds from scratch and imports the app.

### (Deploy note) — Two WSGI bootstraps — *Low*
- `Procfile` (Gunicorn/Render) and `pythonanywhere_wsgi.py` (with a placeholder path) coexist. Pick one target and document it; remove or clearly mark the unused one.

---

## 9. DevOps

### C3 — No automated tests and no CI — *Critical*
- **Explanation:** `TrafficApp/tests.py` is the empty Django stub; there is no `.github/workflows`, Dockerfile, or any pipeline.
- **Impact:** No regression safety net; the broken `DEBUG`, broken signup, and missing-deps issues would all have been caught by basic CI. Every change is high-risk.
- **Solution:** Add a test suite + CI gate.
- **Implementation:** Write unit/integration tests for auth (signup→OTP→login), `predict_view`, RBAC, and `ModelService` feature shaping; add a GitHub Actions workflow that installs from `requirements.txt`, runs migrations, lints, and runs tests on every PR.

### L3 — Local artifacts in working tree — *Low*
- **Explanation:** `db.sqlite3`, `.idea/`, `.ipynb_checkpoints/` present (most are git-ignored, but `.idea/` files appear committed historically).
- **Impact:** Repo noise; potential stale/local data.
- **Solution:** Ensure all are ignored and untracked.
- **Implementation:** Confirm `.idea/` is ignored and `git rm --cached` any tracked IDE files.

---

## 10. Performance

### H1 — Per-request model and service instantiation — *High*
- **Explanation:** `predict_view` creates a new `HybridPredictionService` per request, which constructs `ModelService`, which `joblib.load`s `traffic_model.pkl` (~1 MB) + encoder every time.
- **Impact:** Added latency and GC/memory churn on every prediction; throughput per worker is needlessly low.
- **Solution:** Load the model once per process and reuse.
- **Implementation:** Cache the model/encoder at module scope or via Django's app-ready hook / `functools.lru_cache`; inject the singleton into the service.

### H2 — Synchronous blocking external calls in the request path — *High*
- **Explanation:** A prediction calls Google Directions (10s timeout) and OpenWeatherMap (10s) inline and sequentially; no shared cache.
- **Impact:** User latency tracks the slowest upstream; a slow API ties up Gunicorn workers and can cascade to capacity exhaustion.
- **Solution:** Cache slow-changing context; parallelize/timeout-budget calls; consider async.
- **Implementation:** Cache weather (~10 min TTL), holidays (per day), route geometry; use `concurrent.futures` or async views; set an overall request deadline.

---

## 11. Scalability

### (Cross-listed) H2, H3, H7, M3 are the primary scaling ceilings:
- No shared cache (H3) blocks horizontal scaling of rate limits/response caching.
- Synchronous upstream fan-out (H2) caps per-worker throughput.
- Ephemeral file storage (H7) and CSV-as-datastore prevent multi-instance data integrity.
- In-memory scheduler (M3) prevents HA/multi-instance collection.

### (Scalability note) — No task queue — *Medium*
- **Explanation:** Email sends, prediction work, and collection all run inline or in one worker process.
- **Impact:** Latency-sensitive paths are coupled to slow work; no buffering under load.
- **Solution:** Introduce Celery/RQ + Redis.
- **Implementation:** Move email and (optionally) prediction post-processing to tasks; run the collector as scheduled tasks with locking.

### (Scalability note) — Single-region/city design — *Low–Medium*
- Buea-specific location normalization, a single weather city, and 3-route encoding mean multi-city scaling multiplies external calls and requires re-training + parameterization.

---

## 12. Product Readiness

**Verdict: Not production-ready.** Two issues make the core flows non-functional on a clean deploy (C4 signup, C2 model artifacts), one risks startup/security (C1), and there is no safety net (C3).

| Dimension | State |
|---|---|
| Core signup flow | **Broken** (C4 — OTP never sent) |
| Core prediction flow | **At risk** (C2 — model may not load; H6 — degraded accuracy) |
| Production config | **Broken/unsafe** (C1 — `DEBUG` gate) |
| Test & release safety | **Absent** (C3 — no tests/CI) |
| Data durability | **At risk** (H7 — ephemeral ML data) |
| Security posture | **Partial** — good headers/CSRF/hashing, but H3/H4/H8/M7 outstanding |
| Observability | **Weak** — `print`/stdout, no aggregation/metrics/alerting |
| Feature completeness | Voice/alerts wired but unrouted (M1) |

### Recommended path to readiness (priority order)
1. **Unblock core flows:** C1 (`DEBUG`), C4 (send OTP), C2 (ship + verify model artifacts).
2. **Add safety net:** C3 (tests + CI building from clean deps, covering C1/C4 regressions); M2 (pin deps).
3. **Harden runtime:** H1 (cache model), H2 (cache/parallelize upstream), H3 (shared cache for rate limits), H8 (structured logging, no error leakage), H4/M7 (key restriction, HTTPS reset).
4. **Fix data integrity:** H5 (split CSV schemas), H7 (durable ML storage), M4 (indexes/pagination/retention), M5 (consolidate analytics).
5. **Improve ML correctness:** H6 (train/serve alignment + route coverage), model validation/versioning, L1 (naming).
6. **Operationalize:** M3 (durable scheduler), task queue, M6/M8/L4 (architecture cleanup), M1/L2 (frontend cleanup).

---

> All findings above are recorded for planning. **No code, configuration, schema, or model artifact was changed.**
