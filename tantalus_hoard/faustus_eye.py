"""Faustus looks too: a second, thinking reader for targets read from an open window.

Hermes reads the window itself every few minutes (``fetch/open_window.py``, rules plus the family model in
``extract/window_check.py``). On top of that it asks Faustus, through the hoard copilot contract
(``/api/hoard-copilot/conversations`` + ``/api/chat_stream``), to look at the same tab with Faustus's own browser
extension (``browser_session``: the person's real browser, in the background), to open a product's page or search more
when something looks available or changed, and to answer with its rows as JSON. Hermes's own reading goes in the
request, so Faustus checks it instead of starting blind.

The request runs in a background thread and never blocks a check. Its answer (the *verdict*) is stored on the target
(``extra["faustus"]``); when it disagrees with Hermes or sees something buyable, the target's next check is moved to now so
the engine merges it at once (:func:`merge`).

Nothing here touches the shop: Faustus is told to look only. Without Faustus (not running, extension not connected) the
verdict says so and Hermes keeps watching on its own.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from typing import Any, Callable, Optional

import httpx

from .extract.window_check import STATUS, similarity
from .model import BUYABLE, UNKNOWN, Extraction, Offer

log = logging.getLogger("tantalus.faustus_eye")

DEFAULT_URL = "http://127.0.0.1:7000"
TURN_TIMEOUT_S = 420.0
FRESH_S = 15 * 60               # a verdict older than this is not merged
TURNS_PER_CONVERSATION = 6      # a new Faustus conversation after this many looks, so its context stays small
MATCH_MIN = 0.6

PROMPT = """Hermes's Hoard (el vigilante de productos de Luis) te pide que mires una lista de una tienda y le digas lo que ves. \
Solo mirar: no añadas nada a la cesta, no pulses botones de compra, no cambies nada en la tienda.

Lista: {url}

1. Con la herramienta browser_session (la extensión de Faustus en el navegador de Luis), usa `tabs` y localiza la pestaña \
cuya dirección empieza por esa lista. No actives ni cierres otras pestañas. Si la extensión no está disponible o la pestaña \
no está abierta, NO uses otro navegador: responde enseguida con "rows": [] y explícalo en "notes".
2. Recárgala con la acción `reload` pasando view {{"text": true}}: espera a la página nueva y te la devuelve ya como texto \
(nombre, precio y botón de cada fila). Si la lista es larga, `scroll` hacia abajo y vuelve a leer con snapshot view text.
3. Lee cada producto: nombre, precio y el texto exacto de su botón o etiqueta ("[button …] Añadir", "Agotado temporalmente", \
"Próximamente"…; "(disabled)" significa que el botón está apagado).
4. Compara con lo que ha leído Hermes (abajo). Si algún producto parece disponible, reservable o distinto de lo que dice \
Hermes, mira con más detalle: abre su ficha con `open_tab` (pestaña nueva en segundo plano, no toca la de Luis), léela con \
snapshot view text (y una captura con `screenshot` si el texto no basta), y ciérrala con `close_tab`. Si sirve, busca más \
(por ejemplo si hoy hay reposición anunciada).

Lo que ha leído Hermes ahora mismo:
{hermes}

Responde SOLO con un bloque JSON, sin texto alrededor:
{{"rows": [{{"title": "...", "price": 0.0, "status": "in_stock|out_of_stock|coming_soon|preorder|unknown", \
"evidence": "texto literal del botón o etiqueta", "where": "lista|ficha"}}], "notes": "lo que hayas comprobado de más"}}"""


def _hermes_lines(offers: list[Offer]) -> str:
    out = []
    for o in offers[:40]:
        price = f"{o.price:.2f} €" if o.price is not None else "sin precio"
        out.append(f"- {o.title} · {price} · {o.availability}")
    return "\n".join(out) or "- (Hermes no ha leído filas)"


def parse_answer(text: str) -> Optional[dict[str, Any]]:
    """The last JSON object with ``rows`` in Faustus's answer (it may think aloud before it)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    starts = [m.start() for m in re.finditer(r"\{", text)]
    for start in reversed(starts):
        chunk = text[start:]
        depth, end = 0, None
        for i, ch in enumerate(chunk):
            depth += 1 if ch == "{" else -1 if ch == "}" else 0
            if depth == 0:
                end = i + 1
                break
        if end is None:
            continue
        try:
            value = json.loads(chunk[:end])
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get("rows"), list):
            return value
    return None


class FaustusEye:
    """Asks Faustus to look at a target's open window, one look at a time per target, in a background thread."""

    def __init__(self, store: Any, *, url: Callable[[], str] = lambda: DEFAULT_URL,
                 enabled: Callable[[], bool] = lambda: True, clock: Callable[[], float] = time.time,
                 transport: Optional[httpx.BaseTransport] = None, run_inline: bool = False):
        self.store = store
        self.url = url
        self.enabled = enabled
        self.clock = clock
        self.transport = transport
        self.run_inline = run_inline          # tests: run the look in the calling thread
        self._busy: set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ asking
    def request(self, target: dict[str, Any], offers: list[Offer], reason: str = "check") -> bool:
        """Start a look unless one is running for this target or Faustus is switched off. Returns True when started."""
        if not self.enabled():
            return False
        with self._lock:
            if target["id"] in self._busy:
                return False
            self._busy.add(target["id"])
        args = (target["id"], target["url"], _hermes_lines(offers), reason)
        if self.run_inline:
            self._look(*args)
        else:
            threading.Thread(target=self._look, args=args, name=f"faustus-eye-{target['id']}", daemon=True).start()
        return True

    def _look(self, target_id: str, url: str, hermes: str, reason: str) -> None:
        started = self.clock()
        verdict: dict[str, Any] = {"asked_at": started, "reason": reason, "ok": False}
        try:
            text, session_id = self._ask(target_id, PROMPT.format(url=url, hermes=hermes))
            answer = parse_answer(text)
            verdict["session_id"] = session_id
            if answer is None:
                verdict["error"] = "Faustus no devolvió las filas en JSON"
                verdict["answer_tail"] = (text or "")[-400:]
            else:
                rows = [r for r in answer["rows"] if isinstance(r, dict) and str(r.get("title") or "").strip()][:60]
                verdict.update(ok=bool(rows), rows=rows, notes=str(answer.get("notes") or "")[:800])
                if not rows:
                    verdict["error"] = str(answer.get("notes") or "Faustus no leyó ninguna fila")[:300]
        except Exception as error:  # noqa: BLE001 - Faustus is optional: say why and carry on
            verdict["error"] = f"{type(error).__name__}: {error}"[:300]
        finally:
            with self._lock:
                self._busy.discard(target_id)
        verdict["at"] = self.clock()
        verdict["seconds"] = round(verdict["at"] - started, 1)
        self._store(target_id, verdict)

    def _ask(self, target_id: str, prompt: str) -> tuple[str, str]:
        base = (self.url() or DEFAULT_URL).rstrip("/")
        client = httpx.Client(timeout=httpx.Timeout(TURN_TIMEOUT_S, connect=5), trust_env=False, transport=self.transport)
        try:
            session_id = self._session(client, base, target_id)
            text = ""
            body = {"session": session_id, "message": prompt, "mode": "agent", "client_message_id": str(uuid.uuid4())}
            with client.stream("POST", base + "/api/chat_stream", json=body) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"Faustus respondió {response.status_code}")
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except ValueError:
                        continue
                    if isinstance(obj, dict) and isinstance(obj.get("delta"), str):
                        text += obj["delta"]
            return text, session_id
        finally:
            client.close()

    def _session(self, client: httpx.Client, base: str, target_id: str) -> str:
        """The Faustus conversation for this target's looks; a new one every few looks so its context stays small."""
        key = f"faustus_eye.session.{target_id}"
        saved = (self.store.db.get_setting(key, "") or "").split("|")
        if len(saved) == 2 and saved[0] and int(saved[1] or 0) < TURNS_PER_CONVERSATION:
            self.store.db.set_setting(key, f"{saved[0]}|{int(saved[1]) + 1}")
            return saved[0]
        label = (self.store.target(target_id).get("label") or "ventana abierta")[:60]
        response = client.post(base + "/api/hoard-copilot/conversations", json={
            "context": {"origin": {"app_id": "hermes", "data_space_id": "products", "surface": "open-window-watch"}},
            "name": f"Hermes · {label} · {time.strftime('%d-%m %H:%M', time.localtime(self.clock()))}"})
        if response.status_code >= 400:
            raise RuntimeError(f"Faustus no abrió la conversación ({response.status_code})")
        session_id = str(response.json()["session_id"])
        self.store.db.set_setting(key, f"{session_id}|1")
        return session_id

    def _store(self, target_id: str, verdict: dict[str, Any]) -> None:
        """Kept in its own setting, not in the target's ``extra``: the engine rewrites ``extra`` at the end of each check
        and a verdict arriving meanwhile would be lost."""
        previous = self.latest(target_id)
        self.store.db.set_setting(VERDICT_KEY + target_id, json.dumps(verdict, ensure_ascii=False))
        try:
            target = self.store.target(target_id)
        except Exception:  # noqa: BLE001 - the target was deleted meanwhile
            return
        if verdict.get("ok") and _differs(verdict, dict(target.get("extra") or {}), previous):
            self.store.update_target(target_id, next_check_ts=self.clock())   # merge it now, not in five minutes

    def latest(self, target_id: str) -> Optional[dict[str, Any]]:
        raw = self.store.db.get_setting(VERDICT_KEY + target_id, "") or ""
        try:
            value = json.loads(raw) if raw else None
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def busy(self, target_id: str) -> bool:
        with self._lock:
            return target_id in self._busy


VERDICT_KEY = "faustus_eye.verdict."


def _differs(verdict: dict[str, Any], extra: dict[str, Any], previous: Optional[dict[str, Any]] = None) -> bool:
    """Is this look news for Hermes: a row it follows with another status, or a buyable row it does not follow yet
    that the previous look did not already report?

    A buyable row Hermes leaves out (an unrelated product in the same list) is reported once, not on every look:
    otherwise each look would bring the next check forward and the page would be reloaded every minute."""
    items = list((extra.get("items") or {}).values())
    before = {" ".join(str(row.get("title") or "").casefold().split()): STATUS.get(str(row.get("status") or "").lower(), UNKNOWN)
              for row in (previous or {}).get("rows") or []}
    for row in verdict.get("rows") or []:
        title = str(row.get("title") or "")
        status = STATUS.get(str(row.get("status") or "").lower(), UNKNOWN)
        best = max(items, key=lambda it: similarity(title, it.get("title") or ""), default=None)
        if best is not None and similarity(title, best.get("title") or "") >= MATCH_MIN:
            if status != UNKNOWN and best.get("state") != status:
                return True
            continue
        if status in BUYABLE and before.get(" ".join(title.casefold().split())) not in BUYABLE:
            return True
    return False


# ====================================================================================== merging a verdict into Hermes's reading
def merge(ex: Extraction, verdict: Optional[dict[str, Any]], extra: dict[str, Any], url: str, now: float) -> dict[str, Any]:
    """Put Faustus's latest verdict next to Hermes's own reading of the same page (``ex.offers``, changed in place).

    Each verdict is merged once (``extra["faustus_used_at"]``) and only while fresh. Per row:

    * same status as Hermes → ``faustus_agrees`` (an independent reading: more confidence);
    * Hermes could not decide → Faustus's status, as a row that needs a second reading (``model_only``);
    * Faustus sees it buyable and Hermes does not (the list can lag behind the product page) → Faustus's status, and the
      row needs Faustus to say it again in its next look (``extra["faustus_rows"]`` counts consecutive verdicts):
      ``faustus_twice`` then counts as confirmed;
    * Faustus sees it not buyable while Hermes reads a buy button → the literal button stays, the difference is noted;
    * a buyable product Hermes did not list at all is added the same way.

    Returns the summary stored as ``extra["faustus_check"]``; ``extra`` gets ``faustus_rows`` / ``faustus_used_at``."""
    summary: dict[str, Any] = {"merged": False, "agree": 0, "disagree": 0, "filled": 0, "flagged": 0, "added": 0}
    if not verdict:
        summary["reason"] = "Faustus aún no ha mirado"
        return summary
    summary.update(at=verdict.get("at"), seconds=verdict.get("seconds"), notes=(verdict.get("notes") or "")[:300])
    if not verdict.get("ok"):
        summary["reason"] = verdict.get("error") or "Faustus no leyó la lista"
        return summary
    if now - float(verdict.get("at") or 0) > FRESH_S:
        summary["reason"] = "el último veredicto de Faustus es antiguo"
        return summary
    if extra.get("faustus_used_at") == verdict.get("at"):
        summary["reason"] = "veredicto ya incorporado"
        summary["merged"] = True
        return summary
    extra["faustus_used_at"] = verdict.get("at")
    counts: dict[str, Any] = dict(extra.get("faustus_rows") or {})
    seen_keys: set[str] = set()
    taken: set[int] = set()
    summary["merged"] = True
    for row in verdict.get("rows") or []:
        title = str(row.get("title") or "").strip()
        status = STATUS.get(str(row.get("status") or "").strip().lower(), UNKNOWN)
        evidence = str(row.get("evidence") or "").strip()[:160]
        where = str(row.get("where") or "").strip()[:20]
        note = f"Faustus ({where or 'lista'}): «{evidence}»" if evidence else f"Faustus: {status.lower()}"
        best, score = None, 0.0
        for i, offer in enumerate(ex.offers):
            if i not in taken:
                s = similarity(title, offer.title or "")
                if s > score:
                    best, score = i, s
        if best is not None and score >= MATCH_MIN:
            taken.add(best)
            offer = ex.offers[best]
            key = offer.url or offer.title or title
        else:
            offer = None
            key = f"{url}#item-" + (re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80] or "item")
        seen_keys.add(key)
        streak = int((counts.get(key) or {}).get("count") or 0) + 1 if (counts.get(key) or {}).get("status") == status else 1
        counts[key] = {"status": status, "count": streak, "title": title[:200]}
        if status == UNKNOWN:
            continue
        if offer is None:
            if status in BUYABLE:
                added = Offer(method="faustus", title=title, price=_num(row.get("price")), currency="EUR", availability=status, url=key)
                _mark_from_faustus(added, streak, note)
                ex.offers.append(added)
                summary["added"] += 1
            continue
        offer.extra["faustus_status"] = status
        if offer.availability == status:
            offer.extra["faustus_agrees"] = True
            offer.evidence.append(f"Faustus lo ve igual ({where or 'lista'})")
            summary["agree"] += 1
        elif offer.availability == UNKNOWN:
            offer.availability, offer.method = status, "faustus"
            _mark_from_faustus(offer, streak, note)
            summary["filled"] += 1
        elif status in BUYABLE and offer.availability not in BUYABLE:
            offer.extra["hermes_status"] = offer.availability
            offer.availability, offer.method = status, "faustus"
            _mark_from_faustus(offer, streak, note)
            summary["flagged"] += 1
        else:
            offer.extra["faustus_disagrees"] = status
            offer.evidence.append(f"{note} — no coincide con el botón que lee Hermes")
            summary["disagree"] += 1
    for key in list(counts):                     # a row Faustus no longer mentions starts its streak again
        if key not in seen_keys:
            counts.pop(key)
    extra["faustus_rows"] = counts
    return summary


def _mark_from_faustus(offer: Offer, streak: int, note: str) -> None:
    offer.evidence.append(note)
    if streak >= 2:
        offer.extra["faustus_twice"] = True      # two looks in a row said it: confirmed
    else:
        offer.extra["model_only"] = True          # one look: read again soon, alert when it repeats


def _num(value: Any) -> Optional[float]:
    try:
        return round(float(str(value).replace("€", "").replace(",", ".").strip()), 2) if value not in (None, "") else None
    except ValueError:
        return None
