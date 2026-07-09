from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from stocktrack.models import Event, Product, Watch
from stocktrack.services.history import restock_pattern


def _ev(dt, kind="public"):
    return SimpleNamespace(ts=dt, kind=kind)


def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def test_dst_bst_and_gmt_map_to_same_local_hour():
    # July 05:20 UTC (BST -> 06:20 local) and Jan 06:20 UTC (GMT -> 06:20 local)
    evs = [_ev(_utc(2026, 7, 1, 5, 20)), _ev(_utc(2026, 7, 2, 5, 22)),
           _ev(_utc(2026, 1, 5, 6, 20)), _ev(_utc(2026, 1, 6, 6, 18))]
    pat = restock_pattern(evs, tz="Europe/London")
    assert pat["samples"] == 4
    assert pat["by_hour"][6] == 4          # all bucket to LOCAL 06:xx
    assert "06:" in pat["summary"]         # centre is ~06:20 local, not 05:00


def test_tight_cluster_shows_centre_only():
    evs = [_ev(_utc(2026, 7, d, 5, 15)) for d in range(1, 6)]  # 06:15 local, tight
    pat = restock_pattern(evs, tz="Europe/London")
    assert "around 06:15" in pat["summary"]
    assert "typically" not in pat["summary"]           # band <= 20 -> collapsed
    assert "weekday" in pat["summary"]


def test_moderate_spread_shows_range():
    # local ~06:05..07:05 spread (>20, <=90); offsets in minutes past 05:00 UTC
    # (65 overflows the hour, so build via timedelta rather than a raw minute arg)
    offsets = [5, 20, 35, 50, 65]
    evs = [_ev(_utc(2026, 7, 6, 5, 0) + timedelta(minutes=m)) for m in offsets]
    pat = restock_pattern(evs, tz="Europe/London")
    assert "typically" in pat["summary"] and "–" in pat["summary"]
    assert "around 06:" in pat["summary"]


def test_wide_spread_reads_varies():
    # local spread > 90 min
    evs = [_ev(_utc(2026, 7, 6, 4, 40)), _ev(_utc(2026, 7, 6, 5, 10)),
           _ev(_utc(2026, 7, 7, 6, 30)), _ev(_utc(2026, 7, 8, 7, 10)),
           _ev(_utc(2026, 7, 9, 8, 0))]
    pat = restock_pattern(evs, tz="Europe/London")
    assert pat["summary"].startswith("Restock time varies")


def test_low_samples_hint():
    evs = [_ev(_utc(2026, 7, 1, 5, 15)), _ev(_utc(2026, 7, 2, 5, 16)),
           _ev(_utc(2026, 7, 3, 5, 17))]
    pat = restock_pattern(evs, tz="Europe/London")
    assert pat["summary"].endswith("(only 3 seen)")


def test_sparse_and_non_restock_ignored():
    assert restock_pattern([_ev(_utc(2026, 7, 1, 6, 0), kind="oos")],
                           tz="Europe/London")["summary"] == "Not enough data yet"
    assert restock_pattern([], tz="Europe/London")["samples"] == 0


async def test_restock_patterns_endpoint_returns_one_entry_per_watch(client, sessionmaker_):
    async with sessionmaker_() as s:
        w = Watch(store="ao", url="https://ao.com/l/example", label="AO fryers")
        s.add(w)
        await s.flush()
        p = Product(watch_id=w.id, store="ao", code="A-16K", title="AO Cirro 16K",
                    url="https://ao.com/p/16k", basket_url="https://ao.com/basket?items=A-16K:1")
        s.add(p)
        await s.flush()
        s.add_all([
            Event(product_id=p.id, ts=datetime(2026, 7, 6, 5, 0, tzinfo=timezone.utc), kind="public"),
            Event(product_id=p.id, ts=datetime(2026, 7, 7, 5, 5, tzinfo=timezone.utc), kind="public"),
            Event(product_id=p.id, ts=datetime(2026, 7, 8, 5, 10, tzinfo=timezone.utc), kind="public"),
        ])
        await s.commit()

    r = await client.get("/api/restock-patterns")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    entry = data[0]
    assert entry["watch_id"] == w.id
    assert entry["store"] == "ao"
    assert entry["label"] == "AO fryers"
    assert entry["samples"] == 3
    assert entry["by_hour"][6] == 3
    assert "06:0" in entry["summary"]
