# Plugins

Every store handler is a plugin: a Python module that follows a small contract.
The built in ones live in `backend/stocktrack/sites/`. You can add your own, or
replace a built in one, without rebuilding the image, by pointing
`STOCKTRACK_PLUGINS_DIR` at a folder of plugin modules.

## The contract (plugin API 1)

A plugin module defines:

* `PLUGIN_API: int`, the plugin API version it was written for.
* `HANDLERS: list[SiteHandler]`, the handler instances it provides (see
  [adding-a-store.md](./adding-a-store.md) for writing a handler).

```python
from .base import Product, SiteHandler, fetch_html

class MyShopHandler(SiteHandler):
    name = "myshop"
    kind = "listing"
    def fetch(self, url):
        return fetch_html(url)
    def parse(self, raw):
        ...

handler = MyShopHandler()

PLUGIN_API = 1
HANDLERS = [handler]
```

A plugin can use the standard library, anything in `backend/requirements.txt`
and `stocktrack.*`. It cannot bring its own dependencies: a plugin that needs a
new library needs that library added to StockTrack first.

Core accepts a plugin when `MIN_PLUGIN_API <= PLUGIN_API <= core PLUGIN_API`
(both in `stocktrack/sites/__init__.py`). Core's version goes up when the
contract grows; the minimum only goes up when old plugins genuinely stop working.

## Loading

* A plugin is a `*.py` file, or a package directory with an `__init__.py`.
  Names starting with `_` or `.` are ignored. Files load in sorted name order.
* Each plugin is imported as `stocktrack.sites.<name>`, so a single file plugin
  can use relative imports such as `from .base import Product`. Inside a package
  plugin, `.base` means the package's own module: import
  `from stocktrack.sites.base import ...` there.
* **A plugin with the same name as a built in module replaces it entirely**,
  handlers and all. `myplugins/ao.py` replaces the built in `ao` store.
* A plugin with a new name that provides an existing store and kind pair
  overrides that pair. If two plugins provide the same pair, the later file wins.
* Plugins load once, at startup. Restart the API to pick up a change.

## When a plugin fails

A plugin that fails to import, lacks `PLUGIN_API` or `HANDLERS`, has an
unsupported `PLUGIN_API`, or lists something that is not a `SiteHandler` is
skipped. StockTrack keeps running: a built in module of the same name stays in
place, the reason is logged, and one Gotify alert at startup lists every skipped
plugin.

## Checking what loaded

* `GET /api/plugins` lists every module: its `source` (`builtin` or `plugin`),
  `status` (`loaded`, `replaced` for a built in a plugin took over, or
  `skipped`), its `plugin_api`, its handlers and any error.
* `GET /api/health/plugins` answers 200 when everything loaded and 503 when a
  plugin or the plugins folder failed. Use it as a deploy check.

## Docker

Mount the folder read only and point the variable at it:

```yaml
services:
  stocktrack-api:
    environment:
      STOCKTRACK_PLUGINS_DIR: /plugins
    volumes:
      - ./my-plugins:/plugins:ro
```

The container runs as uid 1001, so the files must be world readable.
