# Phase 3 — Performance Improvements — Changelog

> **Date:** 2026-05-30
> **Scope:** Implements Phase 3 of [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md). Issue IDs map to [ENGINEERING_AUDIT.md](ENGINEERING_AUDIT.md).
> **Schema impact:** None (no migrations).
> **Validation:** `manage.py check` → 0 issues; `manage.py test` → 30 passing.

---

## Summary

Phase 3 removes the avoidable per-request work from the prediction path and decouples non-critical work from the request lifecycle.

| Issue | Severity | Status |
|---|---|---|
| H1 — Model reloaded from disk on every prediction | High | ✅ Fixed (process-level cache) |
| H2 — Slow external calls re-made every request | High | ✅ Fixed (weather + holiday caching) |
| Scalability — no decoupling of fire-and-forget work | P2 | ✅ Seam added (`run_async`); welcome email offloaded |

---

## Changes by file

### `TrafficApp/services/model_service.py` — H1
- Model + label encoder are now loaded by a process-level `@lru_cache` function `_load_artifacts()` instead of inside `ModelService.__init__`. A new `ModelService` per request no longer triggers a ~1 MB `joblib.load`; the artifacts load once per process and are reused.
- Load errors now go through `logging` instead of `print`.
- **Trade-off:** a retrained model requires a process restart (or `_load_artifacts.cache_clear()`) to take effect — documented in the module.

### `traffic_collector/weather_service.py` — H2
- `get_current_weather()` caches successful OpenWeatherMap responses in the Django cache (`weather:buea:current`, 10-min TTL). At most one upstream call per TTL across all predictions and collection cycles. Error/unauthorized responses are **not** cached (they retry next call).

### `traffic_collector/holiday_service.py` — H2
- `is_public_holiday(date)` caches the per-date result for 24h (`holiday:CM:<iso-date>`). Holiday status for a date never changes, so this is a safe long-lived cache.

> Both caches use the backend configured in Phase 1 — local memory in dev/tests, Redis in production when `REDIS_URL` is set.

### `TrafficApp/tasks.py` (new) — scalability seam
- `run_async(func, *args, **kwargs)` — runs fire-and-forget work on a small thread pool, or synchronously when `settings.TASK_ALWAYS_EAGER` is true (tests/local). Single, documented seam to later swap for Celery/RQ + Redis.

### `TrafficApp/views.py`
- `verify_otp` now sends the welcome email via `run_async(...)`. The email was already fire-and-forget (its return value was ignored), so this is a pure latency win on signup completion with **no behavior change**. Reliability-critical emails (OTP, password reset) remain synchronous.

### `TrafficPro/settings.py`
- Added `TASK_ALWAYS_EAGER` (env-driven, default `False`).

### `TrafficApp/tests.py`
- +6 tests (30 total): model loaded once across instances; weather fetched once per TTL; holiday lookup cached; `run_async` eager execution + exception-swallowing. `TASK_ALWAYS_EAGER=True` added to the shared test overrides.

---

## Design note: parallelization

The roadmap suggested optionally parallelizing the external calls in a prediction. After caching weather and holidays, the **only** remaining slow call on the prediction path is the Google Directions request, which is essential and has nothing to run in parallel against. Thread-based parallelization was therefore intentionally **not** added — it would add concurrency complexity for negligible benefit. Caching delivers the real latency reduction.

---

## Behaviour changes

- None user-visible. Predictions return identical payloads, just faster (cached context + no per-request model load). The welcome email now arrives slightly after the signup redirect instead of blocking it.

## Deployment / operational notes

1. **No migration.** Deploy is code-only.
2. **Cache backend:** for the caching to be shared across workers in production, set `REDIS_URL` (Phase 1). Without it each worker keeps its own local-memory cache — still correct, just less hit-sharing.
3. **Model refresh:** after retraining/replacing `traffic_model.pkl`, restart the web process so the cached model reloads.
4. **Task queue:** `run_async` is thread-based. At higher scale, replace its body with a Celery/RQ task (broker = the same Redis) — no call sites change.

## Rollback

`git revert` the Phase 3 commit(s). No data or schema changes.

## Out of Phase 3 scope (still tracked)

- Full Celery/RQ broker-backed queue (needs Redis provisioning) — deferred; `run_async` is the seam.
- Train/serve skew & route coverage (H6) — Phase 5.
- Architecture decoupling / dead-code removal — Phase 4.
