import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from sqlalchemy import select

from stocktrack.bootstrap import get_settings
from stocktrack.db import init_models, make_engine, make_sessionmaker
from stocktrack.models import Watch
from stocktrack.seed import seed_default_watches
from stocktrack.services import gotify
from stocktrack.services.poller import check_watch
from stocktrack.services.settings_service import get as get_setting, gotify_config, seed_from_env

log = logging.getLogger("stocktrack")


async def poll_tick(sessionmaker, secret_key: str) -> None:
    async with sessionmaker() as s:
        watches = (await s.execute(
            select(Watch).where(Watch.enabled.is_(True)))).scalars().all()
    for w in watches:
        async with sessionmaker() as s:
            watch = await s.get(Watch, w.id)
            prev_failures = watch.consecutive_failures
            try:
                res = await check_watch(s, watch, secret_key=secret_key)
                log.info("[%s] %s", watch.store, res)
                if prev_failures:
                    cfg = await gotify_config(s, secret_key)
                    ok = await asyncio.to_thread(
                        gotify.send, cfg,
                        f"✅ stock-watch recovered ({watch.store})",
                        f"Reading {watch.store} again.",
                        priority=2,
                    )
                    if not ok:
                        log.warning("Gotify recovery notification failed for %s", watch.store)
            except Exception as e:
                await s.rollback()
                watch = await s.get(Watch, w.id)
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                watch.consecutive_failures = prev_failures + 1
                watch.last_checked_at = now
                watch.last_error = repr(e)[:500]
                threshold = int(await get_setting(s, "failure_alert_after", "6") or 6)
                if watch.consecutive_failures == threshold:
                    cfg = await gotify_config(s, secret_key)
                    ok = await asyncio.to_thread(
                        gotify.send, cfg,
                        f"⚠️ stock-watch can't read {watch.store}",
                        f"{watch.consecutive_failures} checks failed in a row. Last error: {e}",
                        priority=5,
                    )
                    if not ok:
                        log.warning("Gotify failure alert delivery failed for %s", watch.store)
                await s.commit()
                log.warning("[%s] check failed (%d): %r", watch.store, watch.consecutive_failures, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    env = get_settings()
    engine = make_engine(env.database_url)
    await init_models(engine)
    sm = make_sessionmaker(engine)
    async with sm() as s:
        await seed_from_env(s, env, env.app_secret_key)
        await seed_default_watches(s)
        await s.commit()

    scheduler = AsyncIOScheduler(timezone=env.tz)
    scheduler.add_job(poll_tick, "interval",
                      seconds=env.default_interval_seconds,
                      args=[sm, env.app_secret_key], id="poll", max_instances=1)
    scheduler.start()

    app.state.engine = engine
    app.state.sessionmaker = sm
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await engine.dispose()


def create_app() -> FastAPI:
    from fastapi.middleware.cors import CORSMiddleware
    from stocktrack.api.routes.events import router as events_router
    from stocktrack.api.routes.history import router as history_router
    from stocktrack.api.routes.settings import router as settings_router
    from stocktrack.api.routes.status import router as status_router
    from stocktrack.api.routes.stores import router as stores_router
    from stocktrack.api.routes.watches import router as watches_router

    app = FastAPI(title="StockTrack", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    app.include_router(status_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(stores_router, prefix="/api")
    app.include_router(watches_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")

    return app
