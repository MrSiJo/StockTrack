from fastapi import APIRouter
from fastapi.responses import JSONResponse

from stocktrack.api.schemas import PluginReportOut
from stocktrack.sites import plugin_report, skipped_plugins

router = APIRouter()


@router.get("/plugins", response_model=PluginReportOut)
async def get_plugins():
    return plugin_report()


# Deploy gate: 503 while any plugin (or the plugins dir) failed to load.
# Unauthenticated, so it says only which modules were skipped: the error
# text, sources and the plugins dir path stay on the authenticated
# /api/plugins (and in the startup Gotify alert).
@router.get("/health/plugins")
async def plugin_health():
    skipped = [m["module"] for m in skipped_plugins()]
    if skipped or plugin_report().get("plugins_dir_error"):
        return JSONResponse(status_code=503,
                            content={"status": "degraded", "skipped": skipped})
    return {"status": "ok", "skipped": []}
