import os
from unittest.mock import patch

os.environ.setdefault("APP_SECRET_KEY", "t" * 32)

KEY = "t" * 32


# ── GET /api/settings ──────────────────────────────────────────────────────

async def test_settings_get_defaults(client):
    """GET with empty DB returns defaults; shape is correct."""
    resp = await client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "gotify_url" in data
    assert "gotify_token_set" in data
    assert isinstance(data["gotify_token_set"], bool)
    # Token must NOT be present in the response
    assert "gotify_token" not in data


async def test_settings_get_masks_token(client, sessionmaker_):
    """gotify_token_set is True when a token is stored; value is never returned."""
    from stocktrack.services.settings_service import set_value

    async with sessionmaker_() as s:
        await set_value(s, "gotify_token", "super-secret-token",
                        is_secret=True, secret_key=KEY)
        await s.commit()

    resp = await client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["gotify_token_set"] is True
    assert "gotify_token" not in data
    # The raw token must not appear anywhere in the response body
    assert "super-secret-token" not in resp.text


async def test_settings_get_token_set_false_when_no_token(client):
    resp = await client.get("/api/settings")
    data = resp.json()
    assert data["gotify_token_set"] is False


# ── PUT /api/settings ──────────────────────────────────────────────────────

async def test_settings_put_updates_plain_fields(client):
    resp = await client.put("/api/settings", json={
        "gotify_url": "http://gotify.lan",
        "gotify_priority": 9,
        "default_interval_seconds": 120,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["gotify_url"] == "http://gotify.lan"
    assert data["gotify_priority"] == 9
    assert data["default_interval_seconds"] == 120


async def test_settings_put_encrypts_token_when_provided(client, sessionmaker_):
    """Storing a token encrypts it; subsequent GET shows token_set=True."""
    resp = await client.put("/api/settings", json={"gotify_token": "my-secret"})
    assert resp.status_code == 200
    # GET confirms token is set
    get_resp = await client.get("/api/settings")
    assert get_resp.json()["gotify_token_set"] is True
    # Verify it is stored encrypted (not plaintext) in the DB
    from stocktrack.models.setting import Setting

    async with sessionmaker_() as s:
        row = await s.get(Setting, "gotify_token")
    assert row is not None
    assert row.value != "my-secret"     # must be ciphertext
    assert row.is_secret is True


async def test_settings_put_leaves_token_untouched_when_omitted(client, sessionmaker_):
    """Omitting gotify_token from PUT body must not clear an existing token."""
    from stocktrack.services.settings_service import get_secret, set_value

    async with sessionmaker_() as s:
        await set_value(s, "gotify_token", "original-token",
                        is_secret=True, secret_key=KEY)
        await s.commit()

    # PUT without gotify_token key
    await client.put("/api/settings", json={"gotify_url": "http://gotify.lan"})

    # Token still decryptable
    async with sessionmaker_() as s:
        stored = await get_secret(s, "gotify_token", KEY)
    assert stored == "original-token"


async def test_settings_put_leaves_token_untouched_when_empty_string(client, sessionmaker_):
    """gotify_token="" in PUT body must not clear an existing token."""
    from stocktrack.services.settings_service import get_secret, set_value

    async with sessionmaker_() as s:
        await set_value(s, "gotify_token", "original-token",
                        is_secret=True, secret_key=KEY)
        await s.commit()

    await client.put("/api/settings", json={"gotify_token": ""})

    async with sessionmaker_() as s:
        stored = await get_secret(s, "gotify_token", KEY)
    assert stored == "original-token"


# ── POST /api/settings/test ────────────────────────────────────────────────

async def test_settings_test_returns_delivered_true(client):
    with patch("stocktrack.api.routes.settings.gotify.send", return_value=True):
        resp = await client.post("/api/settings/test")
    assert resp.status_code == 200
    assert resp.json() == {"delivered": True}


async def test_settings_test_returns_delivered_false(client):
    with patch("stocktrack.api.routes.settings.gotify.send", return_value=False):
        resp = await client.post("/api/settings/test")
    assert resp.status_code == 200
    assert resp.json() == {"delivered": False}


async def test_settings_ao_member_and_price_drop_roundtrip(client):
    r = await client.put("/api/settings", json={
        "ao_member": True, "price_drop_min_pct": 8,
        "price_drop_min_abs": 10, "price_drop_priority": 7,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ao_member"] is True
    assert body["price_drop_min_pct"] == 8
    assert body["price_drop_min_abs"] == 10
    assert body["price_drop_priority"] == 7
