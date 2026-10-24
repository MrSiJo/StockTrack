"""Login, logout, /api/auth/me and the session middleware."""
from unittest.mock import patch

import pytest
from sqlalchemy import delete

from stocktrack.api import auth_middleware
from stocktrack.api.auth_middleware import SESSION_COOKIE_NAME, make_serializer
from stocktrack.api.login_throttle import login_throttle
from stocktrack.models import User
from stocktrack.services.auth_service import bootstrap_user
from tests.conftest import csrf_headers

PW = "very-strong-pass"
KEY = "t" * 32


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """The throttle is a process local singleton: isolate it per test."""
    login_throttle.clear()
    yield
    login_throttle.clear()


async def _make_user(sm, username="admin"):
    async with sm() as s:
        return (await bootstrap_user(s, username, PW)).id


async def _nonce(sm, uid):
    async with sm() as s:
        return (await s.get(User, uid)).session_nonce


async def _cookie(sm, uid, key=KEY):
    """A validly signed session cookie for ``uid`` in the current format."""
    return make_serializer(key).dumps({"user_id": uid, "nonce": await _nonce(sm, uid)})


async def _login(c, username="admin", password=PW):
    await c.get("/api/setup")  # primes the CSRF cookie
    return await c.post("/api/auth/login",
                        json={"username": username, "password": password},
                        headers=csrf_headers(c))


async def test_unauthenticated_api_is_401(anon_client):
    r = await anon_client.get("/api/watches")
    assert r.status_code == 401
    assert r.json() == {"detail": "Authentication required"}


async def test_login_sets_session_cookie_and_authenticates(anon_client, sessionmaker_):
    uid = await _make_user(sessionmaker_)
    r = await _login(anon_client)
    assert r.status_code == 200, r.text
    assert r.json() == {"user_id": uid, "username": "admin"}
    set_cookie = r.headers["set-cookie"].lower()
    assert SESSION_COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "max-age=604800" in set_cookie
    assert "path=/" in set_cookie
    # COOKIE_SECURE=false in tests; the default (true) is pinned in test_bootstrap.
    assert "secure" not in set_cookie.replace("samesite", "")

    me = await anon_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"user_id": uid, "username": "admin"}
    assert (await anon_client.get("/api/watches")).status_code == 200


async def test_session_cookie_secure_when_configured(anon_client, sessionmaker_, monkeypatch):
    from stocktrack.bootstrap import get_settings
    await _make_user(sessionmaker_)
    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    r = await _login(anon_client)
    assert r.status_code == 200
    assert "; secure" in r.headers["set-cookie"].lower()


async def test_wrong_password_and_unknown_user_get_the_same_401(anon_client, sessionmaker_):
    await _make_user(sessionmaker_)
    bad_pw = await _login(anon_client, password="wrong-wrong-pass")
    unknown = await _login(anon_client, username="nobody")
    assert bad_pw.status_code == unknown.status_code == 401
    assert bad_pw.json() == unknown.json() == {"detail": "invalid credentials"}
    assert SESSION_COOKIE_NAME not in bad_pw.headers.get("set-cookie", "")


async def test_locked_username_gets_429_with_retry_after(anon_client, sessionmaker_):
    await _make_user(sessionmaker_)
    for _ in range(login_throttle.max_failures):
        login_throttle.record_failure("admin")
    r = await _login(anon_client)  # correct password, still refused
    assert r.status_code == 429, r.text
    assert "retry-after" in {k.lower() for k in r.headers}


async def test_failed_logins_lock_the_username(anon_client, sessionmaker_, monkeypatch):
    await _make_user(sessionmaker_)
    monkeypatch.setattr(login_throttle, "max_failures", 3)
    for _ in range(3):
        assert (await _login(anon_client, password="wrong-wrong-pass")).status_code == 401
    assert (await _login(anon_client)).status_code == 429


async def test_login_is_rate_limited_per_ip(anon_client, sessionmaker_):
    await _make_user(sessionmaker_)
    codes = [(await _login(anon_client, password="wrong-wrong-pass")).status_code
             for _ in range(6)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


async def test_logout_clears_cookie(anon_client, sessionmaker_):
    # A real login, so the jar holds the cookie under the server's domain and
    # the clearing Set-Cookie actually replaces it (as a browser would).
    await _make_user(sessionmaker_)
    assert (await _login(anon_client)).status_code == 200
    client = anon_client
    r = await client.post("/api/auth/logout", headers=csrf_headers(client))
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    set_cookie = r.headers["set-cookie"].lower()
    assert SESSION_COOKIE_NAME in set_cookie
    assert 'max-age=0' in set_cookie or "expires=thu, 01 jan 1970" in set_cookie
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_requires_a_session(anon_client):
    assert (await anon_client.post("/api/auth/logout")).status_code == 401


async def test_me_unauthenticated_is_401(anon_client):
    assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_tampered_cookie_is_401(anon_client, sessionmaker_):
    uid = await _make_user(sessionmaker_)
    good = await _cookie(sessionmaker_, uid)
    anon_client.cookies.set(SESSION_COOKIE_NAME, good[:-2] + "xx")
    assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_cookie_signed_with_another_key_is_401(anon_client, sessionmaker_):
    uid = await _make_user(sessionmaker_)
    anon_client.cookies.set(SESSION_COOKIE_NAME,
                            await _cookie(sessionmaker_, uid, key="o" * 32))
    assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_session_expires_server_side(anon_client, sessionmaker_):
    """A validly signed cookie older than SESSION_MAX_AGE_SECONDS is refused."""
    import time
    from itsdangerous.timed import TimestampSigner
    uid = await _make_user(sessionmaker_)
    eight_days_ago = int(time.time()) - 8 * 24 * 3600
    nonce = await _nonce(sessionmaker_, uid)
    with patch.object(TimestampSigner, "get_timestamp", return_value=eight_days_ago):
        old = make_serializer(KEY).dumps({"user_id": uid, "nonce": nonce})
    anon_client.cookies.set(SESSION_COOKIE_NAME, old)
    assert (await anon_client.get("/api/auth/me")).status_code == 401

    fresh = await _cookie(sessionmaker_, uid)
    anon_client.cookies.set(SESSION_COOKIE_NAME, fresh)
    assert (await anon_client.get("/api/auth/me")).status_code == 200


async def test_payload_without_int_user_id_is_401(anon_client):
    for payload in ({"user_id": "1", "nonce": "n"}, {"other": 1}, [1],
                    {"user_id": True, "nonce": "n"}):
        anon_client.cookies.set(SESSION_COOKIE_NAME, make_serializer(KEY).dumps(payload))
        assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_valid_cookie_for_deleted_user_is_401(client, sessionmaker_):
    """Deliberate addition to the template: deleting the user row kills its
    sessions without rotating APP_SECRET_KEY."""
    assert (await client.get("/api/watches")).status_code == 200
    async with sessionmaker_() as s:
        await s.execute(delete(User))
        await s.commit()
    r = await client.get("/api/watches")
    assert r.status_code == 401
    assert r.json() == {"detail": "Authentication required"}


def test_there_is_no_positive_session_cache():
    """Every request looks the (id, nonce) pair up. A cache raced sign out:
    a lookup begun before the nonce rotation could store the old pair after
    the rotation, keeping the old cookie alive for the cache TTL."""
    assert not hasattr(auth_middleware, "UserExistsCache")
    assert not hasattr(auth_middleware, "user_exists_cache")

async def test_cookie_without_a_nonce_is_401(anon_client, sessionmaker_):
    """The old payload format (user id only) no longer authenticates."""
    uid = await _make_user(sessionmaker_)
    anon_client.cookies.set(SESSION_COOKIE_NAME, make_serializer(KEY).dumps({"user_id": uid}))
    assert (await anon_client.get("/api/auth/me")).status_code == 401
    for bad in (None, 1, ""):
        anon_client.cookies.set(SESSION_COOKIE_NAME,
                                make_serializer(KEY).dumps({"user_id": uid, "nonce": bad}))
        assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_cookie_with_the_wrong_nonce_is_401(anon_client, sessionmaker_):
    uid = await _make_user(sessionmaker_)
    anon_client.cookies.set(SESSION_COOKIE_NAME,
                            make_serializer(KEY).dumps({"user_id": uid, "nonce": "guess"}))
    assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_each_user_gets_a_random_session_nonce(sessionmaker_):
    uid = await _make_user(sessionmaker_)
    nonce = await _nonce(sessionmaker_, uid)
    assert isinstance(nonce, str) and len(nonce) >= 16
    async with sessionmaker_() as s:
        await s.execute(delete(User))
        await s.commit()
    assert await _nonce(sessionmaker_, await _make_user(sessionmaker_)) != nonce


async def test_session_dies_after_delete_and_re_setup(anon_client, sessionmaker_):
    """SQLite would hand the re-created user id 1 again; the nonce (and
    AUTOINCREMENT) stop an old cookie from logging into the new account."""
    old_uid = await _make_user(sessionmaker_)
    old_cookie = await _cookie(sessionmaker_, old_uid)
    anon_client.cookies.set(SESSION_COOKIE_NAME, old_cookie)
    assert (await anon_client.get("/api/auth/me")).status_code == 200

    async with sessionmaker_() as s:
        await s.execute(delete(User))
        await s.commit()
    anon_client.cookies.delete(SESSION_COOKIE_NAME)
    await anon_client.get("/api/setup")  # primes the CSRF cookie
    r = await anon_client.post("/api/setup", json={"username": "admin", "password": PW},
                               headers=csrf_headers(anon_client))
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] != old_uid  # AUTOINCREMENT: ids are never reused

    anon_client.cookies.set(SESSION_COOKIE_NAME, old_cookie)
    assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_old_cookie_with_reused_id_and_old_nonce_is_401(anon_client, sessionmaker_):
    """Even if a re-created user did get the old id, the old nonce fails."""
    uid = await _make_user(sessionmaker_)
    old_cookie = await _cookie(sessionmaker_, uid)
    async with sessionmaker_() as s:
        await s.execute(delete(User))
        await s.commit()
        s.add(User(id=uid, username="admin", password_hash="unused"))
        await s.commit()
    anon_client.cookies.set(SESSION_COOKIE_NAME, old_cookie)
    assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_logout_kills_the_old_cookie_server_side(anon_client, sessionmaker_):
    await _make_user(sessionmaker_)
    assert (await _login(anon_client)).status_code == 200
    stolen = anon_client.cookies.get(SESSION_COOKIE_NAME)
    assert (await anon_client.get("/api/auth/me")).status_code == 200
    r = await anon_client.post("/api/auth/logout", headers=csrf_headers(anon_client))
    assert r.status_code == 200
    anon_client.cookies.set(SESSION_COOKIE_NAME, stolen)
    assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_logout_ends_every_session_for_the_user(sessionmaker_, app):
    """Single user app: sign out on one browser signs out all of them."""
    from httpx import ASGITransport, AsyncClient
    await _make_user(sessionmaker_)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as a, \
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as b:
        assert (await _login(a)).status_code == 200
        assert (await _login(b)).status_code == 200
        assert (await b.get("/api/auth/me")).status_code == 200
        assert (await a.post("/api/auth/logout", headers=csrf_headers(a))).status_code == 200
        assert (await b.get("/api/auth/me")).status_code == 401
        assert (await _login(b)).status_code == 200  # signing in again works
        assert (await b.get("/api/auth/me")).status_code == 200
