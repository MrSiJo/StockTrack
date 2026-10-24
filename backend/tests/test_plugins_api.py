"""GET /api/plugins, GET /api/health/plugins and the startup plugin alert."""
import pytest

from stocktrack import sites
from stocktrack.services.plugin_alert import plugin_alert
from stocktrack.services.settings_service import set_value


@pytest.fixture
def broken_plugin(tmp_path):
    (tmp_path / "bad.py").write_text("raise RuntimeError('boom')", encoding="utf-8")
    sites.load_registry(tmp_path)
    yield
    sites.load_registry(None)


async def test_plugins_endpoint_lists_builtins(client):
    resp = await client.get("/api/plugins")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plugin_api"] == sites.PLUGIN_API
    assert body["plugins_dir"] is False
    by = {m["module"]: m for m in body["modules"]}
    assert by["ao"]["handlers"] == ["ao/listing", "ao/product"]
    assert by["ao"]["source"] == "builtin" and by["ao"]["status"] == "loaded"


async def test_plugin_health_ok(client):
    resp = await client.get("/api/health/plugins")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "skipped": []}


async def test_plugin_health_503_names_only_the_skipped_modules(anon_client, broken_plugin):
    """Unauthenticated, so module names only: no error text, source or paths."""
    resp = await anon_client.get("/api/health/plugins")
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "skipped": ["bad"]}
    assert "boom" not in resp.text


async def test_plugin_health_503_on_a_plugins_dir_error_without_the_path(anon_client, tmp_path):
    missing = tmp_path / "secret-location"
    try:
        sites.load_registry(missing)
        resp = await anon_client.get("/api/health/plugins")
    finally:
        sites.load_registry(None)
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "skipped": []}
    assert "secret-location" not in resp.text


async def test_plugins_endpoint_keeps_the_full_detail(client, broken_plugin):
    """The authenticated report is where the error text lives."""
    resp = await client.get("/api/plugins")
    assert resp.status_code == 200
    by = {m["module"]: m for m in resp.json()["modules"]}
    assert by["bad"]["status"] == "skipped"
    assert by["bad"]["source"] == "plugin"
    assert "boom" in by["bad"]["error"]


async def test_plugins_endpoint_keeps_the_dir_error(client, tmp_path):
    try:
        sites.load_registry(tmp_path / "nope")
        resp = await client.get("/api/plugins")
    finally:
        sites.load_registry(None)
    assert resp.status_code == 200
    assert "nope" in resp.json()["plugins_dir_error"]


async def test_plugins_endpoint_needs_a_session(anon_client):
    assert (await anon_client.get("/api/plugins")).status_code == 401


async def test_plugin_alert_sends_once_per_startup(sessionmaker_, broken_plugin):
    sent = []

    def fake_send(cfg, title, message, **kw):
        sent.append((title, message, kw.get("priority")))
        return True

    async with sessionmaker_() as s:
        await set_value(s, "gotify_url", "http://x")
        await s.commit()
    assert await plugin_alert(sessionmaker_, "k" * 32, sender=fake_send) is True
    title, message, priority = sent[0]
    assert "plugin" in title.lower()
    assert "bad" in message and "boom" in message
    assert priority == 5


async def test_plugin_alert_silent_when_all_loaded(sessionmaker_):
    sent = []
    assert await plugin_alert(sessionmaker_, "k" * 32,
                              sender=lambda *a, **k: sent.append(a)) is False
    assert sent == []
