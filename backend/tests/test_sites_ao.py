from pathlib import Path
import datetime
from unittest.mock import patch
from stocktrack.sites import ao, available, get_handler, stores

FIX = Path(__file__).parent / "fixtures" / "ao_listing.html"

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
    import datetime
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


def test_registry():
    assert "ao" in available() and "johnlewis" in available()
    assert get_handler("ao").name == "ao"           # defaults to kind="listing"
    assert get_handler("ao", "listing").kind == "listing"
    entries = stores()
    listing = [s for s in entries if s["name"] == "ao" and s["kind"] == "listing"]
    assert listing and listing[0]["supported"] is True
