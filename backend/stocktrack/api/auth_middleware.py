"""Session cookie auth middleware.

Reads the ``stocktrack_session`` cookie and verifies it with
``URLSafeTimedSerializer(APP_SECRET_KEY, salt="session")`` and ``max_age``, so
a session expires server side and not only in the browser. The payload is
``{"user_id": <int>, "nonce": <str>}``.

Beyond the fleet template, the cookie's (user id, nonce) pair must still match
a ``user`` row: a deleted user's sessions stop working (within
``UserExistsCache``'s short TTL) without rotating APP_SECRET_KEY, which would
also orphan the Gotify token. The nonce is random per user, so a user deleted
and set up again never inherits the old sessions, and sign out rotates it to
end every session for the user at once. A cookie without a nonce (the first
payload format) is refused.

On a non exempt path a missing, tampered, expired or orphaned cookie gets 401.
On success ``request.state.user_id`` is set for the routes.

Without a valid session, an ``Authorization: Bearer`` API token is accepted
for the read only TOKEN_ALLOWLIST (GET only). An unknown, revoked or expired
token gets the same 401; a valid token anywhere else gets 403. A request with
a valid session is the session: any bearer token on it is ignored, and CSRF
applies in full. The Authorization header and the token are never logged;
the token's name is, at debug.

Adding a path to EXEMPT_PATHS or TOKEN_ALLOWLIST weakens auth: it needs
explicit sign off and the pinned hash in tests/test_security_invariants.py
updated.
"""
import logging
import re
import time
from collections.abc import Callable, Iterable

from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from stocktrack.models import User
from stocktrack.services.token_service import verify_token

log = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "stocktrack_session"
SESSION_SALT = "session"

# Adding a path here weakens auth: requires explicit user sign off.
EXEMPT_PATHS: frozenset[str] = frozenset({
    "/api/health",
    "/api/health/plugins",
    "/api/setup",
    "/api/auth/login",
})


# GET paths an API token may read ({id} is a numeric path segment). Adding a
# path here weakens auth: requires explicit user sign off. Read only by
# design: a token can never write.
TOKEN_ALLOWLIST: frozenset[str] = frozenset({
    "/api/watches",
    "/api/watches/{id}/offers",
    "/api/watches/{id}/offer-changes",
})

_TOKEN_PATTERNS = tuple(
    re.compile(re.escape(p).replace(re.escape("{id}"), "[0-9]+"))
    for p in sorted(TOKEN_ALLOWLIST)
)


def token_allows(method: str, path: str) -> bool:
    return method == "GET" and any(p.fullmatch(path) for p in _TOKEN_PATTERNS)


def _bearer_token(request: Request) -> str | None:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def make_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=SESSION_SALT)


class UserExistsCache:
    """Remembers, briefly, that a session's (user id, nonce) pair matches a row.

    Positive results only, so a deleted user is refused at most
    ``ttl_seconds`` after the delete. Saves one indexed lookup per request.
    Sign out calls ``forget`` so a rotated nonce takes effect immediately.
    """

    def __init__(self, ttl_seconds: float = 30,
                 time_func: Callable[[], float] = time.monotonic) -> None:
        self.ttl_seconds = ttl_seconds
        self._time = time_func
        self._seen: dict[tuple[int, str], float] = {}

    def fresh(self, user_id: int, nonce: str) -> bool:
        seen_at = self._seen.get((user_id, nonce))
        return seen_at is not None and self._time() - seen_at < self.ttl_seconds

    def remember(self, user_id: int, nonce: str) -> None:
        self._seen[(user_id, nonce)] = self._time()

    def forget(self, user_id: int) -> None:
        """Drop every cached pair for ``user_id`` (its nonce just changed)."""
        for key in [k for k in self._seen if k[0] == user_id]:
            del self._seen[key]

    def clear(self) -> None:
        """Drop everything (test hook)."""
        self._seen.clear()


user_exists_cache = UserExistsCache()


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates the signed session cookie on non exempt paths."""

    def __init__(
        self,
        app,
        secret_key: str,
        max_age_seconds: int,
        cookie_name: str = SESSION_COOKIE_NAME,
        exempt_paths: Iterable[str] = EXEMPT_PATHS,
    ) -> None:
        super().__init__(app)
        self.cookie_name = cookie_name
        self.exempt_paths = frozenset(exempt_paths)
        self._serializer = make_serializer(secret_key)
        self._max_age_seconds = max_age_seconds

    def _read_session(self, request: Request) -> tuple[int, str] | None:
        raw = request.cookies.get(self.cookie_name)
        if not raw:
            return None
        try:
            # BadTimeSignature (expired or tampered timestamp) subclasses
            # BadSignature, so one except covers both.
            payload = self._serializer.loads(raw, max_age=self._max_age_seconds)
        except BadSignature:
            return None
        if not isinstance(payload, dict):
            return None
        user_id = payload.get("user_id")
        # bool is an int subclass; a forged True must not mean user 1.
        if not isinstance(user_id, int) or isinstance(user_id, bool):
            return None
        nonce = payload.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            return None
        return user_id, nonce

    async def _session_matches(self, request: Request, user_id: int, nonce: str) -> bool:
        if user_exists_cache.fresh(user_id, nonce):
            return True
        async with request.app.state.sessionmaker() as s:
            found = (await s.execute(
                select(User.id).where(User.id == user_id,
                                      User.session_nonce == nonce))).scalar_one_or_none()
        if found is None:
            return False
        user_exists_cache.remember(user_id, nonce)
        return True

    async def _session_user_id(self, request: Request) -> int | None:
        session = self._read_session(request)
        if session is None or not await self._session_matches(request, *session):
            return None
        return session[0]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        user_id = await self._session_user_id(request)
        request.state.user_id = user_id
        request.state.api_token = None
        if user_id is not None or path in self.exempt_paths:
            return await call_next(request)

        presented = _bearer_token(request)
        if presented is not None:
            async with request.app.state.sessionmaker() as s:
                token = await verify_token(s, presented)
            if token is not None:
                if not token_allows(request.method, path):
                    log.debug("api token %r refused for %s %s",
                              token.name, request.method, path)
                    return JSONResponse(
                        {"detail": "API token not permitted for this endpoint"},
                        status_code=403)
                log.debug("api token %r used for %s", token.name, path)
                request.state.api_token = token.name
                return await call_next(request)
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
