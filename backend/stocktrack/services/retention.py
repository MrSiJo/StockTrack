"""Event retention sweep.

Deletes event rows older than ``event_retention_days`` while preserving
episode boundaries: any episode that is still ongoing, or that ended inside
the retention window, keeps all of its events (from its opening
``early_access``/``public`` onwards) so History reconstruction is unchanged.
Closed episodes age out wholesale once their end falls outside the window.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from stocktrack.models import Event
from stocktrack.services.history import build_episodes
from stocktrack.services.settings_service import get as get_setting

log = logging.getLogger(__name__)


async def prune_old_events(session, retention_days: int, now=None) -> int:
    """Delete events older than ``retention_days``. Returns rows deleted.

    Events newer than the start of any protected episode (ongoing, or ended
    within the window) are kept regardless of age — deleting an ongoing
    episode's opening event would make the episode vanish from History.
    ``retention_days <= 0`` disables pruning.
    """
    if retention_days <= 0:
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)

    events = (await session.execute(select(Event))).scalars().all()
    by_product: dict[int, list[Event]] = {}
    for e in events:
        by_product.setdefault(e.product_id, []).append(e)

    doomed: list[int] = []
    for evs in by_product.values():
        episodes = build_episodes(evs, now)
        protected_starts = [ep.started_ts for ep in episodes
                            if ep.ongoing
                            or (ep.ended_ts is not None and ep.ended_ts >= cutoff)]
        boundary = min(protected_starts) if protected_starts else None
        for e in evs:
            if e.ts >= cutoff:
                continue
            if boundary is not None and e.ts >= boundary:
                continue
            doomed.append(e.id)

    if doomed:
        await session.execute(delete(Event).where(Event.id.in_(doomed)))
    return len(doomed)


async def retention_tick(sessionmaker) -> None:
    """Scheduler entry point: prune per the DB-owned retention setting."""
    async with sessionmaker() as s:
        days = int(await get_setting(s, "event_retention_days", "0") or 0)
        if days <= 0:
            return
        n = await prune_old_events(s, days)
        await s.commit()
        if n:
            log.info("retention sweep deleted %d events older than %dd", n, days)
