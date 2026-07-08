from datetime import datetime, timedelta, timezone
from stocktrack.services.settings_service import set_value
from stocktrack.services.heartbeat import heartbeat_tick

async def test_heartbeat_respects_interval(sessionmaker_):
    sent = []
    def fake_send(cfg, title, message, **kw):
        sent.append((title, message))
        return True
    now = datetime(2026, 7, 8, 6, 0, tzinfo=timezone.utc)
    async with sessionmaker_() as s:
        await set_value(s, "heartbeat_hours", "24")
        await set_value(s, "gotify_url", "http://x")
        await s.commit()
        # first call: no prior heartbeat -> sends
        assert await heartbeat_tick(lambda: sessionmaker_(), "k"*32, sender=fake_send, now=now) is True
        # 1h later: within window -> no send
        soon = now + timedelta(hours=1)
        assert await heartbeat_tick(lambda: sessionmaker_(), "k"*32, sender=fake_send, now=soon) is False
        # 25h later: sends again
        later = now + timedelta(hours=25)
        assert await heartbeat_tick(lambda: sessionmaker_(), "k"*32, sender=fake_send, now=later) is True
    assert len(sent) == 2

async def test_heartbeat_disabled_when_zero(sessionmaker_):
    def fake_send(*a, **k):  # pragma: no cover
        raise AssertionError("should not send")
    async with sessionmaker_() as s:
        await set_value(s, "heartbeat_hours", "0")
        await s.commit()
    assert await heartbeat_tick(lambda: sessionmaker_(), "k"*32, sender=fake_send) is False
