# TrafficPro — Frontend Flow

> **Status:** Understanding-only. No production code was modified.
> **Generated:** 2026-05-30
> **Scope:** Template structure, the JS controller (`static/index.js`), the predict UI, and client↔server interaction.

## 1. Purpose

The frontend is a **server-rendered Django template app** with a single vanilla-JavaScript controller that adds a chat-style, AJAX-driven prediction experience on top of the static pages. There is no SPA framework, build step, or bundler — `index.js` is loaded directly and talks to the backend over `fetch`.

## 2. Template Structure

```
base.html                      # Shared shell: title, head blocks, header/footer/loader/bottom_nav includes
├── landing.html               # Public landing (marketing)
├── sign_in.html / sign_up.html / otp.html
├── predict.html               # Main app: sidebar (history+nav) + chat canvas + input bar
├── analytics.html             # Admin/Analyst dashboard
├── 403.html                   # Permission denied
├── includes/                  # header, footer, bottom_nav, loader, progress_bar, skeletons, contact
└── registration/              # Django password-reset templates + reset email body
```

`predict.html` extends `base.html`, pulls in **Leaflet** (CSS+JS) via `extra_head`, the **Google Maps JS SDK** (`libraries=places&callback=initAutocomplete`, key injected by `predict_view`), and finally `static/index.js?v=1` via `extra_js`. Role-based nav is gated in-template: the Analytics link renders only `{% if user_role == 'Admin' or user_role == 'Analyst' %}`.

## 3. JS Controller (`static/index.js`, ~742 lines)

| Function | Trigger | Action |
|---|---|---|
| `predictTraffic()` | Predict button | Reads origin/destination/day/time, `POST /predict/` with CSRF, renders bot reply |
| `constructBotReply(data, ts)` | after predict | Builds the rich result card (congestion badge, metrics, reasoning, map) |
| `loadChatThreads()` | page load / new thread | `GET /chat-history/` → renders history list |
| `loadThread(id)` | history click | `GET /chat-history/<uuid>/` → replays thread messages |
| `startNewAnalysis()` | New Analysis button | Resets `currentThreadId`, clears chat |
| `initAutocomplete()` | Google SDK callback | Places Autocomplete on origin/destination, biased to Buea (4.1522, 9.2314) |
| `getCookie` / `getCSRFToken` | helpers | Extract `csrftoken` for `X-CSRFToken` header |
| `displayMessage(msg, sender)` | helpers | Append a chat bubble |
| `startRecording` / `stopRecording` / `sendAudioToDjango` | mic button | Voice input → `POST /transcribe/` (**unrouted, 404**) |
| `fetchAlerts()` | `setInterval` 120s + on load | `GET /alerts/` (**unrouted, 404**) |

State is a single module-level `currentThreadId` that ties subsequent predictions to the same `ChatThread`.

## 4. Prediction Request/Response Flow

```
User fills origin/destination (+ optional day/time)
  → predictTraffic()
       UI.startProgress(); displayMessage(status, "user")
       fetch("/predict/", POST x-www-form-urlencoded, X-CSRFToken)
       body: {origin, destination, day, time, [thread_id]}
  ← JSON: {congestion, travel_time, distance, speed, confidence_score,
           probabilities, traffic_pressure_score, pressure_level/trend,
           context_analysis, risk_analysis, ai_reasoning,
           smart_recommendation, polyline, segments_delay,
           is_prediction, hour, day, thread_id, thread_title}
  → branch on data.congestion (Low/Medium/High) → emoji, colors, copy
  → constructBotReply() renders metric grid + reasoning + map polyline
  → if new thread: set currentThreadId, loadChatThreads()
  (data.error → render error bubble)
```

The UI decodes the backend's rich payload into a friendly card: a colored congestion badge, "Smart Forecast" vs "Live Traffic Update" header (`data.is_prediction`), metrics, AI reasoning bullets, optional `recommended_departure` tip, and a map.

## 5. Mapping

Two map libraries are present: **Google Maps JS + Places** (loaded in `predict.html`, used for autocomplete and SDK access) and **Leaflet** (loaded in `extra_head`). Route geometry comes from the backend as an encoded `polyline` in the prediction payload and `segments_delay` for per-segment annotations.

## 6. CSRF & Auth on the Client

- CSRF token is read from the `csrftoken` cookie and sent as the `X-CSRFToken` header on every `fetch` POST.
- The RBAC decorator returns JSON 403 when `X-Requested-With: XMLHttpRequest` is set; note that the `fetch` calls here do **not** set that header, so a forbidden AJAX call would receive the `403.html` page body rather than a JSON error — the client expects JSON.

## 7. Interactions & Dependencies

- **Backend endpoints:** `/predict/`, `/chat-history/`, `/chat-history/<uuid>/` (active); `/transcribe/`, `/alerts/` (missing).
- **External (CDN/SDK):** Google Maps JS SDK + Places, Leaflet (unpkg CDN), Google Fonts / Material Symbols, Tailwind utility classes.
- **Server-injected:** `google_maps_api_key` (from `predict_view`), `user_role`, `contact_form`.

## 8. Risks

1. **Dead endpoints wired to UI** — `fetchAlerts()` polls `/alerts/` every 120s and the mic posts to `/transcribe/`; both 404. The 120s polling generates constant failing requests.
2. **Google Maps API key exposed in HTML** — injected from `GOOGLE_MAPS_API_KEY` into the page (unavoidable for the client SDK, but the key must be **HTTP-referrer/domain restricted** in the Google console).
3. **CDN dependency (unpkg/Leaflet)** — no SRI/pinned version (`unpkg.com/leaflet`), so a CDN outage or content change affects the app; supply-chain exposure.
4. **AJAX 403 mismatch** — forbidden `fetch` calls get HTML (403.html) instead of the JSON the client parses, producing confusing client errors.
5. **No client-side build/minification/cache-busting beyond `?v=1`** — manual versioning is error-prone for cache invalidation.
6. **`alert()`-based validation** and inline HTML string templating (XSS surface if any rendered field were attacker-controlled; currently fields are user's own input echoed back).

## 9. Scalability Concerns

- **Static asset delivery** is handled by WhiteNoise with compressed manifest storage — adequate for moderate traffic, but a CDN in front would be preferable at scale; third-party CDNs (unpkg) are uncontrolled.
- **Polling instead of push** — `fetchAlerts()` every 120s per open tab scales linearly with concurrent users and would hammer the backend once the route exists; a server-push (SSE/WebSocket) or longer interval is preferable.
- **Single monolithic `index.js`** (~742 lines, unbundled) grows without code-splitting; initial load cost increases with features.
- **No client caching of predictions** — repeat queries re-hit the backend (which itself re-calls Google), compounding upstream cost.
