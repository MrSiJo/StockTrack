from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from stocktrack.models import Event, Product, Watch
from stocktrack.services.retention import prune_old_events, retention_tick

NOW = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)


async def _product(session) -> int:
    w = Watch(store="fake", url="u")
    session.add(w)
    await session.flush()
    p = Product(watch_id=w.id, store="fake", code="A")
    session.add(p)
    await session.commit()
    return p.id


def _ev(pid, kind, days_ago, **kw):
    return Event(product_id=pid, kind=kind, ts=NOW - timedelta(days=days_ago), **kw)


async def test_old_closed_episode_is_pruned(sessionmaker_):
    async with sessionmaker_() as s:
        pid = await _product(s)
        s.add_all([
            _ev(pid, "public", 100),
            _ev(pid, "oos", 95, available_seconds=5 * 86400),
            _ev(pid, "public", 10),          # recent episode, ongoing
        ])
        await s.commit()
        n = await prune_old_events(s, 30, now=NOW)
        await s.commit()
        assert n == 2
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert kinds == ["public"]


async def test_ongoing_episode_opening_event_is_protected(sessionmaker_):
    """An episode opened before the cutoff but still ongoing must keep its
    opening event, or it would vanish from History."""
    async with sessionmaker_() as s:
        pid = await _product(s)
        s.add_all([_ev(pid, "public", 100)])   # in stock for 100 days, no oos
        await s.commit()
        n = await prune_old_events(s, 30, now=NOW)
        assert n == 0


async def test_episode_ending_inside_window_keeps_boundary(sessionmaker_):
    """Opened before the cutoff, closed after it: both boundary events stay."""
    async with sessionmaker_() as s:
        pid = await _product(s)
        s.add_all([
            _ev(pid, "public", 100),
            _ev(pid, "oos", 5),
        ])
        await s.commit()
        n = await prune_old_events(s, 30, now=NOW)
        assert n == 0
        kinds = [e.kind for e in (await s.execute(select(Event))).scalars().all()]
        assert sorted(kinds) == ["oos", "public"]


async def test_old_price_events_outside_episodes_are_pruned(sessionmaker_):
    async with sessionmaker_() as s:
        pid = await _product(s)
        s.add_all([
            _ev(pid, "price_drop", 60, price=90.0),
            _ev(pid, "price_drop", 3, price=80.0),
        ])
        await s.commit()
        n = await prune_old_events(s, 30, now=NOW)
        await s.commit()
        assert n == 1
        ev = (await s.execute(select(Event))).scalar_one()
        assert ev.price == 80.0


async def test_retention_zero_is_a_noop(sessionmaker_):
    async with sessionmaker_() as s:
        pid = await _product(s)
        s.add_all([_ev(pid, "public", 400), _ev(pid, "oos", 399)])
        await s.commit()
        assert await prune_old_events(s, 0, now=NOW) == 0
        assert len((await s.execute(select(Event))).scalars().all()) == 2


async def test_retention_tick_reads_db_setting(sessionmaker_):
    from stocktrack.services.settings_service import set_value
    async with sessionmaker_() as s:
        pid = await _product(s)
        s.add_all([
            _ev(pid, "public", 100),
            _ev(pid, "oos", 95),
        ])
        await set_value(s, "event_retention_days", "30")
        await s.commit()
    await retention_tick(sessionmaker_)
    async with sessionmaker_() as s:
        assert (await s.execute(select(Event))).scalars().all() == []
