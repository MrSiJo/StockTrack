# Architecture

How StockTrack fits together. For running it, see [installation](./installation.md),
[build](./build.md), [deployment](./deployment.md), and [setup](./setup.md).

## Shape

Two containers behind one compose file. A FastAPI backend polls retailer
listing pages on a schedule and pushes Gotify alerts on stock transitions;
an nginx container serves the React SPA and reverse-proxies `/api` to the
backend, so the browser only ever talks to one origin. SQLite is the only
datastore; the retailer sites and a Gotify server are the only external calls.

```
Browser ──HTTP──▶ nginx (stocktrack-ui :80)
                    ├── serves the compiled SPA (/usr/share/nginx/html)
                    └── proxies /api/* ─▶ FastAPI (stocktrack-api :9180)
                                            ├── REST API (/api/*)
                                            ├── APScheduler poll loop
                                            ├── SQLite at /data/stocktrack.db
                                            ├── retailer listing pages (fetch)
                                            └── Gotify server (push, egress)
```

There is no separate database server, queue, or cache. The backend never
serves the SPA itself — nginx does, and same-origin `/api` proxying means no
CORS in production (the CORS allow-list in `main.py` exists only for the Vite
dev server on `:5173`).

## Components

- **Frontend** — React 19 + Vite + TypeScript + Tailwind v4, with `zustand`
  for state and `react-router` for routing. Built to static assets at
  image-build time and served by nginx in production; Vite serves it in dev.
  Pages: **Dashboard**, **History**, and the **Watches / Gotify / Stores**
  settings tabs (`frontend/src/components/Layout.tsx`).
- **Backend** — FastAPI (Python 3.12) + async SQLAlchemy 2 + `aiosqlite`.
  `curl_cffi` browser impersonation powers the fetch layer (see below).
  `Base.metadata.create_all` builds the schema on startup — no Alembic; the
  model set is small and additive.
- **Poller** — APScheduler runs one `poll_tick` job every
  `DEFAULT_INTERVAL_SECONDS`; each tick checks every enabled watch
  (`services/poller.py`). The per-watch `interval_seconds` is stored on the
  row but the scheduler currently drives all watches off the one global tick.
- **Site handlers** — one `SiteHandler` subclass per store
  (`sites/ao.py`, `sites/johnlewis.py`), registered in `sites/__init__.py`.
  Each maps a store's listing HTML/JSON to the shared `Product` dataclass.
- **Notifications** — a delivery-safe Gotify sender (`services/gotify.py`).
- **History** — pure episode reconstruction over the event log
  (`services/history.py`), exposed read-only at `GET /api/history`.

## The 3-phase stock model

Every product sits in one of three phases, derived per check:

- **`oos`** — not buyable.
- **`early`** — in stock with a *far-future* placeholder delivery date (a
  pre-public early-access window — e.g. AO listing a unit as "Home delivery
  from 1st January" while the product page still shows out-of-stock). Buyable
  via a direct add-to-basket deep link before it goes public.
- **`public`** — in stock with a near, real delivery date.

A handler classifies `early` vs `public` by how far out the delivery date is,
against the `EARLY_ACCESS_DAYS` threshold (default 30). The poller passes the
live DB setting into the handler via `SiteHandler.configure()` before each
parse, so changing the threshold in the UI takes effect without a redeploy.

## Transitions, events, and delivery-safety

`check_watch` compares each product's previous phase to the freshly parsed
phase and acts only on a *change*:

| Transition | Alert | Event written |
| --- | --- | --- |
| `oos → early` | ⚡ Early access (with 🛒 basket link) | `early_access` |
| `oos/early → public` | 🟢 In stock / Now public | `public` |
| `early/public → oos` | 🔴 Out of stock again (with duration) | `oos` (carries `available_seconds`) |

The rule is **delivery-safe**: the event row and the new phase are persisted
*only if the Gotify push succeeded*. If the alert fails to send, the product's
state is reverted so the transition is retried on the next tick rather than
silently lost. This means there is at most one event per real transition,
which the history reconstruction relies on.

## Episode reconstruction

The **History** view is computed, not stored. `build_episodes(events, now)`
walks a product's event rows in ascending time and pairs each in-stock spell
with the next `oos` to form an **episode** (a contiguous buyable window):

- start = first `early_access` / `public` after OOS or the start of the log
- `early_access_ts` / `public_ts` = the phase timestamps within the spell
- end = the next `oos` (its stored `available_seconds` is the buyable duration);
  no trailing `oos` ⇒ the episode is **ongoing** (`now − start`)
- `early_lead_seconds` = `public_ts − early_access_ts` when both exist

`build_history` groups episodes by product with per-product summaries (episode
count, average buyable time, average early-access lead). The function is pure
over `(events, now)`, so it is unit-tested without a DB or network.

## Data model

SQLAlchemy models in `backend/stocktrack/models/`:

- **Watch** — one store listing to poll: `store`, `url`, include/exclude
  filters, `enabled`, plus scraping-health columns (`last_checked_at`,
  `last_ok_at`, `consecutive_failures`, `last_error`).
- **Product** — one SKU under a watch (unique on `watch_id + code`). Carries
  the current `availability` phase, `current_in_stock`, `current_price`,
  `basket_url`, and `available_since` (when the current buyable spell began).
- **Event** — an immutable transition row: `kind` ∈ `early_access` / `public`
  / `oos`, `ts`, `price`, and `available_seconds` (on `oos` events). This log
  is the sole input to history reconstruction.
- **Setting** — a key/value store for runtime config. Secret values (the
  Gotify token) are stored Fernet-encrypted; `is_secret` flags them.

## Configuration & secrets

Settings live in two layers. Environment variables (`bootstrap.py`,
pydantic-settings) provide boot defaults; `seed_from_env` copies them into the
`setting` table on first boot **only if not already set**, after which the UI
is the source of truth. The Gotify token is encrypted at rest with Fernet,
keyed by `APP_SECRET_KEY` (`crypto.py`) — so `APP_SECRET_KEY` must stay stable;
changing it invalidates the stored token. See [installation](./installation.md)
for the variable reference.

## The fetch layer (Cloudflare resilience)

`sites/base.py` fetches listing HTML through `curl_cffi` browser impersonation,
which defeats the TLS/HTTP2-fingerprint bot wall that returns 403/429/503 to
plain `curl`/`urllib` on Linux. It tries a primary impersonation target and
falls back through a list of browser profiles on a bot-wall status, then
degrades to system `curl` and finally `urllib` if `curl_cffi` is unavailable.
This is why `curl_cffi>=0.7` is a hard dependency, not optional.

## Where things live (in the container)

| Thing | Location |
| --- | --- |
| Database | `/data/stocktrack.db` (named volume `stocktrack-data`) |
| Compiled SPA | `/usr/share/nginx/html` (ui container) |
| API | `stocktrack-api:9180` (proxied as `/api`) |
| Health check | `GET /api/health` |

`/data` is the only directory that must persist — it is the mounted data
volume (see [deployment](./deployment.md)).
