# Installation

Getting StockTrack onto a machine. For building images and local dev see
[build](./build.md); for running it in production see
[deployment](./deployment.md); for first-run configuration see
[setup](./setup.md).

## Prerequisites

**To run (recommended):**

- Docker with Compose v2 (`docker compose`, not the legacy `docker-compose`).
- A [Gotify](https://gotify.net/) server, if you want push notifications
  (optional — StockTrack runs without it and just records transitions).
- A reverse proxy if you want TLS. LAN-only by intent.

**To develop / build from source:** additionally Python 3.12 and Node 22 —
see [build](./build.md).

## Get the code

```bash
git clone https://github.com/MrSiJo/StockTrack.git
cd StockTrack
```

## Configure the environment

StockTrack reads configuration from a `.env` file at the repo root (Compose
loads it via `env_file`).

```bash
cp .env.example .env
# generate a strong secret and put it in .env as APP_SECRET_KEY
openssl rand -hex 32
```

`APP_SECRET_KEY` is **required** and validated at startup — the app refuses to
start if it is shorter than 32 characters. It encrypts the Gotify token at
rest, so keep it stable: changing it invalidates the stored token.

> Never commit real values. `.env` is git-ignored; only `.env.example` (blank
> placeholders) is tracked. A pre-commit hook also blocks RFC1918 LAN IP
> literals from being staged — see [build](./build.md#pre-commit-hooks).

### Environment variables

| Name | Required | Default | Notes |
| --- | --- | --- | --- |
| `APP_SECRET_KEY` | yes | — | 32+ chars (`openssl rand -hex 32`). Encrypts the Gotify token at rest. |
| `DATABASE_URL` | no | `sqlite+aiosqlite:////data/stocktrack.db` | Async SQLite URL. |
| `DATA_DIR` | no | `/data` | Data directory inside the container. |
| `AUTH_ENABLED` | no | `false` | Flag for trusted-LAN deployments. |
| `COOKIE_SECURE` | no | `true` | Marks cookies secure (HTTPS). |
| `FRONTEND_PORT` | no | `9181` | Host port mapped to the UI container's `:80`. |
| `BACKEND_PORT` | no | `9180` | Backend port (also the optional debug host map). |
| `TZ` | no | `Europe/London` | Timezone for the poll scheduler. |
| `LOG_LEVEL` | no | `INFO` | Backend log level. |
| `GOTIFY_URL` | no | — | Base URL of your Gotify server. Blank disables push. |
| `GOTIFY_TOKEN` | no | — | Gotify application token (encrypted at rest). |
| `GOTIFY_PRIORITY` | no | `7` | Default push priority. |
| `RESTOCK_PRIORITY` | no | `8` | Priority for restock (in-stock) alerts. |
| `OOS_PRIORITY` | no | `4` | Priority for out-of-stock alerts. |
| `PRICE_DROP_PRIORITY` | no | `6` | Priority for price-drop alerts. |
| `GOTIFY_SEND_RETRIES` | no | `3` | Retries on 5xx / network errors (4xx never retried). |
| `FAILURE_ALERT_AFTER` | no | `6` | Consecutive scrape failures before a health alert. |
| `HEARTBEAT_HOURS` | no | `0` | Periodic "still alive" heartbeat; `0` disables. |
| `DEFAULT_INTERVAL_SECONDS` | no | `300` | Poll-loop tick interval. |
| `EARLY_ACCESS_DAYS` | no | `30` | Delivery-date distance that separates `early` from `public`. |
| `AO_MEMBER` | no | `false` | Whether the scraping account holds an AO.com membership (affects pricing shown). |
| `PRICE_DROP_MIN_PCT` | no | `5` | Minimum price drop percentage to trigger a price-drop alert. |
| `PRICE_DROP_MIN_ABS` | no | `5` | Minimum absolute price drop (£) to trigger a price-drop alert. |
| `SEED_AO_URL` | no | — | Auto-seed an AO.com watch on first boot; blank to add via UI. |
| `SEED_JL_URL` | no | — | Auto-seed a John Lewis watch on first boot; blank to add via UI. |

Gotify and poller values seeded here are copied into the database on first
boot; after that, edit them in the UI (Gotify / Watches settings). See
[setup](./setup.md).

## Next step

Once `.env` is in place, continue to [deployment](./deployment.md) to build and
run, then [setup](./setup.md) to add watches and configure alerts.
