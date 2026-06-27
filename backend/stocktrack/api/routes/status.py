from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.deps import get_session
from stocktrack.api.schemas import ProductOut, WatchStatusOut
from stocktrack.models import Product, Watch

router = APIRouter()


@router.get("/status", response_model=list[WatchStatusOut])
async def get_status(session: AsyncSession = Depends(get_session)):
    watches = (await session.execute(select(Watch))).scalars().all()
    result = []
    for w in watches:
        products = (await session.execute(
            select(Product).where(Product.watch_id == w.id)
        )).scalars().all()
        result.append(WatchStatusOut(
            id=w.id,
            store=w.store,
            url=w.url,
            label=w.label,
            enabled=w.enabled,
            last_checked_at=w.last_checked_at,
            last_ok_at=w.last_ok_at,
            consecutive_failures=w.consecutive_failures,
            last_error=w.last_error,
            products=[ProductOut.model_validate(p) for p in products],
        ))
    return result
