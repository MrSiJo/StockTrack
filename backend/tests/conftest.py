import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from stocktrack.models.base import Base

os.environ.setdefault("APP_SECRET_KEY", "t" * 32)


@pytest_asyncio.fixture
async def sessionmaker_():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    yield sm
    await engine.dispose()


@pytest_asyncio.fixture
async def client(sessionmaker_):
    """AsyncClient wired to the in-memory DB.

    httpx's ASGITransport does NOT trigger the ASGI lifespan, so we inject
    app.state.sessionmaker directly rather than relying on the lifespan to do it.
    """
    from httpx import ASGITransport, AsyncClient

    from stocktrack.bootstrap import get_settings
    from stocktrack.main import create_app

    get_settings.cache_clear()
    app = create_app()
    # Inject the test sessionmaker directly — routes read it via request.app.state
    app.state.sessionmaker = sessionmaker_

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
