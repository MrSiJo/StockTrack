"""Startup Gotify alert for plugins the loader had to skip."""
import asyncio

from stocktrack import sites
from stocktrack.services import gotify as gotify_service
from stocktrack.services.settings_service import gotify_config


async def plugin_alert(sessionmaker, secret_key, sender=None) -> bool:
    """Push one alert listing every skipped plugin. Returns True if one was sent."""
    skipped = sites.skipped_plugins()
    dir_error = sites.plugin_report().get("plugins_dir_error")
    if not skipped and not dir_error:
        return False
    send = sender or gotify_service.send
    lines = [f"{m['module']}: {m['error']}" for m in skipped]
    if dir_error:
        lines.append(dir_error)
    async with sessionmaker() as session:
        cfg = await gotify_config(session, secret_key)
    # gotify_service.send is blocking: run it off the event loop like the poller.
    ok = await asyncio.to_thread(
        send, cfg, "⚠️ StockTrack skipped a plugin", "\n".join(lines),
        priority=5,
    )
    return bool(ok)
