# TrafficPro — Database Structure

> **Status:** Understanding-only. No schema or data was modified.
> **Generated:** 2026-05-30
> **Scope:** Relational schema (Postgres), file-based stores (CSV), and the external Supabase store.

## 1. Purpose

TrafficPro persists data across **three heterogeneous stores**:
1. **PostgreSQL** — primary relational DB (auth, sessions, chat threads/messages).
2. **CSV files** — append-only traffic records used as the ML training/log dataset.
3. **Supabase** — an external table (`chat_history`) read by the analytics dashboard.

## 2. Engine & Configuration

- **Production:** PostgreSQL via `dj_database_url.parse(os.getenv("DATABASE_URL"))` (`psycopg[binary]`).
- **Local:** `db.sqlite3` present; the SQLite `DATABASES` block in `settings.py` is commented out (the active config always uses `DATABASE_URL`).
- `USE_TZ=True`, `TIME_ZONE="Africa/Douala"`; `DEFAULT_AUTO_FIELD=BigAutoField`.

## 3. Application Schema (`TrafficApp/models.py`)

```
┌────────────────────────────┐        ┌────────────────────────────────┐
│ auth_user (Django built-in) │        │ auth_group / Admin/Analyst/    │
│  id, username, email, ...   │        │  Commuter (RBAC roles)         │
└─────────────┬───────────────┘        └────────────────────────────────┘
              │ 1                                  ▲ M:N (user.groups)
              │                                    │
      ┌───────┴────────┐                  ┌────────┴─────────┐
      │ N              │ N                │ used by rbac.py  │
      ▼                ▼                  └──────────────────┘
┌──────────────────┐   ┌──────────────────────────────────────────┐
│ ChatThread       │   │ ChatMessage                               │
│  id   UUID (pk)  │1 N│  id        BigAuto (pk)                    │
│  user FK→User    │◄──│  thread    FK→ChatThread (null, CASCADE)  │
│  title Char(255) │   │  user      FK→User (CASCADE)              │
│  created_at      │   │  message   Text                           │
└──────────────────┘   │  response  JSONField  (full prediction)   │
                       │  timestamp DateTime (auto_now_add)        │
                       └──────────────────────────────────────────┘
```

**`ChatThread`**
- `id`: UUID primary key (non-sequential, good for opaque URLs — used as `/chat-history/<uuid>/`).
- `user`: FK → `auth.User`, `related_name="chat_threads"`, `on_delete=CASCADE`.
- `title`: defaults to `"New Analysis"`; `predict_view` sets it to `"{origin} to {destination}"`.
- `created_at`: `auto_now_add`.

**`ChatMessage`**
- `thread`: FK → `ChatThread`, **nullable** (`null=True, blank=True`), `related_name="messages"`, `CASCADE`.
- `user`: FK → `auth.User`, `related_name="chat_messages"`, `CASCADE`.
- `message`: human prompt, e.g. `"From X to Y"`.
- `response`: **JSONField** storing the entire hybrid prediction payload.
- `timestamp`: `auto_now_add`.

**Migrations:** `0001_initial` (ChatMessage), `0002_chatthread_chatmessage_thread` (adds ChatThread + thread FK). Plus standard Django tables: `auth_*`, `django_session`, `django_admin_log`, `django_content_type`, `django_migrations`.

## 4. File-Based Store — `google_traffic_data_v2.csv`

Two writers, **two different schemas**, same file:

| Writer | Schema (columns) |
|---|---|
| `traffic_collector/csv_manager.py` (`CSVManager`) | `timestamp, route, distance_km, hour, day, day_of_week, travel_time_mins, speed_kmh, congestion, weather_condition, rainfall_status, holiday_indicator, school_holiday_indicator, school_hours_indicator, working_hours_indicator, office_rush_hour_indicator, event_indicator, event_type, event_severity, traffic_pressure_score` (20) |
| `TrafficApp/views.py` (`predict_view`) | `route, distance, hour, day, travel_time, speed, congestion` (7) |

`CSVManager` dedupes by scanning the last 100 lines for `timestamp,route`. `predict_view` appends without dedupe and writes only the header if the file is missing.

## 5. External Store — Supabase `chat_history`

- `analytics_view` runs `supabase.table("chat_history").select("*")` and aggregates counts where `prediction` ∈ {High, Medium, Low}.
- **No write path to Supabase exists** in the reviewed code — the table is read for analytics but nothing observed populates it, so the dashboard may rely on data written elsewhere/manually or be effectively empty. (Worth confirming.)
- Configured via `SUPABASE_URL` / `SUPABASE_KEY`; client created at module import in `views.py`.

## 6. Interactions & Dependencies

- `predict_view` writes **both** Postgres (`ChatThread`+`ChatMessage`) and the CSV per prediction.
- Chat read endpoints (`chat_history_view`, `thread_detail_view`) query Postgres scoped to `request.user`.
- RBAC reads `auth_group` membership (`user.groups`) on every gated request.
- Sessions are DB-backed (`django.contrib.sessions`), so each authenticated request issues a session query.

## 7. Risks

1. **Schema mismatch on shared CSV** — 7-col vs 20-col rows interleaved produce a ragged file; naive `pandas.read_csv` may misalign columns or drop rows, corrupting training data.
2. **Ephemeral filesystem** — on Render/Heroku, the CSV and `db.sqlite3` live on a non-persistent disk; collected/written CSV rows are lost on restart/redeploy unless mounted to durable storage.
3. **Unbounded JSON blobs** — `ChatMessage.response` stores the full prediction payload with no size cap or retention policy; table growth is unbounded.
4. **No indexes beyond defaults** — queries filter `ChatThread` by `user` and order by `created_at`; without an index on `user`/`created_at`, history listing degrades as data grows.
5. **Supabase read with no observed writer** — analytics may be reading a stale/empty table; data lineage is unclear and split across Postgres + Supabase.
6. **Module-level Supabase client** — created at import time; a misconfigured key fails the whole `views` import, not just analytics.
7. **`db.sqlite3` committed** to the repo — stale local data and potential PII leakage.

## 8. Scalability Concerns

- **Postgres** (managed) is the scalable core, but: add indexes on `ChatThread.user`/`created_at` and `ChatMessage.thread`; introduce pagination + retention for chat history; consider moving large `response` JSON to compressed storage if volume grows.
- **DB-backed sessions** add per-request load; a cache-backed session store (Redis) reduces query pressure under concurrency.
- **CSV is not a scalable shared store** — not concurrency-safe, grows linearly, and the dedupe scan is O(file). Migrate ML data to a dedicated table or object storage + columnar format (Parquet).
- **Split storage (Postgres + CSV + Supabase)** complicates consistency, backup, and analytics; consolidating the analytics source into Postgres would simplify scaling and lineage.
