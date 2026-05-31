# TrafficPro — Implementation Roadmap

> **Status:** Planning only. No code was modified.
> **Generated:** 2026-05-30
> **Source:** Derived from [ENGINEERING_AUDIT.md](ENGINEERING_AUDIT.md). Issue IDs (C1, H1, M3, …) map back to that document.
> **Companion docs:** [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) · [BACKEND_FLOW.md](BACKEND_FLOW.md) · [ML_PIPELINE.md](ML_PIPELINE.md) · [DATABASE_STRUCTURE.md](DATABASE_STRUCTURE.md) · [THIRD_PARTY_SERVICES.md](THIRD_PARTY_SERVICES.md)

## How to read this roadmap

- **Priority** — P0 (blocker), P1 (urgent), P2 (important), P3 (nice-to-have).
- **Effort** — relative size: XS (<½ day), S (½–1 day), M (2–4 days), L (1–2 weeks), XL (>2 weeks).
- **Dependencies** — tasks (or infra) that must land first.
- **Expected impact** — what improves when done.
- **Implementation order** — global sequence number across all phases (do lower numbers first).

> **Sequencing principle:** Phases are themed, but the *Implementation order* column is the authoritative do-this-next signal. Phase 1 + the CI/deps tasks from Phase 6 should land first because they unblock and protect everything else.

---

## Effort & Sequence Overview

| Order | Task | Phase | Issue | Priority | Effort |
|---|---|---|---|---|---|
| 1 | Define `DEBUG` from env | 1 | C1 | P0 | XS |
| 2 | Pin & complete dependencies | 6 | M2 | P0 | S |
| 3 | Bootstrap CI pipeline | 6 | C3 | P0 | M |
| 4 | Ship & verify model artifacts | 6 | C2 | P0 | M |
| 5 | Send signup OTP email | 1 | C4 | P0 | S |
| 6 | Force HTTPS reset links | 1 | M7 | P1 | XS |
| 7 | Stop leaking errors; structured logging | 1 | H8 | P1 | S |
| 8 | Restrict & rename Google key | 1 | H4 | P1 | S |
| 9 | Shared cache backend (Redis) | 1/3 | H3 | P1 | M |
| 10 | Lazy Supabase client | 1 | M9 | P2 | XS |
| 11 | Durable storage for ML/collection data | 2 | H7 | P1 | L |
| 12 | Split prediction-log vs training CSV schema | 2 | H5 | P1 | M |
| 13 | Move collection records to a DB table | 2 | H7/M3 | P1 | M |
| 14 | DB indexes, pagination, retention | 2 | M4 | P2 | M |
| 15 | Consolidate analytics onto Postgres | 2 | M5 | P2 | S |
| 16 | Cache model in-process (singleton) | 3 | H1 | P1 | S |
| 17 | Cache + parallelize external calls | 3 | H2 | P1 | M |
| 18 | Introduce task queue (Celery/RQ) | 3 | scal. | P2 | L |
| 19 | Extract shared `context/` package | 4 | M8 | P2 | M |
| 20 | Consolidate Google client | 4 | L4 | P2 | S |
| 21 | Remove legacy collector | 4 | M6 | P3 | XS |
| 22 | Clean dead frontend endpoints | 4 | M1 | P2 | S |
| 23 | Pin/SRI or self-host CDN assets | 4 | L2 | P3 | XS |
| 24 | Align train/serve features | 5 | H6 | P1 | L |
| 25 | Expand route encoding / re-train | 5 | H6 | P1 | L |
| 26 | Model validation + versioning gate | 5 | ML note | P2 | M |
| 27 | Standardize model naming / model card | 5 | L1 | P3 | XS |
| 28 | Durable scheduler (Celery Beat/cron) | 6 | M3 | P2 | M |
| 29 | Test suite (auth/predict/RBAC/ML) | 6 | C3 | P1 | L |
| 30 | Observability: metrics, alerting, drift | 6 | obs. | P2 | M |
| 31 | Single deploy target + runbook | 6 | deploy note | P3 | S |

---

## Phase 1 — Critical Security Fixes

> Goal: make the app safe to run and unblock the broken core flows. Nothing else should ship before these.

### 1.1 Define `DEBUG` from environment — *(C1)*
- **Priority:** P0
- **Effort:** XS
- **Dependencies:** none
- **Expected impact:** Eliminates startup `NameError`; production security block (SSL redirect, secure cookies, HSTS) actually applies.
- **Implementation order:** **1**

### 1.2 Send the signup OTP email — *(C4)*
- **Priority:** P0
- **Effort:** S
- **Dependencies:** SendGrid key valid (existing); ideally CI (#3) to lock in a regression test.
- **Expected impact:** Restores end-to-end registration (currently impossible); core onboarding works.
- **Implementation order:** **5**

### 1.3 Force HTTPS on password-reset links — *(M7)*
- **Priority:** P1
- **Effort:** XS
- **Dependencies:** 1.1 (HTTPS posture)
- **Expected impact:** Reset tokens no longer transmitted over plaintext links.
- **Implementation order:** **6**

### 1.4 Stop leaking internal errors; adopt structured logging — *(H8)*
- **Priority:** P1
- **Effort:** S
- **Dependencies:** none (full benefit after observability #30)
- **Expected impact:** No internal detail in client responses; queryable server-side logs for incident response.
- **Implementation order:** **7**

### 1.5 Restrict & rename the Google Maps key — *(H4)*
- **Priority:** P1
- **Effort:** S
- **Dependencies:** Google Cloud console access
- **Expected impact:** Prevents key scraping/billing abuse; clearer separation of browser vs server keys.
- **Implementation order:** **8**

### 1.6 Shared cache backend for rate limiting — *(H3)*
- **Priority:** P1
- **Effort:** M
- **Dependencies:** Redis provisioned (shared infra; also unblocks #17, #18)
- **Expected impact:** Auth/OTP/predict throttles actually hold across workers — real brute-force protection.
- **Implementation order:** **9**

### 1.7 Lazy Supabase client construction — *(M9)*
- **Priority:** P2
- **Effort:** XS
- **Dependencies:** none (mooted if #15 removes Supabase)
- **Expected impact:** A bad Supabase key no longer 500s every route — failure isolated to analytics.
- **Implementation order:** **10**

---

## Phase 2 — Data Pipeline Improvements

> Goal: make collected/training data durable and well-structured so the ML pipeline has a trustworthy source.

### 2.1 Durable storage for ML/collection data — *(H7)*
- **Priority:** P1
- **Effort:** L
- **Dependencies:** Postgres (existing) and/or object storage provisioned
- **Expected impact:** Training data and prediction logs survive restarts/redeploys; ML dataset stops eroding.
- **Implementation order:** **11**

### 2.2 Split prediction-log schema from training CSV — *(H5)*
- **Priority:** P1
- **Effort:** M
- **Dependencies:** 2.1
- **Expected impact:** Eliminates ragged 7-col/20-col CSV; clean, parseable training data.
- **Implementation order:** **12**

### 2.3 Move collection records into a DB table — *(H7, M3)*
- **Priority:** P1
- **Effort:** M
- **Dependencies:** 2.1, 2.2
- **Expected impact:** Concurrency-safe writes, unique `(timestamp, route)` constraint replaces O(file) dedupe; multi-instance safe.
- **Implementation order:** **13**

### 2.4 DB indexes, pagination, retention for chat data — *(M4)*
- **Priority:** P2
- **Effort:** M
- **Dependencies:** none
- **Expected impact:** History endpoints stay fast as data grows; table bloat controlled.
- **Implementation order:** **14**

### 2.5 Consolidate analytics onto Postgres — *(M5)*
- **Priority:** P2
- **Effort:** S
- **Dependencies:** 2.4 (data already in `ChatMessage`)
- **Expected impact:** Removes orphan Supabase dependency; analytics reflect real data; simpler lineage.
- **Implementation order:** **15**

---

## Phase 3 — Performance Improvements

> Goal: cut per-request latency and raise throughput per worker.

### 3.1 Cache the model in-process — *(H1)*
- **Priority:** P1
- **Effort:** S
- **Dependencies:** 6.x model artifacts present (#4)
- **Expected impact:** Removes ~1 MB `joblib.load` per request; lower latency and memory churn.
- **Implementation order:** **16**

### 3.2 Cache & parallelize external calls — *(H2)*
- **Priority:** P1
- **Effort:** M
- **Dependencies:** 1.6 (Redis)
- **Expected impact:** Weather/holiday/geometry no longer refetched each request; Google+weather run concurrently with a deadline; faster, more resilient predictions.
- **Implementation order:** **17**

### 3.3 Introduce a task queue (Celery/RQ + Redis) — *(scalability note)*
- **Priority:** P2
- **Effort:** L
- **Dependencies:** 1.6 (Redis)
- **Expected impact:** Email and heavy post-processing leave the request path; buffering under load; foundation for #28.
- **Implementation order:** **18**

---

## Phase 4 — Architecture Refactoring

> Goal: reduce coupling and dead code so the system is easier to evolve. Pure refactors — no behavior change.

### 4.1 Extract shared `context/` package — *(M8)*
- **Priority:** P2
- **Effort:** M
- **Dependencies:** Phase 1–3 stable (refactor on a known-good base)
- **Expected impact:** Web path and collector no longer share imports directly; independent evolution.
- **Implementation order:** **19**

### 4.2 Consolidate Google Directions client — *(L4)*
- **Priority:** P2
- **Effort:** S
- **Dependencies:** 4.1
- **Expected impact:** One client to fix/maintain; removes threshold drift across the 3 copies.
- **Implementation order:** **20**

### 4.3 Remove the legacy collector — *(M6)*
- **Priority:** P3
- **Effort:** XS
- **Dependencies:** 4.2 (confirm nothing references it)
- **Expected impact:** Less confusion/dead code; single canonical collection path.
- **Implementation order:** **21**

### 4.4 Clean up dead frontend endpoints — *(M1)*
- **Priority:** P2
- **Effort:** S
- **Dependencies:** none
- **Expected impact:** Stops 120s `/alerts/` 404 polling and broken mic posts; quieter logs, fewer wasted requests.
- **Implementation order:** **22**

### 4.5 Pin/SRI or self-host CDN assets — *(L2)*
- **Priority:** P3
- **Effort:** XS
- **Dependencies:** none
- **Expected impact:** Removes supply-chain/availability risk from unpkg/Leaflet.
- **Implementation order:** **23**

---

## Phase 5 — AI and ML Improvements

> Goal: make predictions actually accurate and the model lifecycle trustworthy.

### 5.1 Align train/serve features — *(H6)*
- **Priority:** P1
- **Effort:** L
- **Dependencies:** 2.x (durable, clean data); shared feature function
- **Expected impact:** Removes train/serve skew (`prev_hour_speed`=20.0, duplicated derivations); restores temporal signal.
- **Implementation order:** **24**

### 5.2 Expand route encoding and re-train — *(H6)*
- **Priority:** P1
- **Effort:** L
- **Dependencies:** 5.1, sufficient collected data per route (2.3)
- **Expected impact:** Most of the ~60 routes get real route-specific signal instead of all-zero one-hots.
- **Implementation order:** **25**

### 5.3 Model validation + versioning gate — *(ML note)*
- **Priority:** P2
- **Effort:** M
- **Dependencies:** 5.1, CI (#3)
- **Expected impact:** Bad retrains can't ship (holdout-metric threshold); feature-schema contract enforced; reproducible versions.
- **Implementation order:** **26**

### 5.4 Standardize model naming + model card — *(L1)*
- **Priority:** P3
- **Effort:** XS
- **Dependencies:** 5.3
- **Expected impact:** Ends "LightGBM vs XGBoost" confusion; documented canonical artifact/version.
- **Implementation order:** **27**

---

## Phase 6 — DevOps and Production Readiness

> Goal: the safety net and operational maturity. The first three tasks here are front-loaded into the global order because everything depends on them.

### 6.1 Pin & complete dependencies — *(M2)*
- **Priority:** P0
- **Effort:** S
- **Dependencies:** none
- **Expected impact:** Clean deploys stop failing on missing/incompatible `numpy`/`joblib`/xgboost/apscheduler/holidays; reproducible builds.
- **Implementation order:** **2**

### 6.2 Bootstrap CI pipeline — *(C3)*
- **Priority:** P0
- **Effort:** M
- **Dependencies:** 6.1
- **Expected impact:** Every PR builds from clean deps, runs migrations + lint + tests; catches the class of bugs (C1/C4) that currently ship silently.
- **Implementation order:** **3**

### 6.3 Ship & verify model artifacts — *(C2)*
- **Priority:** P0
- **Effort:** M
- **Dependencies:** 6.1; storage channel (registry/object storage/release asset)
- **Expected impact:** Model reliably present at runtime; startup fails fast if missing; version recorded.
- **Implementation order:** **4**

### 6.4 Durable scheduler for collection — *(M3)*
- **Priority:** P2
- **Effort:** M
- **Dependencies:** 3.3 (task queue) or cron infra; 2.3
- **Expected impact:** HA/multi-instance-safe collection; survives restarts; adaptive backoff + quota budget.
- **Implementation order:** **28**

### 6.5 Test suite (auth, predict, RBAC, ML shaping) — *(C3)*
- **Priority:** P1
- **Effort:** L
- **Dependencies:** 6.2 (CI to run it)
- **Expected impact:** Regression protection for the critical flows; confidence to refactor (Phase 4) and re-train (Phase 5).
- **Implementation order:** **29**

### 6.6 Observability: metrics, alerting, drift — *(obs. note)*
- **Priority:** P2
- **Effort:** M
- **Dependencies:** 1.4 (structured logging)
- **Expected impact:** Visibility into latency, error rates, upstream failures, and prediction drift; faster incident response.
- **Implementation order:** **30**

### 6.7 Single deploy target + runbook — *(deploy note)*
- **Priority:** P3
- **Effort:** S
- **Dependencies:** Phase 1–3 stable
- **Expected impact:** One documented path (Render or PythonAnywhere), removes the stale alternate WSGI bootstrap; reproducible operations.
- **Implementation order:** **31**

---

## Milestones

- **M0 — Releasable (unblock + protect):** orders 1–10 → core flows work, app is safe, CI guards regressions. *(Phase 1 + 6.1–6.3)*
- **M1 — Trustworthy data:** orders 11–15 → durable, clean datasets and analytics. *(Phase 2)*
- **M2 — Fast & scalable:** orders 16–18 → low-latency predictions, shared cache, task queue. *(Phase 3)*
- **M3 — Maintainable:** orders 19–23 → decoupled architecture, no dead code. *(Phase 4)*
- **M4 — Accurate & governed ML:** orders 24–27 → aligned, validated, versioned model. *(Phase 5)*
- **M5 — Operationally mature:** orders 28–31 → durable scheduling, tests, observability, clean ops. *(Phase 6 remainder)*

---

> This roadmap is a plan only. **No application code, configuration, schema, or model artifact was changed.**
