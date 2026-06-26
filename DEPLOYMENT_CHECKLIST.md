# Production Deployment Checklist — Dashboards

Click-by-click steps to finish the non-code production hardening. Do them in the
order below to avoid downtime. Menu labels may shift slightly as dashboards update.

**Recommended order:** Redis → Render env vars → Worker → Sentry → Google key → SendGrid → rotate secrets last.

---

## 1. Render

### 1a. Provision Redis (for rate-limiting + Directions cache)
- [ ] Render Dashboard → **New +** → **Key Value** (Render's Redis-compatible store).
- [ ] Name it `traffik-redis`, pick the same region as your web service, choose the Free plan.
- [ ] Click **Create**.
- [ ] Open it → copy the **Internal Key Value URL** (starts with `redis://`).
- [ ] You'll paste this as `REDIS_URL` in step 1b.

### 1b. Set environment variables (web service)
- [ ] Dashboard → your web service (**traffik237**) → **Environment** tab.
- [ ] Add / confirm these (Add Environment Variable for each):
  - [ ] `DEBUG` = `False`  ← **critical: turns on HTTPS redirect, HSTS, secure cookies**
  - [ ] `REDIS_URL` = *(the Internal URL from 1a)*
  - [ ] `DJANGO_SECRET_KEY` = *(see step 6 — rotate)*
  - [ ] `DATABASE_URL` = *(your Supabase URL; rotate password in step 6)*
  - [ ] `ALLOWED_HOSTS` = `traffik237.onrender.com`
  - [ ] `GOOGLE_MAPS_API_KEY` = *(new restricted key from step 4)*
  - [ ] `OPENWEATHER_API_KEY` = *(existing)*
  - [ ] `SENDGRID_API_KEY` = *(new key from step 5)*
  - [ ] `DEFAULT_FROM_EMAIL` = *(your verified sender from step 5)*
  - [ ] `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` = *(from your local `.env`)*
  - [ ] `SENTRY_DSN` = *(from step 3)*
- [ ] **Tip:** Create an **Environment Group** (Dashboard → Environment Groups → New) with all of these, then link it to BOTH the web and worker services — set once, shared.
- [ ] Click **Save Changes** (triggers a redeploy).

### 1c. Set the health check path (web service)
- [ ] Web service → **Settings** → scroll to **Health Check Path**.
- [ ] Set to `/healthz/` → **Save Changes**.

### 1d. Create the Background Worker (runs collector + alerts + email outbox)
- [ ] Dashboard → **New +** → **Background Worker**.
- [ ] Connect the **same GitHub repo / branch** as the web service.
- [ ] **Build Command:** `pip install -r requirements.txt`
- [ ] **Start Command:** `python manage.py start_collector`
- [ ] Under **Environment**, attach the **same Environment Group** from 1b (or re-add the same vars). The worker needs at minimum: `DJANGO_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `GOOGLE_MAPS_API_KEY`, `OPENWEATHER_API_KEY`, `SENDGRID_API_KEY`, `DEFAULT_FROM_EMAIL`, all `VAPID_*`, `SENTRY_DSN`, `DEBUG=False`.
- [ ] **Create Background Worker.**
- [ ] After it boots, check **Logs** for "Starting Traffic Scheduler..." (and no "ML artifact MISSING" warning).

> ⚠️ Without 1d, gridlock alerts, data collection, and queued emails never run in production.

---

## 2. (Alternative to manual Render setup) Blueprint
If you'd rather declare everything from the repo:
- [ ] Commit `render.yaml` (already in the repo).
- [ ] Render → **New +** → **Blueprint** → select the repo.
- [ ] Render reads `render.yaml`, creates the **web + worker**, and prompts for each `sync: false` secret.
- [ ] Fill in the secrets when prompted → **Apply**.
*(Use either this OR the manual steps above, not both.)*

---

## 2b. Background jobs on the FREE plan (no worker) — GitHub Actions cron
Render's free plan has **no background worker**, so an external scheduler triggers
the collector/alerts + drains the outbox by calling `/tasks/run/`.

- [ ] Pick a long random value for `CRON_SECRET` (e.g. `python -c "import secrets;print(secrets.token_urlsafe(32))"`).
- [ ] **Render** → web service → Environment → add `CRON_SECRET` = *(that value)*.
- [ ] **GitHub** → your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:
  - [ ] `CRON_SECRET` = *(the same value)*
  - [ ] `APP_URL` = `https://traffik237.onrender.com` *(no trailing slash)*
- [ ] The workflow `.github/workflows/scheduled-tasks.yml` is already in the repo; it runs every 20 min.
- [ ] Test now: GitHub → **Actions** tab → **Scheduled tasks** → **Run workflow**. It should succeed (green).
- [ ] Manual curl check (optional):
  `curl -X POST https://traffik237.onrender.com/tasks/run/ -H "X-Cron-Secret: <secret>"` → `{"status":"ok",...}`.

> If you later upgrade to a paid plan, re-add the `worker` service (`start_collector`) and you can delete this cron.

---

## 3. Sentry (error monitoring)
- [ ] Go to https://sentry.io → sign up / log in → **Create Project**.
- [ ] Platform: **Django**. Name: `traffik`. Click **Create Project**.
- [ ] On the setup screen, copy the **DSN** (looks like `https://<key>@o123.ingest.sentry.io/456`).
- [ ] Paste it as `SENTRY_DSN` in Render (step 1b) for **both** web and worker.
- [ ] (Optional) Project → **Settings** → **Alerts** → confirm "Issue Alerts" emails you on new errors.
- [ ] Verify: after deploy, hit a deliberately broken URL or check Sentry's "first event" status.

---

## 4. Google Cloud — restrict & rotate the Maps API key
The Maps key is exposed in the browser, so it **must** be restricted.

### 4a. Create a new (replacement) key
- [ ] https://console.cloud.google.com → select your project.
- [ ] **APIs & Services** → **Credentials**.
- [ ] **+ Create Credentials** → **API key**. Copy the new key.

### 4b. Restrict the new key
- [ ] Click the new key to edit it.
- [ ] **Application restrictions** → **Websites** (HTTP referrers) → **Add**:
  - [ ] `https://traffik237.onrender.com/*`
  - [ ] `http://localhost:8000/*` and `http://127.0.0.1:8000/*` (for local dev)
- [ ] **API restrictions** → **Restrict key** → tick only the 3 this project uses:
  - [ ] **Directions API** (server-side route/traffic lookups)
  - [ ] **Maps JavaScript API** (the map on the predict page)
  - [ ] **Places API** (origin/destination autocomplete; may show as "Places API (New)")
- [ ] **Save**.

### 4c. Swap and delete the old key
- [ ] Put the new key in Render as `GOOGLE_MAPS_API_KEY` (step 1b) and redeploy.
- [ ] Confirm predictions + the map still work.
- [ ] Back in Credentials, **delete the old unrestricted key**.
- [ ] (Recommended) **APIs & Services** → **Billing** → set a **budget alert** so abuse can't silently run up cost.

---

## 5. SendGrid — sender auth & key rotation

> **Important — read before choosing:** Domain Authentication (SPF/DKIM) requires a domain
> whose **DNS you control**. It does **NOT** work on a free `*.onrender.com` address — Render
> owns `onrender.com`'s DNS, so you can't add the required records and "Verify" stays Pending.
> It also can't be done on a `gmail.com` address. So:
> - **Option A (best):** only if you **own a real domain** (e.g. bought `yourdomain.com`).
>   Authenticate THAT domain and send from `noreply@yourdomain.com`.
> - **Option B (quick, free, recommended for this project):** **Single Sender Verification**
>   of `traffik147@gmail.com`. Works immediately; deliverability is slightly lower.
>
> If you started Domain Authentication on an `onrender.com` subdomain, delete that attempt
> (Sender Authentication → the domain → delete) — it can never verify.

### 5a. Verify a sender
- [ ] https://app.sendgrid.com → **Settings** → **Sender Authentication**.
- [ ] **Option A (domain you own):** **Authenticate Your Domain** → pick DNS host → add the **CNAME records** SendGrid shows to your DNS → **Verify**. Then set `DEFAULT_FROM_EMAIL` to an address on that domain.
- [ ] **Option B (Gmail address):** **Verify a Single Sender** → enter `traffik147@gmail.com` details → confirm via the email SendGrid sends.

### 5b. Rotate the API key
- [ ] **Settings** → **API Keys** → **Create API Key**.
- [ ] Name: `traffik-prod`. Permission: **Restricted Access** → enable **Mail Send** only. **Create & View**.
- [ ] Copy the key → set as `SENDGRID_API_KEY` in Render (step 1b). Redeploy.
- [ ] Test: trigger a password reset or signup OTP; confirm the email arrives (check spam if 5a not done).
- [ ] Delete the old API key from the list.

---

## 6. Rotate the remaining exposed secrets
These were visible on screen, so rotate them.

### 6a. Django SECRET_KEY
- [ ] Generate a new one locally:
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- [ ] Set it as `DJANGO_SECRET_KEY` in Render (web + worker). *(Note: this logs everyone out — expected.)*

### 6b. Supabase database password
- [ ] https://supabase.com → your project → **Settings** → **Database** → **Reset database password**.
- [ ] Copy the new password → rebuild your `DATABASE_URL` with it → update in Render (web + worker).
- [ ] Redeploy; confirm `/healthz/` returns `{"status":"ok"}`.

### 6c. (Already covered) Google key → step 4, SendGrid key → step 5.

---

## 7. Supabase backups (bonus)
- [ ] Supabase → project → **Database** → **Backups** → confirm daily backups are enabled (Pro plan) or note the free-tier limit.
- [ ] Do one **manual export** now (`Database` → backups → download, or `pg_dump`) so you have at least one off-platform copy before the defense.

---

## Final smoke test (after all of the above)
- [ ] Visit `https://traffik237.onrender.com/healthz/` → `{"status":"ok"}`.
- [ ] Log in, make a prediction → result shows (model loaded, no degraded output).
- [ ] Open **Analytics** as admin → charts render.
- [ ] **Alerts** page → Enable notifications → **Send test** → push arrives.
- [ ] Worker **Logs** show the scheduler running and no "ML artifact MISSING" warning.
- [ ] Trigger a password reset → email arrives via SendGrid.
- [ ] Force an error → it appears in Sentry.
