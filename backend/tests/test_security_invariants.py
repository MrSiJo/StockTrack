"""Security invariants: pinning tests with explicit sign off semantics.

Failures here are intentional trip wires: someone changed an exempt path or
the API token allowlist, added a route that skips auth, or removed CSRF from
a mutating route. Update the pinned constant ONLY after explicit user sign
off, and add a line to the change log below.
"""
import hashlib
import json
import re

import pytest
from fastapi.routing import APIRoute
from starlette.applications import Starlette
from starlette.routing import Mount, Route, WebSocketRoute

from stocktrack.api.auth_middleware import EXEMPT_ROUTES as AUTH_EXEMPT
from stocktrack.api.auth_middleware import TOKEN_ALLOWLIST
from stocktrack.api.csrf import EXEMPT_ROUTES as CSRF_EXEMPT

# Pinned hash of the three sets. The two exempt sets hold (method, path)
# pairs. Recompute with:
#     python -c "import hashlib, json; print(hashlib.sha256(json.dumps(
#         {'auth': sorted([(m, p), ...]), 'csrf': sorted([(m, p), ...]),
#          'token_get': sorted([...])},
#         sort_keys=True).encode()).hexdigest())"
#
# Change log:
#   2026-10-24  initial (auth spec 6.2, 6.3):
#               auth=[/api/auth/login, /api/health, /api/health/plugins, /api/setup]
#               csrf=[/api/health, /api/health/plugins]
#               token_get=[/api/watches, /api/watches/{id}/offer-changes,
#                          /api/watches/{id}/offers]
#   2026-10-24  exempt sets pinned to (method, path) pairs (review finding,
#               approved; a narrowing, not a widening):
#               auth=[GET /api/health, GET /api/health/plugins, GET /api/setup,
#                     POST /api/setup, POST /api/auth/login]
#               csrf=[GET /api/health, GET /api/health/plugins]
#               token_get unchanged
EXPECTED_HASH = "82a14e001fbccca89c81d7fb8f936065de1c60e97f0e138db9b760791176787c"
ALL_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _compute_hash() -> str:
    payload = json.dumps(
        {"auth": sorted(AUTH_EXEMPT), "csrf": sorted(CSRF_EXEMPT),
         "token_get": sorted(TOKEN_ALLOWLIST)},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_exempt_paths_and_token_allowlist_have_not_changed():
    actual = _compute_hash()
    assert actual == EXPECTED_HASH, (
        "An exempt set or the token allowlist changed. Update this constant "
        "ONLY after explicit user sign off.\n"
        f"  auth EXEMPT_ROUTES: {sorted(AUTH_EXEMPT)}\n"
        f"  csrf EXEMPT_ROUTES: {sorted(CSRF_EXEMPT)}\n"
        f"  TOKEN_ALLOWLIST:   {sorted(TOKEN_ALLOWLIST)}\n"
        f"  expected hash: {EXPECTED_HASH}\n"
        f"  actual hash:   {actual}"
    )


def test_token_allowlist_is_get_only_reads_and_excludes_status():
    assert "/api/status" not in TOKEN_ALLOWLIST
    assert not (TOKEN_ALLOWLIST & {path for _, path in AUTH_EXEMPT})


def test_exempt_sets_are_method_path_pairs():
    for method, path in AUTH_EXEMPT | CSRF_EXEMPT:
        assert method in ALL_METHODS and path.startswith("/api/")
    # Safe methods are CSRF exempt anyway: the CSRF set must never hold a
    # mutating method.
    assert not ({m for m, _ in CSRF_EXEMPT} & MUTATING)


def app_routes(app) -> list[tuple[str, set[str]]]:
    """Every (path, methods) the app serves. FastAPI 0.139 keeps an included
    router as ONE ``_IncludedRouter`` entry in ``app.routes`` (no path, no
    methods), so walk into it: a flat loop would silently see no API routes.
    Any other entry it cannot classify fails the test run."""
    out: list[tuple[str, set[str]]] = []

    def walk(routes, prefix: str) -> None:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                ctx = getattr(route, "include_context", None)
                walk(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
                continue
            if not isinstance(route, (APIRoute, Route)):
                # Mount, WebSocketRoute or anything new: fail loudly rather
                # than let it escape every enumeration test below.
                raise AssertionError(
                    f"route walk cannot classify {type(route).__name__} "
                    f"{getattr(route, 'path', route)!r} at prefix {prefix!r}; "
                    "teach app_routes about it")
            out.append((prefix + route.path, set(route.methods or set())))

    walk(app.routes, "")
    return out


class _FakeApp:
    def __init__(self, routes):
        self.routes = routes


@pytest.mark.parametrize("route", [
    Mount("/static", app=Starlette()),
    WebSocketRoute("/ws", endpoint=lambda ws: None),
    object(),
], ids=["mount", "websocket", "unknown"])
def test_the_route_walk_refuses_what_it_cannot_classify(route):
    """A route the walk skipped would silently escape every enumeration test."""
    with pytest.raises(AssertionError, match="cannot classify"):
        app_routes(_FakeApp([APIRoute("/api/ok", endpoint=lambda: None), route]))


def test_the_live_app_has_only_classifiable_routes(app):
    assert app_routes(app)  # raises if any entry cannot be classified


def _concrete(path: str) -> str:
    """Fill every path parameter with 1 so the request reaches the middleware."""
    return re.sub(r"\{[^}]+\}", "1", path)


def test_the_route_walk_sees_every_registered_router(app):
    seen = {(path, m) for path, methods in app_routes(app) for m in methods}
    assert {
        ("/api/health", "GET"),
        ("/api/setup", "POST"),
        ("/api/auth/login", "POST"),
        ("/api/watches", "POST"),
        ("/api/settings", "PUT"),
        ("/api/tokens", "POST"),
        ("/api/tokens/{token_id}/revoke", "POST"),
        ("/api/watches/{watch_id}/offers", "GET"),
    } <= seen


async def test_every_non_exempt_route_is_401_unauthenticated(app, anon_client):
    failures = []
    for path, methods in app_routes(app):
        for method in methods - {"HEAD"}:
            if (method, path) in AUTH_EXEMPT:
                continue
            r = await anon_client.request(method, _concrete(path), json={})
            if r.status_code != 401:
                failures.append(f"{method} {path} -> {r.status_code}")
    # An exempt path is exempt for its pinned methods only: every other verb
    # on it (routed or not) is refused before routing.
    for path in {p for _, p in AUTH_EXEMPT}:
        for method in sorted(ALL_METHODS - {m for m, p in AUTH_EXEMPT if p == path}):
            r = await anon_client.request(method, path, json={})
            if r.status_code != 401:
                failures.append(f"{method} {path} (exempt path, other verb) -> {r.status_code}")
    assert not failures, "unauthenticated access:\n  " + "\n  ".join(failures)


async def test_every_mutating_route_is_403_without_csrf(app, client):
    """Authenticated, but no X-CSRF-Token: every mutating route must 403
    unless its path is CSRF exempt."""
    client.headers.pop("X-CSRF-Token")
    failures = []
    for path, methods in app_routes(app):
        for method in methods & MUTATING:
            r = await client.request(method, _concrete(path), json={})
            if (method, path) in CSRF_EXEMPT:
                if r.status_code == 403 and "CSRF" in r.text:
                    failures.append(f"{method} {path} unexpectedly CSRF blocked")
            elif r.status_code != 403:
                failures.append(f"{method} {path} -> {r.status_code} (expected 403)")
    assert not failures, "CSRF invariant violations:\n  " + "\n  ".join(failures)


async def test_api_token_only_reaches_the_allowlist(app, client, anon_client):
    r = await client.post("/api/tokens", json={"name": "probe", "expires_in_days": None})
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    failures = []
    for path, methods in app_routes(app):
        template = re.sub(r"\{[^}]+\}", "{id}", path)
        for method in methods - {"HEAD"}:
            if (method, path) in AUTH_EXEMPT:
                continue
            r = await anon_client.request(method, _concrete(path), headers=headers, json={})
            allowed = method == "GET" and template in TOKEN_ALLOWLIST
            if allowed and r.status_code in (401, 403):
                failures.append(f"{method} {path} refused a valid token ({r.status_code})")
            if not allowed and r.status_code != 403:
                failures.append(f"{method} {path} -> {r.status_code} with a token (expected 403)")
    assert not failures, "token scope violations:\n  " + "\n  ".join(failures)


async def test_plugin_health_exposes_only_status_and_skipped_names(anon_client, tmp_path):
    """Unauthenticated: exactly {"status", "skipped": [module names]}, healthy
    or not. Error text, sources and paths stay on the authenticated
    /api/plugins."""
    from stocktrack import sites

    def check(r):
        body = r.json()
        assert set(body) == {"status", "skipped"}
        assert body["status"] in ("ok", "degraded")
        assert isinstance(body["skipped"], list)
        assert all(isinstance(name, str) for name in body["skipped"])
        assert (r.status_code, body["status"]) in ((200, "ok"), (503, "degraded"))

    check(await anon_client.get("/api/health/plugins"))
    (tmp_path / "bad.py").write_text("raise RuntimeError('boom')", encoding="utf-8")
    try:
        sites.load_registry(tmp_path)
        r = await anon_client.get("/api/health/plugins")
        sites.load_registry(tmp_path / "missing")
        r_dir = await anon_client.get("/api/health/plugins")
    finally:
        sites.load_registry(None)
    check(r)
    assert r.json()["skipped"] == ["bad"]
    check(r_dir)


async def test_health_is_public(anon_client):
    r = await anon_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
