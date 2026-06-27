from pathlib import Path
from stocktrack.sites import johnlewis

FIX = Path(__file__).parent / "fixtures" / "jl_listing.html"

def test_jl_parses_in_stock():
    prods = johnlewis.handler.parse(FIX.read_text(encoding="utf-8"))
    by = {p.code: p for p in prods}
    assert by["JL1"].in_stock is True
    assert by["JL2"].in_stock is False

def test_jl_price():
    prods = johnlewis.handler.parse(FIX.read_text(encoding="utf-8"))
    by = {p.code: p for p in prods}
    assert by["JL1"].price == 399.0

def test_jl_url_absolute():
    prods = johnlewis.handler.parse(FIX.read_text(encoding="utf-8"))
    by = {p.code: p for p in prods}
    assert by["JL1"].url.startswith("https://www.johnlewis.com")

def test_jl_availability_empty():
    # johnlewis doesn't set availability
    prods = johnlewis.handler.parse(FIX.read_text(encoding="utf-8"))
    by = {p.code: p for p in prods}
    assert by["JL1"].availability == ""
    assert by["JL1"].basket_url == ""
