"""Slowapi rate limiter — singleton wired into the FastAPI app.

The limiter is keyed by the *real* client IP. `headers_enabled=True`
makes slowapi emit the standard `X-RateLimit-*` and `Retry-After`
headers on rate-limited responses.

In the shipped topology the API sits behind an nginx container (itself
behind Nginx Proxy Manager), so the immediate TCP peer
(`request.client.host`) is the proxy's IP for *every* user. `client_ip_key`
therefore reads `X-Forwarded-For`, but ONLY when the immediate peer is a
private/loopback address (the trusted reverse proxy). A direct hit from a
public peer cannot spoof its identity: the header is ignored entirely.

It takes the RIGHT-most entry, not the left-most. The nginx config uses
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`, which
APPENDS the address nginx observed to whatever the client sent. The left
side of the header is therefore client-controlled (a client can rotate
its rate-limit bucket by forging it), while the right-most entry is the one
our own trusted proxy wrote and cannot be forged.

Accepted consequence: behind NPM the right-most entry is NPM's address, so
every browser shares NPM's single bucket. That is acceptable for a
single-user app, and it is stricter, not looser, than per-client keying.

To activate this on the app, set `app.state.limiter = limiter` and
register `slowapi._rate_limit_exceeded_handler` for `RateLimitExceeded`.
Routes opt in via `@limiter.limit("N/period")`.
"""

from __future__ import annotations

import ipaddress

from slowapi import Limiter
from starlette.requests import Request


def _is_trusted_proxy(ip: str) -> bool:
    """True when *ip* is a private/loopback address (a local reverse proxy)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback


def client_ip_key(request: Request) -> str:
    """Rate-limit key: the real client IP, proxy-aware and spoof-resistant."""
    peer = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.getlist("x-forwarded-for")
    if forwarded and _is_trusted_proxy(peer):
        # Right-most entry of the LAST header: the one our trusted proxy appended.
        client = forwarded[-1].rsplit(",", 1)[-1].strip()
        try:
            return str(ipaddress.ip_address(client))
        except ValueError:
            pass
    return peer


limiter = Limiter(key_func=client_ip_key, headers_enabled=True)
