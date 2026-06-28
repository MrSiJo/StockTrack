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


def test_lead_time_text_stable_absolute():
    s = cp._lead_time_text("2026-06-30T04:00Z", "CARRIER")
    assert "30 Jun" in s and "(carrier)" in s and "day" not in s.lower()
    assert cp._lead_time_text(None, "CARRIER") == ""
    assert cp._lead_time_text("not-a-date", "BRANCH") == ""


def test_parse_delivery_only_in_stock():
    products = [
        {"code": "100001", "title": "Fake Panel One 400W", "price": 48.0,
         "url": "https://www.cityplumbing.co.uk/p/fake-panel-one/p/100001"},
        {"code": "100002", "title": "Fake Panel Two", "price": 108.0,
         "url": "https://www.cityplumbing.co.uk/p/fake-panel-two/p/100002"},
    ]
    eligibility = {
        "100001": {"deliveryEligibility": {"status": "AVAILABLE", "type": "CARRIER",
                   "estimatedDateTime": "2026-06-30T04:00Z"},
                   "collectionEligibility": {"status": "AVAILABLE"}},
        "100002": {"deliveryEligibility": {"status": "UNAVAILABLE", "type": None,
                   "estimatedDateTime": None},
                   "collectionEligibility": {"status": "UNAVAILABLE"}},
    }
    raw = cp._build_envelope(products, eligibility)
    out = {p.code: p for p in cp.handler.parse(raw)}
    assert out["100001"].in_stock is True
    assert out["100001"].availability == "" and out["100001"].basket_url == ""
    assert "30 Jun" in out["100001"].delivery
    assert out["100002"].in_stock is False


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
