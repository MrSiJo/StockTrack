# Deployment & operations

Day-2 operations: deploy, data persistence, proxying, backups, updates,
maintenance. Prerequisites and env vars are in [installation](./installation.md);
adding watches and configuring alerts is in [setup](./setup.md).

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
that needs to be reachable; it proxies `/api` internally. Keep
`COOKIE_SECURE=true` when serving over HTTPS.

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

## Manual check & notification

Force a poll of a single watch (bypassing the schedule) from the **Dashboard**
("Check now"), or via the API:

```bash
# check watch 1 now; ?notify=true also pushes a Gotify status summary
curl -X POST "http://<docker-host>:${FRONTEND_PORT:-9181}/api/watches/1/check?notify=true"
```

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
