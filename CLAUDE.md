# StockTrack — Claude context

Self-hostable stock watcher: polls retailer listings, pushes Gotify alerts on
stock transitions, distinguishes early-access from public availability.
Full docs in `docs/` — **[architecture](docs/architecture.md)**,
[installation](docs/installation.md), [build](docs/build.md),
[deployment](docs/deployment.md), [setup](docs/setup.md). Read those before
large changes; this file is just the trap-doors.

## Commands

```bash
# Backend (Python 3.12) — note the --factory flag, create_app is a factory
cd backend && uvicorn stocktrack.main:create_app --factory --reload --port 9180
cd backend && pytest -q                 # asyncio_mode=auto; runs fully offline

# Frontend (Node 22)
cd frontend && npm run dev              # Vite :5173, proxies /api
cd frontend && npm test && npm run build

# One-off listing check without touching the DB
cd backend && python -m stocktrack.cli ao "<listing-url>" --include "cirro" --json

# Stack (two containers) — remote deploy target is the `docker-host` context
docker compose up -d --build
docker --context docker-host compose up -d --build
```

## Architecture in one breath

Two containers: `stocktrack-api` (FastAPI :9180) + `stocktrack-ui` (nginx).
nginx serves the SPA and proxies `/api` to the backend — the backend never
serves the SPA, and there's no CORS in prod (same origin). SQLite at `/data`
(named volume). Schema via `Base.metadata.create_all` on startup — **no Alembic**.

## Gotchas (these have bitten us)

- **`curl_cffi>=0.7` is a hard dependency**, not optional. It defeats
  Cloudflare's TLS-fingerprint wall; plain curl/urllib get 403 on Linux. Never
  drop it from `backend/requirements.txt`.
- **Delivery-safe events**: a transition's `Event` row and phase change are
  persisted *only if the Gotify push succeeds* (`services/poller.py`). Don't
  "simplify" this to write-then-send — it's load-bearing for History accuracy.
- **Settings are DB-owned**: env vars seed the `setting` table on *first boot
  only*; after that the UI is source of truth. Changing `.env` won't move a
  live setting.
- **`APP_SECRET_KEY` must stay stable** — it Fernet-encrypts the Gotify token
  at rest. Changing it invalidates the stored token.
- **3-phase model**: `oos` / `early` / `public`, split by delivery-date
  distance vs `EARLY_ACCESS_DAYS`. Handlers get it via `SiteHandler.configure()`
  each parse — don't read it as a module-level constant.

## Repo hygiene (public repo)

- Public GitHub repo. **Never commit**: LAN IPs, secrets, or real watch URLs.
  Pre-commit enforces this (gitleaks, bandit, ruff, `forbid-environment-ips`) —
  run `pre-commit install`.
- `docs/superpowers/` (specs/plans) and `.env` are git-ignored and stay local.
  `docs/*.md` are the public docs.
- Store plugins (site handlers) are fine to publish; watch URLs are not.
