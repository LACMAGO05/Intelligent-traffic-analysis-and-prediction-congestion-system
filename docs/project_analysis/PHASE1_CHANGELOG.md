# Phase 1 — Critical Security Fixes — Changelog

> **Date:** 2026-05-30
> **Scope:** Implements Phase 1 of [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md). Issue IDs map to [ENGINEERING_AUDIT.md](ENGINEERING_AUDIT.md).
> **Schema impact:** None (no new migrations).
> **Validation:** `manage.py check` → 0 issues; `manage.py test` → 16 passing; `makemigrations --check` → no changes.

---

## Summary

The application **could not start** before this change set (`NameError: DEBUG` at `settings.py:145`), and even past that, `views.py` crashed at import building a Supabase client from settings that were never defined. Phase 1 makes the app boot, restores the broken signup flow, and closes the highest-severity security gaps that don't require new infrastructure.

| Issue | Severity | Status |
|---|---|---|
| C1 — `DEBUG` undefined in settings | Critical | ✅ Fixed |
| C4 — Signup OTP never sent / flow broken | Critical | ✅ Fixed |
| M9 — Module-import-time Supabase client | Medium | ✅ Fixed |
| M7 — Password-reset links default to `http://` | Medium | ✅ Fixed |
| H8 — Error detail leaked to clients; `print`/traceback | High | ✅ Fixed |
| H4 — Google Maps key naming/clarity | High | ✅ Fixed (code) · ⚠️ console restriction is manual |
| H3 — Rate-limit cache not shared across workers | High | ✅ Code path added · ⚠️ requires `REDIS_URL` in prod |

---

## Changes by file

### `TrafficPro/settings.py`
- **C1:** Added `DEBUG = os.getenv('DEBUG', 'False') ...` — explicit, defaults to production-safe `False`. This is what the existing `if not DEBUG:` security block depends on.
- **Config bindings:** Added the previously-missing env→settings bindings: `GOOGLE_MAPS_API_KEY` (a `GOOGLE_CLIENT_SECRET` compatibility alias was added here then later removed), `OPENWEATHER_API_KEY`, `SENDGRID_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`. Code already referenced these on `settings`; they were never defined.
- **H3:** Added `CACHES` — uses `RedisCache` when `REDIS_URL` is set (shared across workers), otherwise `LocMemCache` (dev/test). Non-breaking default.

### `TrafficApp/views.py`
- **M9:** Removed the module-level `create_client(...)`; added a lazy, memoised `get_supabase()` used only by `analytics_view`. A bad Supabase config no longer breaks every route.
- **C4 (`signup_view`):** Added required-field + duplicate username/email validation; now **sends the OTP via `send_verification_email`** and redirects to `/otp/` (previously it stored the OTP but neither sent it nor advanced the flow). Aborts cleanly if email delivery fails.
- **C4 (`verify_otp`):** Rewrote the broken view — it previously read `data` on GET before assignment, used `datetime.fromisoformat` against the `datetime` *module*, and redirected to a non-existent `'login'` URL name. Now: GET renders the OTP page only when a signup is pending; success path assigns the **Commuter** group (without it, `@role_required` would 403 new users out of `/predict/`), sends the welcome email, and redirects to `signin`.
- **M7 (`CustomPasswordResetView`):** Passes `use_https=self.request.is_secure()` so reset links match the request scheme instead of defaulting to `http://`.
- **H8:** Replaced `print(...)`/`traceback.print_exc()` with module `logger`; the prediction error path now logs the full traceback server-side and returns a **generic** client message instead of `str(e)`.
- **H4:** `predict_view` now reads `settings.GOOGLE_MAPS_API_KEY`.

### `TrafficApp/services/hybrid_prediction_service.py`
- **H8:** Converted the `--- AI PREDICTION DEBUG ---` `print` block to a single `logger.debug(...)` call.

### `TrafficApp/services/google_maps_service.py`, `TrafficApp/utils.py`, `traffic_collector/collector.py`, `TrafficApp/data_collector.py`
- **H4:** Read `GOOGLE_MAPS_API_KEY` (the old `GOOGLE_CLIENT_SECRET` name was supported via an alias at the time, since removed).

### `requirements.txt`
- **H3:** Added `redis==5.2.1` for the production shared-cache path.

### `TrafficApp/tests.py`
- New suite (16 tests): config bindings, pure domain logic (congestion, pressure, OTP, sanitisation), the full signup→OTP→user flow with mocked email, and RBAC gating on `/predict/`.

---

## Operational / deployment notes (manual, outside code)

1. **`DEBUG`** — ensure prod env sets `DEBUG=False` (default if unset). Confirm the security block (SSL redirect, HSTS, secure cookies) is active.
2. **H3 / Redis** — to actually share rate-limit counters across workers, set `REDIS_URL` in the prod environment (the `redis` package is now in `requirements.txt`). Without it, limits remain per-process.
3. **H4 / Google key** — **restrict the Maps API key in the Google Cloud console** (HTTP-referrer + enabled-APIs). The code rename does not restrict the key; this step is required and cannot be done from the repo. The env var is now `GOOGLE_MAPS_API_KEY` (the legacy `GOOGLE_CLIENT_SECRET` name has been removed).
4. **No DB migration** — nothing to apply or roll back at the schema level.

## Rollback

`git revert` the Phase 1 commit(s). No data migration to undo. The only externally-visible behavior changes are: signup now emails an OTP and advances to `/otp/`, prediction errors return a generic message, and reset links use the request scheme.

## Follow-up (added during Phase 1–3 verification)

- **`LOGIN_URL` misconfiguration** — `@login_required` was falling back to Django's default `/accounts/login/`, which this project does not route, so anonymous users hitting a protected page landed on a 404. Fixed by setting `LOGIN_URL = "/login/"` and `LOGIN_REDIRECT_URL = "predict"` in `settings.py`. Covered by the tightened `RbacTests.test_anonymous_predict_redirects_to_login` (asserts redirect to `/login/?next=/predict/`) and `test_login_url_setting`.

## Known limitations / deferred

- H3 is only effective once `REDIS_URL` is provisioned (infra, Phase 6).
- H4 console restriction is manual.
- Tests run against SQLite via `DATABASE_URL="sqlite:///test_db.sqlite3"`; wiring this into CI is Phase 6 (C3).
- Out of Phase 1 scope (tracked in the roadmap): per-request model load (H1), blocking external calls (H2), durable ML storage (H7), train/serve skew (H6), dead frontend endpoints (M1).
