"""Offers: one listing, many sellers, several variants (plugin API 2).

Core never interprets a variant label or an ``extra`` value. It stores what the
handler reports, records silent ``ProductChange`` rows when a price or the
discounts change, and works out what each audience would pay.
"""
import json
import logging
from collections import OrderedDict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from stocktrack.models import Product, ProductChange
from stocktrack.sites.base import DISCOUNT_AUDIENCES, Discount

AUDIENCES = ("new_customer", "returning_customer")

log = logging.getLogger(__name__)


def _num(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def discounts_to_json(discounts) -> Optional[str]:
    """None (unknown) stays None; a list becomes a stable JSON string.

    A discount with an unrecognised audience, or with neither a numeric amount
    nor percent, is dropped: applying it to everyone would show a price nobody
    can get. A value that is not a list at all reads as unknown.
    """
    if discounts is None or not isinstance(discounts, (list, tuple)):
        return None
    out = []
    for d in discounts:
        if isinstance(d, Discount):
            row = asdict(d)
        elif isinstance(d, dict):
            row = dict(d)
        else:
            log.warning("offers: ignoring discount %r (not a Discount)", d)
            continue
        if row.get("audience") not in DISCOUNT_AUDIENCES:
            log.warning("offers: ignoring discount with audience %r",
                        row.get("audience"))
            continue
        row["amount"], row["percent"] = _num(row.get("amount")), _num(row.get("percent"))
        if row["amount"] is None and row["percent"] is None:
            continue
        row["code"], row["text"] = str(row.get("code") or ""), str(row.get("text") or "")
        out.append({k: row[k] for k in ("audience", "amount", "percent", "code", "text")})
    return json.dumps(out, sort_keys=True)


def discounts_from_json(raw: Optional[str]) -> Optional[list[dict]]:
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def extra_from_json(raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _fmt(v) -> Optional[str]:
    return None if v is None else repr(float(v))


async def _last_recorded_price(session, product_id) -> Optional[float]:
    raw = (await session.execute(
        select(ProductChange.new)
        .where(ProductChange.product_id == product_id,
               ProductChange.field == "price")
        .order_by(ProductChange.ts.desc(), ProductChange.id.desc())
        .limit(1))).scalar_one_or_none()
    return _num(raw)


async def apply_offer_fields(session, row: Product, p, now, *, old_price=None,
                             record: bool) -> None:
    """Copy the offer fields from a parsed product onto its row.

    With ``record`` (every poll except a row's first sighting) a change of
    price or of the discounts adds a ``ProductChange``. A price is compared
    with the last recorded change when there is one, else with ``old_price``:
    a failed push reverts ``current_price``, and a price can be missing for a
    poll, so ``old_price`` alone would record one move twice or lose it.
    """
    new_discounts = discounts_to_json(getattr(p, "discounts", None))
    new_price = _num(p.price)
    if record and row.id is not None:
        if new_price is not None:
            base = await _last_recorded_price(session, row.id)
            if base is None:
                base = _num(old_price)
            if base is not None and base != new_price:
                session.add(ProductChange(product_id=row.id, ts=now, field="price",
                                          old=_fmt(base), new=_fmt(new_price)))
        if new_discounts != row.discounts_json:
            session.add(ProductChange(product_id=row.id, ts=now, field="discounts",
                                      old=row.discounts_json, new=new_discounts))
    row.variant = str(getattr(p, "variant", "") or "")
    row.seller = str(getattr(p, "seller", "") or "")
    row.seller_rating = _num(getattr(p, "seller_rating", None))
    row.discounts_json = new_discounts
    audience = getattr(p, "price_audience", "any")
    row.price_audience = audience if audience in DISCOUNT_AUDIENCES else "any"
    extra = getattr(p, "extra", None)
    row.extra_json = json.dumps({str(k): str(v) for k, v in extra.items()},
                                sort_keys=True) if isinstance(extra, dict) and extra else ""


def _saving(price: float, d: dict) -> float:
    amount, percent = _num(d.get("amount")), _num(d.get("percent"))
    if amount is not None:
        return amount
    if percent is not None:
        return price * percent / 100.0
    return 0.0


def list_price(price: Optional[float], discounts: Optional[list[dict]],
               price_audience: str = "any") -> Optional[float]:
    """The price before any discount.

    A price quoted for an audience has that audience's discount (or an "any"
    one) already taken off: add it back. None when that discount is unknown
    or cannot be told apart from another one.
    """
    if price is None or price_audience == "any":
        return price
    if discounts is None:
        return None
    taken = [d for d in discounts if d.get("audience", "any") in (price_audience, "any")]
    if not taken:
        return price
    if len(taken) > 1:
        return None
    amount, percent = _num(taken[0].get("amount")), _num(taken[0].get("percent"))
    if amount is not None:
        return round(price + amount, 2)
    if percent is not None and 0 < percent < 100:
        return round(price / (1 - percent / 100.0), 2)
    return None


def audience_price(price: Optional[float], discounts: Optional[list[dict]],
                   audience: str, price_audience: str = "any") -> Optional[float]:
    """List price less the single best discount for ``audience`` or ``any``.

    A price quoted for ``audience`` itself is returned as is, even when the
    discounts are unknown. Otherwise None when the price, the list price or
    the discounts are unknown. Never below zero.
    """
    if price is None:
        return None
    if price_audience == audience:
        return price
    base = list_price(price, discounts, price_audience)
    if base is None or discounts is None:
        return None
    best = max((_saving(base, d) for d in discounts
                if d.get("audience", "any") in (audience, "any")), default=0.0)
    return round(max(base - best, 0.0), 2)


def offer_dict(p: Product) -> dict:
    discounts = discounts_from_json(p.discounts_json)
    quoted_for = p.price_audience or "any"
    return {
        "product_id": p.id, "code": p.code, "title": p.title, "url": p.url,
        "seller": p.seller, "seller_rating": p.seller_rating,
        "price": p.current_price, "price_audience": quoted_for,
        "list_price": list_price(p.current_price, discounts, quoted_for),
        "price_new_customer": audience_price(
            p.current_price, discounts, "new_customer", quoted_for),
        "price_returning_customer": audience_price(
            p.current_price, discounts, "returning_customer", quoted_for),
        "discounts": discounts, "extra": extra_from_json(p.extra_json),
        "last_seen": p.last_seen,
    }


def _price_key(o: dict):
    # Cheapest to start with first: the new customer price, else the quoted one.
    best = o["price_new_customer"] if o["price_new_customer"] is not None else o["price"]
    return (best is None, best if best is not None else 0.0,
            o["seller"].casefold(), o["code"])


def group_offers(products, *, variant: Optional[str] = None,
                 min_rating: Optional[float] = None) -> list[dict]:
    """Available, unarchived products grouped by variant (first seen order),
    each group cheapest to start with first."""
    rows = sorted((p for p in products
                   if p.current_in_stock and p.archived_at is None),
                  key=lambda p: (p.first_seen, p.id))
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for p in rows:
        if variant is not None and p.variant != variant:
            continue
        if min_rating is not None and (p.seller_rating is None
                                       or p.seller_rating < min_rating):
            continue
        groups.setdefault(p.variant, []).append(offer_dict(p))
    return [{"variant": v, "offers": sorted(offers, key=_price_key)}
            for v, offers in groups.items()]


def has_variants(products) -> bool:
    return any(p.variant and p.archived_at is None for p in products)


async def recent_changes(session, product_ids, since) -> list[ProductChange]:
    if not product_ids:
        return []
    return list((await session.execute(
        select(ProductChange)
        .where(ProductChange.product_id.in_(list(product_ids)),
               ProductChange.ts >= since)
        .order_by(ProductChange.ts.desc(), ProductChange.id.desc())
    )).scalars().all())


def summarise_changes(products, changes, *, limit: int = 200) -> list[dict]:
    """Per variant counts of price and discount changes, plus the raw list."""
    by_id = {p.id: p for p in products}
    order = [p.variant for p in sorted(products, key=lambda p: (p.first_seen, p.id))]
    stats: "OrderedDict[str, dict]" = OrderedDict(
        (v, {"variant": v, "price_changes": 0, "offers_with_price_change": 0,
             "max_abs_change": None, "mean_abs_change": None,
             "discount_changes": 0, "changes": []})
        for v in dict.fromkeys(order))
    moved: dict[str, set] = {}
    deltas: dict[str, list[float]] = {}
    for c in changes:
        p = by_id.get(c.product_id)
        if p is None:
            continue
        s = stats[p.variant]
        if c.field == "price":
            s["price_changes"] += 1
            moved.setdefault(p.variant, set()).add(p.id)
            try:
                deltas.setdefault(p.variant, []).append(
                    abs(float(c.new) - float(c.old)))
            except (TypeError, ValueError):
                pass
        elif c.field == "discounts":
            s["discount_changes"] += 1
        if len(s["changes"]) < limit:
            s["changes"].append({"ts": c.ts, "product_id": p.id, "seller": p.seller,
                                 "code": p.code, "field": c.field,
                                 "old": c.old, "new": c.new})
    for v, s in stats.items():
        s["offers_with_price_change"] = len(moved.get(v, ()))
        d = deltas.get(v)
        if d:
            s["max_abs_change"] = round(max(d), 2)
            s["mean_abs_change"] = round(sum(d) / len(d), 2)
    return list(stats.values())


def window_start(days: int, now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=max(days, 0))
