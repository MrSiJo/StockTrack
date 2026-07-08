# First-run setup & configuration

Once the stack is running (see [deployment](./deployment.md)), open
`http://<host>:${FRONTEND_PORT:-9181}` and add watches, then configure Gotify.

## Add a watch (Watches tab)

A **watch** is one retailer listing page that StockTrack polls. To add one:

1. Pick a **store** handler (`ao`, `johnlewis` — see the Stores tab for what's
   registered).
2. Paste the **listing URL** for that store.
3. Optionally set **include** / **exclude** filters — comma-separated
   substrings matched (case-insensitive) against each product's brand + title.
   `*` or blank include matches everything; an exclude wins over an include.
4. **Preview** fetches the page live and shows the products that match your
   filters, with their detected phase (`oos` / `early` / `public`), price, and
   links — so you can confirm the URL and filters before saving.
5. Save. The poll loop picks it up on the next tick.

You can seed one watch per store at first boot instead of using the UI by
setting `SEED_AO_URL` / `SEED_JL_URL` in `.env` (see
[installation](./installation.md)). Seeds apply only to a fresh database.

### The 3-phase model in the UI

Each product shows one of three states:

- 🔴 **out of stock** — not buyable.
- ⚡ **early access** — buyable via a direct add-to-basket link before the item
  is public (detected from a far-future placeholder delivery date). Where the
  store exposes one, the alert and the dashboard carry a 🛒 **Add to basket**
  link.
- 🟢 **in stock** — publicly buyable with a real delivery date.

The boundary between early-access and public is `EARLY_ACCESS_DAYS` (default
30) — the delivery-date distance beyond which a date is treated as a
placeholder. Change it under settings (below); it takes effect on the next
check without a redeploy.

## Configure Gotify (Gotify tab)

[Gotify](https://gotify.net/) is the push channel. Enter:

- **Server URL** — your Gotify base URL.
- **Application token** — write-only in the UI; stored Fernet-encrypted at
  rest. The field shows whether a token is set, never the value. Submitting a
  blank token leaves the existing one unchanged.
- **Priorities** — defaults for general (`7`), restock (`8`), and out-of-stock
  (`4`) alerts.
- **Send retries** — retries on 5xx / network errors (`3`). 4xx responses (e.g.
  a bad token) are never retried.

Use **Test connection** to send a test push and confirm the server is
reachable and the token is valid.

> Notifications are **delivery-safe**: a transition's event is recorded only if
> its push is delivered. If Gotify is unreachable, the transition is retried on
> the next poll rather than silently dropped — so the History view never shows
> a restock you weren't told about.

## Poller & alerting settings

Also editable in settings (seeded from env on first boot, then UI-owned):

- **Poll interval** (`DEFAULT_INTERVAL_SECONDS`, default 300s) — how often the
  loop checks every enabled watch.
- **Early-access window** (`EARLY_ACCESS_DAYS`, default 30) — see above.
- **Failure alert threshold** (`FAILURE_ALERT_AFTER`, default 6) — consecutive
  scrape failures before a single health-warning push.

## History

The **History** tab reconstructs each product's stock **episodes** from the
event log: when it came into stock (and the early-access → public lead where
the store provides it), when it went back out, and how long it was buyable. An
in-stock product shows a live, ongoing episode pinned to the top of its group.
Nothing to configure — it fills forward as StockTrack observes restocks. See
[architecture](./architecture.md#episode-reconstruction) for the model.

## Adding a new store

Drop a `SiteHandler` subclass in `backend/stocktrack/sites/` and register it in
the `_HANDLERS` map in `sites/__init__.py`. Each handler implements `fetch`
(usually via the shared `fetch_html` helper, which handles the Cloudflare bot
wall) and `parse`, mapping the store's HTML/JSON to the shared `Product`
dataclass — set `availability` (`early` / `public`) and a `basket_url` where
the store supports a direct-add link. Use `configure()` to receive runtime
settings such as `early_access_days`. Verify with the
[one-off check CLI](./build.md#one-off-check-cli) before adding a live watch.
