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
        sent.append({"title": title, "message": message,
                     "priority": priority, "click_url": click_url})
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
        s.add(w)
        await s.commit()
        wid = w.id
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
        s.add(w)
        await s.commit()
        wid = w.id
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
        s.add(w)
        await s.commit()
        wid = w.id
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


async def test_new_product_alert_on_established_watch(sessionmaker_):
    from sqlalchemy import select
    from stocktrack.models import Event, Watch
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    # baseline with product A
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel A", True, "", 100.0)])
    # 2nd poll: B is brand new and in stock -> exactly one new_product alert (not a public one)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel A", True, "", 100.0),
                                      P("B", "Panel B", True, "", 150.0)])
        assert res["new_products"] == 1
        assert len(sent) == 1
        assert "New product" in sent[0]["title"]
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert kinds == ["new_product"]


async def test_new_product_send_failure_is_delivery_safe(sessionmaker_):
    from sqlalchemy import select
    from stocktrack.models import Event, Watch
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel A", True, "", 100.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, [P("A", "Panel A", True, "", 100.0),
                                   P("B", "Panel B", True, "", 150.0)], sends_ok=False)
        assert res["new_products"] == 0
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert "new_product" not in kinds


async def test_lead_time_change_alert(sessionmaker_):
    from sqlalchemy import select
    from stocktrack.models import Event, Watch
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    # baseline in stock with delivery X
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0, delivery="Delivery by Mon 30 Jun (carrier)")])
    # 2nd poll: still in stock, delivery swings well past the slide threshold
    # -> lead_time alert
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0, delivery="Delivery by Thu 30 Jul (branch)")])
        assert res["lead_time_changes"] == 1
        assert any("Delivery changed" in x["title"] for x in sent)
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert "lead_time" in kinds


# ---------------------------------------------------------------------------
# Price-creep reference
# ---------------------------------------------------------------------------

async def test_creep_accumulates_to_alert(sessionmaker_):
    """A slow multi-tick decline alerts once the total drop from the local
    peak trips the thresholds, even though each step is under-threshold."""
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 1)
        await _set(s, "price_drop_min_abs", 10)
    for price, expect_drops in [(100.0, 0), (97.0, 0), (94.0, 0), (89.0, 1)]:
        async with sessionmaker_() as s:
            w = await s.get(Watch, wid)
            res, sent = await _run(s, w, [P("A", "Panel", True, "", price)])
            assert res.get("price_drops", 0) == expect_drops, price
    async with sessionmaker_() as s:
        p = (await s.execute(select(Product))).scalar_one()
        assert p.price_ref == 89.0   # reset to the alerted-on price


async def test_price_ref_resets_on_rise(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 1)
        await _set(s, "price_drop_min_abs", 10)
    for price in [100.0, 95.0, 105.0]:
        async with sessionmaker_() as s:
            w = await s.get(Watch, wid)
            await _run(s, w, [P("A", "Panel", True, "", price)])
    async with sessionmaker_() as s:
        p = (await s.execute(select(Product))).scalar_one()
        assert p.price_ref == 105.0


async def test_failed_drop_send_keeps_price_ref(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 1)
        await _set(s, "price_drop_min_abs", 10)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, [P("A", "Panel", True, "", 89.0)], sends_ok=False)
        assert res.get("price_drops", 0) == 0
        p = (await s.execute(select(Product))).scalar_one()
        assert p.price_ref == 100.0   # not advanced -> retries next tick


# ---------------------------------------------------------------------------
# Per-product mute
# ---------------------------------------------------------------------------

async def test_muted_product_records_event_without_push(sessionmaker_):
    from datetime import timedelta
    t0 = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", False, "", 100.0)], now=t0)
        p = (await s.execute(select(Product))).scalar_one()
        p.muted_until = t0 + timedelta(hours=24)
        await s.commit()
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0)],
                               now=t0 + timedelta(hours=1))
        assert sent == []                       # no push while muted
        assert res["public"] == 1               # ...but state/history advance
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert kinds == ["public"]
        p = (await s.execute(select(Product))).scalar_one()
        assert p.current_in_stock is True


async def test_mute_expired_sends_again(sessionmaker_):
    from datetime import timedelta
    t0 = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", False, "", 100.0)], now=t0)
        p = (await s.execute(select(Product))).scalar_one()
        p.muted_until = t0 + timedelta(hours=1)
        await s.commit()
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0)],
                               now=t0 + timedelta(hours=2))
        assert len(sent) == 1                   # mute expired -> push resumes
        assert res["public"] == 1


# ---------------------------------------------------------------------------
# new_product priority
# ---------------------------------------------------------------------------

async def test_new_product_uses_own_priority(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "new_product_priority", 2)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel A", True, "", 100.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel A", True, "", 100.0),
                                      P("B", "Panel B", True, "", 150.0)])
        assert res["new_products"] == 1
        assert sent[0]["priority"] == 2


# ---------------------------------------------------------------------------
# OOS gate for price alerts
# ---------------------------------------------------------------------------

async def test_no_drop_alert_while_oos_by_default(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", False, "", 519.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", False, "", 400.0)])
        assert res.get("price_drops", 0) == 0
        assert sent == []
        p = (await s.execute(select(Product))).scalar_one()
        assert p.current_price == 400.0   # truth still tracked silently


async def test_oos_drop_alert_when_setting_off(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_in_stock_only", "false")
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", False, "", 519.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, [P("A", "Panel", False, "", 400.0)])
        assert res["price_drops"] == 1


async def test_target_fires_even_while_oos(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  price_target=100.0)
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", False, "", 110.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", False, "", 95.0)])
        assert res["price_targets"] == 1
        assert any("Target price" in x["title"] for x in sent)


# ---------------------------------------------------------------------------
# Price-rise (up-recovery) alerts
# ---------------------------------------------------------------------------

def test_is_price_rise_thresholds():
    f = poller.is_price_rise
    assert f(493.0, 519.0, 5, 5) is True          # +26 (+5.3%)
    assert f(519.0, 521.0, 5, 5) is False         # +2, +0.4%
    assert f(20.0, 21.0, 5, 5) is False           # 5% but only £1
    assert f(519.0, 493.0, 5, 5) is False         # fell
    assert f(500.0, 500.0, 5, 5) is False
    assert f(None, 500.0, 5, 5) is False
    assert f(500.0, None, 5, 5) is False


async def test_price_rise_alert_when_enabled(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_rises=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 5)
        await _set(s, "price_drop_min_abs", 5)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 493.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 519.0)])
        assert res["price_rises"] == 1
        assert any("Price back up" in x["title"] for x in sent)
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert "price_rise" in kinds


async def test_price_rise_disabled_by_default(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 493.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 519.0)])
        assert res.get("price_rises", 0) == 0
        assert sent == []


# ---------------------------------------------------------------------------
# New-low (all-time-low) alerts
# ---------------------------------------------------------------------------

async def test_new_low_alert_standalone(sessionmaker_):
    """An under-threshold drop that is still an all-time low alerts as new_low."""
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 1)
        await _set(s, "price_drop_min_abs", 10)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 98.0)])
        assert res["new_lows"] == 1
        assert res["price_drops"] == 0
        assert len(sent) == 1 and "Lowest price ever" in sent[0]["title"]
        p = (await s.execute(select(Product))).scalar_one()
        assert p.lowest_price == 98.0


async def test_new_low_merges_into_drop_push(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 1)
        await _set(s, "price_drop_min_abs", 10)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 85.0)])
        assert res["price_drops"] == 1 and res["new_lows"] == 1
        assert len(sent) == 1                      # merged: one push, not two
        assert "Price drop" in sent[0]["title"]
        kinds = {e.kind for e in (await s.execute(select(Event))).scalars().all()}
        assert {"price_drop", "new_low"} <= kinds
        p = (await s.execute(select(Product))).scalar_one()
        assert p.lowest_price == 85.0


async def test_new_low_silent_on_first_poll(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0)])
        assert sent == []
        p = (await s.execute(select(Product))).scalar_one()
        assert p.lowest_price == 100.0


async def test_new_low_tracks_silently_when_drops_untracked(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=False)
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 90.0)])
        assert res.get("new_lows", 0) == 0 and sent == []
        p = (await s.execute(select(Product))).scalar_one()
        assert p.lowest_price == 90.0   # truth still tracked, just no alert


async def test_failed_new_low_send_keeps_lowest_price(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=True)
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "price_drop_min_pct", 1)
        await _set(s, "price_drop_min_abs", 10)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, [P("A", "Panel", True, "", 98.0)], sends_ok=False)
        assert res.get("new_lows", 0) == 0
        p = (await s.execute(select(Product))).scalar_one()
        assert p.lowest_price == 100.0   # not advanced -> re-alerts next tick
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert "new_low" not in kinds


# ---------------------------------------------------------------------------
# Per-watch thresholds + target price
# ---------------------------------------------------------------------------

async def test_per_watch_thresholds_override_globals(sessionmaker_):
    async with sessionmaker_() as s:
        wa = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                   track_price_drops=True,
                   price_drop_min_pct=20, price_drop_min_abs=50)
        wb = Watch(store="fake", url="u2", include_filter="", exclude_filter="",
                   track_price_drops=True,
                   price_drop_min_pct=0.1, price_drop_min_abs=0.5)
        s.add_all([wa, wb])
        await s.commit()
        wa_id, wb_id = wa.id, wb.id
        await _set(s, "price_drop_min_pct", 5)
        await _set(s, "price_drop_min_abs", 5)
    # watch A: -5% drop meets globals but not its tighter per-watch rule
    async with sessionmaker_() as s:
        w = await s.get(Watch, wa_id)
        await _run(s, w, [P("A", "Panel", True, "", 519.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wa_id)
        res, _ = await _run(s, w, [P("A", "Panel", True, "", 493.0)])
        assert res["price_drops"] == 0
    # watch B: -£2 fails globals but passes its looser per-watch rule
    async with sessionmaker_() as s:
        w = await s.get(Watch, wb_id)
        await _run(s, w, [P("B", "Panel B", True, "", 519.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wb_id)
        res, _ = await _run(s, w, [P("B", "Panel B", True, "", 517.0)])
        assert res["price_drops"] == 1


async def test_price_target_fires_on_crossing(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  track_price_drops=False, price_target=100.0)
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 110.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 95.0)])
        assert res["price_targets"] == 1
        assert any("Target price" in x["title"] for x in sent)
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert "price_target" in kinds


async def test_price_target_no_refire_below(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  price_target=100.0)
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 110.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 95.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 93.0)])
        assert res["price_targets"] == 0
        assert sent == []


async def test_price_target_send_failure_reverts_price(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="",
                  price_target=100.0)
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 110.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, [P("A", "Panel", True, "", 95.0)], sends_ok=False)
        assert res["price_targets"] == 0
        p = (await s.execute(select(Product))).scalar_one()
        assert p.current_price == 110.0   # reverted (delivery-safe) -> refires next tick
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert "price_target" not in kinds


# ---------------------------------------------------------------------------
# Alert grouping
# ---------------------------------------------------------------------------

async def test_alerts_grouped_when_threshold_met(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "alert_group_threshold", 3)
    oos = [P("A", "Panel A", False, "", 100.0),
           P("B", "Panel B", False, "", 150.0),
           P("C", "Panel C", False, "", 200.0)]
    instock = [P("A", "Panel A", True, "", 100.0),
               P("B", "Panel B", True, "", 150.0),
               P("C", "Panel C", True, "", 200.0)]
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, oos)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, instock)
        assert res["public"] == 3
        assert len(sent) == 1
        assert "3 updates" in sent[0]["title"]
        assert sent[0]["priority"] == 8  # max of the grouped restock alerts
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert kinds == ["public", "public", "public"]
        rows = (await s.execute(select(Product))).scalars().all()
        assert all(r.current_in_stock for r in rows)


async def test_alerts_individual_below_threshold(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "alert_group_threshold", 3)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel A", False, "", 100.0),
                          P("B", "Panel B", False, "", 150.0)])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel A", True, "", 100.0),
                                      P("B", "Panel B", True, "", 150.0)])
        assert res["public"] == 2
        assert len(sent) == 2
        assert all("In stock" in x["title"] for x in sent)


async def test_grouped_send_failure_reverts_all(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "alert_group_threshold", 3)
    oos = [P("A", "Panel A", False, "", 100.0),
           P("B", "Panel B", False, "", 150.0),
           P("C", "Panel C", False, "", 200.0)]
    instock = [P("A", "Panel A", True, "", 100.0),
               P("B", "Panel B", True, "", 150.0),
               P("C", "Panel C", True, "", 200.0)]
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, oos)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, instock, sends_ok=False)
        assert res["public"] == 0
        assert (await s.execute(select(Event))).scalars().all() == []
        rows = (await s.execute(select(Product))).scalars().all()
        assert all(not r.current_in_stock for r in rows)


async def test_grouped_push_has_markdown_link_per_product(sessionmaker_):
    """A grouped push renders each product as a single tappable markdown link,
    labelled with the alert's own group_line (emoji + status text), not just
    "title — price" — so a mixed-kind grouped push still tells the reader
    what happened to each product. The notification-level click points at the
    configured dashboard URL."""
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "dashboard_url", "http://stocktrack.local")
        await _set(s, "alert_group_threshold", 2)
    # baseline OOS
    prods_oos = [P(f"c{i}", f"Item {i}", False, "", url=f"http://shop.local/c{i}")
                 for i in range(3)]
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, prods_oos)
    # all come into stock at once
    prods_in = [P(f"c{i}", f"Item {i}", True, "", 10.0 + i, url=f"http://shop.local/c{i}")
                for i in range(3)]
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, prods_in)
        assert res["public"] == 3
        grouped = [p for p in sent if "updates" in p["title"].lower()]
        assert grouped, "expected one grouped push"
        body = grouped[0]["message"]
        assert body.count("](http") == 3   # exactly one link per product, no dupes
        for i in range(3):
            # label preserves per-kind status context (emoji + "in stock"),
            # not just the bare "title — price" pair
            assert (f"[🟢 Item {i}: in stock — £{10.0 + i:.2f}]"
                    f"(http://shop.local/c{i})") in body
        assert grouped[0]["click_url"] == "http://stocktrack.local"


# ---------------------------------------------------------------------------
# Lead-time slide suppression
# ---------------------------------------------------------------------------

NOW_JUL2 = datetime(2026, 7, 2, 9, 0, 0, tzinfo=timezone.utc)


def test_is_lead_time_change_significant():
    f = poller.is_lead_time_change_significant
    # daily slide (next-day delivery rolling forward): suppressed
    assert f("Delivery by Thu 2 Jul", "Delivery by Fri 3 Jul", NOW_JUL2, 7) is False
    # big swing out to ~4 weeks: alerts
    assert f("Delivery by Fri 3 Jul", "Delivery by Thu 30 Jul", NOW_JUL2, 7) is True
    # big swing back in (deal on lead time): alerts
    assert f("Delivery by Thu 30 Jul", "Delivery by Fri 3 Jul", NOW_JUL2, 7) is True
    # exactly at the threshold: alerts
    assert f("Delivery by Fri 3 Jul", "Delivery by Fri 10 Jul", NOW_JUL2, 7) is True
    # channel switch is always significant even with close dates
    assert f("Delivery by Fri 3 Jul", "Collection by Sat 4 Jul", NOW_JUL2, 7) is True
    # unparseable text falls back to alerting on any change
    assert f("2-3 working days", "5-7 working days", NOW_JUL2, 7) is True
    # min_days=0 restores alert-on-any-change
    assert f("Delivery by Thu 2 Jul", "Delivery by Fri 3 Jul", NOW_JUL2, 0) is True
    # year rollover: 30 Dec -> 2 Jan is a 3-day slide, suppressed
    dec_now = datetime(2026, 12, 29, 9, 0, 0, tzinfo=timezone.utc)
    assert f("Delivery by Wed 30 Dec", "Delivery by Sat 2 Jan", dec_now, 7) is False
    # ordinal + full month (AO style) parses too
    assert f("Home delivery from 3rd July", "Home delivery from 4th July",
             NOW_JUL2, 7) is False


async def test_sliding_delivery_date_does_not_alert(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0,
                            delivery="Delivery by Thu 2 Jul")], now=NOW_JUL2)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0,
                                        delivery="Delivery by Fri 3 Jul")],
                               now=NOW_JUL2)
        assert res["lead_time_changes"] == 0
        assert sent == []
        p = (await s.execute(select(Product))).scalar_one()
        assert p.delivery == "Delivery by Fri 3 Jul"   # state still tracks


async def test_big_delivery_swing_still_alerts(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0,
                            delivery="Delivery by Fri 3 Jul")], now=NOW_JUL2)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0,
                                        delivery="Delivery by Thu 30 Jul")],
                               now=NOW_JUL2)
        assert res["lead_time_changes"] == 1
        assert any("Delivery changed" in x["title"] for x in sent)


async def test_slide_alerts_again_when_threshold_zero(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
        await _set(s, "lead_time_min_change_days", 0)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0,
                            delivery="Delivery by Thu 2 Jul")], now=NOW_JUL2)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, [P("A", "Panel", True, "", 100.0,
                                     delivery="Delivery by Fri 3 Jul")],
                            now=NOW_JUL2)
        assert res["lead_time_changes"] == 1


async def test_oos_to_instock_does_not_fire_lead_time(sessionmaker_):
    """A delivery string appearing alongside an OOS->in-stock transition is
    part of the restock, not a lead-time change."""
    from stocktrack.models import Watch
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", False, "", 100.0,
                            delivery="Delivery by Mon 30 Jun (carrier)")])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0,
                                        delivery="Delivery by Thu 2 Jul (branch)")])
        assert res["public"] == 1
        assert res["lead_time_changes"] == 0
        assert len(sent) == 1 and "In stock" in sent[0]["title"]
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert "lead_time" not in kinds


# ---------------------------------------------------------------------------
# Per-watch lock: manual check vs scheduler tick
# ---------------------------------------------------------------------------

async def test_concurrent_checks_do_not_double_fire(sessionmaker_):
    import asyncio
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:  # baseline OOS
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", False, "", 100.0)])

    sent = []

    def sender(cfg, title, message, click_url=None, markdown=False,
               priority=None, sleep=None):
        sent.append(title)
        return True

    async def slow_fetcher(handler, url):
        await asyncio.sleep(0.05)  # let both checks reach the fetch stage
        return "raw"

    async def one_check():
        async with sessionmaker_() as s:
            w = await s.get(Watch, wid)
            return await poller.check_watch(
                s, w, secret_key=KEY,
                handler=_handler_returning([P("A", "Panel", True, "", 100.0)]),
                fetcher=slow_fetcher, sender=sender)

    await asyncio.gather(one_check(), one_check())
    assert len(sent) == 1                     # one push, not two
    async with sessionmaker_() as s:
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert kinds == ["public"]            # one event, not duplicated


# ---------------------------------------------------------------------------
# Delisted products (absent from the parse) -> OOS after staleness grace
# ---------------------------------------------------------------------------

from datetime import timedelta  # noqa: E402

T0 = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
BOTH = [P("A", "Panel A", True, "", 100.0), P("B", "Panel B", True, "", 150.0)]
ONLY_B = [P("B", "Panel B", True, "", 150.0)]


async def _delist_watch(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:  # silent baseline, A+B in stock
        w = await s.get(Watch, wid)
        await _run(s, w, BOTH, now=T0)
    return wid


async def test_delisted_product_waits_out_grace_then_goes_oos(sessionmaker_):
    wid = await _delist_watch(sessionmaker_)
    # 1st absent tick: within the 2-tick grace -> no transition
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, ONLY_B, now=T0 + timedelta(seconds=301))
        assert res["oos"] == 0 and sent == []
        a = (await s.execute(select(Product).where(Product.code == "A"))).scalar_one()
        assert a.current_in_stock is True
    # 2nd absent tick: last_seen is now > 2 * interval_seconds old -> OOS
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, ONLY_B, now=T0 + timedelta(seconds=700))
        assert res["oos"] == 1
        assert any("No longer listed" in x["title"] for x in sent)
        a = (await s.execute(select(Product).where(Product.code == "A"))).scalar_one()
        assert a.current_in_stock is False and a.availability == "oos"
        assert a.available_since is None
        ev = (await s.execute(select(Event))).scalar_one()
        assert ev.kind == "oos" and ev.available_seconds == 700


async def test_delisted_send_failure_is_delivery_safe(sessionmaker_):
    wid = await _delist_watch(sessionmaker_)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, _ = await _run(s, w, ONLY_B, now=T0 + timedelta(seconds=700),
                            sends_ok=False)
        assert res["oos"] == 0
        a = (await s.execute(select(Product).where(Product.code == "A"))).scalar_one()
        assert a.current_in_stock is True   # reverted -> retries next tick
        assert (await s.execute(select(Event))).scalars().all() == []


async def test_product_reappearing_within_grace_resets_clock(sessionmaker_):
    wid = await _delist_watch(sessionmaker_)
    t1 = T0 + timedelta(seconds=301)
    async with sessionmaker_() as s:  # absent once (within grace)
        w = await s.get(Watch, wid)
        await _run(s, w, ONLY_B, now=t1)
    t2 = T0 + timedelta(seconds=650)
    async with sessionmaker_() as s:  # reappears -> no alert, last_seen refreshed
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, BOTH, now=t2)
        assert res["oos"] == 0 and sent == []
        a = (await s.execute(select(Product).where(Product.code == "A"))).scalar_one()
        assert a.current_in_stock is True and a.last_seen == t2


async def test_delisted_then_relisted_fires_restock(sessionmaker_):
    wid = await _delist_watch(sessionmaker_)
    t_oos = T0 + timedelta(seconds=700)
    async with sessionmaker_() as s:  # delisted -> oos
        w = await s.get(Watch, wid)
        await _run(s, w, ONLY_B, now=t_oos)
    async with sessionmaker_() as s:  # relisted in stock -> normal restock alert
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, BOTH, now=t_oos + timedelta(seconds=300))
        assert res["public"] == 1
        assert any("In stock" in x["title"] for x in sent)
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert kinds == ["oos", "public"]


async def test_empty_parse_never_delists(sessionmaker_):
    """A parse returning nothing is indistinguishable from a broken page —
    it must not mass-delist the watch."""
    wid = await _delist_watch(sessionmaker_)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [], now=T0 + timedelta(seconds=700))
        assert res["oos"] == 0 and sent == []
        a = (await s.execute(select(Product).where(Product.code == "A"))).scalar_one()
        assert a.current_in_stock is True


# ---------------------------------------------------------------------------
# Case-insensitive dedup / un-archive / spec_watts (Task 11)
# ---------------------------------------------------------------------------

async def test_recased_code_is_not_a_new_product(sessionmaker_):
    """AO re-casing a product code (A-CIRRO-12K -> A-Cirro-12K) must match the
    existing row, not spawn a duplicate + false new_product alert."""
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    # baseline with UPPER code -> silent baseline
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A-CIRRO-12K", "Meaco 12k", False, "Meaco")])
    # re-cased code on an established watch
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A-Cirro-12K", "Meaco 12k", False, "Meaco")])
    async with sessionmaker_() as s:
        prods = (await s.execute(select(Product))).scalars().all()
        events = (await s.execute(select(Event))).scalars().all()
        assert len(prods) == 1
        assert not any(e.kind == "new_product" for e in events)


async def test_reappearing_product_is_unarchived(sessionmaker_):
    """A product that was archived then reappears in the listing is un-archived."""
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("c", "Panel", False, "")])
    async with sessionmaker_() as s:
        row = (await s.execute(select(Product))).scalars().one()
        row.archived_at = datetime.now(timezone.utc)
        await s.commit()
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("c", "Panel", False, "")])
    async with sessionmaker_() as s:
        row = (await s.execute(select(Product))).scalars().one()
        assert row.archived_at is None


async def test_spec_watts_parsed_from_title(sessionmaker_):
    """spec_watts is derived from the title on create."""
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("c", "Longi 435W Panel", False, "")])
    async with sessionmaker_() as s:
        row = (await s.execute(select(Product))).scalars().one()
        assert row.spec_watts == 435


async def test_lead_time_no_alert_when_unchanged(sessionmaker_):
    from stocktrack.models import Watch
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="", exclude_filter="")
        s.add(w)
        await s.commit()
        wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Panel", True, "", 100.0, delivery="Delivery by Mon 30 Jun (carrier)")])
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0, delivery="Delivery by Mon 30 Jun (carrier)")])
        assert res["lead_time_changes"] == 0
        assert sent == []
