from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.deps import get_session
from stocktrack.api.schemas import ProductHistoryOut
from stocktrack.models import Event, Product
from stocktrack.services.history import build_history

router = APIRouter()


@router.get("/history", response_model=list[ProductHistoryOut])
async def get_history(
    store: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    products = (await session.execute(select(Product))).scalars().all()
    events = (await session.execute(
        select(Event).order_by(Event.ts.asc()))).scalars().all()
    by_product: dict[int, list] = {}
    for e in events:
        by_product.setdefault(e.product_id, []).append(e)
    pairs = [(p, by_product.get(p.id, [])) for p in products]
    return build_history(pairs, now=datetime.now(timezone.utc), store=store)
