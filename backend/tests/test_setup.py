"""GET/POST /api/setup: one-shot first user, unauthenticated."""
from tests.conftest import csrf_headers

PW = "very-strong-pass"


async def _prime_csrf(client):
    await client.get("/api/setup")


async def test_setup_status_true_when_no_user(anon_client):
    r = await anon_client.get("/api/setup")
    assert r.status_code == 200
    assert r.json() == {"setup_needed": True}


async def test_setup_creates_first_user(anon_client):
    await _prime_csrf(anon_client)
    r = await anon_client.post("/api/setup", json={"username": "admin", "password": PW},
                               headers=csrf_headers(anon_client))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "admin"
    assert isinstance(body["user_id"], int)
    # Setup does not log in: the SPA logs in afterwards.
    assert "stocktrack_session" not in r.headers.get("set-cookie", "")


async def test_setup_status_false_after_user_created(anon_client):
    await _prime_csrf(anon_client)
    await anon_client.post("/api/setup", json={"username": "admin", "password": PW},
                           headers=csrf_headers(anon_client))
    r = await anon_client.get("/api/setup")
    assert r.json() == {"setup_needed": False}


async def test_setup_second_call_refused_409(anon_client):
    await _prime_csrf(anon_client)
    r1 = await anon_client.post("/api/setup", json={"username": "admin", "password": PW},
                                headers=csrf_headers(anon_client))
    assert r1.status_code == 201
    r2 = await anon_client.post("/api/setup",
                                json={"username": "second", "password": "another-strong-pass"},
                                headers=csrf_headers(anon_client))
    assert r2.status_code == 409


async def test_setup_rejects_weak_password_400(anon_client):
    await _prime_csrf(anon_client)
    r = await anon_client.post("/api/setup", json={"username": "admin", "password": "short"},
                               headers=csrf_headers(anon_client))
    assert r.status_code == 400
    r = await anon_client.get("/api/setup")
    assert r.json() == {"setup_needed": True}
