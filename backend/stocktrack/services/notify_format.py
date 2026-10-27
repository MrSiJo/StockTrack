"""Markdown notification formatting helpers."""

def fmt_price(price: float) -> str:
    return f"£{price:.2f}"

def human_duration(seconds) -> str:
    """Human-readable duration from seconds, e.g. '5m', '1h 30m', '45s', '1d 0h', '2w 3d'."""
    if seconds is None:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h {minutes % 60}m"
    days = hours // 24
    if days < 7:
        return f"{days}d {hours % 24}h"
    weeks = days // 7
    return f"{weeks}w {days % 7}d"

def md_lines(parts: list[str]) -> str:
    """Join non-empty parts with markdown hard breaks (two trailing spaces).

    Gotify renders markdown, where a bare newline is a soft break shown as a
    space, so plain ``\\n`` joins collapse a message into one paragraph."""
    return "  \n".join(p for p in parts if p)

def md_paragraphs(blocks: list[list[str]]) -> str:
    """Render each block with ``md_lines`` and separate them by a blank line."""
    return "\n\n".join(b for b in (md_lines(blk) for blk in blocks) if b)
