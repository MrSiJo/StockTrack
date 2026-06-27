import pytest
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
