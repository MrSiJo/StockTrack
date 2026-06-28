"""Shared building blocks for site handlers."""
import os
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from typing import Optional

CURL_IMPERSONATE = os.environ.get("CURL_IMPERSONATE", "chrome")
os.environ.pop("CURL_IMPERSONATE", None)

_DEFAULT_FALLBACKS = ["chrome", "firefox", "safari", "edge", "chrome131", "chrome120"]
FALLBACK_IMPERSONATIONS = [
    t.strip() for t in os.environ.get("CURL_IMPERSONATE_FALLBACKS", "").split(",")
    if t.strip()
] or _DEFAULT_FALLBACKS
_BOT_WALL_STATUSES = (403, 429, 503)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "no-cache",
}

@dataclass
class Product:
    code: str
    title: str
    in_stock: bool
    brand: str = ""
    price: Optional[float] = None
    delivery: str = ""
    url: str = ""
    availability: str = ""
    basket_url: str = ""

class SiteHandler:
    name = "base"
    kind = "listing"
    settings_spec: list[dict] = []

    def fetch(self, url: str) -> str:
        raise NotImplementedError

    def parse(self, raw: str) -> "list[Product]":
        raise NotImplementedError

    def configure(self, **opts) -> None:
        """Apply runtime configuration to this handler. No-op by default."""

def fetch_html(url: str, headers: Optional[dict] = None) -> str:
    if _curl_cffi_available():
        return _fetch_via_curl_cffi(url)
    if shutil.which("curl"):
        return fetch_via_curl(url, headers)
    return _fetch_via_urllib(url, headers or DEFAULT_HEADERS)

def _warn(msg: str) -> None:
    print(f"[base.fetch] WARNING: {msg}", file=sys.stderr, flush=True)

def _curl_cffi_available() -> bool:
    try:
        import curl_cffi  # noqa: F401
        return True
    except (ImportError, OSError) as e:
        _warn(f"curl_cffi unavailable ({e!r}); falling back to curl/urllib.")
        return False

def _supported_impersonations():
    try:
        import typing
        from curl_cffi.requests.impersonate import BrowserTypeLiteral
        return set(typing.get_args(BrowserTypeLiteral))
    except Exception:
        return None

_SUPPORTED_IMPERSONATIONS = _supported_impersonations()

def _impersonation_targets() -> "list[str]":
    seen, out = set(), []
    for t in [CURL_IMPERSONATE, *FALLBACK_IMPERSONATIONS]:
        if not t or t in seen:
            continue
        seen.add(t)
        if _SUPPORTED_IMPERSONATIONS is not None and t not in _SUPPORTED_IMPERSONATIONS:
            _warn(f"impersonation {t!r} not supported by installed curl_cffi; skipping")
            continue
        out.append(t)
    return out

def _fetch_via_curl_cffi(url: str) -> str:
    from curl_cffi import requests as creq
    last_err = None
    for target in _impersonation_targets():
        try:
            with creq.Session() as sess:
                resp = sess.get(url, impersonate=target, timeout=30)
        except Exception as e:
            last_err = RuntimeError(f"curl_cffi impersonate={target!r}: {e!r}")
            continue
        if resp.status_code == 200:
            if target != CURL_IMPERSONATE:
                _warn(f"primary impersonation {CURL_IMPERSONATE!r} was blocked; "
                      f"{target!r} worked")
            return resp.text
        last_err = RuntimeError(f"HTTP {resp.status_code} from {url} (impersonate={target})")
        if resp.status_code not in _BOT_WALL_STATUSES:
            break
    raise last_err if last_err else RuntimeError(f"no fetch attempt for {url}")

def post_json(url: str, payload: dict, headers: Optional[dict] = None) -> dict:
    """POST a JSON body through the curl_cffi impersonation layer.

    Mirrors _fetch_via_curl_cffi's bot-wall fallback. Returns parsed JSON on
    HTTP 200; raises RuntimeError otherwise. Used by handlers whose stock needs
    a second (POST) call, e.g. City Plumbing's productEligibility GraphQL.
    """
    if not _curl_cffi_available():
        raise RuntimeError("curl_cffi required for JSON POST but unavailable")
    from curl_cffi import requests as creq
    hdrs = {"content-type": "application/json", "accept": "application/json",
            **(headers or {})}
    last_err = None
    for target in _impersonation_targets():
        try:
            with creq.Session() as sess:
                resp = sess.post(url, json=payload, headers=hdrs,
                                 impersonate=target, timeout=30)
        except Exception as e:  # noqa: BLE001
            last_err = RuntimeError(f"curl_cffi POST impersonate={target!r}: {e!r}")
            continue
        if resp.status_code == 200:
            return resp.json()
        last_err = RuntimeError(f"HTTP {resp.status_code} from {url} (impersonate={target})")
        if resp.status_code not in _BOT_WALL_STATUSES:
            break
    raise last_err if last_err else RuntimeError(f"no POST attempt for {url}")

def fetch_via_curl(url: str, headers: Optional[dict] = None) -> str:
    headers = headers or DEFAULT_HEADERS
    if not shutil.which("curl"):
        return _fetch_via_urllib(url, headers)
    cmd = ["curl", "-sS", "--compressed", "--max-time", "30",
           "-A", headers["User-Agent"]]
    for key, val in headers.items():
        if key == "User-Agent":
            continue
        cmd += ["-H", f"{key}: {val}"]
    cmd += ["-w", "\n%{http_code}", url]
    out = subprocess.run(cmd, capture_output=True, timeout=60)
    if out.returncode != 0:
        err = out.stderr.decode("utf-8", "replace").strip()[:200]
        raise RuntimeError(f"curl failed (rc={out.returncode}): {err}")
    text = out.stdout.decode("utf-8", "replace")
    body, _, code = text.rpartition("\n")
    if code.strip() != "200":
        raise RuntimeError(f"HTTP {code.strip()} from {url}")
    return body

def _fetch_via_urllib(url: str, headers: dict) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
        return resp.read().decode("utf-8", "replace")
