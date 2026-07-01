from datetime import datetime, timezone

from sqlalchemy import select

from stocktrack.models import Event, Product, Watch
from stocktrack.services.digest import build_digest, digest_tick
from stocktrack.services.settings_service import get as get_setting
from stocktrack.services.settings_service import set_value

KEY = "d" * 32

MONDAY_10 = datetime(2026, 6, 29, 10, 0, 0, tzinfo=timezone.utc)   # Monday
TUESDAY_10 = datetime(2026, 6, 30, 10, 0, 0, tzinfo=timezone.utc)  # Tuesday


def _sender_recording(sent, ok=True):
    def sender(cfg, title, message, click_url=None, markdown=False,
               priority=None, sleep=None):
        sent.append({"title": title, "message": message, "priority": priority})
        return ok
    return sender


async def _seed(sessionmaker_, *, cadence="daily", hour=8, with_event=True):
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="u", label="Dehumidifiers")
        s.add(w)
        await s.commit()
        p1 = Product(watch_id=w.id, store="fake", code="A", title="Meaco 12K",
                     availability="public", current_in_stock=True,
                     current_price=519.0, lowest_price=519.0)
        p2 = Product(watch_id=w.id, store="fake", code="B", title="Meaco 10K",
                     availability="public", current_in_stock=True,
                     current_price=399.0, lowest_price=350.0)
        p3 = Product(watch_id=w.id, store="fake", code="C", title="Meaco 8K",
                     availability="oos", current_in_stock=False)
        s.add_all([p1, p2, p3])
        await s.commit()
        if with_event:
            s.add(Event(product_id=p1.id, kind="public", price=519.0,
                        ts=MONDAY_10.replace(hour=6)))
        await set_value(s, "digest_cadence", cadence)
        await set_value(s, "digest_hour", str(hour))
        await s.commit()


def test_build_digest_lists_cheapest_in_stock_and_changes():
    w = Watch(store="fake", url="u", label="Panels")
    p_cheap = Product(watch_id=1, store="fake", code="B", title="Cheap",
                      availability="public", current_in_stock=True,
                      current_price=100.0, lowest_price=100.0)
    p_dear = Product(watch_id=1, store="fake", code="A", title="Dear",
                     availability="public", current_in_stock=True,
                     current_price=200.0, lowest_price=150.0)
    p_oos = Product(watch_id=1, store="fake", code="C", title="Gone",
                    availability="oos", current_in_stock=False)
    ev = Event(product_id=2, kind="price_drop", price=100.0, ts=MONDAY_10)

    title, message = build_digest([(w, [p_dear, p_cheap, p_oos])],
                                  [(ev, p_cheap)], MONDAY_10)
    assert "2/3 in stock" in title
    lines = message.splitlines()
    assert lines[0] == "**Panels**"
    assert "Cheap" in lines[1] and "🏆" in lines[1]   # cheapest first, at its low
    assert "Dear" in lines[2]
    assert "Gone" not in message.split("**Changes**")[0]
    assert "price drop" in message


async def test_digest_tick_off_by_default(sessionmaker_):
    await _seed(sessionmaker_, cadence="daily")
    async with sessionmaker_() as s:
        await set_value(s, "digest_cadence", "off")
        await s.commit()
    sent = []
    ok = await digest_tick(sessionmaker_, KEY, sender=_sender_recording(sent),
                           now=MONDAY_10)
    assert ok is False and sent == []


async def test_digest_tick_sends_once_per_day(sessionmaker_):
    await _seed(sessionmaker_, cadence="daily", hour=8)
    sent = []
    ok = await digest_tick(sessionmaker_, KEY, sender=_sender_recording(sent),
                           now=MONDAY_10)
    assert ok is True and len(sent) == 1
    assert "digest" in sent[0]["title"]
    async with sessionmaker_() as s:
        assert await get_setting(s, "digest_last_sent") == "2026-06-29"
    # second tick the same day: no re-send
    ok = await digest_tick(sessionmaker_, KEY, sender=_sender_recording(sent),
                           now=MONDAY_10.replace(hour=12))
    assert ok is False and len(sent) == 1


async def test_digest_tick_respects_hour(sessionmaker_):
    await _seed(sessionmaker_, cadence="daily", hour=8)
    sent = []
    ok = await digest_tick(sessionmaker_, KEY, sender=_sender_recording(sent),
                           now=MONDAY_10.replace(hour=6))
    assert ok is False and sent == []


async def test_digest_weekly_only_monday(sessionmaker_):
    await _seed(sessionmaker_, cadence="weekly", hour=8)
    sent = []
    ok = await digest_tick(sessionmaker_, KEY, sender=_sender_recording(sent),
                           now=TUESDAY_10)
    assert ok is False and sent == []
    ok = await digest_tick(sessionmaker_, KEY, sender=_sender_recording(sent),
                           now=MONDAY_10)
    assert ok is True and len(sent) == 1


async def test_failed_digest_send_keeps_marker(sessionmaker_):
    await _seed(sessionmaker_, cadence="daily", hour=8)
    sent = []
    ok = await digest_tick(sessionmaker_, KEY,
                           sender=_sender_recording(sent, ok=False),
                           now=MONDAY_10)
    assert ok is False
    async with sessionmaker_() as s:
        assert await get_setting(s, "digest_last_sent") in (None, "")
    # retry succeeds and sets the marker
    ok = await digest_tick(sessionmaker_, KEY, sender=_sender_recording(sent),
                           now=MONDAY_10.replace(hour=11))
    assert ok is True
