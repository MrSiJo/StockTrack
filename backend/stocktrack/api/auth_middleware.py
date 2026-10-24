"""Session cookie auth middleware.

Reads the ``stocktrack_session`` cookie and verifies it with
``URLSafeTimedSerializer(APP_SECRET_KEY, salt="session")`` and ``max_age``, so
a session expires server side and not only in the browser. The payload is
``{"user_id": <int>}``.

Beyond the fleet template, the cookie's user must still exist in ``user``: a
deleted user's sessions stop working (within ``UserExistsCache``'s short TTL)
without rotating APP_SECRET_KEY, which would also orphan the Gotify token.

On a non exempt path a missing, tampered, expired or orphaned cookie gets 401.
On success ``request.state.user_id`` is set for the routes.

Adding a path to EXEMPT_PATHS weakens auth: it needs explicit sign off and the
pinned hash in tests/test_security_invariants.py updated.
"""
import time
from collections.abc import Callable, Iterable

from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from stocktrack.models import User

SESSION_COOKIE_NAME = "stocktrack_session"
SESSION_SALT = "session"

# Adding a path here weakens auth: requires explicit user sign off.
EXEMPT_PATHS: frozenset[str] = frozenset({
    "/api/health",
    "/api/health/plugins",
    "/api/setup",
    "/api/auth/login",
})


def make_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=SESSION_SALT)


class UserExistsCache:
    """Remembers, briefly, that a session's user row exists.

    Positive results only, so a deleted user is refused at most
    ``ttl_seconds`` after the delete. Saves one indexed lookup per request.
    """

    def __init__(self, ttl_seconds: float = 30,
                 time_func: Callable[[], float] = time.monotonic) -> None:
        self.ttl_seconds = ttl_seconds
        self._time = time_func
        self._seen: dict[int, float] = {}

    def fresh(self, user_id: int) -> bool:
        seen_at = self._seen.get(user_id)
        return seen_at is not None and self._time() - seen_at < self.ttl_seconds

    def remember(self, user_id: int) -> None:
        self._seen[user_id] = self._time()

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

    def _read_user_id(self, request: Request) -> int | None:
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
        return user_id

    async def _user_exists(self, request: Request, user_id: int) -> bool:
        if user_exists_cache.fresh(user_id):
            return True
        async with request.app.state.sessionmaker() as s:
            found = (await s.execute(
                select(User.id).where(User.id == user_id))).scalar_one_or_none()
        if found is None:
            return False
        user_exists_cache.remember(user_id)
        return True

    async def _session_user_id(self, request: Request) -> int | None:
        user_id = self._read_user_id(request)
        if user_id is None or not await self._user_exists(request, user_id):
            return None
        return user_id

    async def dispatch(self, request: Request, call_next):
        user_id = await self._session_user_id(request)
        request.state.user_id = user_id
        if user_id is None and request.url.path not in self.exempt_paths:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        return await call_next(request)
