"""The chains' own catalogue pages, read directly: what a shop sells right now, without waiting for an aggregator.

An aggregator only lists the products somebody added to it, and it reads each shop on its own clock. A chain's own listing
of a brand (El Corte Inglés's Pokémon page, Amazon's Pokémon search filtered to what Amazon itself sells) shows every
product the moment the shop puts it up, with its price and whether it can be bought. Each listing is a "page" of the
radar: its rows become shop offers like the aggregators' (same alert rules: chain, shelf price, minimum price, one alert
per offer across sources), and when every page of a listing was read in one cycle the listing is complete, so a product
that drops out of it is sold out and its return is a restock.

* **El Corte Inglés**: the brand page (``/marcas/pokemon/juguetes/``, two pages) is server-rendered; its embedded state
  lists only what can be added to the basket. Read over plain HTTP (``robots.txt`` closes ``/api`` and searches, not
  brand pages).
* **Amazon**: the search for the brand filtered to the seller Amazon itself (``rh=p_6:A1AT7YVPFBWXBL``), which leaves out
  marketplace resellers and anything Amazon cannot sell now. A card says "Disponible por invitación" for invitation
  sales. Amazon throttles quickly, so it is read seldom (``refresh_min``) and through the fetch ladder (a browser when
  the plain request meets its check).
* Carrefour's catalogue sits behind a check that turns away every automated browser; it is read by the browser
  extension of a real browser (``catalog_report``), not here.

Every listing is configurable per watcher (``radar.direct_pages``); the defaults are the Pokémon ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..discovery import fold
from ..extract.phrases import amount_and_currency
from ..model import IN_STOCK, OUT_OF_STOCK, PREORDER, UNKNOWN
from .stocktcg import RadarOffer, _strip_affiliate

SOURCE = "direct"                         # the source switch in ``radar.sources``
AMAZON_SELLER = "A1AT7YVPFBWXBL"          # Amazon itself on amazon.es

DEFAULT_PAGES: list[dict[str, Any]] = [
    {"store": "El Corte Inglés", "slug": "el-corte-ingles", "url": "https://www.elcorteingles.es/marcas/pokemon/juguetes/",
     "next": "{url}{n}/", "pages": 3, "refresh_min": 3, "parser": "eci"},
    {"store": "Amazon", "slug": "amazon", "url": f"https://www.amazon.es/s?k=pokemon+jcc&rh=p_6%3A{AMAZON_SELLER}",
     "next": "{url}&page={n}", "pages": 2, "refresh_min": 10, "parser": "amazon"},
]


@dataclass
class Listing:
    """One read of one page of a listing."""

    offers: list[RadarOffer] = field(default_factory=list)
    full: bool = False                    # the page was full, so a next page may hold more


# ------------------------------------------------------------------------------- helpers
_FMT = (
    (r"\bmini\s*-?\s*latas?\b|\bminilatas?\b|\bmini tins?\b", "mini tin"),
    (r"caja de entrenador [eé]lite|elite trainer box|\betb\b", "etb"),
    (r"\bbooster bundle\b|\blote de (?:6 )?sobres\b", "booster bundle"),
    (r"\bbl[ií]ster\b|\bblister\b", "blister"),
    (r"\blatas?\b|\btins?\b", "tin"),
)


def guess_fmt(title: str) -> str:
    """The format a shop title names, only when it is unambiguous (the shelf-price check depends on it)."""
    low = fold(title)
    for pattern, fmt in _FMT:
        if re.search(pattern, low):
            return fmt
    if re.match(r"\s*(?:pokemon[:\s-]*)?sobre\b", low) and not re.search(r"\b(?:lote|pack de|caja|expositor|display)\b", low):
        return "sobre"
    return ""


def guess_lang(title: str) -> str:
    low = fold(title)
    if re.search(r"\b(?:english|ingles)\b", low):
        return "EN"
    if re.search(r"\b(?:japones|japanese|japon)\b", low):
        return "JA"
    return ""


def page_urls(spec: dict[str, Any]) -> list[str]:
    base = str(spec["url"])
    out = [base]
    for n in range(2, int(spec.get("pages") or 1) + 1):
        out.append(str(spec.get("next") or "{url}").format(url=base, n=n))
    return out


def pages_for(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    pages = cfg.get("direct_pages")
    if not isinstance(pages, list) or not pages:
        return [dict(p) for p in DEFAULT_PAGES]
    out = []
    for p in pages:
        if isinstance(p, dict) and p.get("url") and p.get("slug"):
            out.append({"store": p.get("store") or p["slug"], "next": "{url}", "pages": 1, "refresh_min": 5,
                        "parser": "auto", **p})
    return out


def _offer(spec: dict[str, Any], title: str, url: str, state: str, price: Optional[float], *, invite: bool = False,
           sku: str = "") -> RadarOffer:
    host = re.sub(r"^https?://(?:www\.)?", "", str(spec["url"])).split("/")[0]
    return RadarOffer(source=host, store=str(spec["store"]), store_slug=str(spec["slug"]), title=title[:300], url=url,
                      state=state, price=price, currency="EUR", lang=guess_lang(title), fmt=guess_fmt(title),
                      kind="invite" if invite else "listing",
                      extra={"game": "pokemon", "first_hand": True, **({"invite": True} if invite else {}),
                             **({"sku": sku} if sku else {})})


# ------------------------------------------------------------------------------- El Corte Inglés
def parse_eci(html: str, page_url: str, spec: dict[str, Any]) -> Listing:
    """The products of a brand or category page from its embedded state (``__MOONSHINE_STATE__``)."""
    from ..extract.moonshine import _datalayer_products, _state     # noqa: PLC0415 - the shared reader of that state
    soup = BeautifulSoup(html, "html.parser")
    state = _state(soup)
    if not state:
        return Listing()
    products = _datalayer_products(state)
    uris = {}
    for holder in (state, *(b for b in (state.get("blocks") or []) if isinstance(b, dict))):
        for p in holder.get("products") or []:
            if isinstance(p, dict) and p.get("id") and p.get("_uri"):
                uris[str(p["id"])] = str(p["_uri"])
    out = Listing(full=len(products) >= 12)
    for item in products:
        code, name = str(item.get("code_a") or "").strip(), str(item.get("name") or "").strip()
        if not code or not name or code not in uris:
            continue
        status = str(item.get("status") or "").upper()
        badges = item.get("badges") if isinstance(item.get("badges"), dict) else {}
        provider = str(item.get("eci_provider") or "")
        if provider and "corte" not in fold(provider) and provider not in ("001", "eci"):
            continue                                  # a marketplace vendor inside the site, not the shop's own stock
        state_ = PREORDER if badges.get("coming_soon") else IN_STOCK if status == "ADD" else OUT_OF_STOCK if status else UNKNOWN
        price_block = item.get("price") if isinstance(item.get("price"), dict) else {}
        price = price_block.get("f_price")
        out.offers.append(_offer(spec, name, urljoin(page_url, uris[code]), state_,
                                 float(price) if isinstance(price, (int, float)) else None, sku=code))
    return out


# ------------------------------------------------------------------------------- Amazon
_INVITE = re.compile(r"disponible por invitaci[oó]n|solicitar (?:una )?invitaci[oó]n|request (?:an )?invitation", re.I)
_PREORDER = re.compile(r"reserva ahora|disponible para reservar|pre-?order|preventa", re.I)
_UNAVAILABLE = re.compile(r"actualmente no disponible|no disponible|currently unavailable", re.I)


def parse_amazon(html: str, page_url: str, spec: dict[str, Any]) -> Listing:
    """The result cards of an Amazon search (sponsored cards and cards without a product id are skipped)."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('div[data-component-type="s-search-result"]')
    out = Listing(full=len(cards) >= 40)
    for card in cards:
        asin = str(card.get("data-asin") or "").strip()
        head = card.select_one("h2")
        if not re.fullmatch(r"[A-Z0-9]{10}", asin) or head is None:
            continue
        if card.select_one(".puis-sponsored-label-text, .s-sponsored-label-text"):
            continue
        title = head.get_text(" ", strip=True)
        text = card.get_text(" ", strip=True)
        price_node = card.select_one(".a-price .a-offscreen")
        price = amount_and_currency(price_node.get_text(" ", strip=True))[0] if price_node is not None else None
        invite = bool(_INVITE.search(text))
        if invite or _PREORDER.search(text):
            state = PREORDER
        elif _UNAVAILABLE.search(text) or price is None:
            state = OUT_OF_STOCK
        else:
            state = IN_STOCK
        url = _strip_affiliate(urljoin(page_url, f"/dp/{asin}"))
        out.offers.append(_offer(spec, title, url, state, price, invite=invite, sku=asin))
    return out


PARSERS = {"eci": parse_eci, "amazon": parse_amazon}


def parse(spec: dict[str, Any], html: str, page_url: str) -> Listing:
    parser = PARSERS.get(str(spec.get("parser") or ""))
    if parser is None:
        parser = parse_amazon if "amazon." in page_url else parse_eci
    return parser(html, page_url, spec)


__all__ = ["SOURCE", "DEFAULT_PAGES", "Listing", "guess_fmt", "guess_lang", "page_urls", "pages_for", "parse", "parse_eci",
           "parse_amazon", "AMAZON_SELLER"]
