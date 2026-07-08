from datetime import datetime, timezone

from stocktrack.models import Product


def _mk(**kw):
    base = dict(watch_id=1, store="s", code="c", title="t", brand="b", url="u",
               availability="public", basket_url="", current_in_stock=True,
               first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc))
    base.update(kw)
    return Product(**base)


async def test_status_excludes_archived_and_reports_ppw(sessionmaker_, client):
    async with sessionmaker_() as s:
        from stocktrack.models import Watch
        s.add(Watch(store="s", url="u", label="L", include_filter="", exclude_filter="",
                    interval_seconds=300, enabled=True, consecutive_failures=0, last_error=""))
        s.add(_mk(code="live", current_price=127.14, spec_watts=475))
        s.add(_mk(code="gone", archived_at=datetime.now(timezone.utc)))
        await s.commit()
    r = await client.get("/api/status")
    prods = r.json()[0]["products"]
    codes = {p["code"] for p in prods}
    assert codes == {"live"}
    live = prods[0]
    assert live["spec_watts"] == 475
    assert round(live["price_per_watt"], 4) == round(127.14 / 475, 4)
