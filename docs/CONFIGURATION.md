# Environment configuration

`TrafficPro/settings.py` reads process environment variables and loads a root `.env` file through `python-dotenv`. The repository’s `.gitignore` excludes `.env` and `.env.*`; keep credentials in local environment or deployment secret storage and never commit them. Values shown here describe names and behavior only.

## Application settings

| Variable | Required when | Purpose and behavior | Secret? |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Always | Django signing key. Settings access it as a required environment variable; startup fails if it is absent. Use a unique local development value and a separately generated production value. | Yes |
| `DATABASE_URL` | Always | Database connection URL parsed by `dj-database-url`; active settings do not enable the commented SQLite configuration. PostgreSQL is the documented project database. | Yes; contains credentials |
| `DEBUG` | Optional | Defaults to `False`. Only `1`, `true`, `yes`, or `on` (case-insensitive) enable debug mode. With debug disabled, production security settings include HTTPS redirect and HSTS; use `True` for local HTTP development. | No |
| `ALLOWED_HOSTS` | Optional | Comma-separated hosts. Defaults to local hostnames and a project Render hostname; Render’s `RENDER_EXTERNAL_HOSTNAME`, when present, is added automatically. Set the actual hostnames for the environment. | No |
| `GOOGLE_MAPS_API_KEY` | For live route predictions and collection | Google Directions and browser map integration. This key is rendered into the browser, so restrict it by referrer and enabled APIs. `GOOGLE_MAPS_API` is accepted as a legacy alternative name. | Credential; browser-exposed and must be restricted |
| `OPENWEATHER_API_KEY` | Optional | Enables weather context. Without it, the weather service returns an unknown-weather fallback. | Yes |
| `SENDGRID_API_KEY` | For outbound email | Used by custom SendGrid email calls and Django’s SendGrid SMTP configuration. | Yes |
| `DEFAULT_FROM_EMAIL` | For outbound email | Sender address used by email services. Configure an address accepted by the SendGrid account. | No, but deployment-specific |
| `VAPID_PUBLIC_KEY` | For browser push notifications | Public application-server key passed to the browser. | No; intentionally public |
| `VAPID_PRIVATE_KEY` | For sending push notifications | Signs web-push requests server-side. | Yes |
| `VAPID_SUBJECT` | Optional for push | VAPID contact subject; settings default to a placeholder address. Set an appropriate contact value for a real deployment. | No, but deployment-specific |
| `REDIS_URL` | Optional | Enables Django’s Redis cache. Without it, settings use local-memory cache, so cache and rate-limit counters are not shared across processes. | Yes; contains credentials when applicable |
| `SENTRY_DSN` | Optional | Enables Sentry initialization when set. `send_default_pii` is disabled in the configured SDK initialization. | Treat as sensitive configuration |
| `CRON_SECRET` | When using `/tasks/run/` | Shared secret checked by the scheduled-task endpoint. The scheduled workflow must send the matching value in its request header. | Yes |
| `TASK_ALWAYS_EAGER` | Optional | Defaults to false. Truthy values run the project’s asynchronous task seam synchronously, primarily for tests or local debugging. | No |
| `RENDER_EXTERNAL_HOSTNAME` | Platform-provided on Render | Render hostname added to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`. Do not set unless the deployment platform requires it. | No |

## Declared but not established as active configuration

`SUPABASE_URL` and `SUPABASE_KEY` are read into settings, and the Supabase package is present in `requirements.txt`. The current analytics view reads Django’s `PredictionLog`; the inspected runtime code did not establish an active Supabase use. Do not configure or remove these solely based on this guide: confirm any deployment-specific usage first.

## Local `.env` example

Use placeholders and replace them only in your local, ignored `.env` file. Do not commit the file or paste real values into documentation.

```dotenv
DJANGO_SECRET_KEY=replace-with-a-local-development-secret
DATABASE_URL=postgresql://DB_USER:DB_PASSWORD@127.0.0.1:5432/DB_NAME
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
GOOGLE_MAPS_API_KEY=replace-with-a-restricted-google-api-key
```

Add optional integration variables only when you configure those integrations. See [SETUP.md](SETUP.md) for the local setup flow and [DEPLOYMENT.md](DEPLOYMENT.md) for deployment context.
