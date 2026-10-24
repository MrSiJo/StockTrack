# Deployment & operations

Day-2 operations: deploy, data persistence, proxying, backups, updates,
maintenance. Prerequisites and env vars are in [installation](./installation.md);
creating your account, adding watches and configuring alerts is in
[setup](./setup.md).

## Deploy

StockTrack is two containers behind your own reverse proxy.

```bash
docker compose up -d --build
```

This builds both images and starts them. The UI is published on the host at
`http://localhost:${FRONTEND_PORT:-9181}`; the UI container proxies `/api` to
the backend on the internal compose network, so the backend does not need to
be published. The backend's `9180:9180` host map in `compose.yaml` is optional
(debug only) — comment it out if you don't need it.

### Deploying to a remote Docker host

Point the Docker CLI at the remote daemon with a context — the images build
locally and ship to the remote daemon, same command:

```bash
docker context create docker-host --docker "host=ssh://user@docker-host"
docker --context docker-host compose up -d --build
```

## Data persistence (named volume)

The compose file mounts a named volume for the data directory:

```yaml
volumes:
  - stocktrack-data:/data
```

Everything that must survive a redeploy lives under `/data` — the SQLite
database (`stocktrack.db`). The containers are otherwise disposable.

## Reverse proxy

Terminate TLS at your proxy and point it at
`http://<docker-host>:${FRONTEND_PORT:-9181}`. The UI container is the only one
that needs to be reachable; it proxies `/api` internally.

The proxy must pass the `Authorization` request header through to StockTrack
unchanged. Some proxy features (for example an access list or a basic auth
layer) replace or strip that header, which breaks API token clients. If a token
works when you call the app host directly but not through the proxy, check for
this first.

## Authentication

Everything except the open paths below needs a signed in session or, for a short
read only list, an API token. Create your account straight after the first
deploy (see [setup](./setup.md#create-your-account-first-run)): until you do,
anyone who can reach the instance can complete setup.

### HTTPS and COOKIE_SECURE

`COOKIE_SECURE` defaults to `true`: the session and CSRF cookies are marked
`Secure`, so browsers only send them over HTTPS, and StockTrack expects to run
behind a proxy with TLS. An install served over plain HTTP must set
`COOKIE_SECURE=false` in `.env` (and recreate the containers). Otherwise the
browser drops the cookie and every request after sign in is refused. The sign in
page notices this and says so.

### The secret key and rotation

`APP_SECRET_KEY` has two jobs:

* it encrypts the stored Gotify token (Fernet), and
* it signs session cookies.

Rotating it therefore signs every user out **and** makes the stored Gotify token
unreadable. After a rotation, sign in again and re-enter the Gotify application
token in the Gotify settings tab. API tokens are not affected (they are stored
as hashes and do not use the key). Keep the key stable and out of version
control.

### Open paths

These need no session:

| Path | Why |
| --- | --- |
| `GET /api/health` | container and monitoring health check |
| `GET /api/health/plugins` | status of store modules (status and skipped names only) |
| `/api/setup` | one shot creation of the first user (refuses once a user exists) |
| `POST /api/auth/login` | sign in |

The web app itself (the static page and assets served by nginx) is not behind
API auth; it shows the sign in page when the API answers `401`. Any other `/api`
request without a valid session or an allowed API token gets `401`.

### API tokens for other services

A token lets a script or dashboard read a few endpoints without a browser
session. Create, list and revoke tokens under **Settings > API tokens** (see
[setup](./setup.md#api-tokens)). A token is `st_` followed by random characters.
It is shown once, only its SHA-256 hash is stored, it can have an expiry, and it
can be revoked at any time. The list records when each was last used.

Send it as a bearer token (here held in an environment variable, so it stays out of your shell history and scripts):

```bash
curl -H "Authorization: Bearer $STOCKTRACK_TOKEN" \
  https://stocktrack.example.com/api/watches
```

A token can only make these `GET` requests (`{id}` is a numeric watch id):

* `/api/watches`
* `/api/watches/{id}/offers`
* `/api/watches/{id}/offer-changes`

A valid token used anywhere else (another path, or any method other than `GET`)
gets `403`. An unknown, expired or revoked token gets `401`, the same as no
credentials. A token can never create or revoke tokens or change settings.

Use HTTPS for every token client: the token is a bearer credential sent in a
header on each request. If a request carries both a session cookie and a token,
the session is used and the token is ignored.

## Backups

Back up the named volume — it holds the database.

```bash
# stop writes for a consistent copy (optional but safer)
docker --context docker-host compose stop
docker run --rm -v stocktrack-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/stocktrack-$(date +%F).tgz -C /data .
docker --context docker-host compose start
```

Restore by stopping the containers, extracting the tarball back into the
volume, and starting again. To inspect the DB without disturbing the app, copy
`stocktrack.db` out and open it read-only rather than querying the live file.

## Updating

```bash
git pull
docker compose up -d --build
```

`--build` rebuilds both images; the React build runs inside the UI image, so
frontend changes ship automatically. The schema is created additively on
startup (`Base.metadata.create_all`) — no manual migration step. Settings you
changed in the UI live in the database (the named volume) and are preserved
across redeploys; `SEED_*` env values only apply on the *first* boot of a fresh
database.

### Upgrading an existing install

Installs from before authentication existed need two things after the upgrade:

* **Create your account.** The first visit shows Setup (the `user` table is
  empty). Do it straight away. Set `COOKIE_SECURE=false` first if you serve the
  UI over plain HTTP.
* **Update anything that called the API.** Unauthenticated calls now get `401`.
  A script or dashboard that read `/api/watches`, its offers or its offer
  changes can switch to an [API token](#api-tokens-for-other-services). A plain
  liveness check should use `GET /api/health`. Anything that wrote (for example
  a script that triggered checks) cannot use a token and has to be done from the
  signed in UI.

## Manual check & notification

Force a poll of a single watch (bypassing the schedule) from the **Dashboard**
("Check now"). The same action is `POST /api/watches/{id}/check` (add
`?notify=true` to push a Gotify status summary), but that endpoint needs a
signed in session with its CSRF header, so it is not available to API tokens.

`notify=false` (the default) checks silently and still fires the normal
transition alerts; `notify=true` additionally pushes a one-shot status summary
of every product under the watch.

## Health & scrape monitoring

- **Container health** — the backend `HEALTHCHECK` hits `GET /api/health`; the
  UI container waits for the API to be healthy before starting.
- **Scrape health** — each watch tracks `consecutive_failures` / `last_error`.
  After `FAILURE_ALERT_AFTER` (default 6) consecutive failures a single Gotify
  warning is sent (not one per tick), and a recovery notice when reading
  resumes. This surfaces a broken parser or a blocked fetch without alert spam.

## Logs

```bash
docker compose logs -f stocktrack-api    # poll results, transition counts, errors
docker compose logs -f stocktrack-ui     # nginx access/error
```

Each poll tick logs a per-watch summary like
`{"parsed": N, "early": x, "public": y, "oos": z}`.
