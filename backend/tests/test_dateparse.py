from datetime import date

from stocktrack.dateparse import parse_delivery_date

TODAY = date(2026, 7, 8)


def test_no_match_returns_none():
    assert parse_delivery_date("", TODAY) is None
    assert parse_delivery_date("Free delivery", TODAY) is None
    assert parse_delivery_date("3 Zzz", TODAY) is None


def test_formats_parse():
    assert parse_delivery_date("Delivery by Fri 3 Jul", TODAY) == date(2026, 7, 3)
    assert parse_delivery_date("Home delivery from 3rd July", TODAY) == date(2026, 7, 3)


def test_closest_year_handles_rollover_both_ways():
    assert parse_delivery_date("by Sat 2 Jan", date(2026, 12, 29)) == date(2027, 1, 2)
    assert parse_delivery_date("by Wed 30 Dec", date(2027, 1, 2)) == date(2026, 12, 30)


def test_roll_forward_never_returns_a_past_date():
    # 3 Jul is 5 days ago -> next year
    assert parse_delivery_date("From 3rd July", TODAY,
                               roll_forward=True) == date(2027, 7, 3)
    # upcoming date stays in the current year
    assert parse_delivery_date("From 20th July", TODAY,
                               roll_forward=True) == date(2026, 7, 20)
