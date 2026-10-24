"""Security invariants: pinning tests with explicit sign off semantics.

Failures here are intentional trip wires: someone changed an exempt path or
the API token allowlist, added a route that skips auth, or removed CSRF from
a mutating route. Update the pinned constant ONLY after explicit user sign
off, and add a line to the change log below.
"""
import hashlib
import json
import re

from fastapi.routing import APIRoute
from starlette.routing import Route

from stocktrack.api.auth_middleware import EXEMPT_PATHS as AUTH_EXEMPT
from stocktrack.api.auth_middleware import TOKEN_ALLOWLIST
from stocktrack.api.csrf import EXEMPT_PATHS as CSRF_EXEMPT

# Pinned hash of the three sets. Recompute with:
#     python -c "import hashlib, json; print(hashlib.sha256(json.dumps(
#         {'auth': sorted([...]), 'csrf': sorted([...]), 'token_get': sorted([...])},
#         sort_keys=True).encode()).hexdigest())"
#
# Change log:
#   2026-10-24  initial (auth spec 6.2, 6.3):
#               auth=[/api/auth/login, /api/health, /api/health/plugins, /api/setup]
#               csrf=[/api/health, /api/health/plugins]
#               token_get=[/api/watches, /api/watches/{id}/offer-changes,
#                          /api/watches/{id}/offers]
EXPECTED_HASH = "9cdc045d2a9eac4d862b3a3cd16fc2020886f25e224eb042cd3681ec227e1fc8"

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
        f"  auth EXEMPT_PATHS: {sorted(AUTH_EXEMPT)}\n"
        f"  csrf EXEMPT_PATHS: {sorted(CSRF_EXEMPT)}\n"
        f"  TOKEN_ALLOWLIST:   {sorted(TOKEN_ALLOWLIST)}\n"
        f"  expected hash: {EXPECTED_HASH}\n"
        f"  actual hash:   {actual}"
    )


def test_token_allowlist_is_get_only_reads_and_excludes_status():
    assert "/api/status" not in TOKEN_ALLOWLIST
    assert not (TOKEN_ALLOWLIST & AUTH_EXEMPT)


def app_routes(app) -> list[tuple[str, set[str]]]:
    """Every (path, methods) the app serves. FastAPI 0.139 keeps an included
    router as ONE ``_IncludedRouter`` entry in ``app.routes`` (no path, no
    methods), so walk into it: a flat loop would silently see no API routes."""
    out: list[tuple[str, set[str]]] = []

    def walk(routes, prefix: str) -> None:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                ctx = getattr(route, "include_context", None)
                walk(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
                continue
            if not isinstance(route, (APIRoute, Route)):
                continue
            out.append((prefix + route.path, set(route.methods or set())))

    walk(app.routes, "")
    return out


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
        if path in AUTH_EXEMPT:
            continue
        for method in methods - {"HEAD"}:
            r = await anon_client.request(method, _concrete(path), json={})
            if r.status_code != 401:
                failures.append(f"{method} {path} -> {r.status_code}")
    assert not failures, "unauthenticated access:\n  " + "\n  ".join(failures)


async def test_every_mutating_route_is_403_without_csrf(app, client):
    """Authenticated, but no X-CSRF-Token: every mutating route must 403
    unless its path is CSRF exempt."""
    client.headers.pop("X-CSRF-Token")
    failures = []
    for path, methods in app_routes(app):
        for method in methods & MUTATING:
            r = await client.request(method, _concrete(path), json={})
            if path in CSRF_EXEMPT:
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
        if path in AUTH_EXEMPT:
            continue
        template = re.sub(r"\{[^}]+\}", "{id}", path)
        for method in methods - {"HEAD"}:
            r = await anon_client.request(method, _concrete(path), headers=headers, json={})
            allowed = method == "GET" and template in TOKEN_ALLOWLIST
            if allowed and r.status_code in (401, 403):
                failures.append(f"{method} {path} refused a valid token ({r.status_code})")
            if not allowed and r.status_code != 403:
                failures.append(f"{method} {path} -> {r.status_code} with a token (expected 403)")
    assert not failures, "token scope violations:\n  " + "\n  ".join(failures)


async def test_plugin_health_exposes_only_status_and_skipped(anon_client):
    r = await anon_client.get("/api/health/plugins")
    assert r.status_code in (200, 503)
    assert set(r.json()) == {"status", "skipped"}


async def test_health_is_public(anon_client):
    r = await anon_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
