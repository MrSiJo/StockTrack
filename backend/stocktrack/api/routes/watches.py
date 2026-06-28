import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.deps import get_session
from stocktrack.api.schemas import (
    PreviewProductOut,
    PreviewRequest,
    WatchCreate,
    WatchOut,
    WatchUpdate,
)
from stocktrack.bootstrap import get_settings
from stocktrack.models import Event, Product, Watch
from stocktrack.services import gotify
from stocktrack.services.poller import build_status_summary, check_watch, matches
from stocktrack.services.settings_service import get as get_setting
from stocktrack.services.settings_service import gotify_config
from stocktrack.sites import available, get_handler, supported_kinds

router = APIRouter()


@router.get("/watches", response_model=list[WatchOut])
async def list_watches(session: AsyncSession = Depends(get_session)):
    watches = (await session.execute(select(Watch))).scalars().all()
    return [WatchOut.model_validate(w) for w in watches]


# NOTE: /watches/preview must be registered before /watches/{watch_id}/check
# so the literal path is matched first for POST requests.
@router.post("/watches/preview", response_model=list[PreviewProductOut])
async def preview_watch(
    body: PreviewRequest, session: AsyncSession = Depends(get_session)
):
    if body.store not in available():
        raise HTTPException(status_code=422, detail=f"Unknown store: {body.store!r}")
    try:
        from stocktrack.services.settings_service import store_config_kwargs
        handler = get_handler(body.store, body.kind)
        handler.configure(**await store_config_kwargs(session, handler))
        raw = await asyncio.to_thread(handler.fetch, body.url)
        parsed = handler.parse(raw)
        filtered = [
            p for p in parsed
            if p.code and matches(p, body.include_filter, body.exclude_filter)
        ]
        return [
            PreviewProductOut(
                code=p.code,
                title=p.title,
                brand=p.brand,
                url=p.url,
                in_stock=p.in_stock,
                price=p.price,
                delivery=p.delivery,
                availability=p.availability,
                basket_url=p.basket_url,
            )
            for p in filtered
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/watches/{watch_id}/check")
async def check_watch_now(
    watch_id: int,
    notify: bool = False,
    session: AsyncSession = Depends(get_session),
):
    w = await session.get(Watch, watch_id)
    if w is None:
        raise HTTPException(status_code=404, detail="Watch not found")
    sk = get_settings().app_secret_key
    result = await check_watch(session, w, secret_key=sk)

    notified = False
    if notify:
        products = (
            await session.execute(select(Product).where(Product.watch_id == watch_id))
        ).scalars().all()
        cfg = await gotify_config(session, sk)
        if cfg.get("url") and cfg.get("token"):
            priority = int(await get_setting(session, "gotify_priority", "7") or 7)
            title, message = build_status_summary(w, products)
            try:
                notified = await asyncio.to_thread(
                    gotify.send,
                    cfg,
                    title,
                    message,
                    click_url=w.url or None,
                    markdown=True,
                    priority=priority,
                )
            except Exception:
                notified = False

    return {**result, "notified": notified}


@router.get("/watches/{watch_id}", response_model=WatchOut)
async def get_watch(watch_id: int, session: AsyncSession = Depends(get_session)):
    w = await session.get(Watch, watch_id)
    if w is None:
        raise HTTPException(status_code=404, detail="Watch not found")
    return WatchOut.model_validate(w)


@router.post("/watches", response_model=WatchOut, status_code=201)
async def create_watch(
    body: WatchCreate, session: AsyncSession = Depends(get_session)
):
    if body.store not in available():
        raise HTTPException(status_code=422, detail=f"Unknown store: {body.store!r}")
    if body.kind not in supported_kinds(body.store):
        raise HTTPException(status_code=422,
            detail=f"Store {body.store!r} does not support kind {body.kind!r}")
    w = Watch(**body.model_dump())
    session.add(w)
    await session.commit()
    return WatchOut.model_validate(w)


@router.put("/watches/{watch_id}", response_model=WatchOut)
async def update_watch(
    watch_id: int,
    body: WatchUpdate,
    session: AsyncSession = Depends(get_session),
):
    w = await session.get(Watch, watch_id)
    if w is None:
        raise HTTPException(status_code=404, detail="Watch not found")
    if body.store is not None and body.store not in available():
        raise HTTPException(status_code=422, detail=f"Unknown store: {body.store!r}")
    new_store = body.store if body.store is not None else w.store
    new_kind = body.kind if body.kind is not None else w.kind
    if new_kind not in supported_kinds(new_store):
        raise HTTPException(status_code=422,
            detail=f"Store {new_store!r} does not support kind {new_kind!r}")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(w, field, value)
    await session.commit()
    return WatchOut.model_validate(w)


@router.delete("/watches/{watch_id}", status_code=204)
async def delete_watch(
    watch_id: int, session: AsyncSession = Depends(get_session)
):
    w = await session.get(Watch, watch_id)
    if w is None:
        raise HTTPException(status_code=404, detail="Watch not found")
    products = (await session.execute(
        select(Product).where(Product.watch_id == watch_id)
    )).scalars().all()
    for p in products:
        events = (await session.execute(
            select(Event).where(Event.product_id == p.id)
        )).scalars().all()
        for e in events:
            await session.delete(e)
        await session.delete(p)
    await session.delete(w)
    await session.commit()
