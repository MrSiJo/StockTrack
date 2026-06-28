import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("APP_SECRET_KEY", "t" * 32)


# ── POST /api/watches ──────────────────────────────────────────────────────

async def test_create_watch(client):
    resp = await client.post("/api/watches", json={
        "store": "ao",
        "url": "http://ao.com/dehumidifiers",
        "label": "AO Meaco",
        "include_filter": "Meaco",
        "exclude_filter": "",
        "interval_seconds": 300,
        "enabled": True,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] is not None
    assert data["store"] == "ao"
    assert data["label"] == "AO Meaco"


async def test_create_product_watch_with_price_drops(client):
    r = await client.post("/api/watches", json={
        "store": "ao", "kind": "product", "url": "https://example.test/p/1",
        "track_price_drops": True,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "product"
    assert body["track_price_drops"] is True


async def test_create_watch_unknown_store_returns_422(client):
    resp = await client.post("/api/watches", json={
        "store": "unknown_store_xyz",
        "url": "http://example.com",
    })
    assert resp.status_code == 422


# ── PUT /api/watches/{id} ──────────────────────────────────────────────────

async def test_update_watch(client, sessionmaker_):
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        w = Watch(store="ao", url="http://ao.com/1", label="Old Label", enabled=True)
        s.add(w)
        await s.commit()
        wid = w.id

    resp = await client.put(f"/api/watches/{wid}", json={"label": "New Label", "enabled": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "New Label"
    assert data["enabled"] is False


async def test_update_watch_404(client):
    resp = await client.put("/api/watches/9999", json={"label": "x"})
    assert resp.status_code == 404


async def test_update_watch_unknown_store_returns_422(client, sessionmaker_):
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        w = Watch(store="ao", url="http://ao.com/1", label="AO", enabled=True)
        s.add(w)
        await s.commit()
        wid = w.id

    resp = await client.put(f"/api/watches/{wid}", json={"store": "unknown_store_xyz"})
    assert resp.status_code == 422


# ── DELETE /api/watches/{id} ───────────────────────────────────────────────

async def test_delete_watch(client, sessionmaker_):
    from sqlalchemy import select

    from stocktrack.models import Event, Product, Watch

    async with sessionmaker_() as s:
        w = Watch(store="ao", url="http://ao.com/1", enabled=True)
        s.add(w)
        await s.flush()
        p = Product(watch_id=w.id, store="ao", code="X1", availability="oos")
        s.add(p)
        await s.flush()
        e = Event(product_id=p.id, kind="oos", price=None)
        s.add(e)
        await s.commit()
        wid = w.id

    resp = await client.delete(f"/api/watches/{wid}")
    assert resp.status_code == 204

    async with sessionmaker_() as s:
        assert await s.get(Watch, wid) is None
        products = (await s.execute(select(Product))).scalars().all()
        events = (await s.execute(select(Event))).scalars().all()
        assert products == []
        assert events == []


async def test_delete_watch_404(client):
    resp = await client.delete("/api/watches/9999")
    assert resp.status_code == 404


# ── POST /api/watches/{id}/check ───────────────────────────────────────────

async def test_check_watch_runs_and_returns_result(client, sessionmaker_):
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        w = Watch(store="ao", url="http://ao.com/1", enabled=True)
        s.add(w)
        await s.commit()
        wid = w.id

    fake_result = {"parsed": 3, "early": 0, "public": 1, "oos": 0}
    with patch(
        "stocktrack.api.routes.watches.check_watch",
        new_callable=AsyncMock,
        return_value=fake_result,
    ):
        resp = await client.post(f"/api/watches/{wid}/check")

    assert resp.status_code == 200
    assert resp.json() == {**fake_result, "notified": False}


async def test_check_watch_404(client):
    resp = await client.post("/api/watches/9999/check")
    assert resp.status_code == 404


async def test_check_notify_true_sends_one_status_push(client, sessionmaker_):
    """notify=true sends exactly one status push; title contains 'status'; notified=true."""
    from unittest.mock import call

    from stocktrack.models import Product, Watch
    from stocktrack.services.settings_service import set_value

    async with sessionmaker_() as s:
        w = Watch(store="ao", url="http://ao.com/1", enabled=True)
        s.add(w)
        await s.flush()
        # Two products with different phases
        s.add(Product(watch_id=w.id, store="ao", code="A1", title="Alpha Widget",
                      availability="public", current_in_stock=True, current_price=129.99))
        s.add(Product(watch_id=w.id, store="ao", code="B2", title="Beta Gadget",
                      availability="oos", current_in_stock=False))
        # Seed Gotify config (token is a secret — must be stored encrypted)
        from stocktrack.bootstrap import get_settings
        sk = get_settings().app_secret_key
        await set_value(s, "gotify_url", "http://gotify.example.com")
        await set_value(s, "gotify_token", "test-token", is_secret=True, secret_key=sk)
        await s.commit()
        wid = w.id

    fake_result = {"parsed": 2, "early": 0, "public": 1, "oos": 1}
    captured: list = []

    def fake_send(cfg, title, message, **kwargs):
        captured.append({"title": title, "message": message})
        return True

    with patch("stocktrack.api.routes.watches.check_watch",
               new_callable=AsyncMock, return_value=fake_result), \
         patch("stocktrack.services.gotify.send", side_effect=fake_send):
        resp = await client.post(f"/api/watches/{wid}/check?notify=true")

    assert resp.status_code == 200
    data = resp.json()
    assert data["notified"] is True
    # Exactly one status push
    assert len(captured) == 1
    assert "status" in captured[0]["title"]
    # Per-product lines in body
    assert "Alpha Widget" in captured[0]["message"]
    assert "Beta Gadget" in captured[0]["message"]
    # Stock counts and phase icons
    assert "🟢" in captured[0]["message"]
    assert "🔴" in captured[0]["message"]


async def test_check_notify_false_sends_no_status_push(client, sessionmaker_):
    """notify=false (default) must not send any status push."""
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        w = Watch(store="ao", url="http://ao.com/1", enabled=True)
        s.add(w)
        await s.commit()
        wid = w.id

    fake_result = {"parsed": 1, "early": 0, "public": 0, "oos": 1}
    with patch("stocktrack.api.routes.watches.check_watch",
               new_callable=AsyncMock, return_value=fake_result), \
         patch("stocktrack.services.gotify.send") as mock_send:
        resp = await client.post(f"/api/watches/{wid}/check")

    assert resp.status_code == 200
    assert resp.json()["notified"] is False
    mock_send.assert_not_called()


async def test_check_notify_unconfigured_returns_notified_false(client, sessionmaker_):
    """notified=false when Gotify URL/token are not set."""
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        w = Watch(store="ao", url="http://ao.com/1", enabled=True)
        s.add(w)
        await s.commit()
        wid = w.id

    fake_result = {"parsed": 0, "early": 0, "public": 0, "oos": 0}
    with patch("stocktrack.api.routes.watches.check_watch",
               new_callable=AsyncMock, return_value=fake_result), \
         patch("stocktrack.services.gotify.send") as mock_send:
        resp = await client.post(f"/api/watches/{wid}/check?notify=true")

    assert resp.status_code == 200
    assert resp.json()["notified"] is False
    # send must NOT be called when unconfigured
    mock_send.assert_not_called()


# ── POST /api/watches/preview ──────────────────────────────────────────────

async def test_preview_returns_products_without_persisting(client, sessionmaker_):
    from sqlalchemy import select

    from stocktrack.models import Watch
    from stocktrack.sites.base import Product as P, SiteHandler

    class FakeHandler(SiteHandler):
        name = "ao"
        kind = "listing"

        def fetch(self, url):
            return "raw"

        def parse(self, raw):
            return [
                P("X1", "Meaco Cirro 16K", True, "Meaco", 629.0,
                  availability="early",
                  basket_url="https://ao.com/Build_Shopping_Basket.aspx?items=X1:1"),
                P("X2", "Other Brand 12K", True, "Other", 499.0, availability="public"),
            ]

        def configure(self, **opts):
            pass

    with patch("stocktrack.api.routes.watches.get_handler", return_value=FakeHandler()):
        resp = await client.post("/api/watches/preview", json={
            "store": "ao",
            "url": "http://ao.com/dehumidifiers",
            "include_filter": "Meaco",
            "exclude_filter": "",
        })

    assert resp.status_code == 200
    data = resp.json()
    # include_filter="Meaco" — only Meaco products pass
    assert len(data) == 1
    assert data[0]["code"] == "X1"
    assert data[0]["availability"] == "early"
    assert data[0]["basket_url"] == "https://ao.com/Build_Shopping_Basket.aspx?items=X1:1"

    # Verify nothing was persisted
    async with sessionmaker_() as s:
        watches = (await s.execute(select(Watch))).scalars().all()
        assert watches == []


async def test_preview_unknown_store_returns_422(client):
    resp = await client.post("/api/watches/preview", json={
        "store": "unknown_store_xyz",
        "url": "http://example.com",
    })
    assert resp.status_code == 422


async def test_preview_fetch_error_returns_502(client):
    with patch("stocktrack.api.routes.watches.get_handler") as mock_get_handler:
        mock_handler = MagicMock()
        mock_handler.fetch.side_effect = RuntimeError("connection refused")
        mock_get_handler.return_value = mock_handler

        resp = await client.post("/api/watches/preview", json={
            "store": "ao",
            "url": "http://ao.com/dehumidifiers",
        })

    assert resp.status_code == 502
    assert "connection refused" in resp.json()["detail"]


async def test_preview_configure_respects_early_access_days(client, sessionmaker_):
    """preview_watch must pass the live early_access_days setting to handler.configure."""
    from stocktrack.services.settings_service import set_value
    from stocktrack.sites.base import Product as P, SiteHandler

    # Seed the DB with a non-default threshold
    async with sessionmaker_() as s:
        await set_value(s, "early_access_days", "45")
        await s.commit()

    configured_with: dict = {}

    class FakeHandler(SiteHandler):
        name = "ao"
        kind = "listing"

        def fetch(self, url):
            return "raw"

        def parse(self, raw):
            return [P("X1", "Widget", True, "Acme", 99.0, availability="public")]

        def configure(self, **opts):
            configured_with.update(opts)

    with patch("stocktrack.api.routes.watches.get_handler", return_value=FakeHandler()):
        resp = await client.post("/api/watches/preview", json={
            "store": "ao",
            "url": "http://ao.com/widgets",
        })

    assert resp.status_code == 200
    assert configured_with.get("early_access_days") == 45
