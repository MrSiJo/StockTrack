"""Periodic liveness push so a silent poller stall is noticeable."""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select

from stocktrack.models import Watch
from stocktrack.services import gotify as gotify_service
from stocktrack.services.settings_service import get, gotify_config, set_value

_LAST_KEY = "heartbeat_last_sent"


async def heartbeat_tick(sessionmaker, secret_key, sender=None, now=None) -> bool:
    now = now or datetime.now(timezone.utc)
    send = sender or gotify_service.send
    async with sessionmaker() as session:
        hours = float(await get(session, "heartbeat_hours", "0") or 0)
        if hours <= 0:
            return False
        last_raw = await get(session, _LAST_KEY, "")
        if last_raw:
            last = datetime.fromisoformat(last_raw)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() < hours * 3600:
                return False
        n_watches = (await session.execute(
            select(func.count()).select_from(Watch).where(Watch.enabled.is_(True))
        )).scalar_one()
        last_poll = (await session.execute(
            select(func.max(Watch.last_ok_at))
        )).scalar_one()
        cfg = await gotify_config(session, secret_key)
        stamp = last_poll.strftime("%H:%M") if last_poll else "never"
        priority = int(await get(session, "gotify_priority", "4") or 4)
        title = "\U0001f493 StockTrack alive"
        message = f"{n_watches} watches · last poll {stamp}"
        # gotify_service.send is a blocking (sync) call — run it off the event
        # loop via asyncio.to_thread, matching poller.py / digest.py.
        ok = await asyncio.to_thread(send, cfg, title, message, priority=priority)
        if ok:
            await set_value(session, _LAST_KEY, now.isoformat())
            await session.commit()
        return bool(ok)
