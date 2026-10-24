"""CORS is off unless CORS_DEV_ORIGINS names the dev origins.

In production nginx serves the SPA and proxies /api on the same origin, and
the Vite dev server proxies /api too, so no CORS is needed by default.
"""
from httpx import ASGITransport, AsyncClient

DEV = "http://localhost:5173"


async def _preflight(monkeypatch, value):
    from stocktrack.bootstrap import get_settings
    from stocktrack.main import create_app

    if value is None:
        monkeypatch.delenv("CORS_DEV_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_DEV_ORIGINS", value)
    get_settings.cache_clear()
    try:
        app = create_app()
    finally:
        get_settings.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.options("/api/watches", headers={
            "Origin": DEV, "Access-Control-Request-Method": "POST"})


async def test_no_cors_by_default(monkeypatch):
    r = await _preflight(monkeypatch, None)
    assert "access-control-allow-origin" not in r.headers


async def test_blank_means_no_cors(monkeypatch):
    r = await _preflight(monkeypatch, "  ")
    assert "access-control-allow-origin" not in r.headers


async def test_listed_dev_origins_are_allowed(monkeypatch):
    r = await _preflight(monkeypatch, f"{DEV}, http://127.0.0.1:5173")
    assert r.headers.get("access-control-allow-origin") == DEV
    assert r.headers.get("access-control-allow-credentials") == "true"


async def test_an_unlisted_origin_is_not_allowed(monkeypatch):
    r = await _preflight(monkeypatch, "http://127.0.0.1:5173")
    assert r.headers.get("access-control-allow-origin") != DEV


def test_setting_defaults_to_empty(monkeypatch):
    from stocktrack.bootstrap import Settings
    monkeypatch.delenv("CORS_DEV_ORIGINS", raising=False)
    assert Settings(_env_file=None).cors_dev_origins == ""
