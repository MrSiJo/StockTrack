from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from stocktrack.models import Event, Product
from stocktrack.services.dedupe import merge_duplicate_products

T0 = datetime(2026, 6, 27, tzinfo=timezone.utc)
T1 = datetime(2026, 7, 7, tzinfo=timezone.utc)


def _p(code, first, last):
    return Product(watch_id=1, store="ao", code=code, title="Meaco 12k", brand="b",
                   url="u", availability="oos", basket_url="", current_in_stock=False,
                   first_seen=first, last_seen=last)


async def _seed_recased_pair(s):
    """Add a re-cased duplicate pair plus a real event and the false one."""
    old = _p("A-CIRRO-12K", T0, T0 + timedelta(days=10))
    new = _p("A-Cirro-12K", T1, T1 + timedelta(hours=1))
    s.add(old)
    s.add(new)
    await s.flush()
    s.add(Event(product_id=old.id, ts=T0 + timedelta(days=1), kind="public", price=519.0))
    s.add(Event(product_id=new.id, ts=T1, kind="new_product", price=519.0))  # false
    await s.commit()


async def test_merge_recased_duplicate(sessionmaker_):
    async with sessionmaker_() as s:
        await _seed_recased_pair(s)
        result = await merge_duplicate_products(s, dry_run=False)
        await s.commit()
        prods = (await s.execute(select(Product))).scalars().all()
        events = (await s.execute(select(Event))).scalars().all()
    assert len(prods) == 1
    survivor = prods[0]
    assert survivor.code == "A-Cirro-12K"          # fast-forwarded to latest casing
    assert survivor.first_seen == T0               # kept oldest history
    kinds = sorted(e.kind for e in events)
    assert kinds == ["public"]                     # false new_product dropped
    assert all(e.product_id == survivor.id for e in events)
    assert result[0]["survivor_id"] == survivor.id


async def test_dry_run_mutates_nothing(sessionmaker_):
    async with sessionmaker_() as s:
        await _seed_recased_pair(s)
        result = await merge_duplicate_products(s, dry_run=True)
        await s.commit()
        prods = (await s.execute(select(Product))).scalars().all()
        events = (await s.execute(select(Event))).scalars().all()
    # Dry-run reports the same plan but mutates nothing.
    assert len(prods) == 2
    assert len(events) == 2
    # The only non-survivor event is the false new_product, which is dropped
    # (not moved); no other event needed reassigning.
    assert result[0]["events_moved"] == 0
    assert result[0]["false_new_product_removed"] == 1
    assert len(result[0]["removed_ids"]) == 1


async def test_merge_reassigns_real_events_from_non_survivor(sessionmaker_):
    """Real events on the non-survivor row must be reassigned, not dropped.

    Only a `new_product` event postdating the survivor's first_seen is the
    false artifact of re-casing; other kinds (e.g. `public`, `oos`) on the
    non-survivor row are genuine history and must move to the survivor.
    """
    async with sessionmaker_() as s:
        old = _p("A-CIRRO-12K", T0, T0 + timedelta(days=10))
        new = _p("A-Cirro-12K", T1, T1 + timedelta(hours=1))
        s.add(old)
        s.add(new)
        await s.flush()
        # Real events on the non-survivor row that must be preserved.
        s.add(Event(product_id=new.id, ts=T1, kind="public", price=519.0))
        s.add(Event(product_id=new.id, ts=T1 + timedelta(minutes=30), kind="oos", price=519.0))
        # False new_product event on the non-survivor row, postdating
        # survivor.first_seen — this one should still be dropped.
        s.add(Event(product_id=new.id, ts=T1, kind="new_product", price=519.0))
        await s.commit()

        result = await merge_duplicate_products(s, dry_run=False)
        await s.commit()

        prods = (await s.execute(select(Product))).scalars().all()
        events = (await s.execute(select(Event))).scalars().all()

    assert len(prods) == 1
    survivor = prods[0]
    assert result[0]["survivor_id"] == survivor.id
    assert result[0]["events_moved"] == 2
    assert result[0]["false_new_product_removed"] == 1

    kinds = sorted(e.kind for e in events)
    assert kinds == ["oos", "public"]
    assert all(e.product_id == survivor.id for e in events)


async def test_idempotent_second_run_is_noop(sessionmaker_):
    async with sessionmaker_() as s:
        await _seed_recased_pair(s)
        first = await merge_duplicate_products(s, dry_run=False)
        await s.commit()
        second = await merge_duplicate_products(s, dry_run=False)
        await s.commit()
    assert len(first) == 1
    assert second == []
