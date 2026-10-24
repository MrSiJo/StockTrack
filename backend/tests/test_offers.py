"""Offers (plugin API 2): variants, sellers, discounts, quiet watches.

The example is a mattress comparison page: one listing, several sellers, each
selling Single, Double and King sizes, some with vouchers.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import create_async_engine

from stocktrack.db import init_models, make_sessionmaker
from stocktrack.models import Event, Product, ProductChange, Watch
from stocktrack.services import offers, poller
from stocktrack.services.digest import build_digest
from stocktrack.sites import MIN_PLUGIN_API, PLUGIN_API
from stocktrack.sites.base import Discount, SiteHandler
from stocktrack.sites.base import Product as P

KEY = "p" * 32
T0 = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)


def _offer(seller, size, price, *, rating=4.8, discounts=None, in_stock=True):
    return P(f"{seller.lower()}:{size.lower()}", f"{seller} {size}", in_stock,
             brand=seller, price=price, url=f"https://example.test/{seller}",
             variant=size, seller=seller, seller_rating=rating,
             discounts=discounts, extra={"delivery_days": "3"})


def _handler(products):
    class H(SiteHandler):
        name = "fake"
        kind = "listing"
        def fetch(self, url): return "raw"
        def parse(self, raw): return products
    return H()


async def _run(session, watch, products, *, now, sends_ok=True):
    sent = []
    def sender(cfg, title, message, click_url=None, markdown=False, priority=None,
               sleep=None):
        sent.append(title)
        return sends_ok
    async def fetcher(handler, url):
        return "raw"
    res = await poller.check_watch(session, watch, secret_key=KEY,
                                   handler=_handler(products), fetcher=fetcher,
                                   sender=sender, now=now)
    return res, sent


async def _watch(sm, **kw):
    async with sm() as s:
        w = Watch(store="fake", url="u", **kw)
        s.add(w)
        await s.commit()
        return w.id


def test_plugin_api_grew_and_still_accepts_api_1():
    assert PLUGIN_API == 2 and MIN_PLUGIN_API == 1


def test_product_offer_fields_default_for_api_1_handlers():
    p = P("A", "Thing", True)
    assert (p.variant, p.seller, p.seller_rating, p.discounts, p.extra) == (
        "", "", None, None, {})


def test_discounts_json_keeps_unknown_apart_from_none():
    assert offers.discounts_to_json(None) is None
    assert offers.discounts_to_json([]) == "[]"
    raw = offers.discounts_to_json([Discount("returning_customer", amount=20,
                                             code="BACK20")])
    assert json.loads(raw)[0]["code"] == "BACK20"
    # An unknown audience or a discount worth nothing is dropped, never
    # widened to everyone; junk in place of a list reads as unknown.
    assert offers.discounts_to_json([Discount("staff", amount=1)]) == "[]"
    assert offers.discounts_to_json([Discount("any")]) == "[]"
    assert offers.discounts_to_json([("any", 5)]) == "[]"
    assert json.loads(offers.discounts_to_json(
        [{"audience": "any", "percent": "10"}]))[0]["percent"] == 10.0
    assert offers.discounts_to_json("nope") is None


def test_audience_price_uses_best_single_discount():
    ds = [{"audience": "new_customer", "amount": 40.0},
          {"audience": "returning_customer", "amount": 20.0},
          {"audience": "any", "percent": 10.0}]
    assert offers.audience_price(150.0, ds, "new_customer") == 110.0
    assert offers.audience_price(150.0, ds, "returning_customer") == 130.0
    assert offers.audience_price(100.0, [{"audience": "any", "percent": 25}],
                                 "returning_customer") == 75.0
    assert offers.audience_price(10.0, [{"audience": "any", "amount": 50}],
                                 "new_customer") == 0.0
    assert offers.audience_price(150.0, [], "new_customer") == 150.0
    assert offers.audience_price(150.0, None, "new_customer") is None
    assert offers.audience_price(None, [], "new_customer") is None


async def test_poller_stores_offer_fields_and_records_changes(sessionmaker_):
    wid = await _watch(sessionmaker_)
    first = [_offer("Bedworks", "Double", 300.0, discounts=[]),
             _offer("Sleepco", "Double", 320.0)]
    async with sessionmaker_() as s:
        await _run(s, await s.get(Watch, wid), first, now=T0)
        rows = (await s.execute(select(Product).order_by(Product.code))).scalars().all()
        assert [(r.variant, r.seller, r.seller_rating) for r in rows] == [
            ("Double", "Bedworks", 4.8), ("Double", "Sleepco", 4.8)]
        assert rows[0].discounts_json == "[]" and rows[1].discounts_json is None
        assert json.loads(rows[0].extra_json) == {"delivery_days": "3"}
        assert (await s.execute(select(ProductChange))).scalars().all() == []

    second = [_offer("Bedworks", "Double", 280.0, discounts=[]),
              _offer("Sleepco", "Double", 320.0,
                     discounts=[Discount("new_customer", amount=30)])]
    async with sessionmaker_() as s:
        await _run(s, await s.get(Watch, wid), second, now=T0 + timedelta(days=1))
        changes = (await s.execute(
            select(ProductChange).order_by(ProductChange.id))).scalars().all()
        assert [(c.field, c.old, c.new is not None) for c in changes] == [
            ("price", "300.0", True), ("discounts", None, True)]

    async with sessionmaker_() as s:  # nothing moved: nothing recorded
        await _run(s, await s.get(Watch, wid), second, now=T0 + timedelta(days=2))
        assert len((await s.execute(select(ProductChange))).scalars().all()) == 2


async def test_quiet_watch_records_alerts_without_pushing(sessionmaker_):
    wid = await _watch(sessionmaker_, quiet=True, track_price_drops=True)
    async with sessionmaker_() as s:
        await _run(s, await s.get(Watch, wid),
                   [_offer("Bedworks", "King", 400.0)], now=T0)
    async with sessionmaker_() as s:
        _, sent = await _run(s, await s.get(Watch, wid),
                             [_offer("Bedworks", "King", 300.0),
                              _offer("Sleepco", "King", 390.0)],
                             now=T0 + timedelta(days=1))
        assert sent == []
        kinds = sorted(e.kind for e in (await s.execute(select(Event))).scalars().all())
        assert kinds == ["new_low", "new_product", "price_drop"]


async def test_loud_watch_still_pushes(sessionmaker_):
    wid = await _watch(sessionmaker_)
    async with sessionmaker_() as s:
        await _run(s, await s.get(Watch, wid), [_offer("Bedworks", "King", 400.0)],
                   now=T0)
    async with sessionmaker_() as s:
        _, sent = await _run(s, await s.get(Watch, wid),
                             [_offer("Bedworks", "King", 400.0),
                              _offer("Sleepco", "King", 390.0)],
                             now=T0 + timedelta(days=1))
        assert len(sent) == 1


async def _seed_offers(sm):
    wid = await _watch(sm, label="Mattresses")
    async with sm() as s:
        await _run(s, await s.get(Watch, wid), [
            _offer("Bedworks", "Double", 300.0,
                   discounts=[Discount("new_customer", amount=40),
                              Discount("returning_customer", amount=20)]),
            _offer("Sleepco", "Double", 290.0, rating=4.2, discounts=[]),
            _offer("Dozey", "Double", 310.0),
            _offer("Bedworks", "King", 400.0, discounts=[]),
            _offer("Gone", "King", 100.0, in_stock=False),
        ], now=T0)
    return wid


async def test_offers_api_groups_sorts_and_prices(client, sessionmaker_):
    wid = await _seed_offers(sessionmaker_)
    body = (await client.get(f"/api/watches/{wid}/offers")).json()
    assert [g["variant"] for g in body["variants"]] == ["Double", "King"]
    double = body["variants"][0]["offers"]
    assert [o["seller"] for o in double] == ["Sleepco", "Bedworks", "Dozey"]
    bed = double[1]
    assert (bed["price"], bed["price_new_customer"], bed["price_returning_customer"]) == (
        300.0, 260.0, 280.0)
    assert double[2]["discounts"] is None and double[2]["price_new_customer"] is None
    assert double[0]["discounts"] == [] and double[0]["price_returning_customer"] == 290.0
    assert bed["extra"] == {"delivery_days": "3"}
    assert [o["seller"] for o in body["variants"][1]["offers"]] == ["Bedworks"]


async def test_offers_api_filters(client, sessionmaker_):
    wid = await _seed_offers(sessionmaker_)
    body = (await client.get(f"/api/watches/{wid}/offers",
                             params={"variant": "Double", "min_rating": 4.5})).json()
    assert [g["variant"] for g in body["variants"]] == ["Double"]
    assert [o["seller"] for o in body["variants"][0]["offers"]] == ["Bedworks", "Dozey"]
    assert (await client.get("/api/watches/999/offers")).status_code == 404


async def test_offer_changes_api_summarises_per_variant(client, sessionmaker_):
    wid = await _seed_offers(sessionmaker_)
    now = datetime.now(timezone.utc)
    async with sessionmaker_() as s:
        rows = {r.code: r for r in (await s.execute(select(Product))).scalars().all()}
        s.add_all([
            ProductChange(product_id=rows["bedworks:double"].id, ts=now, field="price",
                          old="300.0", new="280.0"),
            ProductChange(product_id=rows["bedworks:double"].id, ts=now, field="price",
                          old="280.0", new="290.0"),
            ProductChange(product_id=rows["dozey:double"].id, ts=now,
                          field="discounts", old=None, new="[]"),
            ProductChange(product_id=rows["bedworks:king"].id,
                          ts=now - timedelta(days=30), field="price",
                          old="1.0", new="2.0"),
        ])
        await s.commit()
    body = (await client.get(f"/api/watches/{wid}/offer-changes",
                             params={"days": 7})).json()
    double, king = body["variants"]
    assert (double["price_changes"], double["offers_with_price_change"],
            double["max_abs_change"], double["mean_abs_change"],
            double["discount_changes"]) == (2, 1, 20.0, 15.0, 1)
    assert len(double["changes"]) == 3
    assert king["price_changes"] == 0


async def test_digest_renders_offer_watches_as_variant_blocks(sessionmaker_):
    wid = await _seed_offers(sessionmaker_)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        prods = (await s.execute(select(Product))).scalars().all()
        ev_prod = prods[0]
        ev = Event(product_id=ev_prod.id, kind="price_drop", price=1.0, ts=T0)
    summaries = offers.summarise_changes(prods, [])
    title, msg = build_digest([(w, prods)], [(ev, ev_prod)], T0, {wid: summaries})
    assert "*Double*" in msg and "*King*" in msg
    assert "Bedworks £300.00, new £260.00, returning £280.00" in msg
    assert "0 price changes, 0 discount changes" in msg
    assert "**Changes**" not in msg  # offer watch events are summarised, not listed
    assert "Gone" not in msg


async def test_delete_watch_removes_changes(client, sessionmaker_):
    wid = await _seed_offers(sessionmaker_)
    async with sessionmaker_() as s:
        pid = (await s.execute(select(Product.id))).scalars().first()
        s.add(ProductChange(product_id=pid, ts=T0, field="price", old="1", new="2"))
        await s.commit()
    assert (await client.delete(f"/api/watches/{wid}")).status_code == 204
    async with sessionmaker_() as s:
        assert (await s.execute(select(ProductChange))).scalars().all() == []


async def test_watch_quiet_round_trips_through_the_api(client):
    r = await client.post("/api/watches", json={"store": "ao", "url": "u",
                                                "quiet": True})
    assert r.status_code == 201 and r.json()["quiet"] is True
    wid = r.json()["id"]
    r = await client.put(f"/api/watches/{wid}", json={"quiet": False})
    assert r.json()["quiet"] is False


async def test_prune_old_changes(sessionmaker_):
    from stocktrack.services.retention import prune_old_changes
    wid = await _seed_offers(sessionmaker_)
    now = datetime.now(timezone.utc)
    async with sessionmaker_() as s:
        pid = (await s.execute(select(Product.id).where(Product.watch_id == wid))
               ).scalars().first()
        s.add_all([ProductChange(product_id=pid, ts=now - timedelta(days=100),
                                 field="price", old="1", new="2"),
                   ProductChange(product_id=pid, ts=now, field="price",
                                 old="2", new="3")])
        await s.commit()
        assert await prune_old_changes(s, 90, now=now) == 1
        await s.commit()
        assert len((await s.execute(select(ProductChange))).scalars().all()) == 1


async def test_existing_db_gains_offer_columns(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE product (id INTEGER PRIMARY KEY, watch_id INTEGER, "
            "store VARCHAR, code VARCHAR)")
        await conn.exec_driver_sql(
            "INSERT INTO product (id, watch_id, store, code) VALUES (1, 1, 'ao', 'X')")
    await init_models(engine)
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {x["name"] for x in inspect(c).get_columns("product")})
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert {"variant", "seller", "seller_rating", "discounts_json",
            "extra_json"} <= cols
    assert "product_change" in tables
    async with make_sessionmaker(engine)() as s:
        p = await s.get(Product, 1)
        assert p.variant == "" and p.discounts_json is None
    await engine.dispose()


async def test_failed_pushes_record_one_price_move_once(sessionmaker_):
    wid = await _watch(sessionmaker_, track_price_drops=True)
    async with sessionmaker_() as s:
        await _run(s, await s.get(Watch, wid), [_offer("Bedworks", "King", 100.0)],
                   now=T0)
    for day, ok in enumerate([False, False, False, True], start=1):
        async with sessionmaker_() as s:
            await _run(s, await s.get(Watch, wid), [_offer("Bedworks", "King", 50.0)],
                       now=T0 + timedelta(days=day), sends_ok=ok)
    async with sessionmaker_() as s:
        rows = (await s.execute(select(ProductChange))).scalars().all()
        assert [(c.old, c.new) for c in rows] == [("100.0", "50.0")]


async def test_price_gap_does_not_lose_the_move(sessionmaker_):
    wid = await _watch(sessionmaker_)
    for day, price in enumerate([10.0, 12.0, None, 15.0]):
        async with sessionmaker_() as s:
            await _run(s, await s.get(Watch, wid), [_offer("Bedworks", "King", price)],
                       now=T0 + timedelta(days=day))
    async with sessionmaker_() as s:
        rows = (await s.execute(select(ProductChange).order_by(ProductChange.id))
                ).scalars().all()
        assert [(c.old, c.new) for c in rows] == [("10.0", "12.0"), ("12.0", "15.0")]


async def test_bad_plugin_values_do_not_break_the_poll_or_the_api(client, sessionmaker_):
    wid = await _watch(sessionmaker_)
    bad = _offer("Bedworks", "King", 100.0, rating="great",
                 discounts=[object(), {"audience": "any", "amount": "lots"}])
    bad.extra = ["not", "a", "dict"]
    async with sessionmaker_() as s:
        await _run(s, await s.get(Watch, wid), [bad], now=T0)
    body = (await client.get(f"/api/watches/{wid}/offers",
                             params={"min_rating": 4})).json()
    assert body["variants"] == []
    body = (await client.get(f"/api/watches/{wid}/offers")).json()
    o = body["variants"][0]["offers"][0]
    assert o["seller_rating"] is None and o["discounts"] == [] and o["extra"] == {}


def test_digest_trophy_only_after_a_real_drop():
    w = Watch(id=1, store="fake", url="u", label="Mattresses")
    def prod(pid, seller, price, lowest, ref):
        return Product(id=pid, watch_id=1, store="fake", code=seller.lower(),
                       title=seller, variant="King", seller=seller,
                       current_price=price, lowest_price=lowest, price_ref=ref,
                       current_in_stock=True, first_seen=T0, last_seen=T0,
                       discounts_json="[]", extra_json="")
    prods = [prod(1, "Steady", 100.0, 100.0, 100.0),
             prod(2, "Dropped", 90.0, 90.0, 120.0)]
    _, msg = build_digest([(w, prods)], [], T0, {})
    lines = msg.splitlines()
    assert "• Steady £100.00" in lines and "• Dropped £90.00 🏆" in lines
