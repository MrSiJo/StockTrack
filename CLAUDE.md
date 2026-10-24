# StockTrack: Claude context

Self-hostable stock watcher: polls retailer listings, pushes Gotify alerts on
stock transitions, distinguishes early access from public availability. It
tracks product availability, NOT shares. Full docs in `docs/`:
**[architecture](docs/architecture.md)**, [installation](docs/installation.md),
[build](docs/build.md), [deployment](docs/deployment.md), [setup](docs/setup.md).
Read those before large changes; this file is just the trap doors.
Deployment specifics and live status are in the gitignored `CLAUDE.local.md`.

## Commands

```bash
# Backend (Python 3.12). --factory matters: create_app is a factory
cd backend && uvicorn stocktrack.main:create_app --factory --reload --port 9180
cd backend && pytest -q                 # asyncio_mode=auto; runs fully offline

# Frontend (Node 22)
cd frontend && npm run dev              # Vite :5173, proxies /api
cd frontend && npm test && npm run build

# One-off listing check without touching the DB
cd backend && python -m stocktrack.cli ao "<listing-url>" --include "cirro" --json

# Stack (two containers), local only. Production deploys from CI on push to
# main (see Deployment below); never deploy prod by hand from a checkout.
docker compose up -d --build
```

## Architecture in one breath

Two containers: `stocktrack-api` (FastAPI :9180) + `stocktrack-ui` (nginx).
nginx serves the SPA and proxies `/api`; the backend never serves the SPA and
there is no CORS in prod. SQLite at `/data` (named volume). Schema via
`Base.metadata.create_all` on startup, **no Alembic**. New *additive* columns
must also be back-filled by the idempotent `ALTER TABLE ADD COLUMN` pass in
`db.py` (`_add_missing_columns`), because `create_all` never alters an
existing table; without it the new column 500s on any existing volume.

## Gotchas (these have bitten us)

* **`curl_cffi>=0.7` is a hard dependency.** It defeats Cloudflare's TLS
  fingerprint wall; plain curl/urllib get 403 on Linux. Never drop it.
* **Delivery safe events**: a transition's `Event` row and phase change are
  persisted *only if the Gotify push succeeds* (`services/poller.py`). Don't
  "simplify" to write then send; History accuracy depends on it.
* **Settings are DB owned**: env vars seed the `setting` table on *first boot
  only*; after that the UI is the source of truth. Changing `.env` won't move a
  live setting.
* **`APP_SECRET_KEY` must stay stable**: it Fernet encrypts the Gotify token at
  rest. Changing it invalidates the stored token.
* **3 phase model**: `oos` / `early` / `public`, split by delivery date
  distance vs `EARLY_ACCESS_DAYS`. Handlers get it via `SiteHandler.configure()`
  each parse; don't read it as a module level constant.

## Repo hygiene (public repo)

* **Never commit** LAN IPs, secrets, or real watch URLs. Pre-commit enforces
  it (gitleaks, bandit, ruff, `forbid-environment-ips`); run `pre-commit install`.
  Forgejo Actions runs the suites (`.forgejo/workflows`); GitHub has no CI.
  If gitleaks fails with `WinError 4551` (Application
  Control), commit from WSL; never `--no-verify`.
* `docs/superpowers/` (specs, plans) and `.env` are git-ignored and stay local.
  `docs/*.md` are the public docs.
* Store plugins (site handlers) are fine to publish; watch URLs are not. See
  `docs/adding-a-store.md` and `docs/plugins.md`. **The built in handlers and
  their tests are maintained in a private plugins repo and synced here** (the
  commit says `chore(sites): sync ...`). Change them there, not here, or the
  next sync overwrites the edit. Core (`sites/__init__.py`, `sites/base.py`) is
  edited here as normal. Details in `CLAUDE.local.md`.
* Deferred work, known limitations and ideas live in
  `docs/superpowers/BACKLOG.md` (local only). Read it before picking up
  follow-ups; lift an item into a spec when tackling it, delete it when done.

## Ship ritual

1. Substantial work goes on a feature branch off `main` (or a worktree), never
   directly on `main`.
2. Build it via the development ritual below (superpowers: brainstorming →
   writing-plans → subagent-driven-development → whole branch review → fixes).
3. `--no-ff` merge to `main` locally; run the full suite on the merged result.
4. `git push origin main` straight to `main`, **no PR**. The push to Forgejo
   deploys: CI runs both suites, then builds, re-pins, health checks
   (including `/api/health/plugins`) and rolls back on failure.
5. Check the deploy went green, smoke test the touched endpoints live, delete
   the branch.

When told "use the ritual", run the whole sequence without re-asking each
step, but still confirm the push: origin is public and it is hard to reverse.

## Development ritual (fleet standard, all *Track apps)

Every non trivial change follows it; do not skip steps because a change seems small.

1. **Spec first.** Agree a short spec (what, why, out of scope). Ask if ambiguous.
2. **Plan** with TDD. Fan independent items out as **parallel waves of sub-agents**, choosing each agent's model by difficulty (lighter models for mechanical edits, the strongest for poller logic, migrations or anything with correctness risk); one commit per logical change.
3. **Build** with full backend and frontend suites green before every commit; pre-commit must pass.
4. **Verify in the browser** against a **local instance seeded with synthetic data**, never prod. Screenshot affected flows, check the console.
5. **Back up before schema/data changes**, API stopped so the copy is consistent (paths in `CLAUDE.local.md`). Rollback = restore the copy + start the previous image.
6. **Deploy** by pushing `main` (CI deploys), then verify health, smoke checks and logs.
7. **Ship** as above. Conventional commits.

## Deployment: Forgejo CI, not Dockge, not the laptop

Since 2026-10-24 production is deployed by the self hosted Forgejo Actions
pipeline on every push to `main`: it builds both images from the commit and
re-pins them in a host stack that holds no source (so it is still not Dockge
managed). Store plugins reach production separately, from the private plugins
repo, through a read only bind mount and an API restart, without an image
rebuild. Host paths, the stack, rollback and logs are in `CLAUDE.local.md`.

The repo `compose.yaml` stays the standalone, build from source stack for
anyone else running StockTrack.
