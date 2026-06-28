import os
from datetime import datetime, timezone

os.environ.setdefault("APP_SECRET_KEY", "t" * 32)


def test_schemas_importable():
    from stocktrack.api.deps import get_session  # noqa: F401


# ── GET /api/status ────────────────────────────────────────────────────────

async def test_status_empty(client):
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_status_grouping_and_early_access_fields(client, sessionmaker_):
    from stocktrack.models import Product, Watch

    now = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)

    async with sessionmaker_() as s:
        w = Watch(
            store="ao", url="http://ao.com/1", label="AO Meaco",
            include_filter="Meaco", exclude_filter="", enabled=True,
        )
        s.add(w)
        await s.flush()
        p = Product(
            watch_id=w.id, store="ao", code="X1", title="Meaco Cirro 16K",
            brand="Meaco", url="http://ao.com/p/x1", availability="early",
            basket_url="https://ao.com/Build_Shopping_Basket.aspx?items=X1:1",
            current_in_stock=True, current_price=629.0,
            available_since=now, last_checked=now,
        )
        s.add(p)
        await s.commit()

    resp = await client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    group = data[0]
    assert group["store"] == "ao"
    assert group["label"] == "AO Meaco"
    assert "last_checked_at" in group
    assert "consecutive_failures" in group
    assert len(group["products"]) == 1
    prod = group["products"][0]
    assert prod["availability"] == "early"
    assert prod["basket_url"] == "https://ao.com/Build_Shopping_Basket.aspx?items=X1:1"
    assert prod["current_in_stock"] is True
    assert prod["current_price"] == 629.0


async def test_status_multiple_watches(client, sessionmaker_):
    from stocktrack.models import Product, Watch

    async with sessionmaker_() as s:
        w1 = Watch(store="ao", url="http://ao.com/1", enabled=True)
        w2 = Watch(store="johnlewis", url="http://jl.com/1", enabled=True)
        s.add_all([w1, w2])
        await s.flush()
        p1 = Product(watch_id=w1.id, store="ao", code="A1",
                     availability="oos", current_in_stock=False)
        p2 = Product(watch_id=w2.id, store="johnlewis", code="J1",
                     availability="public", current_in_stock=True)
        s.add_all([p1, p2])
        await s.commit()

    resp = await client.get("/api/status")
    data = resp.json()
    assert len(data) == 2
    stores = {g["store"] for g in data}
    assert stores == {"ao", "johnlewis"}


# ── GET /api/events ────────────────────────────────────────────────────────

async def test_events_empty(client):
    resp = await client.get("/api/events")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_events_shape_and_ordering(client, sessionmaker_):
    from datetime import timedelta

    from stocktrack.models import Event, Product, Watch

    t1 = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)
    t2 = t1 + timedelta(hours=1)

    async with sessionmaker_() as s:
        w = Watch(store="ao", url="http://ao.com/1", enabled=True)
        s.add(w)
        await s.flush()
        prod = Product(
            watch_id=w.id, store="ao", code="X1", title="Meaco Cirro 16K",
            url="http://ao.com/p/x1",
            basket_url="https://ao.com/Build_Shopping_Basket.aspx?items=X1:1",
            availability="public", current_in_stock=True,
        )
        s.add(prod)
        await s.flush()
        e1 = Event(product_id=prod.id, ts=t1, kind="early_access", price=629.0)
        e2 = Event(product_id=prod.id, ts=t2, kind="public", price=629.0)
        s.add_all([e1, e2])
        await s.commit()

    resp = await client.get("/api/events")
    data = resp.json()
    assert len(data) == 2
    # newest first
    assert data[0]["kind"] == "public"
    assert data[1]["kind"] == "early_access"
    # joined product fields present
    ev = data[0]
    assert ev["product_title"] == "Meaco Cirro 16K"
    assert ev["store"] == "ao"
    assert ev["url"] == "http://ao.com/p/x1"
    assert ev["basket_url"] == "https://ao.com/Build_Shopping_Basket.aspx?items=X1:1"


async def test_events_limit(client, sessionmaker_):
    from stocktrack.models import Event, Product, Watch

    async with sessionmaker_() as s:
        w = Watch(store="ao", url="http://ao.com/1", enabled=True)
        s.add(w)
        await s.flush()
        prod = Product(watch_id=w.id, store="ao", code="X1", availability="oos")
        s.add(prod)
        await s.flush()
        for i in range(5):
            s.add(Event(
                product_id=prod.id,
                ts=datetime(2026, 6, 27, 10, i, 0, tzinfo=timezone.utc),
                kind="public",
            ))
        await s.commit()

    resp = await client.get("/api/events?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ── GET /api/stores ────────────────────────────────────────────────────────

async def test_stores_returns_list(client):
    resp = await client.get("/api/stores")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    for s in data:
        assert "name" in s
        assert "kind" in s
        assert "supported" in s


async def test_stores_contains_ao_and_johnlewis(client):
    resp = await client.get("/api/stores")
    names = {s["name"] for s in resp.json()}
    assert "ao" in names
    assert "johnlewis" in names


# ── GET /api/watches ───────────────────────────────────────────────────────

async def test_watches_list_empty(client):
    resp = await client.get("/api/watches")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_watches_list(client, sessionmaker_):
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        s.add(Watch(store="ao", url="http://ao.com/1", label="AO", enabled=True))
        await s.commit()

    resp = await client.get("/api/watches")
    data = resp.json()
    assert len(data) == 1
    w = data[0]
    assert w["store"] == "ao"
    assert w["label"] == "AO"
    assert "last_checked_at" in w
    assert "consecutive_failures" in w


async def test_watches_get_single(client, sessionmaker_):
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        watch = Watch(store="johnlewis", url="http://jl.com/1", label="JL")
        s.add(watch)
        await s.commit()
        wid = watch.id

    resp = await client.get(f"/api/watches/{wid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == wid
    assert resp.json()["store"] == "johnlewis"


async def test_watches_get_single_404(client):
    resp = await client.get("/api/watches/9999")
    assert resp.status_code == 404
