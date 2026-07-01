from datetime import datetime, timezone

from stocktrack.models import Event, Product, Watch


async def _mk_product(sessionmaker_, **kw):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u")
        s.add(w)
        await s.commit()
        p = Product(watch_id=w.id, store="fake", code="A", title="Panel", **kw)
        s.add(p)
        await s.commit()
        return p.id


async def test_mute_and_unmute_roundtrip(client, sessionmaker_):
    pid = await _mk_product(sessionmaker_)

    r = await client.post(f"/api/products/{pid}/mute", json={"hours": 24})
    assert r.status_code == 200
    body = r.json()
    assert body["muted_until"] is not None

    async with sessionmaker_() as s:
        p = await s.get(Product, pid)
        assert p.muted_until is not None
        delta = p.muted_until - datetime.now(timezone.utc)
        assert 23 * 3600 < delta.total_seconds() <= 24 * 3600

    r = await client.delete(f"/api/products/{pid}/mute")
    assert r.status_code == 200
    assert r.json()["muted_until"] is None
    async with sessionmaker_() as s:
        p = await s.get(Product, pid)
        assert p.muted_until is None


async def test_mute_validates_hours(client, sessionmaker_):
    pid = await _mk_product(sessionmaker_)
    r = await client.post(f"/api/products/{pid}/mute", json={"hours": 0})
    assert r.status_code == 422


async def test_mute_unknown_product_404(client):
    r = await client.post("/api/products/99999/mute", json={"hours": 1})
    assert r.status_code == 404
    r = await client.delete("/api/products/99999/mute")
    assert r.status_code == 404


async def test_price_history_returns_priced_events(client, sessionmaker_):
    pid = await _mk_product(sessionmaker_)
    t = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    async with sessionmaker_() as s:
        s.add_all([
            Event(product_id=pid, kind="public", price=100.0, ts=t),
            Event(product_id=pid, kind="price_drop", price=90.0,
                  ts=t.replace(day=2)),
            Event(product_id=pid, kind="oos", price=None, ts=t.replace(day=3)),
            Event(product_id=pid, kind="new_low", price=85.0,
                  ts=t.replace(day=4)),
        ])
        await s.commit()

    r = await client.get(f"/api/products/{pid}/price-history")
    assert r.status_code == 200
    points = r.json()
    assert [pt["price"] for pt in points] == [100.0, 90.0, 85.0]  # ts asc, no nulls
    assert [pt["kind"] for pt in points] == ["public", "price_drop", "new_low"]


async def test_price_history_unknown_product_404(client):
    r = await client.get("/api/products/99999/price-history")
    assert r.status_code == 404
