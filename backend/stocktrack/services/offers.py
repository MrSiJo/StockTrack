"""Offers: one listing, many sellers, several variants (plugin API 2).

Core never interprets a variant label or an ``extra`` value. It stores what the
handler reports, records silent ``ProductChange`` rows when a price or the
discounts change, and works out what each audience would pay.
"""
import json
from collections import OrderedDict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from stocktrack.models import Product, ProductChange
from stocktrack.sites.base import DISCOUNT_AUDIENCES, Discount

AUDIENCES = ("new_customer", "returning_customer")


def discounts_to_json(discounts) -> Optional[str]:
    """None (unknown) stays None; a list becomes a stable JSON string."""
    if discounts is None:
        return None
    out = []
    for d in discounts:
        row = asdict(d) if isinstance(d, Discount) else dict(d)
        if row.get("audience") not in DISCOUNT_AUDIENCES:
            row["audience"] = "any"
        out.append(row)
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


def apply_offer_fields(session, row: Product, p, now, *, old_price=None,
                       record: bool) -> None:
    """Copy the offer fields from a parsed product onto its row.

    With ``record`` (every poll except a row's first sighting) a change of
    price against ``old_price``, or of the discounts, adds a ``ProductChange``.
    """
    new_discounts = discounts_to_json(getattr(p, "discounts", None))
    if record and row.id is not None:
        if (old_price is not None and p.price is not None
                and float(old_price) != float(p.price)):
            session.add(ProductChange(product_id=row.id, ts=now, field="price",
                                      old=_fmt(old_price), new=_fmt(p.price)))
        if new_discounts != row.discounts_json:
            session.add(ProductChange(product_id=row.id, ts=now, field="discounts",
                                      old=row.discounts_json, new=new_discounts))
    row.variant = getattr(p, "variant", "") or ""
    row.seller = getattr(p, "seller", "") or ""
    row.seller_rating = getattr(p, "seller_rating", None)
    row.discounts_json = new_discounts
    extra = getattr(p, "extra", None) or {}
    row.extra_json = json.dumps({str(k): str(v) for k, v in extra.items()},
                                sort_keys=True) if extra else ""


def _saving(price: float, d: dict) -> float:
    if d.get("amount") is not None:
        return float(d["amount"])
    if d.get("percent") is not None:
        return price * float(d["percent"]) / 100.0
    return 0.0


def audience_price(price: Optional[float], discounts: Optional[list[dict]],
                   audience: str) -> Optional[float]:
    """List price less the single best discount for ``audience`` or ``any``.

    None when the price or the discounts are unknown. Never below zero.
    """
    if price is None or discounts is None:
        return None
    best = max((_saving(price, d) for d in discounts
                if d.get("audience", "any") in (audience, "any")), default=0.0)
    return round(max(price - best, 0.0), 2)


def offer_dict(p: Product) -> dict:
    discounts = discounts_from_json(p.discounts_json)
    return {
        "product_id": p.id, "code": p.code, "title": p.title, "url": p.url,
        "seller": p.seller, "seller_rating": p.seller_rating,
        "price": p.current_price,
        "price_new_customer": audience_price(p.current_price, discounts, "new_customer"),
        "price_returning_customer": audience_price(
            p.current_price, discounts, "returning_customer"),
        "discounts": discounts, "extra": extra_from_json(p.extra_json),
        "last_seen": p.last_seen,
    }


def _price_key(o: dict):
    return (o["price"] is None, o["price"] if o["price"] is not None else 0.0,
            o["seller"].casefold(), o["code"])


def group_offers(products, *, variant: Optional[str] = None,
                 min_rating: Optional[float] = None) -> list[dict]:
    """Available, unarchived products grouped by variant (first seen order),
    each group sorted by list price."""
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
    return any(p.variant for p in products)


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
