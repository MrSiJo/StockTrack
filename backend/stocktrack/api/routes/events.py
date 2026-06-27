from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.deps import get_session
from stocktrack.api.schemas import EventOut
from stocktrack.models import Event, Product

router = APIRouter()


@router.get("/events", response_model=list[EventOut])
async def get_events(
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(
        select(Event, Product)
        .join(Product, Event.product_id == Product.id)
        .order_by(Event.ts.desc())
        .limit(limit)
    )).all()
    return [
        EventOut(
            id=event.id,
            ts=event.ts,
            kind=event.kind,
            price=event.price,
            available_seconds=event.available_seconds,
            product_title=product.title,
            store=product.store,
            url=product.url,
            basket_url=product.basket_url,
        )
        for event, product in rows
    ]
