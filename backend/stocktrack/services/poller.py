import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select

from stocktrack.dateparse import parse_delivery_date
from stocktrack.models import Event, Product
from stocktrack.services import gotify
from stocktrack.services.notify_format import fmt_price, human_duration, md_lines
from stocktrack.services.settings_service import get as get_setting
from stocktrack.services.settings_service import gotify_config, truthy
from stocktrack.services.specs import parse_watts
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


def _new_product_msg(p):
    parts = []
    status = "in stock" if p.in_stock else "out of stock"
    if p.price is not None:
        parts.append(f"**{fmt_price(p.price)}** — {status}")
    else:
        parts.append(status)
    if p.delivery:
        parts.append(p.delivery)
    if p.url:
        parts.append(f"[Open product page ↗]({p.url})")
    return md_lines(parts) or "new product"


def _oos_msg(p, secs):
    dur = human_duration(secs)
    parts = [f"Was buyable for ~{dur}." if dur else "Was briefly available."]
    if p.url:
        parts.append(f"[Open product page ↗]({p.url})")
    return md_lines(parts)


def _delisted_msg(row, secs):
    dur = human_duration(secs)
    parts = ["No longer listed on the page."]
    if dur:
        parts.append(f"Was buyable for ~{dur}.")
    if row.url:
        parts.append(f"[Open product page ↗]({row.url})")
    return md_lines(parts)


def is_price_drop(old, new, min_pct, min_abs) -> bool:
    """True when ``new`` is a meaningful drop below ``old`` (both thresholds met)."""
    if old is None or new is None or new >= old:
        return False
    drop = old - new
    pct = (drop / old) * 100 if old else 0
    return drop >= min_abs and pct >= min_pct


def is_price_rise(old, new, min_pct, min_abs) -> bool:
    """True when ``new`` is a meaningful rise above ``old`` (both thresholds met)."""
    if old is None or new is None or new <= old:
        return False
    rise = new - old
    pct = (rise / old) * 100 if old else 0
    return rise >= min_abs and pct >= min_pct


def _price_rise_msg(p, old, new) -> str:
    rise = new - old
    pct = (rise / old) * 100 if old else 0
    parts = [f"**{fmt_price(old)} → {fmt_price(new)}** "
             f"(+{fmt_price(rise)}, +{pct:.0f}%)"]
    if getattr(p, "delivery", ""):
        parts.append(f"Delivery: {p.delivery}")
    if p.url:
        parts.append(f"[Open product page ↗]({p.url})")
    return md_lines(parts)


def is_lead_time_change_significant(old, new, now, min_days) -> bool:
    """Filter out naturally sliding delivery estimates (e.g. City Plumbing's
    rolling next-day date) — only a date swing of ``min_days``-or-more is
    alert-worthy. A delivery↔collection channel switch is always significant;
    unparseable strings fall back to alerting on any change; ``min_days`` <= 0
    restores alert-on-any-change."""
    if min_days <= 0:
        return True
    if ("collection" in (old or "").lower()) != ("collection" in (new or "").lower()):
        return True
    d_old = parse_delivery_date(old, now.date())
    d_new = parse_delivery_date(new, now.date())
    if d_old is None or d_new is None:
        return True
    return abs((d_new - d_old).days) >= min_days


def _lead_time_msg(p, old, new):
    parts = [f"**{old or '—'} → {new or '—'}**"]
    if p.url:
        parts.append(f"[Open product page ↗]({p.url})")
    return md_lines(parts)


def _new_low_msg(p) -> str:
    parts = [f"**{fmt_price(p.price)}** — lowest price ever seen"]
    if getattr(p, "delivery", ""):
        parts.append(f"Delivery: {p.delivery}")
    if p.url:
        parts.append(f"[Open product page ↗]({p.url})")
    return md_lines(parts)


def _price_target_msg(p, target) -> str:
    parts = [f"**{fmt_price(p.price)}** — at or below your target of {fmt_price(target)}"]
    if getattr(p, "delivery", ""):
        parts.append(f"Delivery: {p.delivery}")
    if p.url:
        parts.append(f"[Open product page ↗]({p.url})")
    return md_lines(parts)


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


@dataclass
class PendingAlert:
    """A staged notification. The branch that stages it writes state
    optimistically; ``on_success`` persists the Event (delivery-safe),
    ``on_failure`` reverts so the alert retries next tick."""
    row: Product
    kind: str
    title: str
    message: str
    click_url: Optional[str]
    priority: int
    on_success: Callable[[], None]
    on_failure: Callable[[], None]
    group_line: str


def _group_link(a: "PendingAlert") -> str:
    """One grouped-push body line: a tappable markdown link per product so each
    product in a batched notification is individually reachable (the
    notification-level click can only target one URL). The link LABEL reuses
    the alert's own ``group_line`` (emoji + status/kind + any price transition)
    so a mixed-kind grouped push still tells the reader what happened to each
    product, not just its title and current price."""
    label = a.group_line.lstrip()
    for marker in ("- ", "* ", "• "):  # avoid double-bullets if group_line
        if label.startswith(marker):        # ever starts with its own marker
            label = label[len(marker):]
            break
    label = label.replace("]", ")")  # keep the markdown link syntax intact
    return f"- [{label}]({a.click_url})" if a.click_url else f"- {label}"


async def _dispatch(pending, cfg, sender, threshold, store, now,
                    dashboard_url="") -> None:
    """Send staged alerts and run each one's success/failure closure.

    Muted products advance state silently (no push). When a tick stages
    ``threshold``-or-more sendable alerts (0 disables grouping) they collapse
    into one grouped push whose delivery outcome applies to all of them. The
    grouped body lists each product as a markdown link; the notification-level
    click targets ``dashboard_url`` (falling back to the first product's URL).
    """
    sendable = []
    for a in pending:
        muted_until = _utc(getattr(a.row, "muted_until", None))
        if muted_until is not None and now < muted_until:
            a.on_success()
        else:
            sendable.append(a)
    if not sendable:
        return
    if threshold > 0 and len(sendable) >= threshold:
        title = f"📦 {store} · {len(sendable)} updates"
        message = md_lines([_group_link(a) for a in sendable])
        priority = max(a.priority for a in sendable)
        click = dashboard_url or sendable[0].click_url
        ok = await asyncio.to_thread(
            sender, cfg, title, message,
            click_url=click, markdown=True, priority=priority,
        )
        for a in sendable:
            (a.on_success if ok else a.on_failure)()
    else:
        for a in sendable:
            ok = await asyncio.to_thread(
                sender, cfg, a.title, a.message,
                click_url=a.click_url, markdown=True, priority=a.priority,
            )
            (a.on_success if ok else a.on_failure)()


# One lock per watch id: a manual "Check now" and a scheduler tick would
# otherwise read the same pre-transition state concurrently, double-firing
# alerts and duplicating Event rows (which corrupts episode reconstruction).
_watch_locks: dict[int, asyncio.Lock] = {}


async def check_watch(session, watch, *, secret_key, handler=None,
                      fetcher=None, sender=None, now=None) -> dict:
    """Run one check for a watch, serialised per watch id."""
    async with _watch_locks.setdefault(watch.id, asyncio.Lock()):
        return await _check_watch(session, watch, secret_key=secret_key,
                                  handler=handler, fetcher=fetcher,
                                  sender=sender, now=now)


async def _check_watch(session, watch, *, secret_key, handler=None,
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

    rows = {r.code.casefold(): r for r in (await session.execute(
        select(Product).where(Product.watch_id == watch.id))).scalars().all()}

    is_first_poll = len(rows) == 0

    cfg = await gotify_config(session, secret_key)
    restock_priority = int(await get_setting(session, "restock_priority", "8") or 8)
    new_product_priority = int(
        await get_setting(session, "new_product_priority", str(restock_priority))
        or restock_priority)
    oos_priority = int(await get_setting(session, "oos_priority", "4") or 4)
    drop_min_pct = float(await get_setting(session, "price_drop_min_pct", "5") or 5)
    drop_min_abs = float(await get_setting(session, "price_drop_min_abs", "5") or 5)
    # Per-watch overrides beat the global settings
    if watch.price_drop_min_pct is not None:
        drop_min_pct = watch.price_drop_min_pct
    if watch.price_drop_min_abs is not None:
        drop_min_abs = watch.price_drop_min_abs
    drop_priority = int(await get_setting(session, "price_drop_priority", "6") or 6)
    lead_time_priority = int(await get_setting(session, "lead_time_priority", "5") or 5)
    lead_time_min_days = int(
        await get_setting(session, "lead_time_min_change_days", "7") or 7)
    in_stock_only = truthy(await get_setting(session, "price_drop_in_stock_only", "true"))
    dashboard_url = await get_setting(session, "dashboard_url", "") or ""
    counts = {"early": 0, "public": 0, "oos": 0, "price_drops": 0,
              "new_products": 0, "lead_time_changes": 0, "price_targets": 0,
              "new_lows": 0, "price_rises": 0}
    pending: list[PendingAlert] = []

    for p in parsed:
        row = rows.get(p.code.casefold())
        if is_first_poll:
            if row is None:
                row = Product(watch_id=watch.id, store=watch.store, code=p.code,
                              first_seen=now)
                session.add(row)
            curr = _phase(p.availability, p.in_stock)
            row.title, row.brand, row.url = p.title, p.brand, p.url
            row.basket_url, row.delivery = p.basket_url, p.delivery
            row.current_price, row.last_checked, row.last_seen = p.price, now, now
            row.spec_watts = parse_watts(p.title)
            if row.archived_at is not None:
                row.archived_at = None
            row.price_ref = p.price
            row.lowest_price = p.price
            row.availability = curr
            row.current_in_stock = curr != "oos"
            row.available_since = now if curr != "oos" else None
            continue

        if row is None:
            row = Product(watch_id=watch.id, store=watch.store, code=p.code,
                          first_seen=now)
            session.add(row)
            await session.flush()
            curr = _phase(p.availability, p.in_stock)
            row.title, row.brand, row.url = p.title, p.brand, p.url
            row.basket_url, row.delivery = p.basket_url, p.delivery
            row.current_price, row.last_checked, row.last_seen = p.price, now, now
            row.spec_watts = parse_watts(p.title)
            if row.archived_at is not None:
                row.archived_at = None
            row.price_ref = p.price
            row.lowest_price = p.price
            row.availability = "oos"
            row.current_in_stock = False
            row.available_since = None

            def _np_ok(row=row, p=p, curr=curr):
                session.add(Event(product_id=row.id, kind="new_product", price=p.price))
                row.availability = curr
                row.current_in_stock = curr != "oos"
                row.available_since = now if curr != "oos" else None
                counts["new_products"] += 1

            def _np_fail(row=row):
                row.availability = "oos"
                row.current_in_stock = False
                row.available_since = None

            price_sfx = f" — {fmt_price(p.price)}" if p.price is not None else ""
            pending.append(PendingAlert(
                row=row, kind="new_product",
                title=f"🆕 {watch.store} · New product: {p.title or p.code}",
                message=_new_product_msg(p),
                click_url=p.url or None, priority=new_product_priority,
                on_success=_np_ok, on_failure=_np_fail,
                group_line=f"🆕 {p.title or p.code}: new product{price_sfx}",
            ))
            continue

        prev = _phase(row.availability, row.current_in_stock)
        curr = _phase(p.availability, p.in_stock)
        prev_since = _utc(row.available_since)

        # Refresh metadata regardless of phase
        old_price = row.current_price
        old_delivery = row.delivery
        row.title, row.brand, row.url = p.title, p.brand, p.url
        row.basket_url = p.basket_url
        row.delivery = p.delivery
        row.current_price, row.last_checked, row.last_seen = p.price, now, now
        row.spec_watts = parse_watts(p.title)
        if row.archived_at is not None:
            row.archived_at = None

        if curr == prev:
            # No phase change — just update availability and current_in_stock
            row.availability = curr
            row.current_in_stock = curr != "oos"
        elif curr in ("early", "public"):
            # Transition into available (from oos, or early->public)
            new_since = prev_since if prev != "oos" else now
            row.available_since = new_since
            kind = "early_access" if curr == "early" else "public"
            price_sfx = f" — {fmt_price(p.price)}" if p.price is not None else ""
            if curr == "early":
                title = f"⚡ {watch.store} · Early access: {p.title or p.code}"
                msg = _early_msg(p)
                click = p.basket_url or p.url or None
                line = f"⚡ {p.title or p.code}: early access{price_sfx}"
            else:
                lbl = "Now public" if prev == "early" else "In stock"
                title = f"🟢 {watch.store} · {lbl}: {p.title or p.code}"
                msg = _public_msg(p)
                click = p.url or None
                line = f"🟢 {p.title or p.code}: in stock{price_sfx}"

            def _tr_ok(row=row, p=p, curr=curr, kind=kind):
                session.add(Event(product_id=row.id, kind=kind, price=p.price))
                row.availability = curr
                row.current_in_stock = True
                counts["early" if curr == "early" else "public"] += 1

            def _tr_fail(row=row, prev=prev, prev_since=prev_since):
                # Delivery-safe: revert
                row.availability = prev
                row.current_in_stock = prev != "oos"
                row.available_since = prev_since

            pending.append(PendingAlert(
                row=row, kind=kind, title=title, message=msg, click_url=click,
                priority=restock_priority, on_success=_tr_ok, on_failure=_tr_fail,
                group_line=line,
            ))
        else:  # curr == "oos"
            secs = (now - prev_since).total_seconds() if prev_since else None

            def _oos_ok(row=row, p=p, secs=secs):
                session.add(Event(product_id=row.id, kind="oos", price=p.price,
                                  available_seconds=int(secs) if secs else None))
                row.availability = "oos"
                row.current_in_stock = False
                row.available_since = None
                counts["oos"] += 1

            def _oos_fail(row=row, prev=prev, prev_since=prev_since):
                # Delivery-safe: keep it available
                row.availability = prev
                row.current_in_stock = True
                row.available_since = prev_since

            pending.append(PendingAlert(
                row=row, kind="oos",
                title=f"🔴 {watch.store} · Out of stock again: {p.title or p.code}",
                message=_oos_msg(p, secs), click_url=p.url or None,
                priority=oos_priority, on_success=_oos_ok, on_failure=_oos_fail,
                group_line=f"🔴 {p.title or p.code}: out of stock",
            ))

        # Price-creep reference: rises (and backfill) reset it to the current
        # price; drops leave it at the local peak so multi-tick creep
        # accumulates until the thresholds trip.
        if p.price is not None and (row.price_ref is None or p.price > row.price_ref):
            row.price_ref = p.price
        ref_price = row.price_ref if row.price_ref is not None else old_price

        # Drop/rise/new-low alerts are gated on being buyable by default;
        # an explicit price_target is exempt (state always tracks silently).
        price_alerts_ok = (not in_stock_only) or curr != "oos"

        if (price_alerts_ok and watch.track_price_drops
                and is_price_drop(ref_price, p.price, drop_min_pct, drop_min_abs)):

            def _pd_ok(row=row, p=p):
                session.add(Event(product_id=row.id, kind="price_drop", price=p.price))
                row.price_ref = p.price
                counts["price_drops"] += 1

            def _pd_fail(row=row, old_price=old_price):
                row.current_price = old_price  # delivery-safe: revert, retry next tick

            pending.append(PendingAlert(
                row=row, kind="price_drop",
                title=f"💸 {watch.store} · Price drop: {p.title or p.code}",
                message=_price_drop_msg(p, ref_price, p.price),
                click_url=p.url or None, priority=drop_priority,
                on_success=_pd_ok, on_failure=_pd_fail,
                group_line=f"💸 {p.title or p.code}: "
                           f"{fmt_price(ref_price)} → {fmt_price(p.price)}",
            ))

        if (price_alerts_ok and watch.track_price_rises
                and is_price_rise(old_price, p.price, drop_min_pct, drop_min_abs)):

            def _pr_ok(row=row, p=p):
                session.add(Event(product_id=row.id, kind="price_rise", price=p.price))
                counts["price_rises"] += 1

            def _pr_fail(row=row, old_price=old_price):
                row.current_price = old_price  # delivery-safe: revert, retry next tick

            pending.append(PendingAlert(
                row=row, kind="price_rise",
                title=f"📈 {watch.store} · Price back up: {p.title or p.code}",
                message=_price_rise_msg(p, old_price, p.price),
                click_url=p.url or None, priority=drop_priority,
                on_success=_pr_ok, on_failure=_pr_fail,
                group_line=f"📈 {p.title or p.code}: "
                           f"{fmt_price(old_price)} → {fmt_price(p.price)}",
            ))

        # All-time-low tracking. Backfill/silent when drop alerts are off;
        # otherwise lowest_price only advances via a delivered alert (or a
        # merged line on this tick's drop push) so failures retry next tick.
        is_new_low = (p.price is not None and row.lowest_price is not None
                      and p.price < row.lowest_price)
        if p.price is not None and row.lowest_price is None:
            row.lowest_price = p.price
        elif is_new_low and not (watch.track_price_drops and price_alerts_ok):
            row.lowest_price = p.price
        elif is_new_low:
            drop_alert = next((a for a in pending
                               if a.row is row and a.kind == "price_drop"), None)
            if drop_alert is not None:
                drop_alert.message = md_lines([drop_alert.message, "🏆 All-time low"])
                drop_alert.group_line += " 🏆"
                prev_ok = drop_alert.on_success

                def _nl_merged_ok(row=row, p=p, prev_ok=prev_ok):
                    prev_ok()
                    session.add(Event(product_id=row.id, kind="new_low", price=p.price))
                    row.lowest_price = p.price
                    counts["new_lows"] += 1

                drop_alert.on_success = _nl_merged_ok
            else:
                def _nl_ok(row=row, p=p):
                    session.add(Event(product_id=row.id, kind="new_low", price=p.price))
                    row.lowest_price = p.price
                    counts["new_lows"] += 1

                pending.append(PendingAlert(
                    row=row, kind="new_low",
                    title=f"🏆 {watch.store} · Lowest price ever: {p.title or p.code}",
                    message=_new_low_msg(p),
                    click_url=p.url or None, priority=drop_priority,
                    on_success=_nl_ok, on_failure=lambda: None,
                    group_line=f"🏆 {p.title or p.code}: "
                               f"{fmt_price(p.price)} all-time low",
                ))

        if (watch.price_target is not None and p.price is not None
                and p.price <= watch.price_target
                and (old_price is None or old_price > watch.price_target)):

            def _pt_ok(row=row, p=p):
                session.add(Event(product_id=row.id, kind="price_target", price=p.price))
                counts["price_targets"] += 1

            def _pt_fail(row=row, old_price=old_price):
                row.current_price = old_price  # delivery-safe: revert, retry next tick

            pending.append(PendingAlert(
                row=row, kind="price_target",
                title=f"🎯 {watch.store} · Target price hit: {p.title or p.code}",
                message=_price_target_msg(p, watch.price_target),
                click_url=p.url or None, priority=drop_priority,
                on_success=_pt_ok, on_failure=_pt_fail,
                group_line=f"🎯 {p.title or p.code}: {fmt_price(p.price)} "
                           f"≤ target {fmt_price(watch.price_target)}",
            ))

        if (prev != "oos" and curr != "oos"
                and old_delivery and p.delivery and old_delivery != p.delivery
                and is_lead_time_change_significant(
                    old_delivery, p.delivery, now, lead_time_min_days)):

            def _lt_ok(row=row, p=p):
                session.add(Event(product_id=row.id, kind="lead_time", price=p.price))
                counts["lead_time_changes"] += 1

            def _lt_fail(row=row, old_delivery=old_delivery):
                row.delivery = old_delivery  # delivery-safe: revert, retry next tick

            pending.append(PendingAlert(
                row=row, kind="lead_time",
                title=f"🚚 {watch.store} · Delivery changed: {p.title or p.code}",
                message=_lead_time_msg(p, old_delivery, p.delivery),
                click_url=p.url or None, priority=lead_time_priority,
                on_success=_lt_ok, on_failure=_lt_fail,
                group_line=f"🚚 {p.title or p.code}: delivery changed",
            ))

    # Delisted products: rows in the DB but absent from the parse would
    # otherwise stay "in stock" forever (retailers routinely delist OOS
    # items). Treat a row that is absent AND stale — last_seen older than
    # two ticks — as an OOS transition, via the same delivery-safe pending
    # machinery. The 2-tick grace avoids flapping on partial-page parses;
    # an empty parse is indistinguishable from a broken page, so skip it.
    if not is_first_poll and parsed:
        parsed_codes = {p.code for p in parsed}
        stale_after = timedelta(seconds=2 * watch.interval_seconds)
        for row in rows.values():
            if row.code in parsed_codes:
                continue
            prev = _phase(row.availability, row.current_in_stock)
            if prev == "oos":
                continue
            last_seen = _utc(row.last_seen)
            if last_seen is not None and now - last_seen < stale_after:
                continue
            prev_since = _utc(row.available_since)
            secs = (now - prev_since).total_seconds() if prev_since else None

            def _dl_ok(row=row, secs=secs):
                session.add(Event(product_id=row.id, kind="oos",
                                  price=row.current_price,
                                  available_seconds=int(secs) if secs else None))
                row.availability = "oos"
                row.current_in_stock = False
                row.available_since = None
                counts["oos"] += 1

            def _dl_fail(row=row, prev=prev, prev_since=prev_since):
                # Delivery-safe: keep it available, retry next tick
                row.availability = prev
                row.current_in_stock = True
                row.available_since = prev_since

            pending.append(PendingAlert(
                row=row, kind="oos",
                title=f"🔴 {watch.store} · No longer listed: {row.title or row.code}",
                message=_delisted_msg(row, secs),
                click_url=row.url or None, priority=oos_priority,
                on_success=_dl_ok, on_failure=_dl_fail,
                group_line=f"🔴 {row.title or row.code}: no longer listed",
            ))

    threshold = int(await get_setting(session, "alert_group_threshold", "3") or 3)
    await _dispatch(pending, cfg, sender, threshold, watch.store, now,
                    dashboard_url=dashboard_url)

    # Addendum A: update watch health on success
    watch.last_checked_at = now
    watch.last_ok_at = now
    watch.consecutive_failures = 0
    watch.last_error = ""

    await session.commit()
    return {"parsed": len(parsed), **counts}
