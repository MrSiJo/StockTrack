# Adding a store handler

A store "plugin" is a `SiteHandler` subclass in
`backend/stocktrack/sites/<store>.py`. Handlers map a retailer's listing or
product page to the shared `Product` dataclass; everything downstream (poller,
phases, history, alerts) is store-agnostic.

## Contract

- **Class attributes**
  - `name: str` — the store id (e.g. `"ao"`).
  - `kind: str` — `"listing"` (default) or `"product"`. Set it explicitly.
  - `settings_spec: list[dict] = []` — optional per-store settings (see below).
- **`fetch(self, url) -> str`** — delegate to `fetch_html(url)` (shared
  `curl_cffi` layer that defeats the Cloudflare TLS-fingerprint wall). Don't
  reimplement fetching.
- **`parse(self, raw) -> list[Product]`** — locate the page's data blob, find
  the product list, map each item to a `Product`. Raise `RuntimeError("... -
  <store> page layout changed?")` when the blob or list is missing.
- **`configure(self, **opts) -> None`** — optional. Consume runtime settings
  passed by the poller/preview (e.g. `early_access_days`, `ao_member`). The base
  is a no-op and ignores unknown kwargs.
- **Singletons + registration** — create `handler = XHandler()` at module level
  (plus a second instance for an extra kind, e.g. `product_handler`), then
  register by: (a) adding `from . import <store>` to the imports at the top of
  `sites/__init__.py`, and (b) adding the handler instance(s) to the inner
  tuple of the `_HANDLERS` dict comprehension. `_HANDLERS` is a
  `dict[tuple[str, str], SiteHandler]` keyed by `(name, kind)` — not a plain
  tuple.

## The `Product` shape

`Product(code, title, in_stock, brand="", price=None, delivery="", url="",
availability="", basket_url="")`. Leave `availability=""` to let the poller
derive `oos`/`public` from `in_stock`; set it to `oos`/`early`/`public`
yourself only if the store exposes early-access delivery dates (see `ao.py`).

## Per-store settings

Declare settings the store needs as `settings_spec`:

```python
AO_SETTINGS = [{"key": "ao_member",
                "label": "I'm an AO member (track AO member price)",
                "type": "bool", "default": False}]
```

A descriptor is `{key, label, type, default}` with `type` in
`bool` | `int` | `float`. `key` is also the `setting` table key AND a field on
`SettingsOut`/`SettingsUpdate` (the value transport) — add it there too. The
Stores page renders each store's settings in a collapsible panel automatically;
`stores()` aggregates them by store name. Read the live value inside
`configure()`; the poller passes it in.

## Checklist

1. Create `backend/stocktrack/sites/<store>.py` with the class above.
2. Set `name` and `kind` explicitly.
3. `fetch` via `fetch_html`; `parse` → `list[Product]` with a clear RuntimeError.
4. (Optional) `configure` to consume settings; declare `settings_spec` and add
   each key to `SettingsOut`/`SettingsUpdate` + `seed_from_env` + `bootstrap`.
5. In `sites/__init__.py`, add `from . import <store>` to the imports at the
   top of the file, then add `<store>.handler` (and any extra-kind handler,
   e.g. `<store>.product_handler`) to the inner tuple of the `_HANDLERS` dict
   comprehension.
6. Add a **synthetic** fixture under `backend/tests/fixtures/` (fake codes,
   prices, URLs — never a real watch URL) and a `tests/test_sites_<store>.py`
   mirroring `tests/test_sites_ao.py`.
7. `cd backend && pytest -q` — all green.
