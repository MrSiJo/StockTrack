import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from stocktrack.models import Event, Product
from stocktrack.services import gotify
from stocktrack.services.notify_format import fmt_price, human_duration, md_lines
from stocktrack.services.settings_service import get as get_setting
from stocktrack.services.settings_service import gotify_config
from stocktrack.sites import get_handler


def _utc(dt) -> "datetime | None":
    """Ensure a datetime is UTC-aware. SQLite strips tzinfo; treat naive as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def matches(p, include: str, exclude: str) -> bool:
    hay = f"{p.brand} {p.title}".lower()
    excludes = [e.strip().lower() for e in (exclude or "").split(",") if e.strip()]
    if any(e in hay for e in excludes):
        return False
    if (include or "").strip() in ("", "*"):
        return True
    wants = [b.strip().lower() for b in include.split(",") if b.strip()]
    return any(w in hay for w in wants)


async def _default_fetcher(handler, url):
    return await asyncio.to_thread(handler.fetch, url)


def _phase(p_avail, in_stock):
    """Derive canonical phase string from a product's availability field."""
    return p_avail or ("public" if in_stock else "oos")


def _early_msg(p):
    parts = []
    if p.price is not None:
        parts.append(f"**{fmt_price(p.price)}**")
    parts.append("Buyable now via direct link — not yet on the public page.")
    if p.basket_url:
        parts.append(f"[🛒 Add to basket ↗]({p.basket_url})")
    if p.url:
        parts.append(f"[Product page ↗]({p.url})")
    return md_lines(parts) or "now available"


def _public_msg(p):
    parts = []
    if p.price is not None:
        parts.append(f"**{fmt_price(p.price)}**")
    if p.delivery:
        parts.append(p.delivery)
    if p.url:
        parts.append(f"[Open product page ↗]({p.url})")
    return md_lines(parts) or "now available"


def _oos_msg(p, secs):
    dur = human_duration(secs)
    parts = [f"Was buyable for ~{dur}." if dur else "Was briefly available."]
    if p.url:
        parts.append(f"[Open product page ↗]({p.url})")
    return md_lines(parts)


def is_price_drop(old, new, min_pct, min_abs) -> bool:
    """True when ``new`` is a meaningful drop below ``old`` (both thresholds met)."""
    if old is None or new is None or new >= old:
        return False
    drop = old - new
    pct = (drop / old) * 100 if old else 0
    return drop >= min_abs and pct >= min_pct


def _price_drop_msg(p, old, new) -> str:
    drop = old - new
    pct = (drop / old) * 100 if old else 0
    parts = [f"**{fmt_price(old)} → {fmt_price(new)}** "
             f"(−{fmt_price(drop)}, −{pct:.0f}%)"]
    if getattr(p, "delivery", ""):
        parts.append(f"Delivery: {p.delivery}")
    if p.url:
        parts.append(f"[Open product page ↗]({p.url})")
    return md_lines(parts)


_STATUS_ICONS = {"early": "⚡", "public": "🟢", "oos": "🔴"}
_STATUS_LABELS = {"early": "early access", "public": "in stock", "oos": "out of stock"}


def build_status_summary(watch, products) -> tuple[str, str]:
    """Build a Gotify status-summary push for a manual check.

    ``products`` is a list of ``Product`` model rows (already persisted).
    Returns ``(title, message)`` ready to pass to ``gotify.send``.
    """
    sorted_prods = sorted(products, key=lambda p: (p.title or p.code or "").lower())
    in_stock_n = sum(1 for p in sorted_prods if _phase(p.availability, p.current_in_stock) != "oos")
    lines = []
    for p in sorted_prods:
        phase = _phase(p.availability, p.current_in_stock)
        icon = _STATUS_ICONS.get(phase, "❓")
        label = _STATUS_LABELS.get(phase, phase)
        extra = f" — {fmt_price(p.current_price)}" if p.current_in_stock and p.current_price is not None else ""
        lines.append(f"{icon} {p.title or p.code}: {label}{extra}")
    title = f"📦 {watch.store} · status — {in_stock_n}/{len(sorted_prods)} in stock"
    message = md_lines(lines) if lines else "No matching products found."
    return title, message


async def check_watch(session, watch, *, secret_key, handler=None,
                      fetcher=None, sender=None, now=None) -> dict:
    handler = handler or get_handler(watch.store, watch.kind)
    fetcher = fetcher or _default_fetcher
    sender = sender or gotify.send
    now = now or datetime.now(timezone.utc)

    from stocktrack.services.settings_service import store_config_kwargs
    handler.configure(**await store_config_kwargs(session, handler))
    raw = await fetcher(handler, watch.url)
    parsed = [p for p in handler.parse(raw)
              if p.code and matches(p, watch.include_filter, watch.exclude_filter)]

    rows = {r.code: r for r in (await session.execute(
        select(Product).where(Product.watch_id == watch.id))).scalars().all()}

    cfg = await gotify_config(session, secret_key)
    restock_priority = int(await get_setting(session, "restock_priority", "8") or 8)
    oos_priority = int(await get_setting(session, "oos_priority", "4") or 4)
    drop_min_pct = float(await get_setting(session, "price_drop_min_pct", "5") or 5)
    drop_min_abs = float(await get_setting(session, "price_drop_min_abs", "5") or 5)
    drop_priority = int(await get_setting(session, "price_drop_priority", "6") or 6)
    early_count = public_count = oos_count = price_drop_count = 0

    for p in parsed:
        row = rows.get(p.code)
        if row is None:
            row = Product(watch_id=watch.id, store=watch.store, code=p.code,
                          first_seen=now)
            session.add(row)
            await session.flush()

        prev = _phase(row.availability, row.current_in_stock)
        curr = _phase(p.availability, p.in_stock)
        prev_since = _utc(row.available_since)

        # Refresh metadata regardless of phase
        old_price = row.current_price
        row.title, row.brand, row.url = p.title, p.brand, p.url
        row.basket_url = p.basket_url
        row.current_price, row.last_checked, row.last_seen = p.price, now, now

        if curr == prev:
            # No phase change — just update availability and current_in_stock
            row.availability = curr
            row.current_in_stock = curr != "oos"
        elif curr in ("early", "public"):
            # Transition into available (from oos, or early->public)
            new_since = prev_since if prev != "oos" else now
            row.available_since = new_since
            kind = "early_access" if curr == "early" else "public"
            if curr == "early":
                title = f"⚡ {watch.store} · Early access: {p.title or p.code}"
                msg = _early_msg(p)
                click = p.basket_url or p.url or None
            else:
                lbl = "Now public" if prev == "early" else "In stock"
                title = f"🟢 {watch.store} · {lbl}: {p.title or p.code}"
                msg = _public_msg(p)
                click = p.url or None
            ok = await asyncio.to_thread(
                sender, cfg, title, msg,
                click_url=click, markdown=True, priority=restock_priority,
            )
            if ok:
                session.add(Event(product_id=row.id, kind=kind, price=p.price))
                row.availability = curr
                row.current_in_stock = True
                if curr == "early":
                    early_count += 1
                else:
                    public_count += 1
            else:
                # Delivery-safe: revert
                row.availability = prev
                row.current_in_stock = prev != "oos"
                row.available_since = prev_since
        else:  # curr == "oos"
            secs = (now - prev_since).total_seconds() if prev_since else None
            title = f"🔴 {watch.store} · Out of stock again: {p.title or p.code}"
            ok = await asyncio.to_thread(
                sender, cfg, title, _oos_msg(p, secs),
                click_url=p.url or None, markdown=True, priority=oos_priority,
            )
            if ok:
                session.add(Event(product_id=row.id, kind="oos", price=p.price,
                                  available_seconds=int(secs) if secs else None))
                row.availability = "oos"
                row.current_in_stock = False
                row.available_since = None
                oos_count += 1
            else:
                # Delivery-safe: keep it available
                row.availability = prev
                row.current_in_stock = True
                row.available_since = prev_since

        if (watch.track_price_drops
                and is_price_drop(old_price, p.price, drop_min_pct, drop_min_abs)):
            title = f"💸 {watch.store} · Price drop: {p.title or p.code}"
            ok = await asyncio.to_thread(
                sender, cfg, title, _price_drop_msg(p, old_price, p.price),
                click_url=p.url or None, markdown=True, priority=drop_priority,
            )
            if ok:
                session.add(Event(product_id=row.id, kind="price_drop", price=p.price))
                price_drop_count += 1
            else:
                row.current_price = old_price  # delivery-safe: revert, retry next tick

    # Addendum A: update watch health on success
    watch.last_checked_at = now
    watch.last_ok_at = now
    watch.consecutive_failures = 0
    watch.last_error = ""

    await session.commit()
    return {"parsed": len(parsed), "early": early_count, "public": public_count,
            "oos": oos_count, "price_drops": price_drop_count}
