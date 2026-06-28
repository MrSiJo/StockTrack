"""Site handler registry, keyed by (store name, kind)."""
from . import ao, johnlewis
from .base import SiteHandler

_HANDLERS: dict[tuple[str, str], SiteHandler] = {
    (h.name, h.kind): h for h in (
        ao.handler,
        ao.product_handler,
        johnlewis.handler,
    )
}

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
