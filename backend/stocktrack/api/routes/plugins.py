from fastapi import APIRouter
from fastapi.responses import JSONResponse

from stocktrack.api.schemas import PluginReportOut
from stocktrack.sites import plugin_report, skipped_plugins

router = APIRouter()


@router.get("/plugins", response_model=PluginReportOut)
async def get_plugins():
    return plugin_report()


# Deploy gate: 503 while any plugin (or the plugins dir) failed to load.
@router.get("/health/plugins")
async def plugin_health():
    skipped = skipped_plugins()
    dir_error = plugin_report().get("plugins_dir_error")
    if dir_error:
        skipped = [*skipped, {"module": None, "error": dir_error}]
    if skipped:
        return JSONResponse(status_code=503,
                            content={"status": "degraded", "skipped": skipped})
    return {"status": "ok", "skipped": []}
