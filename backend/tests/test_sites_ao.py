from pathlib import Path
import datetime
from stocktrack.sites import ao, available, get_handler, stores

FIX = Path(__file__).parent / "fixtures" / "ao_listing.html"
FIX_PRODUCT = Path(__file__).parent / "fixtures" / "ao_product.html"

def test_ao_parses_state_and_price():
    prods = ao.handler.parse(FIX.read_text(encoding="utf-8"))
    by = {p.code: p for p in prods}
    assert by["AO1"].in_stock is False and by["AO1"].price == 519.0
    assert by["AO2"].in_stock is True
    assert by["AO1"].url == "https://ao.com/p/AO1"

def test_ao_availability_oos():
    prods = ao.handler.parse(FIX.read_text(encoding="utf-8"))
    by = {p.code: p for p in prods}
    assert by["AO1"].availability == "oos"

def test_ao_availability_public():
    prods = ao.handler.parse(FIX.read_text(encoding="utf-8"))
    by = {p.code: p for p in prods}
    # AO2 is in stock, no delivery date => public
    assert by["AO2"].availability == "public"

def test_ao_basket_url():
    prods = ao.handler.parse(FIX.read_text(encoding="utf-8"))
    by = {p.code: p for p in prods}
    assert by["AO2"].basket_url == "https://ao.com/Build_Shopping_Basket.aspx?items=AO2:1"

def test_ao_early_access_far_date():
    # AO3 has "From 1st January" delivery — far in future => early
    prods = ao.handler.parse(FIX.read_text(encoding="utf-8"))
    by = {p.code: p for p in prods}
    assert by["AO3"].availability == "early"

def test_delivery_days_out_no_match():
    assert ao._delivery_days_out("") is None
    assert ao._delivery_days_out("Free delivery") is None

def test_configure_changes_early_access_threshold():
    """configure(early_access_days=N) changes the early/public boundary.

    A delivery 20 days out is 'public' at threshold 30 (20 is NOT > 30)
    but 'early' at threshold 10 (20 IS > 10).
    """
    h = ao.AoHandler()
    today = datetime.date.today()
    future = today + datetime.timedelta(days=20)
    months = ["", "January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    delivery = f"From {future.day}th {months[future.month]}"

    h.configure(early_access_days=30)
    assert ao._availability(True, delivery, h._early_access_days) == "public"

    h.configure(early_access_days=10)
    assert ao._availability(True, delivery, h._early_access_days) == "early"


def test_ao_member_price_selection():
    raw = FIX.read_text(encoding="utf-8")
    h = ao.AoHandler()
    h.configure(ao_member=False)
    by = {p.code: p for p in h.parse(raw)}
    assert by["AO2"].price == 599.0           # non-member default

    h.configure(ao_member=True)
    by = {p.code: p for p in h.parse(raw)}
    assert by["AO2"].price == 569.0           # member price
    assert by["AO1"].price == 519.0           # no PricePodViewModel -> standard price


def test_registry():
    assert "ao" in available() and "johnlewis" in available()
    assert get_handler("ao").name == "ao"           # defaults to kind="listing"
    assert get_handler("ao", "listing").kind == "listing"
    assert get_handler("ao", "product").kind == "product"
    entries = stores()
    listing = [s for s in entries if s["name"] == "ao" and s["kind"] == "listing"]
    assert listing and listing[0]["supported"] is True
    product = [s for s in entries if s["name"] == "ao" and s["kind"] == "product"]
    assert product and product[0]["supported"] is True


def test_ao_product_parses_single_product():
    h = ao.AoProductHandler()
    h.configure(ao_member=False)
    prods = h.parse(FIX_PRODUCT.read_text(encoding="utf-8"))
    assert len(prods) == 1
    p = prods[0]
    assert p.code == "999001"
    assert p.title == "Fake Cooler 12K - White"
    assert p.in_stock is False
    assert p.availability == "oos"
    assert p.price == 519.0
    assert p.basket_url == "https://ao.com/Build_Shopping_Basket.aspx?items=999001:1"


def test_ao_product_member_price():
    h = ao.AoProductHandler()
    h.configure(ao_member=True)
    p = h.parse(FIX_PRODUCT.read_text(encoding="utf-8"))[0]
    assert p.price == 493.0


def test_ao_product_in_stock_is_public():
    raw = FIX_PRODUCT.read_text(encoding="utf-8").replace(
        '"isInStock": false', '"isInStock": true').replace(
        '"out of stock"', '"in stock"')
    h = ao.AoProductHandler()
    h.configure(ao_member=False)
    p = h.parse(raw)[0]
    assert p.in_stock is True
    assert p.availability == "public"


def test_ao_product_blob_brace_in_string():
    """Parser must not fail when a JSON string value contains literal braces."""
    raw = FIX_PRODUCT.read_text(encoding="utf-8").replace(
        '"stockStatus": "out of stock"',
        '"stockStatus": "out of stock", "promoLabel": "Save {now} on this {deal}"',
    )
    h = ao.AoProductHandler()
    h.configure(ao_member=False)
    prods = h.parse(raw)
    assert len(prods) == 1
    assert prods[0].price == 519.0
    assert prods[0].code == "999001"
