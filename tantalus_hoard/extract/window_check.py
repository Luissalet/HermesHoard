"""The family model reads an open-window list page too, as a second reader next to the rules.

The rules (``fetch/open_window.py``) read each row from literal text: the price line, the title above it and the button below.
The model gets the same page text and answers, for each product it sees, its title, price, status and the exact words on the
page that show the status. Its answer is only used where it can be checked against the page:

* a row both read the same way gets ``extra["model_agrees"]`` (a second, independent reading: more confidence);
* a row the rules could not decide (no known button text) takes the model's status when the model's evidence words are on the
  page: ``method="llm"``, ``extra["model_only"]`` (the engine re-reads soon and alerts only when the model says it twice);
* a product the rules missed altogether is added the same way, when its title and evidence are on the page;
* when both decided and disagree, the rules keep the literal button text and ``extra["model_disagrees"]`` records the model.

Without a model (none reachable, switched off, budget used) nothing changes and the summary says why.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

from ..llm import UNTRUSTED, page_block
from ..model import COMING_SOON, IN_STOCK, OUT_OF_STOCK, PREORDER, UNKNOWN, Extraction, Offer

STATUS = {"in_stock": IN_STOCK, "out_of_stock": OUT_OF_STOCK, "coming_soon": COMING_SOON, "preorder": PREORDER}
MATCH_MIN = 0.6           # share of title words two readings must have in common to be the same row

SYSTEM = (
    "You read the text of a shop page that lists products (a favourites list, a search result or a category). "
    "For every product on it, give its name as written, its price as a number (or null), and its status from the button "
    "or label next to it: in_stock (it can be added to the basket or bought now), out_of_stock (sold out, temporarily "
    "unavailable, notify me), coming_soon (announced, not on sale yet), preorder (can be reserved) or unknown. "
    "Copy in 'evidence' the exact words of the page that show the status. Never guess: when nothing on the page says it, "
    "the status is unknown. Answer only JSON: {\"rows\": [{\"title\": str, \"price\": number|null, \"status\": str, "
    "\"evidence\": str}]}. " + UNTRUSTED)


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if unicodedata.category(c) != "Mn")


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", fold(text)) if len(w) > 1}


def similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def _on_page(snippet: str, page: str) -> bool:
    s = re.sub(r"\s+", " ", fold(snippet)).strip()
    return len(s) >= 3 and s in page


def _price(value: Any) -> Optional[float]:
    try:
        return round(float(str(value).replace("€", "").replace(",", ".").strip()), 2) if value not in (None, "") else None
    except ValueError:
        return None


def reinforce(ex: Extraction, lines: list[str], url: str, llm: Any, *, row_url: Any = None) -> dict[str, Any]:
    """Second reading of the page by the model; updates ``ex.offers`` in place and returns a short summary
    ``{"ok", "reason", "rows", "agree", "disagree", "filled", "added"}`` for the target's history."""
    summary: dict[str, Any] = {"ok": False, "reason": "", "rows": 0, "agree": 0, "disagree": 0, "filled": 0, "added": 0}
    if llm is None:
        summary["reason"] = "sin modelo"
        return summary
    ok, reason = llm.available()
    if not ok:
        summary["reason"] = f"modelo no disponible: {reason}"[:200]
        return summary
    text = "\n".join(lines)
    answer = llm.json(SYSTEM, page_block(text, 8000), required=("rows",), max_tokens=2000)
    if not answer or not isinstance(answer.get("rows"), list):
        summary["reason"] = "el modelo no respondió con filas"
        return summary
    page = re.sub(r"\s+", " ", fold(text))
    summary["ok"] = True
    taken: set[int] = set()
    for raw in answer["rows"][:60]:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        status = STATUS.get(str(raw.get("status") or "").strip().lower(), UNKNOWN)
        evidence = str(raw.get("evidence") or "").strip()[:160]
        if not title:
            continue
        summary["rows"] += 1
        best, score = None, 0.0
        for i, offer in enumerate(ex.offers):
            if i in taken:
                continue
            s = similarity(title, offer.title or "")
            price = _price(raw.get("price"))
            if price is not None and offer.price is not None and abs(price - offer.price) > 0.01:
                s -= 0.2
            if s > score:
                best, score = i, s
        verified = status != UNKNOWN and _on_page(evidence, page)
        if best is not None and score >= MATCH_MIN:
            taken.add(best)
            offer = ex.offers[best]
            offer.extra["model_status"] = status
            if status == UNKNOWN:
                continue
            if offer.availability == UNKNOWN:
                if verified:
                    offer.availability, offer.method = status, "llm"
                    offer.extra["model_only"] = True
                    offer.evidence.append(f"modelo: «{evidence}»")
                    summary["filled"] += 1
            elif offer.availability == status:
                offer.extra["model_agrees"] = True
                offer.evidence.append("el modelo lo lee igual")
                summary["agree"] += 1
            else:
                offer.extra["model_disagrees"] = status
                offer.evidence.append(f"el modelo lo lee como {status.lower()}: «{evidence}»")
                summary["disagree"] += 1
        elif verified and _on_page(title, page):
            key = re.sub(r"[^a-z0-9]+", "-", fold(title)).strip("-")[:80] or "item"
            added = Offer(method="llm", title=title, price=_price(raw.get("price")), currency="EUR", availability=status,
                          url=row_url(key) if callable(row_url) else f"{url}#item-{key}")
            added.extra["model_only"] = True
            added.evidence.append(f"modelo: «{evidence}»")
            ex.offers.append(added)
            summary["added"] += 1
    ex.methods = list(ex.methods) + ["llm-check"]
    ex.notes.append(f"modelo: {summary['agree']} coinciden, {summary['disagree']} discrepan, {summary['filled']} completadas, "
                    f"{summary['added']} añadidas")
    return summary
