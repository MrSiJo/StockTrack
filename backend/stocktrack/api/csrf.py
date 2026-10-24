"""Double submit cookie CSRF middleware.

A random 32 byte token is set in the ``stocktrack_csrf`` cookie on a safe
(GET/HEAD/OPTIONS) response whenever the request did not already carry one.
Mutating verbs (POST/PUT/PATCH/DELETE) must echo it in ``X-CSRF-Token``; the
two are compared with ``hmac.compare_digest`` (constant time).

The cookie is readable by JavaScript by design (the SPA echoes it); it is not
a credential on its own. Adding a pair to EXEMPT_ROUTES weakens CSRF: it needs
explicit sign off and the pinned hash in tests/test_security_invariants.py
updated.
"""
import base64
import hmac
import secrets
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

CSRF_COOKIE_NAME = "stocktrack_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# (method, path) pairs exempt from the check. Safe methods are never checked,
# so these GETs only document intent; a mutating pair here would weaken CSRF
# and requires explicit user sign off.
EXEMPT_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/api/health"),
    ("GET", "/api/health/plugins"),
})


def _generate_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


class CsrfMiddleware(BaseHTTPMiddleware):
    """Enforces double submit CSRF on mutating requests."""

    def __init__(
        self,
        app,
        cookie_secure: bool,
        cookie_name: str = CSRF_COOKIE_NAME,
        header_name: str = CSRF_HEADER_NAME,
        exempt_routes: Iterable[tuple[str, str]] = EXEMPT_ROUTES,
    ) -> None:
        super().__init__(app)
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.exempt_routes = frozenset(exempt_routes)
        self.cookie_secure = cookie_secure

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        if (method not in SAFE_METHODS
                and (method, request.url.path) not in self.exempt_routes):
            cookie_token = request.cookies.get(self.cookie_name) or ""
            header_token = request.headers.get(self.header_name) or ""
            if not cookie_token or not header_token or not hmac.compare_digest(
                    cookie_token.encode(), header_token.encode()):
                return JSONResponse({"detail": "CSRF token missing or invalid"},
                                    status_code=403)

        response = await call_next(request)

        # Issue the cookie on safe responses (exempt paths too) so the SPA has
        # a token from its very first request.
        if method in SAFE_METHODS and not request.cookies.get(self.cookie_name):
            response.set_cookie(
                key=self.cookie_name,
                value=_generate_token(),
                httponly=False,  # JS must read it to echo it back as the header
                samesite="strict",
                secure=self.cookie_secure,
                path="/",
            )
        return response
