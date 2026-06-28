from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from stocktrack.main import create_app
from stocktrack.models import Event, Product, Watch


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET_KEY", "h" * 32)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path/'h.db'}")
    from stocktrack.bootstrap import get_settings
    get_settings.cache_clear()
    return create_app()


B = datetime(2026, 6, 27, 6, 0, tzinfo=timezone.utc)
def at(m): return B + timedelta(minutes=m)


async def _seed(sm):
    async with sm() as s:
        w = Watch(store="ao", url="https://ao.com/l/example")
        s.add(w)
        await s.flush()
        p = Product(watch_id=w.id, store="ao", code="A-16K", title="AO Cirro 16K",
                    url="https://ao.com/p/16k", basket_url="https://ao.com/Build_Shopping_Basket.aspx?items=A-16K:1")
        s.add(p)
        await s.flush()
        s.add_all([
            Event(product_id=p.id, ts=at(0), kind="early_access", price=629.0),
            Event(product_id=p.id, ts=at(17), kind="public", price=629.0),
            Event(product_id=p.id, ts=at(47), kind="oos", price=629.0, available_seconds=47 * 60),
        ])
        await s.commit()


async def test_history_groups_and_summarizes(app):
    async with app.router.lifespan_context(app):
        await _seed(app.state.sessionmaker)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.get("/api/history")
            assert r.status_code == 200
            data = r.json()
            assert len(data) == 1
            entry = data[0]
            assert entry["product"]["title"] == "AO Cirro 16K"
            assert entry["summary"]["episodes"] == 1
            assert entry["summary"]["avg_buyable_seconds"] == 47 * 60
            assert entry["summary"]["avg_early_lead_seconds"] == 17 * 60
            ep = entry["episodes"][0]
            assert ep["ongoing"] is False and ep["buyable_seconds"] == 47 * 60
            assert ep["early_lead_seconds"] == 17 * 60


async def test_history_store_filter_excludes_others(app):
    async with app.router.lifespan_context(app):
        await _seed(app.state.sessionmaker)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            assert (await ac.get("/api/history?store=johnlewis")).json() == []
            assert len(((await ac.get("/api/history?store=ao")).json())) == 1
