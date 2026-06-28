from pathlib import Path
import pytest
from stocktrack.sites import cityplumbing as cp
from stocktrack.sites import available, get_handler

FIX = Path(__file__).parent / "fixtures" / "cityplumbing_listing.html"


def test_extract_products_grid_price_title_url():
    prods = cp._extract_products(FIX.read_text(encoding="utf-8"))
    by = {p["code"]: p for p in prods}
    assert set(by) == {"100001", "100002", "100003"}
    assert by["100001"]["price"] == 48.0
    assert by["100001"]["title"] == "Fake Panel One 400W"          # JSON name
    assert by["100002"]["title"] == "Fake Panel Two"               # slug-derived
    assert by["100001"]["url"] == "https://www.cityplumbing.co.uk/p/fake-panel-one/p/100001"


def test_extract_products_no_grid_raises():
    with pytest.raises(RuntimeError):
        cp._extract_products("<html><body>no products</body></html>")


def test_fulfilment_text_stable_absolute():
    s = cp._fulfilment_text("Delivery", "2026-06-30T04:00Z")
    assert s == "Delivery by Tue 30 Jun" and "day" not in s.lower()
    assert cp._fulfilment_text("Collection", "2026-07-02T06:00Z") == "Collection by Thu 2 Jul"
    assert cp._fulfilment_text("Delivery", None) == ""
    assert cp._fulfilment_text("Delivery", "not-a-date") == ""


def test_parse_prefers_delivery_with_collection_fallback():
    products = [
        {"code": "100001", "title": "Carrier panel", "price": 48.0,
         "url": "https://www.cityplumbing.co.uk/p/fake-panel-one/p/100001"},
        {"code": "100002", "title": "Branch-delivery panel", "price": 108.0,
         "url": "https://www.cityplumbing.co.uk/p/fake-panel-two/p/100002"},
        {"code": "100003", "title": "Collection-only panel", "price": 180.0,
         "url": "https://www.cityplumbing.co.uk/p/fake-panel-three/p/100003"},
        {"code": "100004", "title": "Unavailable panel", "price": 72.0,
         "url": "https://www.cityplumbing.co.uk/p/fake-panel-four/p/100004"},
    ]
    eligibility = {
        # carrier delivery → "Delivery by ..."
        "100001": {"deliveryEligibility": {"status": "AVAILABLE", "type": "CARRIER",
                   "estimatedDateTime": "2026-06-30T04:00Z"},
                   "collectionEligibility": {"status": "AVAILABLE",
                   "estimatedDateTime": "2026-07-02T06:00Z"}},
        # branch is still delivery → "Delivery by ..." (not collection)
        "100002": {"deliveryEligibility": {"status": "AVAILABLE", "type": "BRANCH",
                   "estimatedDateTime": "2026-07-02T06:00Z"},
                   "collectionEligibility": {"status": "AVAILABLE",
                   "estimatedDateTime": "2026-07-02T06:00Z"}},
        # delivery unavailable but collection available → "Collection by ..."
        "100003": {"deliveryEligibility": {"status": "UNAVAILABLE", "type": None,
                   "estimatedDateTime": None},
                   "collectionEligibility": {"status": "AVAILABLE",
                   "estimatedDateTime": "2026-07-03T06:00Z"}},
        # neither → OOS
        "100004": {"deliveryEligibility": {"status": "UNAVAILABLE", "type": None,
                   "estimatedDateTime": None},
                   "collectionEligibility": {"status": "UNAVAILABLE"}},
    }
    raw = cp._build_envelope(products, eligibility)
    out = {p.code: p for p in cp.handler.parse(raw)}

    assert out["100001"].in_stock is True
    assert out["100001"].delivery == "Delivery by Tue 30 Jun"
    assert out["100001"].availability == "" and out["100001"].basket_url == ""
    # branch route is delivery, not collection
    assert out["100002"].in_stock is True
    assert out["100002"].delivery == "Delivery by Thu 2 Jul"
    # collection-only is in stock, labelled collection
    assert out["100003"].in_stock is True
    assert out["100003"].delivery == "Collection by Fri 3 Jul"
    # neither channel → out of stock, no fulfilment string
    assert out["100004"].in_stock is False
    assert out["100004"].delivery == ""


def test_registered():
    assert "cityplumbing" in available()
    assert get_handler("cityplumbing", "listing") is cp.handler


def test_missing_postcode_raises():
    # Guard fires before any network I/O — postcode empty → RuntimeError immediately.
    cp.handler.configure(cp_delivery_postcode="", cp_collection_branch_id="4207")
    with pytest.raises(RuntimeError, match="delivery postcode"):
        cp.handler.fetch("https://www.cityplumbing.co.uk/c/whatever")


async def test_store_config_kwargs_wires_cp_handler(sessionmaker_):
    """store_config_kwargs builds the correct kwargs and configure() applies them."""
    from stocktrack.services.settings_service import set_value, store_config_kwargs

    async with sessionmaker_() as s:
        await set_value(s, "cp_delivery_postcode", "SW1A 1AA")
        await set_value(s, "cp_collection_branch_id", "9001")
        await s.commit()
        kwargs = await store_config_kwargs(s, cp.handler)

    # store_config_kwargs also injects early_access_days — configure must absorb it.
    assert kwargs["cp_delivery_postcode"] == "SW1A 1AA"
    assert kwargs["cp_collection_branch_id"] == "9001"
    assert "early_access_days" in kwargs

    cp.handler.configure(**kwargs)
    assert cp.handler._delivery_postcode == "SW1A 1AA"
    assert cp.handler._collection_branch_id == "9001"
