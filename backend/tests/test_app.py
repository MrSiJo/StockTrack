from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
import os

os.environ.setdefault("APP_SECRET_KEY", "t" * 32)

KEY = "t" * 32

async def test_health_endpoint():
    from stocktrack.bootstrap import get_settings
    get_settings.cache_clear()

    mock_session = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("stocktrack.main.make_engine") as mock_engine, \
         patch("stocktrack.main.init_models", new_callable=AsyncMock), \
         patch("stocktrack.main.make_sessionmaker") as mock_sm, \
         patch("stocktrack.main.seed_from_env", new_callable=AsyncMock), \
         patch("stocktrack.main.seed_default_watches", new_callable=AsyncMock), \
         patch("stocktrack.main.AsyncIOScheduler") as mock_sched:

        mock_engine.return_value = MagicMock()
        mock_engine.return_value.dispose = AsyncMock()
        mock_sm.return_value = MagicMock(return_value=mock_session_cm)
        mock_sched.return_value = MagicMock()

        from stocktrack.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}


async def test_poll_tick_records_failure_on_exception(sessionmaker_):
    """check_watch raising still persists consecutive_failures == 1 after rollback."""
    from stocktrack.main import poll_tick
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        w = Watch(store="fake", url="http://x", include_filter="", exclude_filter="", enabled=True)
        s.add(w)
        await s.commit()
        wid = w.id

    with patch("stocktrack.main.check_watch", new_callable=AsyncMock,
               side_effect=RuntimeError("boom")):
        await poll_tick(sessionmaker_, KEY)

    async with sessionmaker_() as s:
        w2 = await s.get(Watch, wid)
        assert w2.consecutive_failures == 1
        assert "boom" in w2.last_error


async def test_poll_tick_skips_watch_deleted_before_check(sessionmaker_):
    """A watch deleted between the tick's snapshot and its re-fetch is skipped,
    and later watches in the same tick still get checked."""
    from stocktrack.main import poll_tick
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        w1 = Watch(store="fake1", url="http://x1", include_filter="", exclude_filter="", enabled=True)
        w2 = Watch(store="fake2", url="http://x2", include_filter="", exclude_filter="", enabled=True)
        s.add_all([w1, w2])
        await s.commit()
        wid2 = w2.id

    checked = []

    async def fake_check(session, watch, secret_key=None):
        checked.append(watch.store)
        # Simulate a concurrent DELETE /api/watches/{wid2} while checking w1
        async with sessionmaker_() as s2:
            other = await s2.get(Watch, wid2)
            if other is not None:
                await s2.delete(other)
                await s2.commit()
        return "ok"

    with patch("stocktrack.main.check_watch", side_effect=fake_check):
        await poll_tick(sessionmaker_, KEY)  # must not raise

    assert checked == ["fake1"]  # w2 was skipped, not crashed on


async def test_poll_tick_survives_watch_deleted_during_failed_check(sessionmaker_):
    """check_watch raising after the watch was deleted mid-flight must not
    abort the tick; remaining watches are still checked."""
    from stocktrack.main import poll_tick
    from stocktrack.models import Watch

    async with sessionmaker_() as s:
        w1 = Watch(store="fake1", url="http://x1", include_filter="", exclude_filter="", enabled=True)
        w2 = Watch(store="fake2", url="http://x2", include_filter="", exclude_filter="", enabled=True)
        s.add_all([w1, w2])
        await s.commit()
        wid1 = w1.id

    checked = []

    async def fake_check(session, watch, secret_key=None):
        checked.append(watch.store)
        if watch.id == wid1:
            # Watch deleted concurrently, then the check itself errors
            async with sessionmaker_() as s2:
                doomed = await s2.get(Watch, wid1)
                await s2.delete(doomed)
                await s2.commit()
            raise RuntimeError("boom")
        return "ok"

    with patch("stocktrack.main.check_watch", side_effect=fake_check):
        await poll_tick(sessionmaker_, KEY)  # must not raise

    assert checked == ["fake1", "fake2"]  # w2 still ran after w1's failure
