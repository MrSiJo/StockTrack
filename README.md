# StockTrack

A self-hostable web app that watches retailer listing pages and pushes [Gotify](https://gotify.net/) alerts when products come into stock. It distinguishes a pre-public **early-access** buyable window from full public availability, and surfaces a one-tap **add-to-basket** link where the store exposes one.

## Features

- **3-phase stock model** — out-of-stock / early-access / public-availability, with configurable early-access window (`EARLY_ACCESS_DAYS`)
- **Pluggable store handlers** — ships with AO.com and John Lewis listing-page parsers; add new stores by dropping in a `SiteHandler` subclass
- **Cloudflare-resilient fetching** — `curl_cffi` browser impersonation to avoid bot blocks
- **Delivery-safe Gotify notifications** — restock alerts sent at high priority; out-of-stock notifications duration-tagged and de-duped
- **Per-watch scraping health** — tracks consecutive failures and last-seen timestamps without alert spam
- **React dashboard + settings UI** — manage watches, view stock history, and configure alerts from a browser

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI · async SQLAlchemy / SQLite · APScheduler |
| Frontend | React · Vite · Tailwind CSS |
| Deploy | Docker Compose |

## Quick start

```bash
cp .env.example .env
# Edit .env — set a 32+ character APP_SECRET_KEY
# Optionally set GOTIFY_URL / GOTIFY_TOKEN and SEED_*_URL
docker compose up -d --build
```

The UI is available at `http://localhost:${FRONTEND_PORT:-9181}`.  
Add watches via **Settings → Watches** in the UI.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `APP_SECRET_KEY` | *(required)* | 32+ char secret for session signing |
| `AUTH_ENABLED` | `false` | Enable login gate (intended for trusted-LAN use) |
| `GOTIFY_URL` | | Base URL of your Gotify server |
| `GOTIFY_TOKEN` | | Gotify application token (encrypted at rest) |
| `EARLY_ACCESS_DAYS` | `7` | Days a product stays in "early access" before promoting to public |
| `DEFAULT_INTERVAL_SECONDS` | `300` | Poll interval per watch (seconds) |
| `SEED_AO_URL` | | Auto-seed a watch for an AO.com listing on first boot; leave blank to add via UI |
| `SEED_JL_URL` | | Auto-seed a watch for a John Lewis listing on first boot; leave blank to add via UI |

## Security

- Gotify token is encrypted at rest using Fernet symmetric encryption
- No secrets in the repository — only `.env.example` with blank placeholders
- Pre-commit hooks: **gitleaks** (secret scanning), **bandit** (Python security), **ruff** (linting), and a custom hook that forbids environment IPs from being committed
- Auth is disabled by default (`AUTH_ENABLED=false`) — this app is designed for single-operator, trusted-LAN use

## Adding a store

Drop a `SiteHandler` subclass in `backend/stocktrack/sites/` and register it in the handler registry. Each store needs a small bespoke listing-page parser that maps the store's HTML/JSON structure to the shared `Product` schema.

## License

MIT — see [LICENSE](LICENSE).
