"""Shared day+month delivery-date parsing.

Handles the strings retailers put in fulfilment copy — "Delivery by Fri 3
Jul", "Home delivery from 3rd July" — which carry no year. Two year-inference
modes:

- default (lead-time comparisons): the candidate closest to ``today``,
  handling Dec -> Jan rollover in both directions;
- ``roll_forward=True`` (availability distance): never in the past — a
  delivery estimate is always upcoming, so a "past" date means next year.
"""
import re
from datetime import date

_MONTH_NUMS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

_DAY_MONTH_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\b")


def parse_delivery_date(text, today: date, *,
                        roll_forward: bool = False) -> "date | None":
    """Extract the first day+month from ``text`` and infer the year."""
    m = _DAY_MONTH_RE.search(text or "")
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTH_NUMS.get(m.group(2).lower())
    if not month:
        return None
    candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if roll_forward:
        future = [d for d in candidates if d >= today]
        return min(future) if future else None
    if not candidates:
        return None
    return min(candidates, key=lambda d: abs((d - today).days))
