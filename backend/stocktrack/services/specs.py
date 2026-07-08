"""Derive product specs (e.g. wattage) from listing titles."""
import re

# Matches "435W", "460Wp", "0.62kW" (case-insensitive). The negative
# lookahead on the leading digits avoids matching "12k BTU" style tokens
# where the unit is not W.
_WATT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(k)?W(?:p)?(?![\w])", re.IGNORECASE)


def parse_watts(title: str) -> int | None:
    """Return the wattage encoded in ``title`` as an int, or None.

    "435W" -> 435, "460Wp" -> 460, "0.62kW" -> 620, "12k BTU" -> None.
    """
    if not title:
        return None
    m = _WATT_RE.search(title)
    if not m:
        return None
    value = float(m.group(1))
    if m.group(2):  # "k" prefix -> kilowatts
        value *= 1000
    watts = int(round(value))
    return watts or None
