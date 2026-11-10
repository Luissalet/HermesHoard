"""Stock notices the shops send by mail, turned into the alerts of the watched products.

A shop where you asked "avísame cuando vuelva", keep a wishlist or follow a product mails you itself when the product is back,
when reservations open, when its price drops or when it sold out. Those mails are the shop's own word: they need no browser
and no page read, so they keep working where a page cannot be read (Hermes on a Spark, away from the Windows browser that the
"Mi ventana abierta" mode needs, or a shop that only answers an ordinary browser window).

One scan reads the Faustus mailbox (read-only, the same account the mail deals and the e-mail alerts use) for mail from the
shops of the watched targets and, for each mail:

1. **classifies it** with the phrase rules below (``RULES``): back in stock / on sale, reservations open, price drop, sold out.
   A phrase in the subject is enough; a phrase only in the body counts when the mail is personal (your wishlist, your alert,
   "nos pediste que te avisáramos"), so a newsletter that says "ya disponible" about something else is not a notice;
2. **matches it** to the watched targets of that shop only (the sender must be the shop: same domain, or a sending domain the
   shop is known to use): by the product link in the mail, by the product number of the target's link, or by the product name
   (every significant word of the target's name, or of one row of an open-window list, in the mail);
3. **raises the same alert a page check would**: ``RESTOCK`` (``SALE_OPEN`` when the product said "Próximamente"),
   ``PREORDER_OPEN`` (``SALE_OPEN`` with reservations), ``PRICE_DROP``; ``data.source`` is ``mail_notice``. A "sold out" mail
   ends the live alerts of that product with the usual "se acabó" follow-up.

Lifecycle: a mail alert ends like any other (the shop's page or the radar read it sold out, with the follow-up), and a mail
alert no page has confirmed ends quietly as "unconfirmed" after ``mail.notices.live_hours``. A mail older than
``mail.notices.max_age_hours`` is recorded without an alert. Nothing is fetched, clicked, answered or bought: mail links are
only read as text, and the mailbox is never changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from .. import rules
from ..engine import MAIL_NOTICE_SOURCE, WINDOWS_HOST, Engine
from ..model import (BUYABLE, COMING_SOON, OUT_OF_STOCK, PREORDER_OPEN, PRICE_DROP, RESTOCK, SALE_OPEN, UNKNOWN,
                     MODE_AVAILABILITY)
from ..store import LIVE_ALERT_TYPES
from .parse import clean_title, clean_url, fold, prices, unwrap
from .source import MailSource
from .stores import DEFAULT_STORES, domain_of

log = logging.getLogger("tantalus.mail.notices")

DEFAULTS = {"mail.notices.enabled": "1", "mail.notices.interval_min": "10", "mail.notices.history_days": "3",
            "mail.notices.max_age_hours": "12", "mail.notices.live_hours": "12", "mail.notices.domains": ""}
NUMERIC = {"mail.notices.interval_min": (5, 1440), "mail.notices.history_days": (1, 30), "mail.notices.max_age_hours": (1, 168),
           "mail.notices.live_hours": (1, 168)}
MAX_PER_RUN = 200
MATCH_MIN = 80
CONFIDENCE = {"link": 90, "reference": 88, "name": 80, "manual": 90}

AVAILABLE, PREORDER, PRICE, SOLD = "available", "preorder", "price_drop", "sold_out"
KINDS = (PREORDER, AVAILABLE, PRICE, SOLD)          # the order a mail is classified in: the first kind found wins

# The phrase rules, on lower-case text without accents. ``label`` is what the rules screen shows.
RULES: dict[str, list[tuple[str, str]]] = {
    PREORDER: [
        (r"\breserva(?:lo|la|los|las)? ya\b", "reserva ya"),
        (r"\bya (?:puedes|se puede|podeis) reservar", "ya puedes reservar"),
        (r"\breservas? (?:ya )?(?:abiertas?|disponibles?)\b", "reservas abiertas"),
        (r"\babr(?:e|en|imos) (?:las? )?reservas?\b", "abrimos las reservas"),
        (r"\bpreventa (?:ya )?(?:abierta|disponible)\b", "preventa abierta"),
        (r"\bdisponible para reservar\b", "disponible para reservar"),
        (r"\bpre-?orders? (?:is |are )?(?:now )?(?:open|available|live)\b", "pre-orders open"),
        (r"\bpre-?order (?:it |yours )?now\b", "pre-order now"),
    ],
    AVAILABLE: [
        (r"\bvuelven? a estar (?:disponibles?|en stock|a la venta)\b", "vuelve a estar disponible"),
        (r"\b(?:de nuevo|otra vez|nuevamente) (?:disponibles?|en stock|a la venta)\b", "de nuevo disponible"),
        (r"\bya (?:esta|estan|lo tenemos|la tenemos|los tenemos|tenemos)\b[^.\n]{0,25}\b(?:disponibles?|en stock|de nuevo)\b",
         "ya está disponible"),
        (r"\bya (?:a la venta|disponibles?)\b", "ya disponible / ya a la venta"),
        (r"\b(?:hemos repuesto|ya hay stock|ya hay unidades|nuevas unidades|reponemos stock)\b", "hemos repuesto / nuevas unidades"),
        (r"\b(?:ya )?puedes comprar(?:lo|la|los|las)?\b", "ya puedes comprarlo"),
        (r"\b(?:back in stock|in stock again|available again|restocked)\b", "back in stock"),
        (r"\b(?:is|are) back\b", "is back"),
        (r"\b(?:now available|available now|on sale now|now on sale|out now)\b", "now available"),
    ],
    PRICE: [
        (r"\bha bajado(?: de precio)?\b", "ha bajado de precio"),
        (r"\b(?:bajada|rebaja) de precio\b", "bajada de precio"),
        (r"\bbaja(?:do)? de precio\b", "baja de precio"),
        (r"\bprecio (?:rebajado|mas bajo|reducido)\b", "precio rebajado"),
        (r"\b(?:price drop|price (?:has )?dropped|dropped in price)\b", "price drop"),
        (r"\b(?:ahora mas barato|now cheaper)\b", "ahora más barato"),
    ],
    SOLD: [
        (r"\bse (?:ha|han) agotado\b", "se ha agotado"),
        (r"\bagotad[oa]s?\b", "agotado"),
        (r"\bsin stock\b", "sin stock"),
        (r"\b(?:sold out|out of stock)\b", "sold out"),
    ],
}
# A notice in the body (not the subject) counts only in a personal mail: the shop writes about something you asked for.
PERSONAL: list[tuple[str, str]] = [
    (r"\btu lista de dese(?:os|ados)\b", "tu lista de deseos"),
    (r"\btus? (?:favoritos?|productos guardados|alertas?)\b", "tus favoritos / tu alerta"),
    (r"\balerta de (?:stock|disponibilidad|precio)\b", "alerta de stock"),
    (r"\b(?:nos )?pediste que te avis", "nos pediste que te avisáramos"),
    (r"\bte avisamos\b", "te avisamos"),
    (r"\bavisame\b", "avísame"),
    (r"\byour wish ?list\b", "your wishlist"),
    (r"\bsaved items?\b", "saved items"),
    (r"\byou asked us to\b", "you asked us"),
    (r"\b(?:stock|price) alert\b", "stock alert"),
]
_COMPILED = {kind: [(re.compile(rx), label) for rx, label in items] for kind, items in RULES.items()}
_PERSONAL = [(re.compile(rx), label) for rx, label in PERSONAL]
_NOT_YET = re.compile(r"\b(?:proximamente|muy pronto|coming soon)\b")

# Sending domains a shop uses besides its own: the mail of "game.es" comes from "mail-game.net".
SHOP_SENDERS: dict[str, list[str]] = {"carrefour.es": ["carrefour.com"]}
for _store in DEFAULT_STORES:
    _own = [d for d in _store["domains"]]
    for _d in _own:
        SHOP_SENDERS.setdefault(_d, [])
        SHOP_SENDERS[_d] = sorted(set(SHOP_SENDERS[_d]) | (set(_own) - {_d}))

SECOND_LEVEL = {"co.uk", "com.au", "com.br", "co.jp", "com.mx", "com.ar", "com.tr", "co.nz"}
STOP = {"con", "para", "por", "del", "las", "los", "una", "uno", "the", "and", "for", "with", "from", "edicion", "edition", "version",
        "años", "anos", "pack", "nuevo", "nueva", "new", "oficial", "official", "tienda", "online", "envio", "gratis"}


# ----------------------------------------------------------------------------- pure helpers
def registrable(host: str) -> str:
    """``mail.game.es`` -> ``game.es``; ``shop.example.co.uk`` -> ``example.co.uk``."""
    host = (host or "").lower().strip(".").split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and ".".join(parts[-2:]) in SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def parse_pairs(raw: Any) -> dict[str, str]:
    """``mail.notices.domains``: one ``sender=shop`` pair a line (or comma separated): the sender domain counts as that shop."""
    out: dict[str, str] = {}
    for item in re.split(r"[\n,;]+", str(raw or "")):
        if "=" not in item:
            continue
        sender, shop = (registrable(domain_of(x.strip())) for x in item.split("=", 1))
        if sender and shop and "." in sender and "." in shop:
            out[sender] = shop
    return out


def shop_domains(url: str) -> set[str]:
    """The registrable domains whose mail speaks for the shop of ``url``."""
    own = registrable(urlsplit(url or "").hostname or "")
    if not own:
        return set()
    out = {own}
    for domain, senders in SHOP_SENDERS.items():
        if registrable(domain) == own:
            out |= {registrable(s) for s in senders}
    return out


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def significant(text: str) -> list[str]:
    seen: list[str] = []
    for w in words(text):
        if (len(w) >= 3 or (w.isdigit() and len(w) >= 2)) and w not in STOP and w not in seen:
            seen.append(w)
    return seen


def classify(subject: str, text: str) -> dict[str, Any]:
    """``{"kind", "phrase", "personal", "where"}``; ``kind`` is ``""`` when the mail is not a stock notice."""
    subj = fold(subject)
    body = fold(text)[:4000]
    personal = next((label for rx, label in _PERSONAL if rx.search(subj) or rx.search(body)), "")
    for where, hay in (("subject", subj), ("body", body)):
        if where == "body" and not personal:
            break
        for kind in KINDS:
            if kind == SOLD and where == "body":
                continue                          # "agotado" in a body is too often about something else
            for rx, label in _COMPILED[kind]:
                hit = rx.search(hay)
                if not hit:
                    continue
                if kind == AVAILABLE and _NOT_YET.search(hay[max(0, hit.start() - 30):hit.end() + 5]):
                    continue                      # "próximamente disponible" is the opposite of a notice
                return {"kind": kind, "phrase": label, "personal": bool(personal), "personal_phrase": personal, "where": where}
    return {"kind": "", "phrase": "", "personal": bool(personal), "personal_phrase": personal, "where": ""}


def link_urls(message: dict[str, Any]) -> list[tuple[str, str]]:
    out, seen = [], set()
    for link in message.get("links") or []:
        raw = str(link.get("url") if isinstance(link, dict) else link or "")
        label = str(link.get("label") or "") if isinstance(link, dict) else ""
        url = clean_url(unwrap(raw)) if raw else ""
        if url.startswith("http") and url not in seen:
            seen.add(url)
            out.append((url, label))
    return out


def norm_path(url: str) -> str:
    parts = urlsplit(url or "")
    return (parts.path or "/").rstrip("/").lower()


def references(url: str) -> list[str]:
    """Product numbers in a target's link (five digits or more, or a code such as ``8433890612345`` / ``B0DXYZ1234``)."""
    path = urlsplit(url or "").path
    found = re.findall(r"(?<![0-9])\d{5,}(?![0-9])", path) + re.findall(r"\b[A-Z0-9]{10}\b", path)
    return list(dict.fromkeys(found))


def name_score(name: str, haystack_words: set[str]) -> tuple[int, float]:
    """Score (0-100) of a product name found in a mail: every significant word present gives 95."""
    tokens = significant(name)
    if len(tokens) < 2:
        return 0, 0.0
    present = sum(1 for t in tokens if t in haystack_words)
    frac = present / len(tokens)
    return (int(round(60 + 35 * frac)) if frac >= 0.85 else 0), frac


def mail_prices(subject: str, text: str) -> tuple[Optional[float], Optional[float], str]:
    """``(price, old_price, currency)``: the lowest and highest price near the top of the mail."""
    found = prices(f"{subject}\n{text[:2500]}")
    if not found:
        return None, None, ""
    amounts = [a for _, a, _ in found[:6]]
    low, high = min(amounts), max(amounts)
    return low, (high if high > low else None), found[0][2] or "EUR"


# ----------------------------------------------------------------------------- the scanner
class StockNotices:
    def __init__(self, store: Any, engine: Engine, db: Any, source: MailSource,
                 settings_get: Callable[[str, Optional[str]], Optional[str]], set_setting: Callable[[str, str], None],
                 clock: Callable[[], float] = time.time):
        self.store = store
        self.engine = engine
        self.db = db
        self.source = source
        self.get = settings_get
        self.put = set_setting
        self.clock = clock
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ settings
    def _s(self, key: str) -> str:
        value = self.get(key, None)
        return DEFAULTS[key] if value in (None, "") else str(value)

    def _n(self, key: str) -> int:
        low, high = NUMERIC[key]
        try:
            return max(low, min(high, int(float(self._s(key)))))
        except ValueError:
            return int(DEFAULTS[key])

    def enabled(self) -> bool:
        return self._s("mail.notices.enabled") == "1"

    def due(self, now: float) -> bool:
        if not self.enabled() or self._lock.locked():
            return False
        last = float(self.get("mail.notices.last_attempt_ts", "0") or 0)
        return now - last >= self._n("mail.notices.interval_min") * 60

    def run_job(self, ref: str = "all") -> dict[str, Any]:
        return self.run()

    # ------------------------------------------------------------------ the shops being watched
    def watched(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """``(watcher, target)`` of every product target of the enabled availability watchers."""
        out = []
        for watcher in self.store.watchers(mode=MODE_AVAILABILITY, enabled=True):
            for target in self.store.targets(watcher_id=watcher["id"]):
                if target.get("status") != "paused" and str(target.get("url") or "").startswith("http"):
                    out.append((watcher, target))
        return out

    def shops(self) -> list[dict[str, Any]]:
        """One row per watched shop: its domain, the sender domains that speak for it, how many targets it has."""
        pairs = parse_pairs(self._s("mail.notices.domains"))
        rows: dict[str, dict[str, Any]] = {}
        for watcher, target in self.watched():
            own = registrable(urlsplit(target["url"]).hostname or "")
            if not own:
                continue
            row = rows.setdefault(own, {"shop": own, "senders": set(), "targets": 0, "paused_here": 0,
                                        "retailer": target.get("retailer") or ""})
            row["senders"] |= shop_domains(target["url"])
            row["targets"] += 1
            if self._paused(target):
                row["paused_here"] += 1
        for sender, shop in pairs.items():
            if shop in rows:
                rows[shop]["senders"].add(sender)
        return [{**r, "senders": sorted(r["senders"])} for r in sorted(rows.values(), key=lambda r: r["shop"])]

    def _senders_of(self, target: dict[str, Any], pairs: dict[str, str]) -> set[str]:
        out = shop_domains(target["url"])
        own = registrable(urlsplit(target["url"]).hostname or "")
        out |= {sender for sender, shop in pairs.items() if shop == own}
        return out

    @staticmethod
    def _paused(target: dict[str, Any]) -> bool:
        """Would a page check of this target wait here (open window, or a window-only shop, off Windows)?"""
        return not WINDOWS_HOST and (target.get("fetch_tier") == "open_window" or Engine._window_site(target))

    # ------------------------------------------------------------------ one scan
    def run(self, *, history_days: Optional[int] = None, limit: int = MAX_PER_RUN) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "skipped": "a scan is already running"}
        now = self.clock()
        run_id = self.store.start_run("mail_notices")
        summary: dict[str, Any] = {"ok": True, "scanned": 0, "notices": 0, "matched": 0, "alerts": 0, "ended": 0, "expired": 0,
                                   "errors": []}
        try:
            self.put("mail.notices.last_attempt_ts", str(now))
            summary["expired"] = self.expire(now)
            pairs = parse_pairs(self._s("mail.notices.domains"))
            watched = self.watched()
            domains = sorted({d for _, t in watched for d in self._senders_of(t, pairs)} | set(pairs))
            summary["shops"] = len({registrable(urlsplit(t["url"]).hostname or "") for _, t in watched})
            if not domains:
                return self._finish(run_id, summary)
            days = int(history_days or self._n("mail.notices.history_days"))
            skip = [r["message_id"] for r in self.db.query("SELECT message_id FROM mail_notice_seen WHERE seen_ts >= ?",
                                                             (now - (days + 30) * 86400,))]
            answer = self.source.scan(days, limit, domains, skip)
            messages = answer.get("messages") or []
            if not answer.get("ok") and not messages:
                summary.update(ok=False, errors=[str(answer.get("error") or "mail not readable")[:300]])
                return self._finish(run_id, summary)
            if answer.get("error"):
                summary["errors"].append(str(answer["error"])[:300])
            for msg in sorted(messages, key=lambda m: float(m.get("ts") or 0)):
                summary["scanned"] += 1
                try:
                    self._ingest(msg, watched, pairs, now, summary)
                except Exception as error:  # noqa: BLE001 - one odd mail never stops the scan
                    log.exception("stock notice failed")
                    summary["errors"].append(f"{type(error).__name__}: {error}"[:200])
            return self._finish(run_id, summary)
        except Exception as error:  # noqa: BLE001
            log.exception("stock notice scan failed")
            summary.update(ok=False, errors=[f"{type(error).__name__}: {error}"[:300]])
            return self._finish(run_id, summary)
        finally:
            self._lock.release()

    def _finish(self, run_id: int, summary: dict[str, Any]) -> dict[str, Any]:
        self.put("mail.notices.last_run_ts", str(self.clock()))
        self.put("mail.notices.last_summary", json.dumps(summary, ensure_ascii=False)[:4000])
        self.put("mail.notices.last_error", "; ".join(summary.get("errors") or [])[:300] if not summary.get("ok") else "")
        self.store.finish_run(run_id, bool(summary.get("ok")), summary)
        return summary

    def _ingest(self, msg: dict[str, Any], watched: list[tuple[dict[str, Any], dict[str, Any]]], pairs: dict[str, str], now: float,
                summary: dict[str, Any]) -> None:
        sender = registrable(domain_of(str(msg.get("from_address") or "")))
        subject = str(msg.get("subject") or "")
        message_id = str(msg.get("message_id") or "") or "noid:" + hashlib.sha1(
            f"{sender}|{subject}|{msg.get('ts')}".encode()).hexdigest()[:24]
        self.db.execute("INSERT INTO mail_notice_seen(message_id, seen_ts) VALUES (?,?) ON CONFLICT(message_id) DO NOTHING",
                        (message_id, now))
        text = str(msg.get("text") or "")
        verdict = classify(subject, text)
        if not verdict["kind"]:
            return
        summary["notices"] += 1
        mail_ts = float(msg.get("ts") or 0) or now
        links = link_urls(msg)
        price, old_price, currency = mail_prices(subject, text)
        base = {"message_id": message_id, "sender_domain": sender, "kind": verdict["kind"], "phrase": verdict["phrase"],
                "personal": verdict["personal"], "subject": clean_title(subject, 300), "price": price, "old_price": old_price,
                "currency": currency, "mail_ts": mail_ts}
        candidates = [(w, t) for w, t in watched if sender in self._senders_of(t, pairs)]
        matches = self.match(msg, candidates, links)
        if not matches:
            shop = next((registrable(urlsplit(t["url"]).hostname or "") for _, t in candidates), pairs.get(sender, sender))
            title = next((label for _, label in links if len(significant(label)) >= 2), "") or clean_title(subject, 200)
            self._save({**base, "item_key": "", "shop": shop, "title": title, "url": links[0][0] if links else "",
                        "status": "unmatched", "note": "" if candidates else "no_target_for_shop"})
            return
        summary["matched"] += 1
        for m in matches:
            outcome = self.apply(base, m, now)
            summary["alerts"] += 1 if outcome.get("alert") else 0
            summary["ended"] += outcome.get("ended", 0)

    # ------------------------------------------------------------------ matching
    def match(self, msg: dict[str, Any], candidates: list[tuple[dict[str, Any], dict[str, Any]]],
              links: list[tuple[str, str]]) -> list[dict[str, Any]]:
        """The watched targets (or rows of an open-window list) the mail is about, best first, each scoring ``MATCH_MIN`` or more."""
        hay = " ".join([str(msg.get("subject") or ""), str(msg.get("text") or "")[:6000],
                        " ".join(label for _, label in links), " ".join(map(str, msg.get("images") or []))])
        hay_words = set(words(hay))
        link_paths = {norm_path(u) for u, _ in links}
        link_text = " ".join(urlsplit(u).path for u, _ in links)
        found: list[dict[str, Any]] = []
        for watcher, target in candidates:
            best = {"score": 0, "how": "", "item_key": "", "title": "", "state": target.get("last_state") or UNKNOWN, "url": ""}
            if norm_path(target["url"]) in link_paths and norm_path(target["url"]) not in ("", "/"):
                best.update(score=100, how="link", url=target["url"])
            else:
                for ref in references(target["url"]):
                    if ref in link_text:
                        best.update(score=95, how="reference", url=next((u for u, _ in links if ref in u), target["url"]))
                        break
                    if ref.lower() in hay_words or ref in hay:
                        best.update(score=85, how="reference")
                        break
            items = (target.get("extra") or {}).get("items") or {}
            if target.get("fetch_tier") == "open_window" and items:
                # a list in an open window: the mail speaks for one of its rows (a link to the list alone says which none)
                row_best: Optional[tuple[int, str, dict[str, Any]]] = None
                for key, row in items.items():
                    score, _ = name_score(row.get("title") or "", hay_words)
                    if score >= MATCH_MIN and (row_best is None or score > row_best[0]):
                        row_best = (score, key, row)
                if row_best is None:
                    best["score"] = 0
                else:
                    score, key, row = row_best
                    best.update(score=max(score, best["score"]), how=best["how"] or "name", item_key=key, title=row.get("title") or "",
                                state=row.get("state") or UNKNOWN, url=key if key.startswith("http") else (best["url"] or target["url"]))
            elif best["score"] < MATCH_MIN:
                name = target.get("last_title") or target.get("label") or ""
                score, _ = name_score(name, hay_words)
                if score > best["score"]:
                    best.update(score=score, how="name", title=name)
            if best["score"] >= MATCH_MIN:
                found.append({**best, "watcher": watcher, "target": target})
        found.sort(key=lambda m: -m["score"])
        # Two products with nearly the same name (the Mew and the Mewtwo box): a match by name alone goes to the closest only.
        by_name = [m for m in found if m["how"] == "name"]
        if len(by_name) > 1:
            top = by_name[0]["score"]
            found = [m for m in found if m["how"] != "name" or m["score"] == top]
        return found

    # ------------------------------------------------------------------ alerts
    def apply(self, base: dict[str, Any], m: dict[str, Any], now: float, *, manual: bool = False) -> dict[str, Any]:
        """Record the notice for one matched target and raise (or end) its alert. ``{"alert": event | None, "ended": n}``."""
        watcher, target = m["watcher"], m["target"]
        title = m.get("title") or target.get("last_title") or target.get("label") or base.get("subject") or ""
        row = {**base, "item_key": m.get("item_key") or target["id"], "shop": registrable(urlsplit(target["url"]).hostname or ""),
               "title": clean_title(title, 200), "url": m.get("url") or target["url"], "target_id": target["id"],
               "watcher_id": watcher["id"], "match_how": "manual" if manual else m["how"], "match_score": int(m["score"])}
        fresh = base["mail_ts"] >= now - self._n("mail.notices.max_age_hours") * 3600
        kind = base["kind"]
        live = [e for e in self.store.live_alerts(target_id=target["id"])
                if not m.get("item_key") or (e.get("data") or {}).get("item_key") == m["item_key"] or e.get("url") == m.get("url")]
        if kind == SOLD:
            ended = self.engine.end_alerts(watcher, live, state=OUT_OF_STOCK, at=now, notify=fresh) if live else []
            self._save({**row, "status": "ended" if live else "matched", "note": "ended" if live else ""})
            return {"alert": None, "ended": len(live), "follow_ups": ended}
        if not fresh:
            self._save({**row, "status": "old", "note": "too_old"})
            return {"alert": None, "ended": 0}
        state = m.get("state") or UNKNOWN
        if kind == PRICE:
            alert_type, extra = PRICE_DROP, {}
            old = base.get("old_price") or target.get("last_price")
            if base.get("price") is None:
                self._save({**row, "status": "matched", "note": "no_price"})
                return {"alert": None, "ended": 0}
            if old and float(old) > float(base["price"]):
                extra["drop_pct"] = round((float(old) - float(base["price"])) / float(old) * 100, 1)
        elif kind == PREORDER:
            alert_type, extra = (SALE_OPEN, {"sale_kind": "preorder"}) if state == COMING_SOON else (PREORDER_OPEN, {})
        else:
            alert_type, extra = (SALE_OPEN, {"sale_kind": "sale"}) if state == COMING_SOON else (RESTOCK, {})
        family = {PRICE_DROP: {PRICE_DROP, "PRICE_THRESHOLD_CROSSED"}}.get(alert_type, {RESTOCK, "LOCAL_RESTOCK", PREORDER_OPEN, SALE_OPEN})
        twin = next((e for e in live if e["type"] in family), None)
        if twin is not None:
            # the page (or an earlier mail) already announced it and it is still on: one alert, not two
            self._save({**row, "status": "matched", "alert_type": alert_type, "event_id": twin["id"],
                        "note": "already_announced"})
            return {"alert": None, "ended": 0}
        event = self._raise(watcher, target, row, alert_type, extra, now)
        self._save({**row, "status": "alerted" if event["status"] == "confirmed" else "matched", "alert_type": alert_type,
                    "event_id": event["id"], "note": "" if event["status"] == "confirmed" else "watcher_quiet"})
        fields: dict[str, Any] = {"extra": {**(target.get("extra") or {}), "mail_notice": {
            "kind": kind, "at": now, "subject": row["subject"][:200], "event_id": event["id"], "sender": base["sender_domain"]}}}
        if not self._paused(target):
            fields["next_check_ts"] = now          # the page gets a look now: it confirms the alert or ends it
        self.store.update_target(target["id"], **fields)
        return {"alert": event if event["status"] == "confirmed" else None, "ended": 0}

    def _raise(self, watcher: dict[str, Any], target: dict[str, Any], row: dict[str, Any], alert_type: str, extra: dict[str, Any],
               now: float) -> dict[str, Any]:
        policies = rules.policies_for(watcher.get("config") or {})
        alert_on = set(policies.get("alert_on") or [])
        if alert_on & {RESTOCK, PREORDER_OPEN}:
            alert_on.add(SALE_OPEN)
        confidence = CONFIDENCE.get(row["match_how"], 80)
        require = int(policies.get("require_confidence") or rules.ALERT_THRESHOLD)
        status = "confirmed" if alert_type in alert_on and confidence >= require else "logged"
        retailer = target.get("retailer") or row["shop"]
        currency = row.get("currency") or target.get("last_currency") or "EUR"
        price = row.get("price") if row.get("price") is not None else (None if alert_type == PRICE_DROP else target.get("last_price"))
        old_price = row.get("old_price") or (target.get("last_price") if alert_type == PRICE_DROP else None)
        summary = rules.summary_for(alert_type, title=row["title"], retailer=retailer, state="", price=price, currency=currency,
                                    old_price=old_price, extra=extra)
        summary = re.sub(r" \(antes ponía «Próximamente»\)$", "", summary) if alert_type != SALE_OPEN else summary
        summary += f" · aviso de la tienda por correo: «{row['subject'][:120]}»"
        how = {"link": "el enlace del producto", "reference": "la referencia del producto", "name": "el nombre del producto",
               "manual": "asignado a mano"}.get(row["match_how"], row["match_how"])
        factors = [{"key": "official_mail", "points": confidence, "label": f"Aviso de la propia tienda por correo ({row['sender_domain']})"},
                   {"key": "mail_match", "points": 0, "label": f"Casado por {how}"}]
        key = rules.dedupe_key(f"mail:{row['message_id']}:{row['item_key']}", alert_type, "", price)
        data = {**extra, "source": MAIL_NOTICE_SOURCE, "retailer": retailer, "factors": factors, "method": "mail",
                "evidence": [f"«{row['phrase']}» en el correo de {row['sender_domain']}"], "image": target.get("last_image") or "",
                "message_id": row["message_id"], "mail_subject": row["subject"][:300], "match_how": row["match_how"]}
        if row["item_key"] != target["id"]:
            data["item_key"] = row["item_key"]
        event = self.store.add_event({
            "watcher_id": watcher["id"], "target_id": target["id"], "type": alert_type, "severity": rules.SEVERITY.get(alert_type, "medium"),
            "status": status, "old_state": target.get("last_state") or "", "new_state": "", "price": price, "old_price": old_price,
            "currency": currency, "confidence": confidence, "dedupe_key": key, "url": row["url"], "title": row["title"],
            "summary": summary[:600], "data": data, "detected_at": now})
        if status == "confirmed":
            try:
                self.engine.dispatch(event, watcher)
            except Exception:  # noqa: BLE001 - the alert is stored; a channel failure must not lose the next notice
                log.exception("dispatch of stock notice %s failed", event["id"])
            event = self.store.event(event["id"])
        return event

    def expire(self, now: float) -> int:
        """Mail alerts no page has confirmed end quietly ("unconfirmed") after ``mail.notices.live_hours``."""
        horizon = now - self._n("mail.notices.live_hours") * 3600
        ended = 0
        for ev in self.store.live_alerts():
            if (ev.get("data") or {}).get("source") != MAIL_NOTICE_SOURCE or float(ev["detected_at"]) > horizon:
                continue
            target = None
            if ev.get("target_id"):
                try:
                    target = self.store.target(ev["target_id"])
                except Exception:  # noqa: BLE001 - a deleted target: nothing vouches for the alert any more
                    target = None
            if target and float(target.get("last_check_ts") or 0) > float(ev["detected_at"]) and target.get("last_state") in BUYABLE \
                    and not (ev.get("data") or {}).get("item_key"):
                continue                               # the page itself still sells it: the page will end it
            watcher = self.store.watcher(ev["watcher_id"]) if ev.get("watcher_id") else {"config": {}}
            self.engine.end_alerts(watcher, [ev], state=UNKNOWN, at=now)
            ended += 1
        return ended

    # ------------------------------------------------------------------ storage
    # ``note`` codes: no_target_for_shop (the sender is no watched shop), already_announced (an alert of the same kind is still
    # live), too_old (older than mail.notices.max_age_hours), no_price (a price-drop mail without a price), watcher_quiet (the
    # watcher does not alert on this kind), ended (a sold-out mail ended the live alerts).
    COLUMNS = ("message_id", "item_key", "sender_domain", "shop", "kind", "phrase", "personal", "title", "subject", "price", "old_price",
               "currency", "url", "mail_ts", "first_seen_ts", "status", "target_id", "watcher_id", "match_how", "match_score",
               "alert_type", "event_id", "note")

    def _save(self, row: dict[str, Any]) -> dict[str, Any]:
        values = {c: row.get(c) for c in self.COLUMNS}
        values["first_seen_ts"] = values["first_seen_ts"] or self.clock()
        values["personal"] = 1 if row.get("personal") else 0
        values["match_score"] = int(row.get("match_score") or 0)
        for c in ("sender_domain", "shop", "kind", "phrase", "title", "subject", "currency", "url", "status", "target_id", "watcher_id",
                  "match_how", "alert_type", "event_id", "note", "item_key"):
            values[c] = str(values[c] or "")
        values["status"] = values["status"] or "unmatched"
        cols = ",".join(self.COLUMNS)
        updates = ",".join(f"{c} = excluded.{c}" for c in self.COLUMNS if c not in ("message_id", "item_key", "first_seen_ts"))
        self.db.execute(f"INSERT INTO mail_notices({cols}) VALUES ({','.join('?' * len(self.COLUMNS))})"
                        f" ON CONFLICT(message_id, item_key) DO UPDATE SET {updates}", [values[c] for c in self.COLUMNS])
        return self.notice_by_key(values["message_id"], values["item_key"]) or values

    def notice_by_key(self, message_id: str, item_key: str) -> Optional[dict[str, Any]]:
        row = self.db.one("SELECT * FROM mail_notices WHERE message_id = ? AND item_key = ?", (message_id, item_key))
        return self._row(row) if row else None

    def notice(self, notice_id: int) -> Optional[dict[str, Any]]:
        row = self.db.one("SELECT * FROM mail_notices WHERE id = ?", (int(notice_id),))
        return self._row(row) if row else None

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        d = dict(row)
        d["personal"] = bool(d.get("personal"))
        return d

    def notices(self, *, status: str = "", kind: str = "", target_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM mail_notices WHERE 1=1", []
        if status == "matched":
            sql += " AND status IN ('alerted','matched','ended','old')"
        elif status:
            sql += " AND status = ?"
            params.append(status)
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if target_id:
            sql += " AND target_id = ?"
            params.append(target_id)
        rows = self.db.query(sql + " ORDER BY mail_ts DESC, id DESC LIMIT ?", params + [max(1, min(500, int(limit)))])
        out = [self._row(r) for r in rows]
        labels = {}
        for n in out:
            if n["target_id"] and n["target_id"] not in labels:
                try:
                    t = self.store.target(n["target_id"])
                    labels[n["target_id"]] = t.get("label") or t.get("last_title") or t["url"]
                except Exception:  # noqa: BLE001
                    labels[n["target_id"]] = ""
            n["target_label"] = labels.get(n["target_id"], "")
        return out

    def counts(self) -> dict[str, int]:
        rows = self.db.query("SELECT status, COUNT(*) AS n FROM mail_notices GROUP BY status")
        out = {r["status"]: int(r["n"]) for r in rows}
        out["seen_mails"] = int(self.db.one("SELECT COUNT(*) FROM mail_notice_seen")[0])
        return out

    # ------------------------------------------------------------------ manual corrections
    def assign(self, notice_id: int, target_id: str, item_key: str = "") -> dict[str, Any]:
        """Match a notice to a target by hand (the rules missed it). A fresh notice raises its alert as a matched one would."""
        n = self.notice(notice_id)
        if n is None:
            raise LookupError(f"notice {notice_id} does not exist")
        target = self.store.target(target_id)
        watcher = self.store.watcher(target["watcher_id"])
        items = (target.get("extra") or {}).get("items") or {}
        row = items.get(item_key) if item_key else None
        base = {k: n[k] for k in ("message_id", "sender_domain", "kind", "phrase", "personal", "subject", "price", "old_price",
                                  "currency", "mail_ts")}
        m = {"watcher": watcher, "target": target, "score": 100, "how": "manual", "item_key": item_key if row else "",
             "title": (row or {}).get("title") or "", "state": (row or {}).get("state") or target.get("last_state") or UNKNOWN,
             "url": item_key if row and item_key.startswith("http") else target["url"]}
        outcome = self.apply(base, m, self.clock(), manual=True)
        if n["status"] == "unmatched" and n["item_key"] == "":
            self.db.execute("DELETE FROM mail_notices WHERE id = ?", (int(notice_id),))
        saved = self.notice_by_key(n["message_id"], m["item_key"] or target["id"])
        return {"notice": saved, "alert": outcome.get("alert"), "ended": outcome.get("ended", 0)}

    def ignore(self, notice_id: int) -> dict[str, Any]:
        n = self.notice(notice_id)
        if n is None:
            raise LookupError(f"notice {notice_id} does not exist")
        self.db.execute("UPDATE mail_notices SET status = 'ignored' WHERE id = ?", (int(notice_id),))
        return self.notice(notice_id) or {}

    # ------------------------------------------------------------------ status and rules
    def status(self) -> dict[str, Any]:
        last = float(self.get("mail.notices.last_run_ts", "0") or 0)
        attempt = float(self.get("mail.notices.last_attempt_ts", "0") or 0)
        try:
            summary = json.loads(self.get("mail.notices.last_summary", "") or "{}")
        except ValueError:
            summary = {}
        return {"enabled": self.enabled(), "interval_min": self._n("mail.notices.interval_min"),
                "history_days": self._n("mail.notices.history_days"), "max_age_hours": self._n("mail.notices.max_age_hours"),
                "live_hours": self._n("mail.notices.live_hours"), "domains": self._s("mail.notices.domains"),
                "last_run_ts": last or None, "last_attempt_ts": attempt or None,
                "next_run_ts": (attempt + self._n("mail.notices.interval_min") * 60) if self.enabled() and attempt else None,
                "last_error": self.get("mail.notices.last_error", "") or "", "last_summary": summary, "running": self._lock.locked(),
                "counts": self.counts(), "shops": self.shops(), "windows_here": WINDOWS_HOST}

    @staticmethod
    def rules() -> dict[str, Any]:
        """The phrase rules as the screen shows them."""
        return {"kinds": {kind: [label for _, label in RULES[kind]] for kind in KINDS},
                "personal": [label for _, label in PERSONAL],
                "alert_for": {AVAILABLE: [RESTOCK, SALE_OPEN], PREORDER: [PREORDER_OPEN, SALE_OPEN], PRICE: [PRICE_DROP], SOLD: []},
                "match_min": MATCH_MIN, "sender_aliases": {k: v for k, v in SHOP_SENDERS.items() if v}}


__all__ = ["StockNotices", "classify", "registrable", "shop_domains", "name_score", "parse_pairs", "DEFAULTS", "NUMERIC", "RULES",
           "LIVE_ALERT_TYPES"]
