"""Offers read API: a watch's products grouped by variant, and how they moved."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.deps import get_session
from stocktrack.models import Product, Watch
from stocktrack.services.offers import (
    group_offers,
    recent_changes,
    summarise_changes,
    window_start,
)

router = APIRouter()


async def _watch_products(session: AsyncSession, watch_id: int):
    w = await session.get(Watch, watch_id)
    if w is None:
        raise HTTPException(status_code=404, detail="Watch not found")
    products = (await session.execute(
        select(Product).where(Product.watch_id == watch_id))).scalars().all()
    return w, products


@router.get("/watches/{watch_id}/offers")
async def watch_offers(
    watch_id: int,
    variant: Optional[str] = None,
    min_rating: Optional[float] = None,
    session: AsyncSession = Depends(get_session),
):
    w, products = await _watch_products(session, watch_id)
    return {"watch_id": w.id, "checked_at": w.last_ok_at,
            "variants": group_offers(products, variant=variant,
                                     min_rating=min_rating)}


@router.get("/watches/{watch_id}/offer-changes")
async def watch_offer_changes(
    watch_id: int,
    days: int = Query(14, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    w, products = await _watch_products(session, watch_id)
    since = window_start(days)
    changes = await recent_changes(session, [p.id for p in products], since)
    return {"watch_id": w.id, "days": days, "since": since,
            "variants": summarise_changes(products, changes)}
