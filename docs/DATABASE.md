# Database and persistence

The application uses Django’s ORM and migrations for its primary relational data. `TrafficPro/settings.py` builds the default database from `DATABASE_URL`; PostgreSQL is used in the checked-in deployment configuration. See [CONFIGURATION.md](CONFIGURATION.md) for connection configuration and [SETUP.md](SETUP.md) for local setup.

## Models and relationships

All application models are defined in `TrafficApp/models.py`. Django’s built-in `User` model is the user identity referenced by these records.

| Model | Purpose and key relationships |
|---|---|
| `ChatThread` | A user-owned prediction/conversation thread. Deleting the user cascades to their threads. |
| `ChatMessage` | Stores the submitted message and JSON response. It belongs to a user and may reference a thread; thread deletion cascades to its messages. |
| `TrafficRecord` | Durable collected route/context observations used as training data. A unique `(timestamp, route)` constraint deduplicates collection records; indexes support route/time and congestion queries. |
| `PredictionLog` | One prediction record with route, travel metrics, congestion, optional user and model confidence. The analytics view uses these records. User deletion sets the optional user relation to null. |
| `AnalyticsEvent` | Lightweight guest/signup funnel events, with optional session key and user relation. Deleting a user leaves the event and clears its user reference. |
| `TrustedDevice` | Stores a user’s trusted-device token hash, metadata, and expiry. The raw token is kept in the browser cookie rather than this model. |
| `PushSubscription` | Stores a browser push endpoint and subscription keys for a user. The endpoint is unique. |
| `RouteWatch` | A user’s route and optional day/time preferences for gridlock alerts. User and route combination is unique. |
| `TrafficAlert` | Records a sent alert window for deduplication; has a user relation and an optional route-watch relation. |
| `TaskOutbox` | Persists registered asynchronous work, its JSON payload, status, attempts, and error details for processing/retry. It is not a Celery queue. |

The analytics dashboard uses `TrafficRecord` for collected observations and route/context analysis. Its admin usage panels also use `PredictionLog` and user records; the guest conversion funnel uses `AnalyticsEvent`. The current view does not read analytics from Supabase. `TrafficRecord` is also the source for collected traffic history used by the export/training workflow.

## Migrations

Schema changes are in `TrafficApp/migrations/`. Apply them with `python manage.py migrate` after configuring `DATABASE_URL`. CI runs `makemigrations --check --dry-run`, Django system checks, migrations, and the test suite; see [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). Those checks are not asserted to pass here because they were not run for this documentation update.

## Traffic data and training export

The collector writes ORM records to `TrafficRecord`; prediction requests write to the separate `PredictionLog` table. Training data can be exported from collected records with:

```bash
python manage.py export_training_data
```

The command writes `traffic_training_export.csv` in the project root by default. Use `--output PATH` to choose another destination. The export includes collected route metrics and context fields; it does not export prediction logs. The training command has its own default input path, so pass the export explicitly when needed (see [ML_PIPELINE.md](ML_PIPELINE.md)).

The `purge_old_data` command removes old `ChatThread` records (and their related messages through cascade) and old `PredictionLog` records. It does not purge `TrafficRecord` or other models. Review its `--dry-run` output and retention requirements before scheduling deletion.

## Other storage/configuration notes

- `DATABASE_URL` is the configured database source; a local `db.sqlite3` file is ignored and is not selected by an active default SQLite settings block.
- `REDIS_URL`, when configured, supplies Django’s cache backend. Without it, cache data is local-memory and process-local.
- Supabase variables and a client dependency remain in the repository, but current analytics use Django records. Their deployment-specific use has not been established by the current analytics implementation.
