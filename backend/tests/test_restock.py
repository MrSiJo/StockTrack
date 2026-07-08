from datetime import datetime, timezone
from types import SimpleNamespace

from stocktrack.models import Event, Product, Watch
from stocktrack.services.history import restock_pattern


def _ev(hour, kind="public", day=6):
    return SimpleNamespace(ts=datetime(2026, 7, day, hour, 20, tzinfo=timezone.utc), kind=kind)


def test_restock_pattern_summarises_morning_cluster():
    events = [_ev(6), _ev(6), _ev(7), _ev(6, kind="early")]
    pat = restock_pattern(events)
    assert pat["samples"] == 4
    assert pat["by_hour"][6] == 3
    assert pat["by_hour"][7] == 1
    assert "06:00" in pat["summary"] or "06:" in pat["summary"]


def test_restock_pattern_ignores_non_restock_and_reports_sparse():
    pat = restock_pattern([_ev(6, kind="oos"), _ev(9, kind="price_drop")])
    assert pat["samples"] == 0
    assert pat["summary"] == "Not enough data yet"


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
            Event(product_id=p.id, ts=datetime(2026, 7, 6, 6, 0, tzinfo=timezone.utc), kind="public"),
            Event(product_id=p.id, ts=datetime(2026, 7, 7, 6, 5, tzinfo=timezone.utc), kind="public"),
            Event(product_id=p.id, ts=datetime(2026, 7, 8, 6, 10, tzinfo=timezone.utc), kind="public"),
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
    assert "06:00" in entry["summary"]
