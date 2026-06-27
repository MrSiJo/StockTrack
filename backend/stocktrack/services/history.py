from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Iterable, Optional


@dataclass
class Episode:
    started_ts: datetime
    early_access_ts: Optional[datetime] = None
    public_ts: Optional[datetime] = None
    ended_ts: Optional[datetime] = None
    ongoing: bool = False
    buyable_seconds: Optional[int] = None
    early_lead_seconds: Optional[int] = None
    price: Optional[float] = None


def _finalize(ep: Episode) -> Episode:
    if ep.early_access_ts and ep.public_ts:
        ep.early_lead_seconds = int((ep.public_ts - ep.early_access_ts).total_seconds())
    return ep


def build_episodes(events: Iterable, now: datetime) -> "list[Episode]":
    """Reconstruct buyable episodes from one product's event rows.

    Pure: takes the events and a `now` (for the duration of a still-open
    episode); no DB or clock access. Events need .ts, .kind, .price,
    .available_seconds. An `oos` with no open episode (log starts mid-OOS) is
    ignored; a trailing in-stock spell with no `oos` is an ongoing episode.
    """
    episodes: list[Episode] = []
    cur: Optional[Episode] = None
    for e in sorted(events, key=lambda x: x.ts):
        if e.kind in ("early_access", "public"):
            if cur is None:
                cur = Episode(started_ts=e.ts)
            if e.kind == "early_access" and cur.early_access_ts is None:
                cur.early_access_ts = e.ts
            if e.kind == "public" and cur.public_ts is None:
                cur.public_ts = e.ts
            if e.price is not None:
                cur.price = e.price
        elif e.kind == "oos":
            if cur is not None:
                cur.ended_ts = e.ts
                cur.buyable_seconds = (
                    e.available_seconds
                    if e.available_seconds is not None
                    else int((e.ts - cur.started_ts).total_seconds())
                )
                episodes.append(_finalize(cur))
                cur = None
            # else: OOS with no open episode -> nothing to close
    if cur is not None:
        cur.ongoing = True
        cur.buyable_seconds = int((now - cur.started_ts).total_seconds())
        episodes.append(_finalize(cur))
    return episodes


def build_history(products_events, now: datetime, store: "str | None" = None) -> "list[dict]":
    """Group reconstructed episodes by product with summary stats.

    products_events: iterable of (product, events) where product exposes
    .id/.title/.store/.url/.basket_url. Returns the API shape; products with no
    episodes are omitted; episodes are ordered ongoing-first then newest-first.
    """
    out = []
    for product, events in products_events:
        if store and product.store != store:
            continue
        eps = build_episodes(events, now)
        if not eps:
            continue
        eps.sort(key=lambda e: (e.ongoing, e.started_ts), reverse=True)  # ongoing first, newest first
        completed = [e for e in eps if not e.ongoing]
        buyables = [e.buyable_seconds for e in completed if e.buyable_seconds is not None]
        leads = [e.early_lead_seconds for e in completed if e.early_lead_seconds is not None]
        out.append({
            "product": {"id": product.id, "title": product.title, "store": product.store,
                        "url": product.url, "basket_url": product.basket_url},
            "summary": {"episodes": len(eps),
                        "avg_buyable_seconds": (mean(buyables) if buyables else None),
                        "avg_early_lead_seconds": (mean(leads) if leads else None)},
            "episodes": [
                {"started_ts": e.started_ts, "early_access_ts": e.early_access_ts,
                 "public_ts": e.public_ts, "ended_ts": e.ended_ts, "ongoing": e.ongoing,
                 "buyable_seconds": e.buyable_seconds, "early_lead_seconds": e.early_lead_seconds,
                 "price": e.price}
                for e in eps],
        })
    return out
