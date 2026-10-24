"""Scoped API tokens: hashed at rest, shown once, read only allowlist."""
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from stocktrack.models import ApiToken, Watch
from stocktrack.services import token_service

FIELDS = {"id", "name", "created_at", "expires_at", "last_used_at", "revoked_at"}


async def _create(client, name="reader", expires_in_days=None):
    r = await client.post("/api/tokens",
                          json={"name": name, "expires_in_days": expires_in_days})
    assert r.status_code == 201, r.text
    return r.json()


async def _watch(sm) -> int:
    async with sm() as s:
        w = Watch(store="ao", url="https://example.com/listing")
        s.add(w)
        await s.commit()
        return w.id


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── management (session + CSRF) ────────────────────────────────────────────

async def test_create_returns_token_once_and_stores_only_its_hash(client, sessionmaker_):
    body = await _create(client)
    assert set(body) == FIELDS | {"token"}
    token = body["token"]
    assert token.startswith("st_")
    assert len(token) >= 3 + 43  # st_ + 32 random bytes, base64url
    assert body["name"] == "reader"
    assert body["expires_at"] is None and body["revoked_at"] is None
    assert body["last_used_at"] is None
    assert body["created_at"].endswith("Z")  # ISO 8601 UTC

    async with sessionmaker_() as s:
        row = (await s.execute(select(ApiToken))).scalar_one()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in {row.name, row.token_hash}


async def test_list_is_metadata_only_newest_first(client):
    first = await _create(client, "first")
    second = await _create(client, "second")
    r = await client.get("/api/tokens")
    assert r.status_code == 200
    rows = r.json()
    assert [t["name"] for t in rows] == ["second", "first"]
    for row in rows:
        assert set(row) == FIELDS
    assert first["token"] not in r.text and second["token"] not in r.text


async def test_duplicate_name_is_409(client):
    await _create(client, "dup")
    r = await client.post("/api/tokens", json={"name": "dup", "expires_in_days": None})
    assert r.status_code == 409


@pytest.mark.parametrize("body", [
    {"name": "", "expires_in_days": None},
    {"name": "x" * 65, "expires_in_days": None},
    {"name": "ok", "expires_in_days": 0},
    {"name": "ok", "expires_in_days": 3651},
])
async def test_create_validates(client, body):
    assert (await client.post("/api/tokens", json=body)).status_code == 422


async def test_expiry_in_days(client):
    body = await _create(client, expires_in_days=30)
    expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    created = datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
    assert abs((expires - created) - timedelta(days=30)) < timedelta(seconds=5)


async def test_revoke_is_idempotent_and_404s_unknown(client):
    tok = await _create(client)
    r1 = await client.post(f"/api/tokens/{tok['id']}/revoke")
    assert r1.status_code == 200
    assert set(r1.json()) == FIELDS
    assert r1.json()["revoked_at"] is not None
    r2 = await client.post(f"/api/tokens/{tok['id']}/revoke")
    assert r2.status_code == 200
    assert r2.json()["revoked_at"] == r1.json()["revoked_at"]
    assert (await client.post("/api/tokens/9999/revoke")).status_code == 404


async def test_management_needs_csrf(client):
    client.headers.pop("X-CSRF-Token")
    r = await client.post("/api/tokens", json={"name": "x", "expires_in_days": None})
    assert r.status_code == 403


async def test_management_needs_a_session(anon_client):
    assert (await anon_client.get("/api/tokens")).status_code == 401


# ── using a token ───────────────────────────────────────────────────────────

async def test_token_reads_each_allowlisted_get(client, anon_client, sessionmaker_):
    tok = (await _create(client))["token"]
    wid = await _watch(sessionmaker_)
    for path in ("/api/watches", f"/api/watches/{wid}/offers",
                 f"/api/watches/{wid}/offer-changes"):
        r = await anon_client.get(path, headers=_bearer(tok))
        assert r.status_code == 200, f"{path} -> {r.status_code}"


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/status"),
    ("GET", "/api/settings"),
    ("GET", "/api/tokens"),
    ("GET", "/api/auth/me"),
    ("GET", "/api/watches/1/offers/extra"),
    ("GET", "/api/watches/abc/offers"),
    ("POST", "/api/watches"),
    ("PUT", "/api/watches/1"),
    ("DELETE", "/api/watches/1"),
    ("PUT", "/api/settings"),
    ("POST", "/api/tokens"),
    ("POST", "/api/auth/logout"),
])
async def test_token_is_403_off_the_allowlist(client, anon_client, method, path):
    tok = (await _create(client))["token"]
    r = await anon_client.request(method, path, headers=_bearer(tok), json={})
    assert r.status_code == 403, f"{method} {path} -> {r.status_code}"


async def test_unknown_revoked_and_expired_tokens_are_401(client, anon_client, sessionmaker_):
    revoked = await _create(client, "revoked")
    await client.post(f"/api/tokens/{revoked['id']}/revoke")
    expired = await _create(client, "expired", expires_in_days=1)
    async with sessionmaker_() as s:
        row = await s.get(ApiToken, expired["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await s.commit()
    for tok in ("st_" + "a" * 43, revoked["token"], expired["token"], "garbage"):
        r = await anon_client.get("/api/watches", headers=_bearer(tok))
        assert r.status_code == 401
        assert r.json() == {"detail": "Authentication required"}


async def test_non_bearer_authorization_is_401(client, anon_client):
    tok = (await _create(client))["token"]
    r = await anon_client.get("/api/watches", headers={"Authorization": f"Basic {tok}"})
    assert r.status_code == 401


async def test_last_used_at_is_touched_at_most_once_a_minute(client, anon_client,
                                                             sessionmaker_):
    tok = await _create(client)

    async def last_used():
        async with sessionmaker_() as s:
            return (await s.get(ApiToken, tok["id"])).last_used_at

    await anon_client.get("/api/watches", headers=_bearer(tok["token"]))
    first = await last_used()
    assert first is not None
    await anon_client.get("/api/watches", headers=_bearer(tok["token"]))
    assert await last_used() == first  # within the minute: no write

    async with sessionmaker_() as s:
        row = await s.get(ApiToken, tok["id"])
        row.last_used_at = first - timedelta(seconds=61)
        await s.commit()
    await anon_client.get("/api/watches", headers=_bearer(tok["token"]))
    assert await last_used() > first - timedelta(seconds=61)


async def test_session_wins_over_bearer_and_keeps_csrf(client):
    """A browser request carrying both is the cookie session: full CSRF applies
    and session only routes work."""
    tok = (await _create(client))["token"]
    me = await client.get("/api/auth/me", headers=_bearer(tok))
    assert me.status_code == 200
    csrf = client.headers.pop("X-CSRF-Token")
    r = await client.post("/api/tokens", headers=_bearer(tok),
                          json={"name": "n2", "expires_in_days": None})
    assert r.status_code == 403
    assert "CSRF" in r.text
    r = await client.post("/api/tokens", headers={**_bearer(tok), "X-CSRF-Token": csrf},
                          json={"name": "n2", "expires_in_days": None})
    assert r.status_code == 201


async def test_token_and_header_never_logged(client, anon_client, caplog):
    tok = await _create(client, "logged-name")
    caplog.set_level(logging.DEBUG)
    await anon_client.get("/api/watches", headers=_bearer(tok["token"]))
    await anon_client.get("/api/status", headers=_bearer(tok["token"]))
    await anon_client.get("/api/watches", headers=_bearer("st_" + "b" * 43))
    assert tok["token"] not in caplog.text
    assert "Bearer" not in caplog.text
    assert "authorization" not in caplog.text.lower()
    assert "logged-name" in caplog.text  # the name is logged, at debug


def test_generated_tokens_are_prefixed_and_unique():
    tokens = {token_service.generate_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(t.startswith("st_") for t in tokens)
