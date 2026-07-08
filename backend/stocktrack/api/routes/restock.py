from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.deps import get_session
from stocktrack.api.schemas import RestockPatternOut
from stocktrack.models import Event, Product, Watch
from stocktrack.services.history import restock_pattern

router = APIRouter()


@router.get("/restock-patterns", response_model=list[RestockPatternOut])
async def get_restock_patterns(session: AsyncSession = Depends(get_session)):
    watches = (await session.execute(select(Watch))).scalars().all()
    pid_to_watch = {
        p.id: p.watch_id
        for p in (await session.execute(select(Product))).scalars().all()
    }
    events_by_watch: dict[int, list[Event]] = {}
    for e in (await session.execute(select(Event))).scalars().all():
        wid = pid_to_watch.get(e.product_id)
        if wid is not None:
            events_by_watch.setdefault(wid, []).append(e)
    out = []
    for w in watches:
        pat = restock_pattern(events_by_watch.get(w.id, []))
        out.append(RestockPatternOut(
            watch_id=w.id, store=w.store, label=w.label, **pat))
    return out
