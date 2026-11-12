"""lamafiadelsobre.com: a second stock aggregator, read for the big chains.

It follows ~175 Spanish and European TCG shops and has a page per shop (``/es/tiendas/<slug>``, server-rendered, the
products in stock first, twelve per page) whose rows carry the shop's own title, the format and set, the state, the
edition language, when it was last seen, the price and the link to the shop's page. It covers chains the other
aggregator does not (Fnac, Hipercor, DRIM) and reads the shared ones on its own clock, so a restock one of them misses
or sees late still arrives. ``robots.txt`` allows these pages (it closes ``/api/`` and the account pages).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from bs4 import BeautifulSoup

from ..extract.phrases import amount_and_currency
from ..model import IN_STOCK, OUT_OF_STOCK, PREORDER, UNKNOWN
from .stocktcg import RadarOffer, _strip_affiliate

SOURCE = "lamafiadelsobre.com"
BASE = "https://lamafiadelsobre.com"
# our shop slug -> theirs (the same today; kept as a table because the two sites name shops on their own)
CHAINS = {"carrefour": "carrefour", "el-corte-ingles": "el-corte-ingles", "game": "game", "alcampo": "alcampo",
          "toys-r-us": "toys-r-us", "fnac": "fnac", "hipercor": "hipercor", "drim": "drim"}
EXTRA_CHAINS = ("fnac", "hipercor", "drim")     # chains only this source follows: their stock always alerts too
MAX_PAGES = 3                                    # pages of one shop read in a cycle while every row is still buyable
REFRESH_MIN = 5                                  # a shop page is read at most this often

_STATES = {"en stock": IN_STOCK, "preventa": PREORDER, "reserva": PREORDER, "agotado": OUT_OF_STOCK}
_SEEN = re.compile(r"visto hace\s+(\d+)\s*(s|seg|min|h|d)", re.IGNORECASE)
_UNIT_S = {"s": 1, "seg": 1, "min": 60, "h": 3600, "d": 86400}


def store_url(slug: str, page: int = 1) -> str:
    return f"{BASE}/es/tiendas/{slug}" + (f"?pagina={page}" if page > 1 else "")


def parse_store_page(html: str, store_slug: str, *, now: Optional[float] = None) -> tuple[list[RadarOffer], bool]:
    """The rows of one shop page, and whether every one of them is buyable (then the next page may hold more stock)."""
    soup = BeautifulSoup(html, "html.parser")
    head = soup.find("h1")
    store = head.get_text(" ", strip=True) if head is not None else store_slug
    offers: list[RadarOffer] = []
    for art in soup.select("li > article"):
        product = art.select_one('a[href^="/es/producto/"]')
        texts = [t for t in art.stripped_strings]
        chips = [c.get_text(" ", strip=True) for c in art.select("span.inline-flex")]
        state = next((_STATES[c.lower()] for c in chips if c.lower() in _STATES), UNKNOWN)
        title_node = art.select_one("h3")
        title = title_node.get_text(" ", strip=True) if title_node is not None else (texts[0] if texts else "")
        if not title or state == UNKNOWN:
            continue
        caption = title_node.find_next("p") if title_node is not None else None
        fmt, _, set_name = (caption.get_text(" ", strip=True) if caption is not None else "").partition(",")
        lang = next((c for c in chips if re.fullmatch(r"[A-Z]{2}", c)), "")
        price_node = art.select_one("p.font-display")
        price, currency = amount_and_currency(price_node.get_text(" ", strip=True)) if price_node is not None else (None, "")
        link = next((a.get("href") for a in art.select('a[href^="http"]') if BASE not in (a.get("href") or "")), "")
        seen = _SEEN.search(" ".join(texts))
        seen_ts = now - int(seen.group(1)) * _UNIT_S[seen.group(2).lower()] if seen and now is not None else None
        offers.append(RadarOffer(
            source=SOURCE, store=store, store_slug=store_slug, title=title, url=_strip_affiliate(link or ""), state=state,
            price=price, currency=currency or "EUR", lang=lang, set_name=set_name.strip(), fmt=fmt.strip(), seen_ts=seen_ts,
            kind="listing", extra={"game": "pokemon", "their_page": (product.get("href") if product is not None else "") or ""}))
    return offers, bool(offers) and all(o.state in (IN_STOCK, PREORDER) for o in offers)
