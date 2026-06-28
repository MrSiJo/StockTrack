import pytest
from sqlalchemy import select
from stocktrack.models import Watch, Product, Event

async def test_watch_product_event_roundtrip(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="ao", url="https://ao.com/x", label="AO Meaco",
                  include_filter="Meaco", exclude_filter="Heating",
                  interval_seconds=300, enabled=True)
        s.add(w)
        await s.flush()
        p = Product(watch_id=w.id, store="ao", code="SKU1", title="Meaco 12K",
                    brand="Meaco", url="https://ao.com/p/1",
                    availability="public", current_in_stock=True, current_price=519.0)
        s.add(p)
        await s.flush()
        s.add(Event(product_id=p.id, kind="public", price=519.0))
        await s.commit()

    async with sessionmaker_() as s:
        prods = (await s.execute(select(Product))).scalars().all()
        assert len(prods) == 1
        assert prods[0].current_in_stock is True
        assert prods[0].availability == "public"
        evs = (await s.execute(select(Event))).scalars().all()
        assert evs[0].kind == "public"

async def test_product_unique_per_watch_code(sessionmaker_):
    from sqlalchemy.exc import IntegrityError
    async with sessionmaker_() as s:
        w = Watch(store="ao", url="u")
        s.add(w); await s.flush()
        s.add(Product(watch_id=w.id, store="ao", code="DUP", title="a"))
        s.add(Product(watch_id=w.id, store="ao", code="DUP", title="b"))
        with pytest.raises(IntegrityError):
            await s.commit()

async def test_watch_health_columns(sessionmaker_):
    from datetime import datetime, timezone
    async with sessionmaker_() as s:
        w = Watch(store="ao", url="u")
        s.add(w); await s.commit()
    async with sessionmaker_() as s:
        w = (await s.execute(select(Watch))).scalar_one()
        assert w.consecutive_failures == 0
        assert w.last_checked_at is None
        assert w.last_error == ""

async def test_watch_kind_and_price_drop_defaults(sessionmaker_):
    from stocktrack.models import Watch
    async with sessionmaker_() as s:
        w = Watch(store="ao", url="u")
        s.add(w); await s.commit()
        assert w.kind == "listing"
        assert w.track_price_drops is False
