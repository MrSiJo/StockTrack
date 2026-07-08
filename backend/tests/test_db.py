"""Tests for additive, idempotent schema migration in init_models."""
from datetime import datetime, timezone
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import create_async_engine

from stocktrack.db import init_models, make_sessionmaker
from stocktrack.models import Watch, Product


async def test_init_models_adds_missing_columns(tmp_path):
    """init_models ALTERs an existing table to add new model columns.

    Simulates a pre-existing DB (created before kind/track_price_drops were
    added) and verifies the columns are added with their defaults applied to
    existing rows — the create_all-only path cannot do this.
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'old.db'}"
    engine = create_async_engine(url)
    # Old schema: watch table WITHOUT kind / track_price_drops
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE watch ("
            "id INTEGER PRIMARY KEY, store VARCHAR, url VARCHAR, "
            "label VARCHAR DEFAULT '', include_filter VARCHAR DEFAULT '', "
            "exclude_filter VARCHAR DEFAULT '', interval_seconds INTEGER DEFAULT 300, "
            "enabled BOOLEAN DEFAULT 1, created_at DATETIME, last_checked_at DATETIME, "
            "last_ok_at DATETIME, consecutive_failures INTEGER DEFAULT 0, "
            "last_error VARCHAR DEFAULT '')"
        )
        await conn.exec_driver_sql(
            "INSERT INTO watch (id, store, url) VALUES (1, 'ao', 'http://example.test/x')"
        )

    await init_models(engine)

    sm = make_sessionmaker(engine)
    async with sm() as s:
        w = await s.get(Watch, 1)
        assert w.kind == "listing"          # default applied to pre-existing row
        assert w.track_price_drops is False
    await engine.dispose()


async def test_init_models_is_idempotent(tmp_path):
    """Running init_models repeatedly does not error once columns exist."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}"
    engine = create_async_engine(url)
    await init_models(engine)
    await init_models(engine)  # second run: columns already present, no-op
    async with engine.begin() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("watch")}
        )
    assert "kind" in cols and "track_price_drops" in cols
    await engine.dispose()


async def test_product_has_archive_and_watts_columns(sessionmaker_):
    async with sessionmaker_() as s:
        archived_time = datetime.now(timezone.utc)
        p = Product(
            watch_id=1, store="ao", code="X1", title="t", brand="b",
            url="u", availability="oos", basket_url="", current_in_stock=False,
            first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc),
            spec_watts=435, archived_at=archived_time,
        )
        s.add(p)
        await s.commit()
        got = (await s.execute(select(Product))).scalars().one()
        assert got.spec_watts == 435
        assert got.archived_at is not None
        assert got.archived_at.tzinfo is not None
