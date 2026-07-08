# StockTrack — Code Quality Review

**Date:** 2026-07-08 · Part of a review of all `*Track` apps; cross-app index at `C:\code\TRACK-APPS-CODE-REVIEW.md`.

## How to use this document (instructions for a Claude session)

This is a code-quality review of StockTrack, one of Simon's personal projects. If you've been given finding IDs (e.g. "implement STOCK-H1"):

1. **IDs** are `STOCK-<PRIORITY><n>` — `H` high, `M` medium, `L` low/polish.
2. **Scope discipline:** findings are about code quality, correctness, optimisation, and consistency — do NOT add features, change end-user functionality, or redesign UI. Keep each fix minimal and targeted.
3. **This is a personal project** — don't add enterprise ceremony unless a finding explicitly calls for it.
4. **Verify line numbers before editing** — this is a snapshot from 2026-07-08; re-locate code by the symbols/strings named in the finding.
5. Run the test suites (pytest backend — 185 tests; vitest frontend) before and after changes; each finding's `Verify:` note gives a functional check.
6. **Secrets:** untracked local `.env` files are known and fine — do not "fix" them.
7. **Commits:** one per finding (or tightly-related group), message referencing the ID, e.g. `fix: transition delisted products to OOS (STOCK-H1)`.

**Effort key:** `quick` = minutes, single-file · `small` = under an hour · `involved` = multi-file / needs care and testing.

---

**Stack:** Python 3.12 / FastAPI + async SQLAlchemy 2 (SQLite via aiosqlite) + APScheduler backend; React 19 + Vite + Tailwind 4 + zustand frontend behind nginx; two-container Docker Compose; pytest (185 tests) + vitest; ruff/bandit/gitleaks pre-commit.

**Overall assessment:** A genuinely well-built hobby app — clear layering (sites/services/api/models), a thoughtfully engineered delivery-safe alert pattern with revert closures, an additive-migration shim in place of Alembic, strong test coverage for the core poller, and clean git hygiene (no secrets, caches, or data tracked). The findings below are mostly logic gaps and consistency drift rather than structural problems. The biggest issues are a stock-model blind spot (delisted products never go out of stock) and an operational one (the server never configures logging, so the poll loop is effectively silent).

## High priority

### STOCK-H1 — Products that disappear from a listing never transition to OOS
*(effort: involved)*
`check_watch` (`backend/stocktrack/services/poller.py:294-298, 325`) only iterates products present in the current parse; rows in the DB but absent from the page are never touched. Retailers routinely delist out-of-stock items, so such a product stays `public`/`in stock` on the dashboard forever, its history episode stays "ongoing" indefinitely, and no OOS alert ever fires — silently breaking the app's core promise. The `Product.last_seen` column (`backend/stocktrack/models/product.py:30`) is written every tick but never read.
**Fix:** after the parse loop, treat rows with `code not in parsed` and a non-oos phase as OOS transitions (or at least mark them stale after N ticks using `last_seen`), reusing the existing delivery-safe pending-alert machinery.
**Verify:** add a poller test where a previously in-stock product is absent from the fixture HTML — it must transition to OOS and queue an alert.
**Status:** fixed — absence detection after the parse loop via the delivery-safe pending machinery; conservative rule (absent from a non-empty parse AND `last_seen` older than 2× `interval_seconds`) avoids flapping on partial parses; empty parses never delist. 5 new poller tests (disappear, grace, reappear, relist-restock, delivery-safe failure).

### STOCK-H2 — Logging is never configured in the server; `LOG_LEVEL` is dead
*(effort: quick)*
`main.py:19` creates the `stocktrack` logger but nothing calls `logging.basicConfig()`; under uvicorn only the `uvicorn.*` loggers get handlers, so `log.info("[%s] %s", watch.store, res)` (`main.py:41`) and every other INFO record vanishes (Python's last-resort handler only emits WARNING+). Meanwhile `Settings.log_level` (`backend/stocktrack/bootstrap.py:13`) and the documented `LOG_LEVEL` env var are read into config and never used. The CLI (`cli.py:6`) does configure logging — only the long-running service, where it matters most, doesn't.
**Fix:** `logging.basicConfig(level=env.log_level, ...)` in `lifespan`.
**Verify:** container logs show per-tick INFO lines after restart.
**Status:** fixed — `logging.basicConfig(level=env.log_level.upper(), ...)` in `lifespan`; no-op under pytest where the root logger already has handlers. (Container restart verification left for the next deploy — no deploys from this session.)

### STOCK-H3 — Phantom auth settings + API published directly on the host
*(effort: quick)*
`bootstrap.py:10-11` defines `auth_enabled` (default `True`) and `cookie_secure`, both `.env.example` files document them, and the README's Security section says "Auth is off by default (`AUTH_ENABLED=false`)" — but no auth code exists anywhere in the app, and the defaults contradict each other (`true` in code, `false` in root `.env.example`, `true` in `backend/.env.example`). On top of that, `compose.yaml:9-10` publishes the unauthenticated API on host port 9180 (labelled "optional debug"), bypassing the nginx proxy entirely. For a public repo whose README implies an auth toggle, this misleads users.
**Fix:** delete `auth_enabled`/`cookie_secure` and the README claim (or implement the toggle), and comment out the 9180 host port mapping by default.
**Status:** fixed — settings deleted from bootstrap, both `.env.example`s, README, `docs/installation.md` and `docs/deployment.md`; README now states plainly there is no built-in auth; `:9180` host mapping commented out in `compose.yaml` with a note.

## Medium priority

### STOCK-M1 — No per-watch lock: manual "Check now" can race the scheduler tick and double-fire alerts
*(effort: small)*
`POST /watches/{id}/check` (`backend/stocktrack/api/routes/watches.py:70-80`) and `poll_tick` (`main.py:40`) both run `check_watch` with independent sessions. Fetches take seconds-to-minutes (see STOCK-M6), so both can read the same pre-transition state, both push to Gotify, and both commit duplicate `Event` rows — which also corrupts episode reconstruction (two `public` events, doubled counts).
**Fix:** a module-level `dict[int, asyncio.Lock]` keyed by watch id around `check_watch` is enough for a single-process app.
**Status:** fixed — `check_watch` is now a locking wrapper around `_check_watch`, one `asyncio.Lock` per watch id; test proves two concurrent checks produce one push and one event (verified to fail without the lock).

### STOCK-M2 — Recovery notice fires after a single blip, defeating the failure-alert threshold
*(effort: quick)*
`main.py:42-51` sends "✅ recovered" whenever `prev_failures > 0`, but the "⚠️ can't read" alert only fires at `consecutive_failures == threshold` (default 6). One transient network error therefore produces a recovery push for a failure you were never told about — exactly the noise the threshold was designed to suppress. Also, the `== threshold` equality check (`main.py:64`) means lowering the threshold mid-streak (e.g. 6→3 when count is already 4) never alerts.
**Fix:** gate recovery on `prev_failures >= threshold`, and use `>=` with an "already alerted" marker for the failure alert.
**Status:** fixed — in-memory `_failure_alerted` set of watch ids whose failure alert was actually delivered; recovery fires only for alerted (or `>= threshold`) streaks, failure alert uses `>=` + marker (fires once per streak, still fires when threshold is lowered mid-streak, retries if the push fails). 4 new tests.

### STOCK-M3 — `default_interval_seconds` is UI-editable but only takes effect on restart
*(effort: small)*
The poll job is scheduled once from the env value (`main.py:90-92`), yet the setting is seeded to the DB, exposed in `GET/PUT /settings` (`api/routes/settings.py:56-58`) and shown in the UI, implying it's live. This contradicts the project's own "settings are DB-owned; digest re-reads every tick" principle (`main.py:94` comment).
**Fix:** read it from the DB each tick and `scheduler.reschedule_job`, or drop it from the settings UI and document it as env-only.
**Status:** fixed — live-reschedule option: `poll_tick` re-reads the DB setting each tick and `reschedule_job`s its own "poll" job when the value moves (matches the DB-owned-settings principle). 2 new tests.

### STOCK-M4 — `heartbeat_hours` is a dead setting wired through the whole stack
*(effort: quick)*
Defined in `bootstrap.py:23`, seeded (`settings_service.py:90`), exposed in the API (`api/routes/settings.py:29,62`), present in schemas and both `.env.example` files, but no heartbeat job or consumer exists anywhere. Users setting it get nothing.
**Fix:** remove it end-to-end (or implement the heartbeat push).
**Status:** fixed — removed end-to-end: bootstrap, seed, API keys/schemas, both `.env.example`s, docs (installation/setup), frontend types and the settings form field. No heartbeat feature implemented.

### STOCK-M5 — Fernet decrypt failure is swallowed, silently disabling all alerts while still recording transitions
*(effort: quick)*
`get_secret` (`services/settings_service.py:27-29`) returns `""` on any decrypt exception; `gotify.send` treats an empty token as "unconfigured" and returns `True` (`services/gotify.py:32-34`), so every pending alert's `on_success` runs. If `APP_SECRET_KEY` ever changes, notifications stop with zero log output and events keep persisting as if delivered.
**Fix:** `log.error("gotify_token decrypt failed — APP_SECRET_KEY changed?")` in the except branch; consider surfacing it on `/api/status`.
**Status:** fixed — ERROR log in the except branch naming the setting and pointing at `APP_SECRET_KEY`; test asserts the log record. `/api/status` surfacing skipped as scope creep for a quick finding.

### STOCK-M6 — Manual check can exceed nginx's 60s proxy timeout
*(effort: small)*
The fetch layer tries up to 6 impersonation targets × 30s each on bot-wall statuses (`sites/base.py:96-114`), City Plumbing adds a second GraphQL POST with the same fallback chain, and Gotify retries add 3+6s backoffs — worst case several minutes — while `frontend/nginx.conf:15` sets `proxy_read_timeout 60s`. The browser gets a 504 and "Check failed" even though the check completes server-side.
**Fix:** raise the timeout for this route, or cap the fallback chain's total budget (e.g. 2 targets or an overall deadline).
**Status:** fixed — `proxy_read_timeout` raised 60s → 300s for `/api/` with an explanatory comment. Capping the impersonation-chain budget was deliberately not done: it would change fetch semantics behind real bot walls.

### STOCK-M7 — Unbounded event growth + `/api/history` loads the entire table every request
*(effort: small)*
`api/routes/history.py:20-27` selects all products and all events into memory on every History page view, and nothing ever prunes `event` rows. Fine today; a year of 5-minute polling on price-volatile watches will make the History page progressively slower.
**Fix:** either a retention setting (delete events older than N days, keeping episode boundaries) or filter the query by a time window / store server-side.
**Status:** fixed — new DB-owned `event_retention_days` setting (default 0 = keep forever, wired env→seed→API→UI) plus a daily `retention_tick` scheduler job. The sweep preserves episode boundaries: any episode ongoing or ended inside the window keeps all its events from its opening transition; closed episodes age out wholesale (an orphan `oos` is already ignored by `build_episodes`). 6 new tests. `/api/history` still loads whole tables per request — acceptable once retention bounds the table.

### STOCK-M8 — Watch deletion is a hand-rolled N+1 cascade
*(effort: small)*
`api/routes/watches.py:157-175` loads every product, then loops a per-product `SELECT` of events and deletes row-by-row. Same pattern class as `/api/status`'s per-watch product query (`api/routes/status.py:16-19`).
**Fix:** two bulk deletes (`delete(Event).where(Event.product_id.in_(select(Product.id).where(Product.watch_id == id)))`) or FK `ondelete="CASCADE"` + relationship cascade; `/api/status` can use one `selectinload` or a single join.
**Status:** fixed — two bulk DELETEs in `delete_watch`; `/api/status` now runs one product query grouped in memory (no relationships exist on the models, so no `selectinload`).

## Low priority / polish

### STOCK-L1 — Duplicated, divergent delivery-date parsing
*(effort: small)* — `poller._parse_delivery_date`/`_MONTH_NUMS` (`poller.py:121-152`) and `ao._delivery_days_out`/`_MONTHS` (`sites/ao.py:17-19, 89-106`) parse the same "3rd July" strings with different month tables and different year-inference (closest-to-now vs roll-forward), and the AO one calls `datetime.date.today()` (container-local wall clock, untestable) while the poller version takes `now` as a parameter. Extract one shared helper taking `now`.
**Status:** fixed — new `stocktrack/dateparse.py` with one month table/regex and `parse_delivery_date(text, today, roll_forward=)`; poller uses closest-to-now mode, AO uses roll-forward (its "far date ⇒ early" semantics depend on never inferring a past year) with an injectable `today`. New `test_dateparse.py`.

### STOCK-L2 — `.env.example` drift
*(effort: quick)* — root and `backend/.env.example` disagree (AUTH_ENABLED true vs false, DATABASE_URL path), and both are missing ~10 newer settings the code seeds (`NEW_PRODUCT_PRIORITY`, `LEAD_TIME_*`, `ALERT_GROUP_THRESHOLD`, `PRICE_DROP_IN_STOCK_ONLY`, `DIGEST_*`, `CP_*`). Low impact since settings are DB-owned after first boot, but the reference doc is stale.
**Status:** fixed — both files rewritten with the full seeded-setting list (incl. the new `EVENT_RETENTION_DAYS`); AUTH/COOKIE vars already removed by STOCK-H3. The `DATABASE_URL` path difference is intentional (container vs local dev) and kept.

### STOCK-L3 — 4 tests hard-fail without `curl_cffi`
*(effort: quick)* — `tests/test_sites_base.py:43` imports it directly; on a machine without the wheel the suite reports 4 failures despite CLAUDE.md's "runs fully offline" claim. Use `pytest.importorskip("curl_cffi")` in those tests.
**Status:** fixed — the 4 tests use `pytest.importorskip("curl_cffi.requests")`. (curl_cffi was installed on this machine, so the baseline showed no failures.)

### STOCK-L4 — Test deps ship in the production image
*(effort: quick)* — `backend/requirements.txt:13-14` includes `pytest`/`pytest-asyncio`, installed by the Dockerfile. Split a `requirements-dev.txt`.
**Status:** fixed — `backend/requirements-dev.txt` (`-r requirements.txt` + pytest pins); `docs/build.md` dev setup updated; Dockerfile unchanged (installs runtime file only).

### STOCK-L5 — `sites/base.py` import-time side effects and print-based warnings
*(effort: quick)* — line 11 silently does `os.environ.pop("CURL_IMPERSONATE")` (undocumented why), and `_warn` (`base.py:63-64`) prints to stderr instead of using `logging` like the rest of the app. Once STOCK-H2 is fixed, switch to a module logger and comment the pop.
**Status:** fixed — `_warn` now logs via a module logger; the `CURL_IMPERSONATE` pop is documented (curl-impersonate reads the env var itself, which would pin every request and defeat the fallback chain).

### STOCK-L6 — Dead frontend state
*(effort: quick)* — `checkToast`/`clearCheckToast` in `frontend/src/stores/statusStore.ts:10,23,39` are declared and clearable but never set anywhere. Remove.
**Status:** fixed — removed; vitest + build pass.

### STOCK-L7 — Stale branches and agent worktrees
*(effort: quick)* — a divergent legacy `master` branch coexists with `main`, three merged `worktree-agent-*` branches plus `backlog-sweep`, `lead-time-slide-suppression`, `feat/stocktrack-m1-fullstack` linger, and three `.claude/worktrees/*` checkouts (one containing a full copied venv, ~13k files) are still registered. `git worktree prune` + branch cleanup.
**Status:** partial — all three worktree checkouts removed from disk and pruned; merged branches `backlog-sweep` and `lead-time-slide-suppression` deleted. The `worktree-agent-*` branches turned out NOT to be ancestry-merged (no merge base with `main` — orphan roots), so per instructions they were left alone along with `master` and `feat/stocktrack-m1-fullstack`; all five are stale 2026-06-27-or-earlier snapshots whose content is superseded by `main` — Simon to decide on deletion (`git branch -D`).

### STOCK-L8 — Money as `float`
*(effort: n/a — accepted)* — prices flow as floats end-to-end. Acceptable here: the app compares against user thresholds rather than doing arithmetic ledgers, and the one float-equality (`digest.py:55-56`) compares values from the same source. Not worth converting; just don't add float summation later.
**Status:** accepted — no action, as recorded in the finding.

## Patterns snapshot

- **Config:** pydantic-settings env vars (`.env`) seed a DB `setting` table on first boot; DB/UI is source of truth thereafter; secrets Fernet-encrypted at rest keyed by `APP_SECRET_KEY`
- **Logging:** stdlib `logging` with named loggers; never configured in the server (CLI only) — effectively no logs at INFO (see STOCK-H2)
- **DB access:** async SQLAlchemy 2.0 (`Mapped`/`mapped_column`), SQLite + aiosqlite, `create_all` + custom idempotent `ALTER TABLE ADD COLUMN` shim instead of Alembic; custom `UTCDateTime` TypeDecorator for tz-aware datetimes
- **Scheduling:** APScheduler `AsyncIOScheduler`, interval jobs, `max_instances=1`; blocking HTTP (curl_cffi/httpx) pushed through `asyncio.to_thread`
- **Frontend:** React 19 + TypeScript + Vite 8, Tailwind CSS 4 (via `@tailwindcss/vite`), zustand, react-router 7; fetch wrapper with typed `ApiError`
- **Tests:** pytest + pytest-asyncio (`asyncio_mode=auto`), 185 passing, HTML fixtures for parsers, heavy poller coverage; vitest for frontend lib functions (2 test files)
- **Docker:** two containers (FastAPI + nginx SPA/proxy), named volume for SQLite, healthcheck on API only, backend runs non-root, `restart: unless-stopped`; UI container has no healthcheck and nginx runs as root
- **Lint/format:** ruff + bandit + gitleaks + custom LAN-IP blocker via pre-commit (backend); oxlint (frontend)
- **Scripts:** Python only (`scripts/*.py`, with its own test file); no ps1/sh
