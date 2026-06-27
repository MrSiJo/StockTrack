"""johnlewis.com site handler."""
import json
import re

from .base import Product, SiteHandler, fetch_html

BASE = "https://www.johnlewis.com"

class JohnLewisHandler(SiteHandler):
    name = "johnlewis"

    def fetch(self, url):
        return fetch_html(url)

    def parse(self, raw):
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S,
        )
        if not m:
            raise RuntimeError("__NEXT_DATA__ blob not found - JL page layout changed?")
        data = json.loads(m.group(1))
        products = _find_products(data)
        if not products:
            raise RuntimeError("no product list inside JL __NEXT_DATA__")
        return [self._to_product(p) for p in products]

    def _to_product(self, p):
        oos = p.get("outOfStock")
        in_stock = (not oos) if oos is not None else bool(p.get("isAvailableToOrder"))
        url = p.get("url") or ""
        if url.startswith("/"):
            url = BASE + url
        return Product(
            code=str(p.get("productId") or ""),
            title=p.get("title") or "",
            brand=p.get("brand") or "",
            in_stock=in_stock,
            price=_price(p),
            delivery="",
            url=url,
        )

def _find_products(o):
    if isinstance(o, dict):
        pld = o.get("productListingData")
        if isinstance(pld, dict) and isinstance(pld.get("products"), list):
            return pld["products"]
        for v in o.values():
            r = _find_products(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_products(v)
            if r:
                return r
    return None

def _price(p):
    rng = p.get("variantPriceRange") or {}
    val = (rng.get("value") or {}).get("min")
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

handler = JohnLewisHandler()
