"""Site handler registry."""
from . import ao, johnlewis
from .base import SiteHandler

_HANDLERS: dict[str, SiteHandler] = {h.name: h for h in (
    ao.handler,
    johnlewis.handler,
)}

def get_handler(name: str) -> SiteHandler:
    try:
        return _HANDLERS[name]
    except KeyError:
        raise ValueError(f"unknown store {name!r}; available: {', '.join(sorted(_HANDLERS))}")

def available() -> list[str]:
    return sorted(_HANDLERS)

def stores() -> list[dict]:
    return [{"name": h.name, "kind": h.kind, "supported": True}
            for h in _HANDLERS.values()]
