# StockTrack

A self-hostable web app that watches retailer listing pages and pushes [Gotify](https://gotify.net/) alerts when products come into stock. It distinguishes a pre-public **early-access** buyable window from full public availability, and surfaces a one-tap **add-to-basket** link where the store exposes one.

## Features

- **3-phase stock model** — out-of-stock / early-access / public-availability, with a configurable early-access window (`EARLY_ACCESS_DAYS`)
- **Add-to-basket deep links** — where a store exposes a direct-add link, early-access alerts carry a 🛒 one-tap buy link before the item is public
- **Pluggable store handlers** — ships with AO.com and John Lewis listing-page parsers; add new stores by dropping in a `SiteHandler` subclass
- **Cloudflare-resilient fetching** — `curl_cffi` browser impersonation to get past TLS/HTTP2-fingerprint bot walls
- **Delivery-safe Gotify notifications** — a transition is recorded only if its push is delivered, so a restock is never silently lost
- **Stock history** — reconstructs each product's buyable **episodes** (in → out, how long, early-access lead) from the event log
- **Per-watch scraping health** — tracks consecutive failures and alerts once (not per tick), with a recovery notice
- **React dashboard + settings UI** — manage watches, preview matches live, view history, and configure alerts from a browser

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI · async SQLAlchemy 2 / SQLite · APScheduler |
| Frontend | React 19 · Vite · Tailwind CSS · nginx |
| Deploy | Docker Compose (two services) |

## Quick start

```bash
cp .env.example .env
# Edit .env — set a 32+ character APP_SECRET_KEY (openssl rand -hex 32)
# Optionally set GOTIFY_URL / GOTIFY_TOKEN and SEED_*_URL
docker compose up -d --build
```

The UI is available at `http://localhost:${FRONTEND_PORT:-9181}`. Add watches
via the **Watches** tab. Full walkthrough in [docs/setup.md](docs/setup.md).

## Documentation

- **[Installation](docs/installation.md)** — prerequisites, `.env`, environment variable reference
- **[Build & local dev](docs/build.md)** — image builds, running from source, the check CLI, tests, pre-commit
- **[Deployment & operations](docs/deployment.md)** — deploy, remote Docker hosts, data persistence, backups, updates, monitoring
- **[First-run setup](docs/setup.md)** — adding watches, the 3-phase model, Gotify, history, adding a store
- **[Architecture](docs/architecture.md)** — how it fits together: the stock model, delivery-safety, episode reconstruction, data model

## Security

- The Gotify token is encrypted at rest using Fernet, keyed by `APP_SECRET_KEY`.
- No secrets in the repository — only `.env.example` with blank placeholders.
- Pre-commit hooks: **gitleaks**, **bandit**, **ruff**, and a custom hook that forbids LAN IP literals from being committed.
- Auth is off by default (`AUTH_ENABLED=false`) — StockTrack is designed for single-operator, trusted-LAN use behind your own reverse proxy.

## License

MIT — see [LICENSE](LICENSE).
