"""One-off merge of case-insensitive duplicate products (re-casing artifact)."""
from sqlalchemy import select

from stocktrack.models import Event, Product

# Survivor state fast-forwarded to the most-recently-seen duplicate row.
_FAST_FORWARD_ATTRS = (
    "code", "title", "current_price", "current_in_stock", "availability",
    "delivery", "basket_url", "url", "last_seen", "last_checked", "spec_watts",
)


async def merge_duplicate_products(session, *, dry_run: bool = False) -> list[dict]:
    """Merge active products that share a watch and a case-folded code.

    Keeps the earliest-``first_seen`` row (richest history) as survivor,
    fast-forwards its current-state fields to the most-recently-seen row,
    reassigns other rows' events to it, drops the false ``new_product`` events
    the re-casing produced, and deletes the emptied duplicate rows.

    ``dry_run=True`` mutates nothing but still returns the records describing
    what would happen. Running twice is a no-op: after a merge no group has
    more than one active row, so the second pass finds nothing.
    """
    products = (await session.execute(
        select(Product).where(Product.archived_at.is_(None))
    )).scalars().all()

    groups: dict[tuple[int, str], list[Product]] = {}
    for p in products:
        groups.setdefault((p.watch_id, p.code.casefold()), []).append(p)

    results = []
    for (watch_id, _), members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda p: p.first_seen)
        survivor = members[0]
        newest = max(members, key=lambda p: p.last_seen)
        removed = [p for p in members if p.id != survivor.id]
        member_ids = {p.id for p in members}

        events = (await session.execute(select(Event))).scalars().all()
        moved = 0
        dropped = 0
        for e in events:
            if e.product_id not in member_ids:
                continue
            # Drop the false new_product event introduced by re-casing:
            # a new_product on a non-survivor row that post-dates the
            # survivor's first_seen.
            if e.kind == "new_product" and e.product_id != survivor.id \
                    and e.ts > survivor.first_seen:
                if not dry_run:
                    await session.delete(e)
                dropped += 1
                continue
            if e.product_id != survivor.id:
                if not dry_run:
                    e.product_id = survivor.id
                moved += 1

        if not dry_run:
            # Delete the emptied duplicate rows and flush BEFORE fast-forwarding
            # the survivor's code. The (watch_id, code) unique constraint would
            # otherwise be violated while the newest row still holds that code.
            for p in removed:
                await session.delete(p)
            await session.flush()
            for attr in _FAST_FORWARD_ATTRS:
                setattr(survivor, attr, getattr(newest, attr))

        results.append({
            "watch_id": watch_id,
            "survivor_id": survivor.id,
            "removed_ids": [p.id for p in removed],
            "events_moved": moved,
            "false_new_product_removed": dropped,
        })
    return results
