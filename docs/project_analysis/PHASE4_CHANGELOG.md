# Phase 4 — Architecture Refactoring (Changelog)

**Date:** 2026-05-31
**Scope:** Behavior-preserving cleanup. No user-facing behavior change; no DB schema change; no new migrations.
**Audit items addressed:** M8, L4, M6, M1, L2 (see [ENGINEERING_AUDIT.md](ENGINEERING_AUDIT.md)).
**Validation:** `manage.py check` clean · **36/36 tests pass** (SQLite) · live end-to-end hybrid prediction confirmed against the real Google Directions API.

---

## 4.1 — Extract a neutral `traffic_context/` package *(M8)*

**Problem:** The web prediction path (`TrafficApp.services.hybrid_prediction_service`) imported 7 modules directly from `traffic_collector`, tightly coupling the online request path to the background collector.

**Change:** Created a new neutral package **`traffic_context/`** and moved the shared providers into it:
`logger`, `weather_service`, `holiday_service`, `school_service`, `event_detector`, `congestion`, `pressure_score`, `feature_engineering` (via `git mv`, history preserved).

- `traffic_collector/` now keeps only collection concerns: `collector`, `scheduler`, `record_store`.
- Both consumers — `TrafficApp.services` (online) and `traffic_collector` (offline) — now depend on the neutral `traffic_context` package instead of on each other.
- Rewired imports in: `hybrid_prediction_service.py`, `collector.py`, `scheduler.py`, `record_store.py`, `start_collector.py`, `tests.py`.
- **Deleted** dead `traffic_collector/csv_manager.py` (replaced by `record_store.py` in Phase 2; no longer imported).

## 4.2 — Single Google Directions client *(L4)*

**Problem:** The "clean location → call Directions API → read distance/duration/duration_in_traffic off the first leg" logic was copy-pasted in **three** places with divergent timeouts and congestion thresholds (`GoogleMapsService`, `utils.get_realtime_traffic`, `collector.fetch_google_traffic`).

**Change:** Added **`traffic_context/directions_client.py`** as the single place that talks to Google:
- `clean_location()`, `parse_leg_metrics()`, and `DirectionsClient.fetch()` (raises `DirectionsError` on missing key / non-OK status / network error).
- All three callers now delegate to it and only layer their own output shaping on top. Each caller's response shape is **unchanged**.
- Side benefit: `utils.get_realtime_traffic` previously had **no request timeout** (could hang forever) — it now inherits the client's timeout.

## 4.3 — Remove the legacy collector *(M6)*

**Change:** Deleted **`TrafficApp/data_collector.py`** — a second, legacy Distance-Matrix-based collector that was imported nowhere (confirmed dead). `traffic_collector/` is now the single canonical collection path.

## 4.4 — Remove dead frontend endpoints *(M1)*

**Problem:** `static/index.js` posted voice to `/transcribe/` (no such route) and polled `/alerts/` every 120 s (route commented out in `urls.py`) — broken feature + recurring 404s.

**Change:**
- Mic button no longer attempts a recording/upload to the non-existent `/transcribe/`; it now shows a friendly "voice input coming soon" notice. Removed `startRecording`/`stopRecording`/`sendAudioToDjango`.
- Removed the `fetchAlerts()` function and its 2-minute `setInterval` poll. (`loadChatThreads()` on page load is retained.)

## 4.5 — Pin + SRI the Leaflet CDN *(L2)*

**Problem:** `predict.html` loaded Leaflet from `unpkg.com/leaflet` (unversioned, no integrity) — supply-chain / availability risk.

**Change:** Pinned to **`leaflet@1.9.4`** with Subresource Integrity. Hashes were **computed from the actual pinned files**, not copied from memory:
- JS: `sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH`
- CSS: `sha384-sHL9NAb7lN7rfvG5lfHpm643Xkcjzp4jFvuavGOndn6pjVqS6ny56CAt3nsEVT4H`
- Added `crossorigin="anonymous"` (required for SRI on cross-origin assets).

---

## Files touched

| File | Change |
|---|---|
| `traffic_context/__init__.py` | **new** package |
| `traffic_context/{logger,weather_service,holiday_service,school_service,event_detector,congestion,pressure_score,feature_engineering}.py` | **moved** from `traffic_collector/` |
| `traffic_context/directions_client.py` | **new** — single Google client |
| `traffic_collector/csv_manager.py` | **deleted** (dead) |
| `TrafficApp/data_collector.py` | **deleted** (dead legacy collector) |
| `traffic_collector/{collector,scheduler,record_store}.py` | rewired imports; collector uses `DirectionsClient` |
| `TrafficApp/services/google_maps_service.py` | uses `DirectionsClient` + `parse_leg_metrics` |
| `TrafficApp/services/hybrid_prediction_service.py` | imports providers from `traffic_context` |
| `TrafficApp/utils.py` | `get_realtime_traffic` uses `DirectionsClient` |
| `TrafficApp/management/commands/start_collector.py` | logger import path |
| `TrafficApp/static/index.js` | removed dead mic/transcribe + alerts polling |
| `TrafficApp/templates/predict.html` | pinned + SRI Leaflet |
| `TrafficApp/tests.py` | updated module paths; added `DirectionsClientTests` |

## Risks & rollback

- **Risk:** import-graph breakage from the module move / Google output drift from consolidation. **Mitigation:** `manage.py check`, the 36-test suite, and a live prediction all pass.
- **Rollback:** `git revert` of the Phase 4 commit restores the prior layout (moves were `git mv`, so history is intact). No data or schema changes to undo.

## Follow-ups (later phases)

- The collector still imports `TrafficApp.models` inside `record_store` (web↔collector coupling is reduced but not zero) — acceptable; revisit if the collector is split into its own service.
- `utils.find_best_departure_time` / `get_realtime_traffic` remain imported in `views.py` but unused; left in place pending the Phase 5 "recommended departure" work.
