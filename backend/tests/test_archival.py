from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from stocktrack.models import Product
from stocktrack.services.archival import archive_stale_products

def _p(**kw):
    base = dict(watch_id=1, store="s", code="c", title="t", brand="b", url="u",
               availability="oos", basket_url="", current_in_stock=False,
               first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))
    base.update(kw)
    return Product(**base)

async def test_archives_stale_oos_only(sessionmaker_):
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    async with sessionmaker_() as s:
        s.add_all([
            _p(code="old-oos", last_seen=now - timedelta(days=20)),          # archive
            _p(code="recent-oos", last_seen=now - timedelta(days=3)),        # keep
            _p(code="old-instock", current_in_stock=True, availability="public",
               last_seen=now - timedelta(days=20)),                         # keep (in stock)
        ])
        await s.commit()
        n = await archive_stale_products(s, days=14, now=now)
        await s.commit()
        archived = {p.code: p.archived_at for p in
                    (await s.execute(select(Product))).scalars().all()}
    assert n == 1
    assert archived["old-oos"] == now
    assert archived["recent-oos"] is None
    assert archived["old-instock"] is None
