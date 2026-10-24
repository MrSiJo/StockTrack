"""Double submit CSRF: cookie stocktrack_csrf echoed in X-CSRF-Token."""
from stocktrack.api.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

WATCH = {"store": "ao", "url": "https://example.com/listing"}


def _drop_header(client):
    client.headers.pop(CSRF_HEADER_NAME, None)


async def test_mutating_request_without_header_is_403(client):
    _drop_header(client)
    r = await client.post("/api/watches", json=WATCH)
    assert r.status_code == 403
    assert r.json() == {"detail": "CSRF token missing or invalid"}


async def test_mutating_request_with_wrong_header_is_403(client):
    r = await client.post("/api/watches", json=WATCH,
                          headers={CSRF_HEADER_NAME: "not-the-cookie"})
    assert r.status_code == 403


async def test_mutating_request_without_cookie_is_403(client):
    token = client.cookies.get(CSRF_COOKIE_NAME)
    client.cookies.delete(CSRF_COOKIE_NAME)
    r = await client.post("/api/watches", json=WATCH, headers={CSRF_HEADER_NAME: token})
    assert r.status_code == 403


async def test_matching_header_passes(client):
    r = await client.put("/api/settings", json={})
    assert r.status_code != 403


async def test_every_mutating_verb_is_checked(client):
    _drop_header(client)
    for method, path in (("PUT", "/api/settings"), ("PATCH", "/api/watches/1"),
                         ("DELETE", "/api/watches/1"), ("POST", "/api/watches")):
        r = await client.request(method, path, json={})
        assert r.status_code == 403, f"{method} {path} -> {r.status_code}"


async def test_safe_response_sets_cookie_when_absent(anon_client):
    r = await anon_client.get("/api/setup")
    set_cookie = r.headers["set-cookie"]
    assert set_cookie.startswith(f"{CSRF_COOKIE_NAME}=")
    low = set_cookie.lower()
    assert "httponly" not in low  # the SPA must read it to echo it
    assert "samesite=strict" in low
    assert "path=/" in low
    token = anon_client.cookies.get(CSRF_COOKIE_NAME)
    assert token and len(token) >= 43  # 32 random bytes, base64url


async def test_cookie_not_reissued_when_present(anon_client):
    await anon_client.get("/api/setup")
    first = anon_client.cookies.get(CSRF_COOKIE_NAME)
    r = await anon_client.get("/api/setup")
    assert CSRF_COOKIE_NAME not in r.headers.get("set-cookie", "")
    assert anon_client.cookies.get(CSRF_COOKIE_NAME) == first


async def test_cookie_secure_follows_setting(anon_client, monkeypatch, sessionmaker_):
    from httpx import ASGITransport, AsyncClient

    from stocktrack.bootstrap import get_settings
    from stocktrack.main import create_app
    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    app = create_app()
    app.state.sessionmaker = sessionmaker_
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/setup")
    assert "; secure" in r.headers["set-cookie"].lower()


async def test_login_and_setup_need_csrf(anon_client):
    body = {"username": "admin", "password": "very-strong-pass"}
    assert (await anon_client.post("/api/setup", json=body)).status_code == 403
    assert (await anon_client.post("/api/auth/login", json=body)).status_code == 403


async def test_health_exemptions_are_get_only(anon_client, client):
    assert (await anon_client.get("/api/health")).status_code == 200
    # Unauthenticated, a POST on an exempt path is not exempt from auth...
    assert (await anon_client.post("/api/health")).status_code == 401
    # ...and signed in, it is not exempt from CSRF either.
    client.headers.pop("X-CSRF-Token")
    r = await client.post("/api/health")
    assert r.status_code == 403 and "CSRF" in r.text


async def test_unauthenticated_mutation_is_401_before_csrf(anon_client):
    r = await anon_client.post("/api/watches", json=WATCH)
    assert r.status_code == 401
