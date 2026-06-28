from datetime import datetime, timezone
from sqlalchemy import select
from stocktrack.models import Event, Product, Watch
from stocktrack.services import poller
from stocktrack.sites.base import Product as P, SiteHandler

KEY = "p" * 32


def _handler_returning(products):
    class H(SiteHandler):
        name = "fake"
        kind = "listing"
        def fetch(self, url): return "raw"
        def parse(self, raw): return products
    return H()


async def _run(session, watch, products, *, sends_ok=True, now=None):
    sent = []
    def sender(cfg, title, message, click_url=None, markdown=False, priority=None, sleep=None):
        sent.append({"title": title, "priority": priority, "click_url": click_url})
        return sends_ok
    async def fetcher(handler, url):
        return "raw"
    res = await poller.check_watch(
        session, watch, secret_key=KEY,
        handler=_handler_returning(products), fetcher=fetcher, sender=sender, now=now)
    return res, sent


async def test_public_then_oos_with_duration(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id

    # 1) baseline all OOS -> no sends
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Meaco 12K", False, "Meaco", 519.0)])
        assert res["public"] == 0 and sent == []

    # 2) A in stock (availability="" => derived "public") -> 1 public event
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 519.0)])
        assert res["public"] == 1 and sent[0]["priority"] == 8
        p = (await s.execute(select(Product))).scalar_one()
        assert p.current_in_stock is True and p.available_since is not None

    # 3) A back OOS -> 1 oos event at priority 4
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Meaco 12K", False, "Meaco", 519.0)])
        assert res["oos"] == 1 and sent[0]["priority"] == 4
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert kinds == ["public", "oos"]


async def test_first_poll_is_silent_baseline(sessionmaker_):
    from sqlalchemy import select
    from stocktrack.models import Event, Product as PModel, Watch
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w); await s.commit(); wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0)])
        assert sent == []                          # no alert burst
        assert res["public"] == 0
        evs = (await s.execute(select(Event))).scalars().all()
        assert evs == []                           # no events on baseline
        p = (await s.execute(select(PModel))).scalar_one()
        assert p.current_in_stock is True and p.current_price == 100.0  # state recorded
        assert p.available_since is not None


async def test_failed_public_send_does_not_advance_state(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco", exclude_filter="")
        s.add(w); await s.commit(); wid = w.id
    # baseline OOS (silent)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", False, "Meaco", 519.0)])
    # 2nd poll: in stock but send fails -> state not advanced
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 519.0)], sends_ok=False)
        p = (await s.execute(select(Product))).scalar_one()
        assert p.current_in_stock is False
        assert p.available_since is None


async def test_early_to_public_sequence(sessionmaker_):
    """oos -> early -> public -> oos, checking event kinds and available_seconds."""
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id

    t0 = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 6, 27, 11, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 27, 12, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 6, 27, 13, 0, 0, tzinfo=timezone.utc)

    # oos
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", False, "Meaco", 519.0, availability="oos")], now=t0)

    # early
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 519.0, availability="early",
                                        basket_url="https://ao.com/basket?items=A:1")], now=t1)
        assert res["early"] == 1
        assert sent[0]["click_url"] == "https://ao.com/basket?items=A:1"
        p = (await s.execute(select(Product))).scalar_one()
        assert p.available_since == t1

    # public (available_since should stay at t1)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 519.0, availability="public")], now=t2)
        assert res["public"] == 1
        p = (await s.execute(select(Product))).scalar_one()
        assert p.available_since == t1  # unchanged since prev was "early" not "oos"

    # oos - available_seconds = t3-t1 = 7200 secs
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", False, "Meaco", 519.0, availability="oos")], now=t3)
        evs = (await s.execute(select(Event))).scalars().all()
        kinds = [e.kind for e in evs]
        assert kinds == ["early_access", "public", "oos"]
        oos_ev = [e for e in evs if e.kind == "oos"][0]
        assert oos_ev.available_seconds == int((t3 - t1).total_seconds())  # 7200


async def test_watch_health_updated_on_success(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    t = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", False, "Meaco")], now=t)
        w2 = await s.get(Watch, wid)
        assert w2.last_ok_at == t
        assert w2.consecutive_failures == 0


# ---------------------------------------------------------------------------
# Price-drop helpers
# ---------------------------------------------------------------------------

def test_is_price_drop_thresholds():
    f = poller.is_price_drop
    # 519 -> 493 = -26 (-5.0%): meets pct>=5 and abs>=5
    assert f(519.0, 493.0, 5, 5) is True
    # tiny drop below both thresholds
    assert f(519.0, 517.0, 5, 5) is False        # 2.0 abs, 0.39%
    # meets pct but not abs floor (20 -> 19 = 5% but only £1)
    assert f(20.0, 19.0, 5, 5) is False
    # price rose
    assert f(493.0, 519.0, 5, 5) is False
    # equal
    assert f(500.0, 500.0, 5, 5) is False
    # null baseline / null new
    assert f(None, 500.0, 5, 5) is False
    assert f(500.0, None, 5, 5) is False


# ---------------------------------------------------------------------------
# Price-drop integration tests
# ---------------------------------------------------------------------------

async def _set(session, key, value):
    from stocktrack.services.settings_service import set_value
    await set_value(session, key, str(value))
    await session.commit()


async def test_price_drop_alerts_when_threshold_met(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco",
                  exclude_filter="", track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 5)
        await _set(s, "price_drop_min_abs", 5)
        await _set(s, "price_drop_priority", 6)

    # 1) baseline: in stock at 519 -> public event, no drop (first sighting)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 519.0)])
        assert res.get("price_drops", 0) == 0

    # 2) price drops to 493 -> price_drop event at priority 6
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 493.0)])
        assert res["price_drops"] == 1
        drop_send = [x for x in sent if x["priority"] == 6]
        assert drop_send
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert "price_drop" in kinds
        p = (await s.execute(select(Product))).scalar_one()
        assert p.current_price == 493.0


async def test_price_drop_not_sent_below_threshold(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco",
                  exclude_filter="", track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 5)
        await _set(s, "price_drop_min_abs", 5)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 519.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 517.0)])
        assert res.get("price_drops", 0) == 0


async def test_delivery_persisted_on_product(sessionmaker_):
    from sqlalchemy import select
    from stocktrack.models import Product as PModel, Watch
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w); await s.commit(); wid = w.id
    # baseline poll then a second in-stock poll carrying a delivery string
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", False, "", 100.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0, delivery="Delivery by Mon 30 Jun (carrier)")])
        p = (await s.execute(select(PModel))).scalar_one()
        assert p.delivery == "Delivery by Mon 30 Jun (carrier)"


async def test_price_drop_disabled_when_flag_off(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco",
                  exclude_filter="", track_price_drops=False)
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 519.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 400.0)])
        assert res.get("price_drops", 0) == 0


async def test_store_config_kwargs_coerces_types(sessionmaker_):
    from stocktrack.services.settings_service import store_config_kwargs, set_value
    from stocktrack.sites.base import SiteHandler

    class H(SiteHandler):
        name = "fake2"
        settings_spec = [
            {"key": "ao_member", "type": "bool", "default": False},
            {"key": "cp_delivery_postcode", "type": "str", "default": ""},
        ]

    async with sessionmaker_() as s:
        await set_value(s, "early_access_days", "12")
        await set_value(s, "ao_member", "true")
        await set_value(s, "cp_delivery_postcode", "ZZ1 1ZZ")
        await s.commit()
        kw = await store_config_kwargs(s, H())
        assert kw["early_access_days"] == 12
        assert kw["ao_member"] is True
        assert kw["cp_delivery_postcode"] == "ZZ1 1ZZ"


async def test_failed_price_drop_send_reverts_price(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco",
                  exclude_filter="", track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 5)
        await _set(s, "price_drop_min_abs", 5)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 519.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 493.0)],
                            sends_ok=False)
        assert res.get("price_drops", 0) == 0
        p = (await s.execute(select(Product))).scalar_one()
        assert p.current_price == 519.0   # reverted (delivery-safe)
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert "price_drop" not in kinds
