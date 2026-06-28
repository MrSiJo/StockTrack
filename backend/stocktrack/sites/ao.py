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
AO_SETTINGS = [{"key": "ao_member",
                "label": "I'm an AO member (track AO member price)",
                "type": "bool", "default": False}]

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}

class _AoBase(SiteHandler):
    """Shared AO config: early-access threshold + membership flag."""
    _early_access_days = None  # None → fall back to EARLY_ACCESS_DAYS
    _ao_member = False
    settings_spec = AO_SETTINGS

    def configure(self, *, early_access_days=None, ao_member=None, **_):
        if early_access_days is not None:
            self._early_access_days = int(early_access_days)
        if ao_member is not None:
            self._ao_member = bool(ao_member)


class AoHandler(_AoBase):
    name = "ao"
    kind = "listing"
    # configure(), _early_access_days, _ao_member now inherited from _AoBase

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


class AoProductHandler(_AoBase):
    name = "ao"
    kind = "product"
    # configure(), _early_access_days, _ao_member now inherited from _AoBase

    def fetch(self, url):
        return fetch_html(url)

    def parse(self, raw):
        blob = _extract_product_blob(raw)
        in_stock = bool(blob.get("isInStock"))
        code = _attr(raw, "data-saleable-id") or _attr(raw, "data-product-code") or ""
        title = _attr(raw, "data-product-name") or ""
        delivery = _attr(raw, "data-price-with-delivery") or ""
        price = _select_price(blob, self._ao_member)
        url = _attr(raw, "data-product-url") or ""
        return [Product(
            code=code,
            title=title,
            brand="",
            in_stock=in_stock,
            price=price,
            delivery=delivery,
            url=url,
            availability=_availability(in_stock, "", self._early_access_days),
            basket_url=BASKET_URL.format(code=code) if code else "",
        )]


def _extract_product_blob(raw):
    i = raw.find("window.digitalData.page.product = Object.assign(")
    if i < 0:
        raise RuntimeError("AO product blob not found - PDP layout changed?")
    comma = raw.find(",", i)
    if comma < 0:
        raise RuntimeError("AO product blob literal not found")
    lit_index = raw.find("{", comma)
    if lit_index < 0:
        raise RuntimeError("AO product blob literal not found")
    obj, _ = json.JSONDecoder().raw_decode(raw, lit_index)
    return obj


def _select_price(blob, ao_member):
    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    if ao_member and blob.get("hasMemberPrice"):
        m = _num(blob.get("memberPrice"))
        if m is not None:
            return m
    return _num(blob.get("price"))


def _attr(raw, name):
    m = re.search(name + r'="([^"]*)"', raw)
    return m.group(1) if m else ""


product_handler = AoProductHandler()
