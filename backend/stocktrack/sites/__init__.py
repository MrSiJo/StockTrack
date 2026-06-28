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
    return [{"name": h.name, "kind": h.kind, "supported": True}
            for h in _HANDLERS.values()]
