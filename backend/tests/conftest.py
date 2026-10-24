import os

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from stocktrack.models.base import Base

os.environ.setdefault("APP_SECRET_KEY", "t" * 32)
# The test transport is plain http://, so a Secure cookie would never be sent.
os.environ.setdefault("COOKIE_SECURE", "false")

CSRF_COOKIE_NAME = "stocktrack_csrf"


def csrf_headers(client) -> dict[str, str]:
    """Echo the client's CSRF cookie back as the header a mutating call needs."""
    return {"X-CSRF-Token": client.cookies.get(CSRF_COOKIE_NAME, "")}


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
    from stocktrack.api.rate_limit import limiter
    from stocktrack.bootstrap import get_settings
    from stocktrack.main import create_app

    get_settings.cache_clear()
    limiter.reset()
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
async def client(app):
    """AsyncClient wired to the in-memory DB."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
