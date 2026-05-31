# Phase 2 — Data Pipeline Improvements — Changelog

> **Date:** 2026-05-30
> **Scope:** Implements Phase 2 of [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md). Issue IDs map to [ENGINEERING_AUDIT.md](ENGINEERING_AUDIT.md).
> **Schema impact:** One new migration — `TrafficApp/migrations/0003_predictionlog_trafficrecord_and_more.py`.
> **Validation:** `manage.py check` → 0 issues; `manage.py test` → 25 passing; migration applies cleanly.

---

## Summary

Phase 2 moves the data layer off fragile files and an external Supabase table onto durable, indexed PostgreSQL tables. Collected traffic data and per-prediction logs now live in the database; the analytics dashboard reads local Postgres; and chat history is paginated with a retention path.

| Issue | Severity | Status |
|---|---|---|
| H7 — Ephemeral-disk loss of ML/collection data | High | ✅ Fixed (DB store + export command) |
| H5 — Dual-schema writes to one training CSV | High | ✅ Fixed (separate `PredictionLog` table) |
| M3 — O(file), non-concurrency-safe dedup | Medium | ✅ Fixed (DB unique constraint) |
| M4 — No indexes / pagination / retention for chat data | Medium | ✅ Fixed |
| M5 — Analytics read from orphan Supabase table | Medium | ✅ Fixed (aggregates from Postgres) |

---

## Changes by file

### `TrafficApp/models.py`
- **New `TrafficRecord`** — durable store for the collection pipeline (the 20-field collected schema). Unique constraint `(timestamp, route)` replaces the file-scan dedup; indexes on `(route, timestamp)` and `congestion`.
- **New `PredictionLog`** — per-prediction log written by `predict_view` (origin/destination/distance/hour/day/travel_time/speed/congestion/is_prediction/user). Kept **separate** from the training dataset so schemas never collide. Indexes on `congestion` and `created_at`.
- **`ChatThread` / `ChatMessage`** — added `Meta.ordering` and indexes (`idx_thread_user_created`, `idx_message_thread_time`).

### `TrafficApp/migrations/0003_predictionlog_trafficrecord_and_more.py`
- Auto-generated: creates the two models, the unique constraint, and all indexes. No data migration.

### `traffic_collector/record_store.py` (new)
- `TrafficRecordStore.append_record()` — ORM-backed, concurrency-safe insert via `get_or_create` on `(timestamp, route)`; returns `True`/`False` for created/skipped. Naive collector timestamps are made timezone-aware.

### `traffic_collector/collector.py`
- Uses `TrafficRecordStore` instead of `CSVManager`; calls `close_old_connections()` at the start of each collection cycle (safe ORM use from the long-lived APScheduler thread). (`csv_manager.py` is left in place but no longer used by the runtime path.)

### `TrafficApp/views.py`
- **`predict_view`** — replaced the 7-column CSV append with a `PredictionLog.objects.create(...)`. No more runtime writes to `google_traffic_data_v2.csv`.
- **`chat_history_view`** — paginated (`?page`, `?page_size`, clamped 1–100, default 20). Response keeps the `history` key the frontend expects and adds `page`/`num_pages`/`total`/`has_next`.
- **`analytics_view`** — aggregates High/Medium/Low counts from `PredictionLog` (Postgres); the Supabase client/import/`get_supabase()` helper were removed.

### `TrafficApp/management/commands/export_training_data.py` (new)
- `manage.py export_training_data [--output PATH]` — exports `TrafficRecord` rows to a clean CSV for the ML notebook (default `BASE_DIR/traffic_training_export.csv`).

### `TrafficApp/management/commands/purge_old_data.py` (new)
- `manage.py purge_old_data [--days 180] [--dry-run]` — retention: deletes chat threads (messages cascade) and prediction logs older than N days.

### `TrafficApp/tests.py`
- +9 tests (25 total): record-store create/dedup/validation, analytics-from-Postgres counts, chat pagination + clamping, and the export/purge commands.

---

## Behaviour changes

- The app **no longer writes** `google_traffic_data_v2.csv` at runtime (neither the collector nor predictions). The existing file is left untouched as historical training data; regenerate a clean dataset from the DB with `export_training_data`.
- Analytics now reflects **local prediction logs**, not the external Supabase `chat_history` table.
- `/chat-history/` returns at most `page_size` (default 20) threads per call.

---

## Deployment / operational notes

1. **Run the migration:** `python manage.py migrate` (creates `TrafficRecord`, `PredictionLog`, indexes, constraint). This is required before deploying the new code paths.
2. **Optional backfill:** historical rows in `google_traffic_data_v2.csv` are *not* imported automatically (the legacy file mixes two schemas). Import selectively if needed; new data accrues in `TrafficRecord`.
3. **Retraining workflow:** run `export_training_data` to produce a clean CSV for `Model_training.ipynb`.
4. **Retention:** schedule `purge_old_data --days N` (e.g. via cron / the Phase 6 scheduler) to bound table growth.

## Rollback

`python manage.py migrate TrafficApp 0002` then `git revert` the Phase 2 commit(s). The legacy CSV path still exists in history; no destructive data change was made (the old CSV remains on disk).

## Out of Phase 2 scope (still tracked)

- Per-request model load (H1) and blocking external calls (H2) — Phase 3.
- Train/serve skew and route coverage (H6) — Phase 5.
- Durable scheduler for the collector (M3 scheduler half) — Phase 6.
- Removing the now-unused `csv_manager.py` and legacy `data_collector.py` — Phase 4 cleanup.
