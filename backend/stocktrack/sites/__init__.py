"""Site handler registry, keyed by (store name, kind).

Handlers come from modules that follow the plugin contract: a module level
``PLUGIN_API`` (int) and ``HANDLERS`` (list of SiteHandler). The built in
modules in this package are discovered by scanning it; extra modules load from
the folder named by ``STOCKTRACK_PLUGINS_DIR``. A plugin is imported as
``stocktrack.sites.<stem>``, so one with a built in's stem replaces that module
entirely. A plugin that fails to load is skipped and reported, never fatal.
See docs/plugins.md.
"""
import importlib
import importlib.util
import logging
import os
import pkgutil
import sys
from pathlib import Path
from typing import Optional

from .base import SiteHandler

log = logging.getLogger(__name__)

# The contract version core implements, and the oldest it still accepts.
PLUGIN_API = 1
MIN_PLUGIN_API = 1

_NOT_MODULES = {"base"}

_BUILTINS: dict[str, object] = {}
_HANDLERS: dict[tuple[str, str], SiteHandler] = {}
_REPORT: dict = {}


def plugins_dir_from_env() -> Optional[Path]:
    raw = os.environ.get("STOCKTRACK_PLUGINS_DIR", "").strip()
    return Path(raw) if raw else None


def _check_contract(mod) -> list[SiteHandler]:
    api = getattr(mod, "PLUGIN_API", None)
    if not isinstance(api, int):
        raise ValueError("module has no integer PLUGIN_API")
    if not MIN_PLUGIN_API <= api <= PLUGIN_API:
        raise ValueError(f"PLUGIN_API {api} is outside the supported range "
                         f"{MIN_PLUGIN_API}..{PLUGIN_API}")
    handlers = getattr(mod, "HANDLERS", None)
    if not isinstance(handlers, (list, tuple)):
        raise ValueError("module has no HANDLERS list")
    for h in handlers:
        if not isinstance(h, SiteHandler):
            raise ValueError(f"HANDLERS item {h!r} is not a SiteHandler")
    return list(handlers)


def _discover_builtins() -> None:
    for info in pkgutil.iter_modules(__path__):
        if info.name in _NOT_MODULES or info.name.startswith("_"):
            continue
        _BUILTINS[info.name] = importlib.import_module(f"{__name__}.{info.name}")


def _plugin_files(plugins_dir: Path) -> list[tuple[str, Path]]:
    out = []
    for p in sorted(plugins_dir.iterdir()):
        if p.name.startswith(("_", ".")):
            continue
        if p.is_file() and p.suffix == ".py":
            out.append((p.stem, p))
        elif p.is_dir() and (p / "__init__.py").is_file():
            out.append((p.name, p / "__init__.py"))
    return out


def _import_plugin(stem: str, path: Path):
    """Import a plugin file as stocktrack.sites.<stem>; leaves no trace on failure."""
    name = f"{__name__}.{stem}"
    kwargs = {}
    if path.name == "__init__.py":
        kwargs["submodule_search_locations"] = [str(path.parent)]
    spec = importlib.util.spec_from_file_location(name, path, **kwargs)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
        handlers = _check_contract(mod)
    except BaseException:
        if previous is not None:
            sys.modules[name] = previous
        else:
            sys.modules.pop(name, None)
        raise
    return mod, handlers


def _entry(module, source, status, mod=None, handlers=(), error=None) -> dict:
    return {
        "module": module,
        "source": source,
        "status": status,
        "plugin_api": getattr(mod, "PLUGIN_API", None) if mod is not None else None,
        "handlers": [f"{h.name}/{h.kind}" for h in handlers],
        "error": error,
    }


def load_registry(plugins_dir: Optional[Path]) -> None:
    """(Re)build the registry from the built ins plus ``plugins_dir``."""
    package = sys.modules[__name__]
    # Start from the built ins, undoing any earlier plugin replacement.
    for stem in list(package.__dict__):
        mod = package.__dict__[stem]
        if (getattr(mod, "__name__", None) == f"{__name__}.{stem}"
                and stem not in _BUILTINS and stem not in _NOT_MODULES):
            delattr(package, stem)
            sys.modules.pop(f"{__name__}.{stem}", None)
    modules: dict[str, tuple[object, list[SiteHandler]]] = {}
    for stem, mod in _BUILTINS.items():
        sys.modules[f"{__name__}.{stem}"] = mod
        setattr(package, stem, mod)
        modules[stem] = (mod, _check_contract(mod))

    entries: dict[str, dict] = {
        stem: _entry(stem, "builtin", "loaded", mod, handlers)
        for stem, (mod, handlers) in modules.items()
    }
    plugin_entries: list[dict] = []
    dir_error = None
    plugin_order: list[str] = []

    if plugins_dir is not None:
        try:
            files = _plugin_files(Path(plugins_dir))
        except OSError as e:
            files = []
            dir_error = f"cannot read plugins dir {plugins_dir}: {e}"
            log.warning(dir_error)
        for stem, path in files:
            try:
                mod, handlers = _import_plugin(stem, path)
            except BaseException as e:  # noqa: BLE001 - a plugin must never kill startup
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                err = f"{type(e).__name__}: {e}"
                log.warning("plugin %s skipped: %s", stem, err)
                plugin_entries.append(_entry(stem, "plugin", "skipped", error=err))
                continue
            if stem in entries:
                entries[stem]["status"] = "replaced"
            setattr(package, stem, mod)
            modules[stem] = (mod, handlers)
            plugin_order.append(stem)
            plugin_entries.append(_entry(stem, "plugin", "loaded", mod, handlers))

    handlers_by_key: dict[tuple[str, str], SiteHandler] = {}
    # Built ins first, then plugins in file order, so a later pair wins.
    order = [s for s in modules if s not in plugin_order] + plugin_order
    for stem in order:
        for h in modules[stem][1]:
            key = (h.name, h.kind)
            if key in handlers_by_key:
                log.info("store %s/%s from %s overrides an earlier handler",
                         h.name, h.kind, stem)
            handlers_by_key[key] = h

    _HANDLERS.clear()
    _HANDLERS.update(handlers_by_key)
    _REPORT.clear()
    _REPORT.update({
        "plugin_api": PLUGIN_API,
        "min_plugin_api": MIN_PLUGIN_API,
        "plugins_dir": plugins_dir is not None,
        "plugins_dir_error": dir_error,
        "modules": list(entries.values()) + plugin_entries,
    })


def plugin_report() -> dict:
    return {**_REPORT, "modules": [dict(m) for m in _REPORT.get("modules", [])]}


def skipped_plugins() -> list[dict]:
    return [m for m in plugin_report()["modules"] if m["status"] == "skipped"]


def get_handler(name: str, kind: str = "listing") -> SiteHandler:
    try:
        return _HANDLERS[(name, kind)]
    except KeyError:
        pairs = ", ".join(f"{n}/{k}" for n, k in sorted(_HANDLERS))
        raise ValueError(f"unknown store/kind {name!r}/{kind!r}; available: {pairs}")

def available() -> list[str]:
    return sorted({name for name, _ in _HANDLERS})

def supported_kinds(name: str) -> list[str]:
    return sorted(k for n, k in _HANDLERS if n == name)

def stores() -> list[dict]:
    by_name: dict[str, dict] = {}
    for h in _HANDLERS.values():
        entry = by_name.setdefault(
            h.name, {"name": h.name, "kinds": set(), "supported": True, "_settings": {}}
        )
        entry["kinds"].add(h.kind)
        for spec in getattr(h, "settings_spec", []):
            entry["_settings"].setdefault(spec["key"], spec)
    out = []
    for entry in sorted(by_name.values(), key=lambda e: e["name"]):
        out.append({
            "name": entry["name"],
            "kinds": sorted(entry["kinds"]),
            "supported": entry["supported"],
            "settings": list(entry["_settings"].values()),
        })
    return out


_discover_builtins()
load_registry(plugins_dir_from_env())
