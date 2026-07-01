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
    # 2nd poll: still in stock, delivery changed -> lead_time alert
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        res, sent = await _run(s, w, [P("A", "Panel", True, "", 100.0, delivery="Delivery by Thu 2 Jul (branch)")])
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
