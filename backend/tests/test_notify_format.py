from stocktrack.services.notify_format import fmt_price, human_duration, md_lines

def test_fmt_price():
    assert fmt_price(519.0) == "£519.00"
    assert fmt_price(9.99) == "£9.99"

def test_human_duration_seconds():
    assert human_duration(45) == "45s"
    assert human_duration(0) == "0s"

def test_human_duration_minutes():
    assert human_duration(300) == "5m"
    assert human_duration(3600) == "1h"
    assert human_duration(3660) == "1h 1m"

def test_human_duration_none():
    assert human_duration(None) == ""

def test_md_lines():
    assert md_lines(["a", "", "b"]) == "a\nb"
    assert md_lines([]) == ""
