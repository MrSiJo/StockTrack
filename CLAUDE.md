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
New *additive* columns are also back-filled onto pre-existing tables by an
idempotent `ALTER TABLE ADD COLUMN` pass in `db.py` (`_add_missing_columns`),
because `create_all` never alters an existing table — adding a column to a model
without this would 500 on any deployment with an existing data volume.

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
  See `docs/adding-a-store.md` for the handler pattern.

## Development ritual (fleet standard — all *Track apps)

Every non-trivial change follows the same ritual. Do not skip steps because a change "seems small" — the ritual is what keeps the fleet consistent.

1. **Spec first.** Write or agree a short spec (what's changing, why, and what's out of scope) before touching code. If requirements are ambiguous, ask before building.
2. **Plan.** Break the spec into an implementation plan. Use TDD — failing test, then implementation, then green. Where work items are independent, fan out **parallel waves of sub-agents** rather than working serially; keep one commit per logical change.
3. **Build.** Implement with the full backend and frontend test suites green before every commit. Pre-commit hooks (gitleaks / bandit / ruff) must pass.
4. **Verify in the browser.** For anything UI-visible, drive the app with Chrome browser automation against a **local instance seeded with synthetic data** — never against prod data. Screenshot the affected flows; check the console for errors.
5. **Back up before schema/data changes.** If the deploy includes a schema or data migration, back up the database on the docker host FIRST, with the API container stopped so the copy is consistent:
   `docker stop <api-container> && cp -a /dockerdata/<app>/data /dockerdata/backups/<app>-$(date +%Y%m%d-%H%M%S)`
   Rollback = restore the copy + start the previous image.
6. **Deploy** to the `docker-host` context on the LAN (never the `default` context) using this repo's documented deploy method, then verify: containers healthy, endpoint smoke checks pass, logs clean.
7. **Ship it properly.** Conventional commit messages, push to `origin/main`, and where the repo has GitHub Actions (public images / release-please), confirm the runs go green.
