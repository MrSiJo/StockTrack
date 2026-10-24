import os
import secrets

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from stocktrack.models.base import Base

os.environ.setdefault("APP_SECRET_KEY", "t" * 32)
# The test transport is plain http://, so a Secure cookie would never be sent.
os.environ.setdefault("COOKIE_SECURE", "false")

from stocktrack.api.csrf import CSRF_COOKIE_NAME  # noqa: E402


def csrf_headers(client) -> dict[str, str]:
    """Echo the client's CSRF cookie back as the header a mutating call needs."""
    return {"X-CSRF-Token": client.cookies.get(CSRF_COOKIE_NAME, "")}


async def authenticate(client, sessionmaker, username: str = "tester") -> int:
    """Make ``client`` a logged in browser: a user row, a signed session
    cookie, and a CSRF cookie echoed on every request. Returns the user id."""
    from stocktrack.api.auth_middleware import SESSION_COOKIE_NAME, make_serializer
    from stocktrack.bootstrap import get_settings
    from stocktrack.models import User

    async with sessionmaker() as s:
        # The middleware only checks the (id, nonce) row exists; skip argon2 per test.
        user = User(username=username, password_hash="unused")
        s.add(user)
        await s.commit()
        user_id = user.id
        nonce = user.session_nonce
    token = make_serializer(get_settings().app_secret_key).dumps(
        {"user_id": user_id, "nonce": nonce})
    csrf = secrets.token_urlsafe(32)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.cookies.set(CSRF_COOKIE_NAME, csrf)
    client.headers["X-CSRF-Token"] = csrf
    return user_id


@pytest_asyncio.fixture
async def sessionmaker_():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    yield sm
    await engine.dispose()


@pytest_asyncio.fixture
async def app(sessionmaker_):
    """The app wired to the in-memory DB, with per process auth state reset.

    httpx's ASGITransport does NOT trigger the ASGI lifespan, so we inject
    app.state.sessionmaker directly rather than relying on the lifespan to do it.
    """
    from stocktrack.api.login_throttle import login_throttle
    from stocktrack.api.rate_limit import limiter
    from stocktrack.bootstrap import get_settings
    from stocktrack.main import create_app

    get_settings.cache_clear()
    limiter.reset()
    login_throttle.clear()
    application = create_app()
    # Inject the test sessionmaker directly — routes read it via request.app.state
    application.state.sessionmaker = sessionmaker_
    return application


@pytest_asyncio.fixture
async def anon_client(app):
    """A client with no session: for setup, login and the security tests."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def client(app, sessionmaker_):
    """An authenticated AsyncClient (session cookie + CSRF header) wired to
    the in-memory DB. The default for API tests; use ``anon_client`` to test
    auth itself."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        await authenticate(c, sessionmaker_)
        yield c
