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
        s.add(w); await s.commit(); wid = w.id

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


async def test_failed_public_send_does_not_advance_state(sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco", exclude_filter="")
        s.add(w); await s.commit(); wid = w.id
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", True, "Meaco", 519.0)], sends_ok=False)
        p = (await s.execute(select(Product))).scalar_one()
        assert p.current_in_stock is False  # not advanced
        assert p.available_since is None


async def test_early_to_public_sequence(sessionmaker_):
    """oos -> early -> public -> oos, checking event kinds and available_seconds."""
    from datetime import timedelta
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", include_filter="Meaco", exclude_filter="")
        s.add(w); await s.commit(); wid = w.id

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
        s.add(w); await s.commit(); wid = w.id
    t = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)
    async with sessionmaker_() as s:
        w = await s.get(Watch, wid)
        await _run(s, w, [P("A", "Meaco 12K", False, "Meaco")], now=t)
        w2 = await s.get(Watch, wid)
        assert w2.last_ok_at == t
        assert w2.consecutive_failures == 0
