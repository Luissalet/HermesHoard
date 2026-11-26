"""List pages of shops built on the Mabisy storefront: every product card states its own stock.

A page of such a shop names the platform in ``<meta name="generator">``. A category page (``/<slug>_c<id>/``, further
pages as ``?lp=N``) counts its products in ``span.counter-stats`` and renders each one as a ``div.mb-product`` card:
the link and name (``a.name``), the maker (``a.manufacturer``), the price (``span.price``, with ``span.price-old``
beside it on a discount), the shop's own stock label (``span.label-existstock`` "En stock" / ``span.label-nostock``
"Sin stock") and attribute labels such as "Producto en preventa", sometimes with its launch date. The "Añadir" button
sits on every card, sold out or not, so it says nothing.

The label is the shop's statement about that product, so one reading of the page answers for all of them. A category
with no products is still such a page (its counter says 0): it reads as an empty list, and the first product the shop
puts in it is news. Product pages carry microdata and are left to the generic extractors.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..model import IN_STOCK, OUT_OF_STOCK, PREORDER, Offer
from .phrases import norm, parse_number, snippet

METHOD = "site:mabisy"
_GENERATOR = re.compile(r"^generator$", re.I)
_LAUNCH = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_PREORDER_NAMES = ("preventa", "pre-venta", "preorder", "pre-order")


def is_storefront(soup: BeautifulSoup) -> bool:
    tag = soup.find("meta", attrs={"name": _GENERATOR})
    return tag is not None and "mabisy" in str(tag.get("content") or "").lower()


def _cards(soup: BeautifulSoup) -> Optional[list[Tag]]:
    """The product cards the page lists, or ``None`` when it is not a list page. A category page counts its own
    products: only the cards of that module are its products (a strip of featured products elsewhere on the page is
    not what the category sells)."""
    counter = soup.select_one("span.counter-stats")
    if counter is not None:
        for parent in counter.parents:
            if isinstance(parent, Tag) and parent.select_one("div.mb-product-list, div.noproduct") is not None:
                return parent.select("div.mb-product[data-id]")
    cards = soup.select("div.mb-product[data-id]")
    return cards if cards or counter is not None else None


def _launch_date(card: Tag) -> Optional[date]:
    """The launch date a pre-order card prints ("Fecha de lanzamiento 06/11/2026"), when it prints one."""
    for el in card.select("span.attribute"):
        text = el.get_text(" ", strip=True)
        found = _LAUNCH.search(text)
        if found and "lanzamiento" in norm(text):
            day, month, year = (int(x) for x in found.groups())
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def _offer(card: Tag, base_url: str, position: int, today: Optional[date]) -> Optional[Offer]:
    link = card.select_one("a.name[href]") or card.select_one("a.image-box[href]")
    if link is None:
        return None
    title = link.get_text(" ", strip=True) or str(link.get("title") or "")
    offer = Offer(url=urljoin(base_url, str(link["href"]).strip()), title=snippet(title, 200) or None, method=METHOD,
                  sku=str(card.get("data-id") or "").strip() or None, seller_is_retailer=True)
    maker = card.select_one(".manufacturer")
    if maker is not None:
        offer.brand = snippet(maker.get_text(" ", strip=True), 80) or None
    price = card.select_one(".prices .price")
    if price is not None:
        shown = price.get_text(" ", strip=True)
        value = parse_number(shown)
        if value is not None:
            offer.price, offer.currency = value, "EUR"
            offer.evidence.append(snippet(f"price {shown}"))
    old = card.select_one(".prices .price-old")
    was = parse_number(old.get_text(" ", strip=True)) if old is not None else None
    if was is not None:
        offer.extra["list_price"] = was
    image = card.select_one("img[data-src], img[src]")
    if image is not None:
        src = str(image.get("data-src") or image.get("src") or "").strip()
        offer.image = urljoin(base_url, src) if src and not src.startswith("data:") else None
    names = [norm(el.get_text(" ", strip=True)) for el in card.select("span.attribute .name")]
    preorder = any(n == "reserva" or any(word in n for word in _PREORDER_NAMES) for n in names)
    label = card.select_one("span.label-nostock, span.label-existstock")
    classes = set(label.get("class") or []) if label is not None else set()
    if "label-nostock" in classes:
        offer.availability, offer.buy_button = OUT_OF_STOCK, False
    elif "label-existstock" in classes:
        launch = _launch_date(card) if preorder else None
        # "Pre-order" stays on a card after its launch day: with stock and the day gone by, it is simply on sale.
        if preorder and (launch is None or today is None or launch > today):
            offer.availability = PREORDER
            offer.preorder_date = launch.isoformat() if launch is not None else None
            offer.evidence.append("Producto en preventa")
        else:
            offer.availability = IN_STOCK
    if label is not None:
        offer.evidence.append(snippet(label.get_text(" ", strip=True)))
    offer.extra["position"] = position
    return offer if (offer.title or offer.price is not None) else None


def listing(soup: BeautifulSoup, base_url: str = "", *, today: Optional[date] = None, limit: int = 80) -> Optional[list[Offer]]:
    """The products of a list page of this storefront, each with the stock its card states; ``None`` when the page is
    not one (another platform, or a page of the shop that neither lists products nor counts them)."""
    if not is_storefront(soup):
        return None
    cards = _cards(soup)
    if cards is None:
        return None
    today = today or date.today()
    offers: list[Offer] = []
    seen: set[str] = set()
    for card in cards:
        offer = _offer(card, base_url, len(offers) + 1, today)
        if offer is None or offer.url in seen:
            continue
        seen.add(offer.url or "")
        offers.append(offer)
        if len(offers) >= limit:
            break
    return offers
