"""Scheduled digest push: a periodic roll-up instead of per-transition noise.

``digest_tick`` runs every 15 minutes (registered in main.py); settings are
DB-owned so cadence changes take effect without rescheduling. A digest is due
when the cadence is active, the local hour has passed ``digest_hour`` and the
``digest_last_sent`` marker (ISO date, internal) is older than today (weekly:
Mondays only). The marker only advances when the push is delivered.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from stocktrack.models import Event, Product, Watch
from stocktrack.services import gotify
from stocktrack.services.notify_format import fmt_price, md_lines
from stocktrack.services.settings_service import get as get_setting
from stocktrack.services.settings_service import gotify_config, set_value

_KIND_ICONS = {"early_access": "⚡", "public": "🟢", "oos": "🔴",
               "new_product": "🆕", "price_drop": "💸", "lead_time": "🚚",
               "new_low": "🏆", "price_rise": "📈", "price_target": "🎯"}
_KIND_LABELS = {"early_access": "early access", "public": "in stock",
                "oos": "out of stock", "new_product": "new product",
                "price_drop": "price drop", "lead_time": "delivery changed",
                "new_low": "all-time low", "price_rise": "price back up",
                "price_target": "target price hit"}


def _phase(p) -> str:
    return p.availability or ("public" if p.current_in_stock else "oos")


def build_digest(watch_products, recent_events, now) -> tuple[str, str]:
    """Pure formatter. ``watch_products`` is ``[(Watch, [Product, ...]), ...]``,
    ``recent_events`` is ``[(Event, Product), ...]`` newest-first."""
    all_products = [p for _, prods in watch_products for p in prods]
    in_stock = [p for p in all_products if _phase(p) != "oos"]
    title = (f"📰 StockTrack digest — "
             f"{len(in_stock)}/{len(all_products)} in stock")

    lines = []
    for watch, prods in watch_products:
        buyable = sorted(
            (p for p in prods if _phase(p) != "oos"),
            key=lambda p: (p.current_price is None, p.current_price),
        )
        if not buyable:
            continue
        lines.append(f"**{watch.label or watch.store}**")
        for p in buyable:
            icon = "⚡" if _phase(p) == "early" else "🟢"
            price = f" — {fmt_price(p.current_price)}" if p.current_price is not None else ""
            low = (" 🏆" if p.current_price is not None
                   and p.current_price == p.lowest_price else "")
            lines.append(f"{icon} {p.title or p.code}{price}{low}")
    if not lines:
        lines.append("Nothing in stock right now.")

    if recent_events:
        lines.append("")
        lines.append("**Changes**")
        for e, p in recent_events:
            icon = _KIND_ICONS.get(e.kind, "•")
            label = _KIND_LABELS.get(e.kind, e.kind)
            price = f" ({fmt_price(e.price)})" if e.price is not None else ""
            lines.append(f"{icon} {p.title or p.code}: {label}{price}")

    return title, md_lines(lines)


async def digest_tick(sessionmaker, secret_key: str, *, tz: str = "UTC",
                      sender=None, now=None) -> bool:
    """Send the digest if one is due. Returns True when a push was delivered."""
    sender = sender or gotify.send
    now = now or datetime.now(timezone.utc)
    async with sessionmaker() as s:
        cadence = (await get_setting(s, "digest_cadence", "off") or "off").strip().lower()
        if cadence not in ("daily", "weekly"):
            return False
        hour = int(await get_setting(s, "digest_hour", "8") or 8)
        priority = int(await get_setting(s, "digest_priority", "4") or 4)

        local = now.astimezone(ZoneInfo(tz))
        if local.hour < hour:
            return False
        if cadence == "weekly" and local.weekday() != 0:  # Mondays only
            return False
        today = local.date().isoformat()
        last = await get_setting(s, "digest_last_sent", "") or ""
        if last >= today:
            return False

        watches = (await s.execute(
            select(Watch).where(Watch.enabled.is_(True)))).scalars().all()
        products = (await s.execute(select(Product))).scalars().all()
        if not products:
            return False
        by_watch = [(w, [p for p in products if p.watch_id == w.id])
                    for w in watches]

        window = timedelta(days=7 if cadence == "weekly" else 1)
        recent = (await s.execute(
            select(Event, Product)
            .join(Product, Event.product_id == Product.id)
            .where(Event.ts >= now - window)
            .order_by(Event.ts.desc())
            .limit(30)
        )).all()

        title, message = build_digest(by_watch, recent, now)
        cfg = await gotify_config(s, secret_key)
        ok = await asyncio.to_thread(sender, cfg, title, message,
                                     markdown=True, priority=priority)
        if ok:
            await set_value(s, "digest_last_sent", today)
            await s.commit()
        return bool(ok)
