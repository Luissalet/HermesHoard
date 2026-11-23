"""A shop's own catalogue feed: one request answers what every product of a collection costs and whether it can be bought.

Shops on the hosted storefront platform most small card shops use publish each collection as JSON next to its page:
``/collections/<handle>/products.json?limit=250&page=N`` (250 products a page at most, in the collection's own order).
Per product: ``title``, ``handle`` (its page is ``/products/<handle>``), ``vendor``, ``product_type``, ``tags`` and
``variants[]`` with ``available`` (true while it can be added to the cart), ``price`` and ``compare_at_price`` as
strings in the shop's currency. The feed does not say the currency; these shops sell in euros.

The collection page itself shows 20 products a page and puts the sold-out ones last or hides them, so a product coming
back would have to be caught on whatever page it lands. The feed lists them all, sold out or not: a product whose
variants were all unavailable and now has one available is a restock, read without opening its page.

A profile opts in with ``catalog_feed=True`` once the feed has been seen to answer; the target stays the collection
page the person gave (its filters and sort order do not apply to the feed and are not needed). The feed is read like
a page, by whatever rung the shop's profile asks for: a browser shows a JSON document inside ``<pre>`` (``unwrap``).
"""

from __future__ import annotations

import html
import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit

from ..model import IN_STOCK, OUT_OF_STOCK, PREORDER, Offer
from .sites import profile_for_host, retailer_for_host

NAME = "catalog"
METHOD = "api:catalog"
PAGE_SIZE = 250
_COLLECTION = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?collections/([^/?#]+)/?$", re.I)
_FEED = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?collections/[^/?#]+/products\.json$", re.I)
_PRE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.I | re.S)
_PREORDER = re.compile(r"\b(?:reserva|pre-?order|pre-?venta|pre-?compra)\b", re.I)


def adapter_url(url: str, hints: Optional[dict] = None) -> Optional[str]:
    """The feed to read for a collection page of a shop whose profile has one, or ``None``."""
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    profile = profile_for_host(url)
    if profile is None or not profile.catalog_feed:
        return None
    match = _COLLECTION.match(parts.path)
    if not match:
        return None
    try:
        page = max(1, min(int((parse_qs(parts.query).get("page") or ["1"])[0]), 40))
    except ValueError:
        page = 1
    return f"https://{parts.hostname}/collections/{match.group(1)}/products.json?limit={PAGE_SIZE}&page={page}"


def unwrap(body: str) -> str:
    """The JSON document a browser shows as a page (inside ``<pre>``), or ``""`` when the page is not one."""
    match = _PRE.search(body or "")
    inner = html.unescape(match.group(1)).strip() if match else ""
    return inner if inner[:1] in ("{", "[") else ""


def is_payload(data: Any, url: str = "") -> bool:
    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        return False
    if _FEED.match(urlsplit(url or "").path or ""):
        return True                                   # an empty page of the feed is still the feed
    first = next((p for p in data["products"] if isinstance(p, dict)), None)
    return bool(first and first.get("handle") and isinstance(first.get("variants"), list))


def _price(value: Any) -> Optional[float]:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def extract_payload(data: dict[str, Any], *, url: str, hints: Optional[dict] = None) -> tuple[list[Offer], str, list[str]]:
    """Feed -> one offer per product. Returns ``(offers, page_kind, notes)``."""
    host = urlsplit(url).hostname or ""
    seller = retailer_for_host(url) or host
    offers: list[Offer] = []
    for product in data.get("products") or []:
        if not isinstance(product, dict):
            continue
        handle, title = str(product.get("handle") or "").strip(), str(product.get("title") or "").strip()
        variants = [v for v in (product.get("variants") or []) if isinstance(v, dict)]
        if not handle or not title or not variants:
            continue
        live = [v for v in variants if v.get("available") is True]
        prices = [p for p in (_price(v.get("price")) for v in (live or variants)) if p is not None]
        state = (PREORDER if _PREORDER.search(title) else IN_STOCK) if live else OUT_OF_STOCK
        names = [str(v.get("title") or "") for v in live if str(v.get("title") or "").lower() not in ("", "default title")]
        evidence = [f"variantes a la venta: {len(live)} de {len(variants)}"]
        if names and len(variants) > 1:
            evidence.append("a la venta: " + ", ".join(names[:6]))
        was = _price(variants[0].get("compare_at_price"))
        image = next((str(i.get("src") or "") for i in (product.get("images") or []) if isinstance(i, dict) and i.get("src")), "")
        offers.append(Offer(
            availability=state, price=min(prices) if prices else None, currency="EUR", title=title,
            url=f"https://{host}/products/{handle}", sku=str(product.get("id") or "") or None,
            brand=str(product.get("vendor") or "") or None, image=image or None, seller=seller, seller_is_retailer=True,
            buy_button=bool(live), evidence=evidence, method=METHOD,
            extra={k: v for k, v in (("product_type", product.get("product_type")), ("compare_at_price", was),
                                     ("variants", len(variants)), ("variants_available", len(live))) if v not in (None, "")}))
    notes = [f"catalogue feed: {len(offers)} products"]
    if len(offers) >= PAGE_SIZE:
        notes.append("the feed has more pages (add ?page=2 to the collection URL to read the next one)")
    return offers, "listing", notes
