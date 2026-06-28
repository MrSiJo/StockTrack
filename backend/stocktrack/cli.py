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
    handler.configure(delivery_postcode=postcode, collection_branch_id=branch)
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


def main(argv=None):
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


if __name__ == "__main__":
    main()
