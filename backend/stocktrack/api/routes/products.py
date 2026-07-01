from datetime import timedelta, timezone, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.deps import get_session
from stocktrack.api.schemas import MuteIn, PricePointOut, ProductOut
from stocktrack.models import Event, Product

router = APIRouter()


async def _get_product(session: AsyncSession, product_id: int) -> Product:
    p = await session.get(Product, product_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


@router.post("/products/{product_id}/mute", response_model=ProductOut)
async def mute_product(
    product_id: int, body: MuteIn, session: AsyncSession = Depends(get_session)
):
    p = await _get_product(session, product_id)
    p.muted_until = datetime.now(timezone.utc) + timedelta(hours=body.hours)
    await session.commit()
    return ProductOut.model_validate(p)


@router.delete("/products/{product_id}/mute", response_model=ProductOut)
async def unmute_product(
    product_id: int, session: AsyncSession = Depends(get_session)
):
    p = await _get_product(session, product_id)
    p.muted_until = None
    await session.commit()
    return ProductOut.model_validate(p)


@router.get("/products/{product_id}/price-history",
            response_model=list[PricePointOut])
async def price_history(
    product_id: int, session: AsyncSession = Depends(get_session)
):
    await _get_product(session, product_id)
    events = (await session.execute(
        select(Event)
        .where(Event.product_id == product_id, Event.price.is_not(None))
        .order_by(Event.ts.asc(), Event.id.asc())
    )).scalars().all()
    return [PricePointOut(ts=e.ts, kind=e.kind, price=e.price) for e in events]
