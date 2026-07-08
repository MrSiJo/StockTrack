from stocktrack.services.notify_format import fmt_price, human_duration, md_lines

def test_fmt_price():
    assert fmt_price(519.0) == "£519.00"
    assert fmt_price(9.99) == "£9.99"

def test_human_duration_seconds():
    assert human_duration(45) == "45s"
    assert human_duration(0) == "0s"

def test_human_duration_minutes():
    assert human_duration(300) == "5m"
    assert human_duration(3600) == "1h 0m"
    assert human_duration(3660) == "1h 1m"

def test_human_duration_none():
    assert human_duration(None) == ""

def test_md_lines():
    assert md_lines(["a", "", "b"]) == "a\nb"
    assert md_lines([]) == ""

def test_human_duration_ladder():
    assert human_duration(30) == "30s"
    assert human_duration(90) == "1m"
    assert human_duration(3690) == "1h 1m"
    assert human_duration(24 * 3600) == "1d 0h"
    assert human_duration((6 * 24 + 23) * 3600) == "6d 23h"
    assert human_duration(7 * 24 * 3600) == "1w 0d"
    assert human_duration((2 * 7 + 3) * 24 * 3600) == "2w 3d"
