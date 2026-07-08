from datetime import datetime, timedelta, timezone
from stocktrack.services.settings_service import set_value
from stocktrack.services.heartbeat import heartbeat_tick

async def test_heartbeat_respects_interval(sessionmaker_):
    sent = []
    def fake_send(cfg, title, message, **kw):
        sent.append((title, message, kw.get("priority")))
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
    # liveness pings are low priority — must not interrupt like a restock alert
    assert all(priority == 2 for _title, _message, priority in sent)


async def test_heartbeat_message_includes_date(sessionmaker_):
    """T8: a stale last-poll from days ago must show its date, not just a
    time, or it misleadingly reads as recent."""
    from stocktrack.models import Watch
    sent = []
    def fake_send(cfg, title, message, **kw):
        sent.append(message)
        return True
    async with sessionmaker_() as s:
        s.add(Watch(store="ao", url="http://x", label="w", enabled=True,
                     last_ok_at=datetime(2026, 6, 30, 9, 15, tzinfo=timezone.utc)))
        await set_value(s, "heartbeat_hours", "24")
        await set_value(s, "gotify_url", "http://x")
        await s.commit()
    now = datetime(2026, 7, 8, 6, 0, tzinfo=timezone.utc)
    assert await heartbeat_tick(lambda: sessionmaker_(), "k"*32, sender=fake_send, now=now) is True
    assert len(sent) == 1
    assert "2026-06-30 09:15" in sent[0]

async def test_heartbeat_disabled_when_zero(sessionmaker_):
    def fake_send(*a, **k):  # pragma: no cover
        raise AssertionError("should not send")
    async with sessionmaker_() as s:
        await set_value(s, "heartbeat_hours", "0")
        await s.commit()
    assert await heartbeat_tick(lambda: sessionmaker_(), "k"*32, sender=fake_send) is False
