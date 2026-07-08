"""One-off check CLI for ops and parity checks."""
import argparse
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("stocktrack.cli")


async def _run_check(store: str, url: str, include: str, exclude: str,
                     postcode: str = "", branch: str = "") -> dict:
    from stocktrack.sites import get_handler

    handler = get_handler(store)
    handler.configure(cp_delivery_postcode=postcode, cp_collection_branch_id=branch)
    log.info("Fetching %s ...", url)
    raw = await asyncio.to_thread(handler.fetch, url)

    all_prods = handler.parse(raw)
    log.info("Parsed %d products total", len(all_prods))

    from stocktrack.services.poller import matches
    filtered = [p for p in all_prods if p.code and matches(p, include, exclude)]
    log.info("Matched %d after filters (include=%r, exclude=%r)", len(filtered), include, exclude)

    return {
        "store": store,
        "parsed": len(all_prods),
        "matched": len(filtered),
        "products": [
            {
                "code": p.code,
                "title": p.title,
                "in_stock": p.in_stock,
                "availability": p.availability,
                "price": p.price,
                "url": p.url,
                "basket_url": p.basket_url,
            }
            for p in filtered
        ],
    }


async def _run_merge(dry_run: bool) -> list[dict]:
    """Open a session against the app DB and merge re-cased duplicate products."""
    from stocktrack.bootstrap import get_settings
    from stocktrack.db import init_models, make_engine, make_sessionmaker
    from stocktrack.services.dedupe import merge_duplicate_products

    env = get_settings()
    engine = make_engine(env.database_url)
    try:
        await init_models(engine)
        sm = make_sessionmaker(engine)
        async with sm() as s:
            result = await merge_duplicate_products(s, dry_run=dry_run)
            if not dry_run:
                await s.commit()
        return result
    finally:
        await engine.dispose()


def _merge_main(argv) -> list[dict]:
    parser = argparse.ArgumentParser(
        prog="stocktrack merge-duplicates",
        description="Merge case-insensitive duplicate products (re-casing cleanup)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without mutating the DB")
    args = parser.parse_args(argv)

    result = asyncio.run(_run_merge(args.dry_run))

    import json
    log.info("%s: %d duplicate group(s) %s",
             "DRY RUN" if args.dry_run else "MERGED",
             len(result), "would be merged" if args.dry_run else "merged")
    print(json.dumps(result, indent=2))
    return result


def _check_main(argv) -> dict:
    parser = argparse.ArgumentParser(description="StockTrack one-off check")
    parser.add_argument("store", help="Store name (e.g. ao, johnlewis)")
    parser.add_argument("url", help="Listing URL to fetch")
    parser.add_argument("--include", default="", help="Include filter (comma-separated)")
    parser.add_argument("--exclude", default="", help="Exclude filter (comma-separated)")
    parser.add_argument("--postcode", default="", help="Delivery postcode (City Plumbing)")
    parser.add_argument("--branch", default="", help="Collection branch ID (City Plumbing)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args(argv)

    result = asyncio.run(_run_check(args.store, args.url, args.include, args.exclude,
                                    args.postcode, args.branch))

    if args.json:
        import json
        print(json.dumps(result, indent=2))
    else:
        print(f"Store: {result['store']}")
        print(f"Parsed: {result['parsed']} products, matched: {result['matched']}")
        for p in result["products"]:
            stock = "IN STOCK" if p["in_stock"] else "OOS"
            avail = f" [{p['availability']}]" if p["availability"] else ""
            price = f" £{p['price']:.2f}" if p["price"] else ""
            print(f"  [{stock}{avail}]{price} {p['title']} ({p['code']})")
    return result


def main(argv=None):
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    # First arg selects the subcommand; anything else is the legacy store check
    # (`stocktrack.cli ao <url>`), which stays backward compatible.
    if argv and argv[0] == "merge-duplicates":
        return _merge_main(argv[1:])
    return _check_main(argv)


if __name__ == "__main__":
    main()
