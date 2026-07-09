from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean, median, quantiles
from typing import Iterable, Optional
from zoneinfo import ZoneInfo


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


def availability_stats(episodes: "list[Episode]", now: datetime,
                       window_days: int = 7) -> dict:
    """Pure availability roll-up over a trailing window.

    uptime_pct = buyable seconds overlapping the window / window length;
    typical_window_seconds = median full duration of episodes touching the
    window (ongoing ones measured to ``now``).
    """
    window_start = now - timedelta(days=window_days)
    window_secs = window_days * 86400
    overlap_total = 0.0
    durations = []
    n = 0
    for ep in episodes:
        end = ep.ended_ts if ep.ended_ts is not None else now
        o_start = max(ep.started_ts, window_start)
        o_end = min(end, now)
        if o_end <= o_start:
            continue
        n += 1
        overlap_total += (o_end - o_start).total_seconds()
        if ep.buyable_seconds is not None:
            durations.append(ep.buyable_seconds)
    return {
        "uptime_pct": round(100 * overlap_total / window_secs, 1),
        "typical_window_seconds": int(median(durations)) if durations else None,
        "episodes_in_window": n,
    }


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
                        "avg_early_lead_seconds": (mean(leads) if leads else None),
                        **availability_stats(eps, now)},
            "episodes": [
                {"started_ts": e.started_ts, "early_access_ts": e.early_access_ts,
                 "public_ts": e.public_ts, "ended_ts": e.ended_ts, "ongoing": e.ongoing,
                 "buyable_seconds": e.buyable_seconds, "early_lead_seconds": e.early_lead_seconds,
                 "price": e.price}
                for e in eps],
        })
    return out


# Kinds that represent a transition *into* availability. Real Event rows use
# "early_access" (see poller.py) rather than "early", but the pattern is kept
# permissive — the spec calls it "early" and a bare "restock" kind isn't
# currently emitted anywhere either, so both spellings are accepted to avoid
# silently dropping real early-access restocks.
_RESTOCK_KINDS = {"public", "early", "early_access", "restock"}


def _hhmm(minutes: int) -> str:
    minutes = int(round(minutes)) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def restock_pattern(events, tz: str = "Europe/London", now=None) -> dict:
    """Aggregate restock (into-availability) events into a local-time pattern.

    Timestamps are converted to ``tz`` (DST-aware via zoneinfo) before bucketing,
    then summarised as a centre time (median) plus a typical interquartile band.
    """
    zone = ZoneInfo(tz)
    by_hour = [0] * 24
    by_weekday = [0] * 7
    minutes: list[int] = []
    for e in events:
        if e.kind not in _RESTOCK_KINDS:
            continue
        ts = e.ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        local = ts.astimezone(zone)
        by_hour[local.hour] += 1
        by_weekday[local.weekday()] += 1
        minutes.append(local.hour * 60 + local.minute)

    samples = len(minutes)
    base = {"samples": samples, "by_hour": by_hour, "by_weekday": by_weekday}
    if samples < 3:
        return {**base, "summary": "Not enough data yet"}

    centre = median(minutes)
    if samples >= 4:
        q1, _, q3 = quantiles(minutes, n=4)
        lo, hi = q1, q3
    else:  # n == 3: quartiles are noisy; use the honest full span
        lo, hi = min(minutes), max(minutes)
    band = hi - lo

    weekday_hits = sum(by_weekday[:5])
    if weekday_hits >= samples / 2:
        when = "weekday mornings" if centre < 720 else "weekdays"
    else:
        when = "any day"

    if band > 90:
        summary = f"Restock time varies: mostly {_hhmm(lo)}–{_hhmm(hi)} · {when}"
    elif band <= 20:
        summary = f"Usually restocks around {_hhmm(centre)} · {when}"
    else:
        summary = (f"Usually restocks around {_hhmm(centre)}, "
                   f"typically {_hhmm(lo)}–{_hhmm(hi)} · {when}")
    if samples < 5:
        summary += f" (only {samples} seen)"

    return {**base, "summary": summary}
