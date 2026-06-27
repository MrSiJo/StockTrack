from stocktrack.sites.base import Product, SiteHandler

def test_product_defaults():
    p = Product(code="c", title="t", in_stock=True)
    assert p.brand == "" and p.price is None and p.url == ""
    assert p.availability == "" and p.basket_url == ""

def test_handler_declares_kind():
    assert SiteHandler.kind == "listing"

def test_impersonation_targets_dedup_and_primary_first(monkeypatch):
    from stocktrack.sites import base
    monkeypatch.setattr(base, "CURL_IMPERSONATE", "chrome")
    monkeypatch.setattr(base, "FALLBACK_IMPERSONATIONS", ["chrome", "firefox", "safari"])
    monkeypatch.setattr(base, "_SUPPORTED_IMPERSONATIONS", None)
    assert base._impersonation_targets() == ["chrome", "firefox", "safari"]
