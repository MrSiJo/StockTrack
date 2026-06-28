"""ao.com site handler."""
import datetime
import html as html_mod
import json
import os
import re

from .base import Product, SiteHandler, fetch_html

OOS_STATE = "outofstock"
BASKET_URL = "https://ao.com/Build_Shopping_Basket.aspx?items={code}:1"
EARLY_ACCESS_DAYS = int(os.environ.get("EARLY_ACCESS_DAYS", "30"))

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}

class AoHandler(SiteHandler):
    name = "ao"
    _early_access_days = None  # set via configure(); None → fall back to EARLY_ACCESS_DAYS
    _ao_member = False  # set via configure()

    def configure(self, *, early_access_days=None, ao_member=None, **_):
        """Store the early-access threshold and membership flag for parse."""
        if early_access_days is not None:
            self._early_access_days = int(early_access_days)
        if ao_member is not None:
            self._ao_member = bool(ao_member)

    def fetch(self, url):
        return fetch_html(url)

    def parse(self, raw):
        m = re.search(
            r'<script type="application/json" id="lister-data">(.*?)</script>',
            raw, re.S,
        )
        if not m:
            raise RuntimeError("lister-data blob not found - AO page layout changed?")
        data = json.loads(m.group(1))
        products = _find_products(data)
        if not products:
            raise RuntimeError("no product list inside AO lister-data")
        return [self._to_product(p) for p in products]

    def _price(self, p):
        if self._ao_member:
            pod = p.get("PricePodViewModel") or {}
            member = pod.get("MemberPrice")
            if member:
                return member
        return p.get("Price")

    def _to_product(self, p):
        state = (p.get("State") or "").strip().lower()
        code = p.get("Code")
        delivery = _delivery_text(p)
        in_stock = state not in ("", OOS_STATE)
        return Product(
            code=code,
            title=p.get("Title") or "",
            brand=p.get("Brand") or "",
            in_stock=in_stock,
            price=self._price(p),
            delivery=delivery,
            url=p.get("FullProductUrl") or p.get("ProductUrl") or "",
            availability=_availability(in_stock, delivery, self._early_access_days),
            basket_url=BASKET_URL.format(code=code) if code else "",
        )

def _availability(in_stock, delivery, threshold=None):
    if not in_stock:
        return "oos"
    days = _delivery_days_out(delivery)
    if days is None:
        return "public"
    t = threshold if threshold is not None else EARLY_ACCESS_DAYS
    return "early" if days > t else "public"

def _delivery_days_out(text):
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)", text or "")
    if not m:
        return None
    day, month = int(m.group(1)), _MONTHS.get(m.group(2).strip().lower())
    if not month:
        return None
    today = datetime.date.today()
    try:
        when = datetime.date(today.year, month, day)
    except ValueError:
        return None
    if when < today:
        try:
            when = datetime.date(today.year + 1, month, day)
        except ValueError:
            return None
    return (when - today).days

def _find_products(o):
    if (isinstance(o, list) and o and isinstance(o[0], dict)
            and any("Code" in x for x in o[:3] if isinstance(x, dict))):
        return o
    if isinstance(o, dict):
        for v in o.values():
            r = _find_products(v)
            if r:
                return r
    if isinstance(o, list):
        for v in o:
            r = _find_products(v)
            if r:
                return r
    return None

def _delivery_text(p):
    bullets = p.get("DynamicDeliveryBulletsViewModel") or []
    if not bullets:
        return ""
    text = re.sub(r"<[^>]+>", "", bullets[0])
    text = html_mod.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s*\*+\s*$", "", text).strip()

handler = AoHandler()
