"""Soft-archive products that have been absent from their listing."""
from datetime import datetime, timezone

from sqlalchemy import select

from stocktrack.models import Product


async def archive_stale_products(session, days: int, now=None) -> int:
    """Set ``archived_at`` on active, OOS products unseen for ``days`` days.

    Returns the number of products archived. ``days <= 0`` disables archiving.
    """
    if days <= 0:
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff = now.timestamp() - days * 86400
    rows = (await session.execute(
        select(Product).where(Product.archived_at.is_(None))
    )).scalars().all()
    count = 0
    for p in rows:
        if p.current_in_stock:
            continue
        last = p.last_seen
        if last is None:
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last.timestamp() < cutoff:
            p.archived_at = now
            count += 1
    return count


async def archival_tick(sessionmaker) -> None:
    """Scheduler entry point: read the setting and archive."""
    from stocktrack.services.settings_service import get
    async with sessionmaker() as session:
        days = int(await get(session, "product_archive_days", "14") or 14)
        await archive_stale_products(session, days)
        await session.commit()
