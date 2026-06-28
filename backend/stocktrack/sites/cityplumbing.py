"""cityplumbing.co.uk site handler — two-stage: GET listing + GraphQL eligibility."""
import datetime
import json
import re

from .base import Product, SiteHandler, fetch_html, post_json

BASE = "https://www.cityplumbing.co.uk"
GRAPHQL_URL = f"{BASE}/graphql"

CP_SETTINGS = [
    {"key": "cp_delivery_postcode", "label": "Delivery postcode",
     "type": "str", "default": ""},
    {"key": "cp_collection_branch_id", "label": "Collection branch ID",
     "type": "str", "default": ""},
]

_ELIGIBILITY_QUERY = (
    "query productEligibility($items: [ItemEntryInput], "
    "$customerLocation: CustomerLocationInput) {\n"
    "  productEligibility(items: $items, customerLocation: $customerLocation) {\n"
    "    item { productCode quantity __typename }\n"
    "    collectionEligibility { status statusReason estimatedDateTime __typename }\n"
    "    deliveryEligibility { status statusReason type estimatedDateTime __typename }\n"
    "    __typename\n  }\n}\n"
)

_HREF_RE = re.compile(r'"(/p/[a-z0-9\-]+/p/(\d+))"')
_MONTHS_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _slug_title(slug: str) -> str:
    return slug.replace("-", " ").title()


def _select_price(blob: dict):
    retail = (blob.get("retailPrice") or {}).get("valueIncVat")
    try:
        return float(retail)
    except (TypeError, ValueError):
        return None


def _extract_products(html: str) -> list[dict]:
    # Grid = trailing code in /p/<slug>/p/<code> hrefs.
    grid: dict[str, str] = {}
    for m in _HREF_RE.finditer(html):
        grid.setdefault(m.group(2), m.group(1))
    if not grid:
        raise RuntimeError("no product grid found - City Plumbing page layout changed?")

    # Price blobs keyed by productCode.
    dec = json.JSONDecoder()
    prices: dict[str, float] = {}
    for m in re.finditer(r'\{"productCode":"(\d+)","tradePrice"', html):
        try:
            obj, _ = dec.raw_decode(html, m.start())
        except ValueError:
            continue
        prices.setdefault(m.group(1), _select_price(obj))

    # Clean JSON names from __typename:"Product" objects.
    names: dict[str, str] = {}
    for m in re.finditer(r'\{"code":"(\d+)"', html):
        try:
            obj, _ = dec.raw_decode(html, m.start())
        except ValueError:
            continue
        if obj.get("__typename") == "Product" and obj.get("name"):
            names.setdefault(m.group(1), obj["name"])

    out = []
    for code, path in grid.items():
        slug = path.split("/p/")[1] if "/p/" in path else ""
        out.append({
            "code": code,
            "title": names.get(code) or _slug_title(slug),
            "price": prices.get(code),
            "url": BASE + path,
        })
    return out


def _lead_time_text(estimated_iso, dtype) -> str:
    if not estimated_iso:
        return ""
    try:
        d = datetime.datetime.fromisoformat(
            str(estimated_iso).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return ""
    label = f"{_WEEKDAYS[d.weekday()]} {d.day} {_MONTHS_ABBR[d.month]}"
    suffix = f" ({str(dtype).lower()})" if dtype else ""
    return f"Delivery by {label}{suffix}"


def _build_envelope(products: list[dict], eligibility: dict) -> str:
    return json.dumps({"products": products, "eligibility": eligibility})


class CityPlumbingHandler(SiteHandler):
    name = "cityplumbing"
    kind = "listing"
    settings_spec = CP_SETTINGS

    def __init__(self):
        self._delivery_postcode = ""
        self._collection_branch_id = ""

    def configure(self, *, cp_delivery_postcode=None, cp_collection_branch_id=None, **_):
        if cp_delivery_postcode is not None:
            self._delivery_postcode = str(cp_delivery_postcode)
        if cp_collection_branch_id is not None:
            self._collection_branch_id = str(cp_collection_branch_id)

    def fetch(self, url):
        if not self._delivery_postcode:
            raise RuntimeError(
                "City Plumbing needs a delivery postcode - set it in Stores settings")
        html = fetch_html(url)
        products = _extract_products(html)
        items = [{"productCode": p["code"], "quantity": 1} for p in products]
        payload = {
            "operationName": "productEligibility",
            "variables": {
                "items": items,
                "customerLocation": {
                    "deliveryPostcode": self._delivery_postcode,
                    "collectionBranchId": self._collection_branch_id,
                },
            },
            "query": _ELIGIBILITY_QUERY,
        }
        data = post_json(GRAPHQL_URL, payload, headers={"origin": BASE, "referer": BASE + "/"})
        rows = (data.get("data") or {}).get("productEligibility") or []
        eligibility = {}
        for r in rows:
            code = (r.get("item") or {}).get("productCode")
            if code:
                eligibility[str(code)] = {
                    "deliveryEligibility": r.get("deliveryEligibility") or {},
                    "collectionEligibility": r.get("collectionEligibility") or {},
                }
        return _build_envelope(products, eligibility)

    def parse(self, raw):
        env = json.loads(raw)
        elig = env.get("eligibility") or {}
        out = []
        for p in env.get("products") or []:
            de = (elig.get(p["code"]) or {}).get("deliveryEligibility") or {}
            in_stock = de.get("status") == "AVAILABLE"
            delivery = _lead_time_text(de.get("estimatedDateTime"), de.get("type")) if in_stock else ""
            out.append(Product(
                code=p["code"],
                title=p.get("title") or "",
                brand="",
                in_stock=in_stock,
                price=p.get("price"),
                delivery=delivery,
                url=p.get("url") or "",
                availability="",
                basket_url="",
            ))
        return out


handler = CityPlumbingHandler()
