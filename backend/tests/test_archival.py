from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from stocktrack.models import Product
from stocktrack.services.archival import archive_stale_products, archival_tick
from stocktrack.services.settings_service import set_value

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


async def test_archive_boundary_exact_days_not_archived(sessionmaker_):
    """A product last seen EXACTLY `days` days ago must NOT be archived —
    the cutoff comparison is strict `<`."""
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    async with sessionmaker_() as s:
        s.add(_p(code="exact-boundary", last_seen=now - timedelta(days=14)))
        await s.commit()
        n = await archive_stale_products(s, days=14, now=now)
        await s.commit()
        p = (await s.execute(
            select(Product).where(Product.code == "exact-boundary")
        )).scalar_one()
    assert n == 0
    assert p.archived_at is None


async def test_archive_boundary_just_past_days_is_archived(sessionmaker_):
    """One second past the exact boundary IS archived — pins the cutoff
    from the other side."""
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    async with sessionmaker_() as s:
        s.add(_p(code="just-past-boundary",
                  last_seen=now - timedelta(days=14, seconds=1)))
        await s.commit()
        n = await archive_stale_products(s, days=14, now=now)
        await s.commit()
        p = (await s.execute(
            select(Product).where(Product.code == "just-past-boundary")
        )).scalar_one()
    assert n == 1
    assert p.archived_at == now


async def test_archive_stale_products_skips_already_archived(sessionmaker_):
    """Idempotency: a pre-archived product is left untouched and not
    re-counted; only the fresh stale product is archived."""
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    pre_archived_at = now - timedelta(days=5)
    async with sessionmaker_() as s:
        s.add_all([
            _p(code="already-archived", last_seen=now - timedelta(days=30),
               archived_at=pre_archived_at),
            _p(code="fresh-stale", last_seen=now - timedelta(days=20)),
        ])
        await s.commit()
        n = await archive_stale_products(s, days=14, now=now)
        await s.commit()
        rows = {p.code: p.archived_at for p in
                (await s.execute(select(Product))).scalars().all()}
    assert n == 1
    assert rows["already-archived"] == pre_archived_at
    assert rows["fresh-stale"] == now


async def test_archival_tick_archives_using_setting(sessionmaker_):
    """archival_tick reads product_archive_days from settings and archives
    stale OOS products through a fresh session per call."""
    stale_last_seen = datetime.now(timezone.utc) - timedelta(days=20)
    async with sessionmaker_() as s:
        await set_value(s, "product_archive_days", "14")
        s.add(_p(code="tick-stale", last_seen=stale_last_seen))
        await s.commit()

    await archival_tick(lambda: sessionmaker_())

    async with sessionmaker_() as s:
        p = (await s.execute(
            select(Product).where(Product.code == "tick-stale")
        )).scalar_one()
    assert p.archived_at is not None


async def test_archival_tick_disabled_with_zero_setting(sessionmaker_):
    """product_archive_days = "0" disables archiving entirely."""
    stale_last_seen = datetime.now(timezone.utc) - timedelta(days=20)
    async with sessionmaker_() as s:
        await set_value(s, "product_archive_days", "0")
        s.add(_p(code="tick-disabled", last_seen=stale_last_seen))
        await s.commit()

    await archival_tick(lambda: sessionmaker_())

    async with sessionmaker_() as s:
        p = (await s.execute(
            select(Product).where(Product.code == "tick-disabled")
        )).scalar_one()
    assert p.archived_at is None
