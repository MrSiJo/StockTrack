import json
import pytest
from stocktrack.sites.base import Product, SiteHandler
from stocktrack.sites import base


def test_product_defaults():
    p = Product(code="c", title="t", in_stock=True)
    assert p.brand == "" and p.price is None and p.url == ""
    assert p.availability == "" and p.basket_url == ""

def test_handler_declares_kind():
    assert SiteHandler.kind == "listing"

def test_impersonation_targets_dedup_and_primary_first(monkeypatch):
    monkeypatch.setattr(base, "CURL_IMPERSONATE", "chrome")
    monkeypatch.setattr(base, "FALLBACK_IMPERSONATIONS", ["chrome", "firefox", "safari"])
    monkeypatch.setattr(base, "_SUPPORTED_IMPERSONATIONS", None)
    assert base._impersonation_targets() == ["chrome", "firefox", "safari"]


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self.text = body

    def json(self):
        return json.loads(self.text)


class _Sess:
    def __init__(self, resp):
        self._resp = resp
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def post(self, url, json=None, headers=None, impersonate=None, timeout=None):
        return self._resp


def test_post_json_returns_parsed_on_200(monkeypatch):
    fake = _Resp(200, '{"data": {"ok": true}}')
    monkeypatch.setattr(base, "_curl_cffi_available", lambda: True)
    import curl_cffi.requests as creq
    monkeypatch.setattr(creq, "Session", lambda *a, **k: _Sess(fake))
    out = base.post_json("https://example.test/graphql", {"q": 1})
    assert out == {"data": {"ok": True}}


def test_post_json_raises_on_non_200(monkeypatch):
    fake = _Resp(500, "nope")
    monkeypatch.setattr(base, "_curl_cffi_available", lambda: True)
    import curl_cffi.requests as creq
    monkeypatch.setattr(creq, "Session", lambda *a, **k: _Sess(fake))
    with pytest.raises(RuntimeError):
        base.post_json("https://example.test/graphql", {"q": 1})
