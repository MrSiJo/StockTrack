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


async def test_recovery_not_sent_after_single_blip(sessionmaker_):
    """One transient failure (below the alert threshold) must not produce a
    recovery push for a failure the user was never told about."""
    from stocktrack import main
    from stocktrack.models import Watch

    main._failure_alerted.clear()
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="http://x", enabled=True,
                  consecutive_failures=1)
        s.add(w)
        await s.commit()

    with patch("stocktrack.main.check_watch", new_callable=AsyncMock,
               return_value={}), \
         patch("stocktrack.main.gotify.send", return_value=True) as mock_send:
        await main.poll_tick(sessionmaker_, KEY)
    mock_send.assert_not_called()


async def test_recovery_sent_after_alerted_streak(sessionmaker_):
    from stocktrack import main
    from stocktrack.models import Watch

    main._failure_alerted.clear()
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="http://x", enabled=True,
                  consecutive_failures=6)   # >= default threshold of 6
        s.add(w)
        await s.commit()

    with patch("stocktrack.main.check_watch", new_callable=AsyncMock,
               return_value={}), \
         patch("stocktrack.main.gotify.send", return_value=True) as mock_send:
        await main.poll_tick(sessionmaker_, KEY)
    assert mock_send.call_count == 1
    assert "recovered" in mock_send.call_args[0][1]


async def test_failure_alert_fires_once_at_threshold(sessionmaker_):
    from stocktrack import main
    from stocktrack.models import Watch
    from stocktrack.services.settings_service import set_value

    main._failure_alerted.clear()
    async with sessionmaker_() as s:
        await set_value(s, "failure_alert_after", "2")
        w = Watch(store="fake", url="http://x", enabled=True)
        s.add(w)
        await s.commit()
        wid = w.id

    with patch("stocktrack.main.check_watch", new_callable=AsyncMock,
               side_effect=RuntimeError("boom")), \
         patch("stocktrack.main.gotify.send", return_value=True) as mock_send:
        for _ in range(4):     # failures 1..4; threshold 2
            async with sessionmaker_() as s:   # reset the interval gate
                w = await s.get(Watch, wid)
                w.last_checked_at = None
                await s.commit()
            await main.poll_tick(sessionmaker_, KEY)
    assert mock_send.call_count == 1           # at the crossing, not each tick
    assert "can't read" in mock_send.call_args[0][1]


async def test_failure_alert_fires_when_threshold_lowered_mid_streak(sessionmaker_):
    """Count already past a freshly-lowered threshold: >= (not ==) still fires."""
    from stocktrack import main
    from stocktrack.models import Watch
    from stocktrack.services.settings_service import set_value

    main._failure_alerted.clear()
    async with sessionmaker_() as s:
        await set_value(s, "failure_alert_after", "3")
        w = Watch(store="fake", url="http://x", enabled=True,
                  consecutive_failures=4)      # already past the new threshold
        s.add(w)
        await s.commit()

    with patch("stocktrack.main.check_watch", new_callable=AsyncMock,
               side_effect=RuntimeError("boom")), \
         patch("stocktrack.main.gotify.send", return_value=True) as mock_send:
        await main.poll_tick(sessionmaker_, KEY)
    assert mock_send.call_count == 1


async def test_poll_tick_reschedules_on_interval_change(sessionmaker_):
    """default_interval_seconds is DB-owned: a UI change takes effect live."""
    from datetime import timedelta
    from stocktrack.main import poll_tick
    from stocktrack.services.settings_service import set_value

    async with sessionmaker_() as s:
        await set_value(s, "default_interval_seconds", "120")
        await s.commit()

    scheduler = MagicMock()
    scheduler.get_job.return_value = MagicMock(
        trigger=MagicMock(interval=timedelta(seconds=300)))
    await poll_tick(sessionmaker_, KEY, scheduler)
    scheduler.reschedule_job.assert_called_once_with(
        "poll", trigger="interval", seconds=120)


async def test_poll_tick_no_reschedule_when_interval_unchanged(sessionmaker_):
    from datetime import timedelta
    from stocktrack.main import poll_tick
    from stocktrack.services.settings_service import set_value

    async with sessionmaker_() as s:
        await set_value(s, "default_interval_seconds", "300")
        await s.commit()

    scheduler = MagicMock()
    scheduler.get_job.return_value = MagicMock(
        trigger=MagicMock(interval=timedelta(seconds=300)))
    await poll_tick(sessionmaker_, KEY, scheduler)
    scheduler.reschedule_job.assert_not_called()


async def test_poll_tick_skips_recently_checked_watch(sessionmaker_):
    """A watch checked more recently than its interval_seconds is skipped."""
    from datetime import datetime, timedelta, timezone
    from stocktrack.main import poll_tick
    from stocktrack.models import Watch

    now = datetime.now(timezone.utc)
    async with sessionmaker_() as s:
        s.add(Watch(store="fake", url="http://x", interval_seconds=3600,
                    last_checked_at=now - timedelta(seconds=60), enabled=True))
        await s.commit()

    with patch("stocktrack.main.check_watch", new_callable=AsyncMock) as mock_check:
        await poll_tick(sessionmaker_, KEY)
    mock_check.assert_not_awaited()


async def test_poll_tick_checks_stale_and_never_checked_watches(sessionmaker_):
    from datetime import datetime, timedelta, timezone
    from stocktrack.main import poll_tick
    from stocktrack.models import Watch

    now = datetime.now(timezone.utc)
    async with sessionmaker_() as s:
        s.add_all([
            Watch(store="stale", url="http://x", interval_seconds=3600,
                  last_checked_at=now - timedelta(hours=2), enabled=True),
            Watch(store="fresh-run", url="http://y", interval_seconds=300,
                  last_checked_at=None, enabled=True),
        ])
        await s.commit()

    checked = []

    async def fake_check(session, watch, secret_key=None):
        checked.append(watch.store)
        return {}

    with patch("stocktrack.main.check_watch", side_effect=fake_check):
        await poll_tick(sessionmaker_, KEY)
    assert sorted(checked) == ["fresh-run", "stale"]


async def test_poll_tick_failed_watch_retries_next_tick(sessionmaker_):
    """Failures update last_checked_at, but a failing watch keeps retrying at
    the global tick cadence only until its own interval gates it again."""
    from datetime import datetime, timedelta, timezone
    from stocktrack.main import poll_tick
    from stocktrack.models import Watch

    now = datetime.now(timezone.utc)
    async with sessionmaker_() as s:
        w = Watch(store="fake", url="http://x", interval_seconds=60,
                  last_checked_at=now - timedelta(seconds=120), enabled=True)
        s.add(w)
        await s.commit()
        wid = w.id

    with patch("stocktrack.main.check_watch", new_callable=AsyncMock,
               side_effect=RuntimeError("boom")):
        await poll_tick(sessionmaker_, KEY)

    async with sessionmaker_() as s:
        w2 = await s.get(Watch, wid)
        assert w2.consecutive_failures == 1  # was due, got checked, failed


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
