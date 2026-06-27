# Building & local development

For just running the published flow, you only need Docker — see
[deployment](./deployment.md). This page covers building the images and running
the stack from source.

## Build the Docker images

The stack is two images, both built from the compose file:

```bash
docker compose build
# or build + run:
docker compose up -d --build
```

`--build` forces a fresh image. The frontend build (`npm run build`) runs
*inside* the UI image build, so a `git pull` + `--build` is all that's needed
to ship frontend or backend changes.

- **`stocktrack-api`** — `python:3.12-slim`, installs `requirements.txt`, runs
  as a non-root user, exposes `:9180`, and `HEALTHCHECK`s `GET /api/health`.
- **`stocktrack-ui`** — multi-stage `node:22-alpine` build → `nginx:alpine`
  serving the static bundle and proxying `/api` to `stocktrack-api:9180`.

## Local development (without Docker)

Useful for fast iteration. Run the backend and frontend in two terminals.

### Backend (Python 3.12)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# minimal env: a 32+ char secret and a local SQLite DB
export APP_SECRET_KEY=$(openssl rand -hex 32)
export DATABASE_URL="sqlite+aiosqlite:///./data/stocktrack.db"
uvicorn stocktrack.main:create_app --factory --reload --port 9180
```

The backend serves only `/api/*` — point the Vite dev server at it (below).
The CORS allow-list already includes Vite's `http://localhost:5173`.

### Frontend (Node 22)

```bash
cd frontend
npm ci
npm run dev          # Vite dev server on :5173, proxies /api to the backend
```

`npm run build` produces the static bundle the nginx image serves from
`/usr/share/nginx/html`.

## One-off check CLI

Fetch and classify a listing without touching the DB — handy for verifying a
new watch URL or debugging a parser:

```bash
cd backend
python -m stocktrack.cli ao "https://ao.com/<listing-url>" --include "cirro" --json
```

`store` is a registered handler name (`ao`, `johnlewis`); `--include` /
`--exclude` are comma-separated substring filters; `--json` prints structured
output. It prints each matched product's stock state, phase, price, and links.

## Tests

Keep both suites green before deploying.

### Backend (pytest)

```bash
cd backend
pytest -q
```

`asyncio_mode = auto` is set in `pyproject.toml`, so async tests need no
decorator. The suite runs fully offline — site fetches and Gotify sends are
injected/stubbed (`check_watch` and `gotify.send` accept overrides).

### Frontend (vitest)

```bash
cd frontend
npm test             # vitest run
npm run build        # tsc + vite build the production image uses
```

## Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

Configured in `.pre-commit-config.yaml`:

- **gitleaks** — secret scanning
- **bandit** — Python security linting (`backend/stocktrack`, `-ll`)
- **ruff** — Python lint + autofix (`backend/`)
- **forbid-environment-ips** — a local hook (`scripts/forbid_environment_ips.py`)
  that fails the commit if any RFC1918 LAN IP literal is staged

## Project layout

```
backend/stocktrack/      FastAPI app
  api/routes/            REST endpoints (status, events, history, stores, watches, settings)
  api/schemas.py         pydantic request/response models
  services/              poller, gotify sender, history reconstruction, settings, formatting
  sites/                 SiteHandler registry + per-store parsers (ao, johnlewis)
  models/                SQLAlchemy models (watch, product, event, setting)
  bootstrap.py           pydantic-settings env config
  crypto.py              Fernet encrypt/decrypt for secret settings
  main.py                app factory + lifespan (DB init, seed, scheduler)
  cli.py                 one-off check CLI
backend/tests/           pytest suites
frontend/src/            React SPA
  pages/ components/     UI
  api/ stores/ lib/      client, zustand stores, pure helpers
  tests/                 vitest suites
docs/                    this documentation
compose.yaml             two-service deployment
```
