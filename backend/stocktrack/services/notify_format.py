"""Markdown notification formatting helpers."""

def fmt_price(price: float) -> str:
    return f"£{price:.2f}"

def human_duration(seconds) -> str:
    """Human-readable duration from seconds, e.g. '5m', '1h 30m', '45s'."""
    if seconds is None:
        return ""
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    rem_mins = mins % 60
    if rem_mins:
        return f"{hours}h {rem_mins}m"
    return f"{hours}h"

def md_lines(parts: list[str]) -> str:
    """Join non-empty parts with newlines."""
    return "\n".join(p for p in parts if p)
