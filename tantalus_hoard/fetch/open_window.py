"""Read a page from a browser window the person already has open (fetch tier ``open_window``).

Some shops answer any automated browser with a check (Carrefour: Cloudflare), while a window the person opened and passed the
check in keeps working. This tier never opens a browser: it finds the Brave / Chrome / Edge window whose active tab shows the
target address, presses that window's own Reload button through Windows UI Automation, scrolls the page to the end and back
to the top (so lazy lists load every row) and reads the page's text. The window is not brought to the front and no keys or
clicks are sent, so the person can keep working on the computer.

The text becomes a small HTML page. Product rows found in it (name, price, the text of the buy button) also go out as a
schema.org ``ItemList`` so the usual extraction and the engine (alerts, "se acabó" follow-ups, restock) treat them like any
other listing; each row gets its own link (the page address plus ``#item-<slug>``) so its alerts are told apart.

When the window shows a check instead of the page the read comes back blocked (``captcha``) and the page is left alone: the
person solves it in that window and the next read goes on.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from ..hoard_link.web.fetch import FetchResult

TIER = "open_window"
BROWSER_CLASS = "Chrome_WidgetWin_1"       # Brave, Chrome, Edge, Vivaldi, Opera: every Chromium top-level window
LOAD_TIMEOUT_S = 30.0
SETTLE_S = 1.2                             # the text must stay the same this long before it counts as loaded
SCROLL_PAUSE_S = 1.0

_PRICE = re.compile(r"^(?:desde\s+)?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?\s*(€|eur)\s*$", re.I)
_PRICE_ANY = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+),(\d{2})\s*€")
# The text of the row's button / label, folded. Order matters: "no disponible" before "disponible".
_STATUS = (
    ("OutOfStock", ("agotado", "sin stock", "no disponible", "fuera de stock", "out of stock", "sold out", "avisame", "notify me")),
    ("ComingSoon", ("proximamente", "coming soon", "disponible pronto")),
    ("PreOrder", ("reservar", "reserva ya", "preventa", "pre-order", "preorder")),
    ("InStock", ("anadir", "comprar", "add to cart", "add to basket", "buy now", "en stock", "disponible")),
)
_BADGE = ("maximo", "envio", "unidad", "oferta", "descuento", "nuevo", "patrocinado", "vendido por", "%", "2a unidad", "unidades")
_CHECK = ("verify you are human", "verifica que eres un humano", "verificar que eres humano", "comprobando si la conexion",
          "checking if the site connection is secure", "checking your browser", "just a moment", "un momento",
          "attention required", "you have been blocked", "has sido bloqueado", "captcha", "press & hold", "manten pulsado")


class OpenWindowError(Exception):
    """The window could not be read (not open, no UI Automation on this system, the page never loaded)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if unicodedata.category(c) != "Mn")


def available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import uiautomation  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def address_key(url: str) -> str:
    """``carrefour.es/mis-listas/1`` from any spelling of the address (scheme, www., trailing slash, fragment)."""
    raw = (url or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = parts.path.rstrip("/")
    return host + path + (("?" + parts.query) if parts.query else "")


def same_page(target_url: str, shown: str) -> bool:
    want, have = address_key(target_url), address_key(shown)
    return bool(want) and (have == want or have.startswith(want + "?") or have.startswith(want + "/"))


# ====================================================================================== text -> rows
def clean_lines(text: str) -> list[str]:
    """The page text as lines: object-replacement marks and icon-font glyphs (private use, odd CJK blocks) dropped."""
    out = []
    for line in (text or "").replace("\r", "\n").split("\n"):
        line = "".join(c for c in line if c != "￼" and unicodedata.category(c) not in ("Co", "Cs", "Cc"))
        line = re.sub(r"[가-힣]", "", line)          # icon fonts mapped onto Hangul code points
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            out.append(line)
    return out


def _price_of(line: str) -> Optional[float]:
    m = _PRICE.match(line)
    if not m:
        return None
    whole, cents = m.group(1).replace(".", ""), m.group(2) or "0"
    return round(int(whole) + int(cents.ljust(2, "0")) / 100, 2)


def status_of(line: str) -> Optional[str]:
    f = fold(line)
    if len(f) > 60:
        return None
    for availability, words in _STATUS:
        if any(w in f for w in words):
            return availability
    return None


def _is_badge(line: str) -> bool:
    f = fold(line)
    return len(f) < 4 or any(f.startswith(b) or b == f for b in _BADGE) or bool(_PRICE_ANY.search(line))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")[:80] or "item"


def parse_rows(lines: list[str]) -> list[dict[str, Any]]:
    """Product rows of a list page: each price line, the title above it (badges skipped) and the button / label below it.

    Works on shop lists, favourites and search results whose rows read "name … price … button", which is how Carrefour,
    GAME, El Corte Inglés and most Spanish shops lay them out. A row with no recognisable button keeps ``availability``
    empty (unknown), never a guess."""
    rows: list[dict[str, Any]] = []
    used: set[int] = set()
    for i, line in enumerate(lines):
        price = _price_of(line)
        if price is None:
            continue
        title, j = "", i - 1
        while j >= 0 and i - j <= 6 and j not in used:
            cand = lines[j]
            if _price_of(cand) is not None or status_of(cand):
                break
            if not _is_badge(cand) and len(cand) >= 8 and re.search(r"[a-zA-Z]{3}", cand):
                title = cand
                break
            j -= 1
        if not title:
            continue
        availability, label = "", ""
        for k in range(i + 1, min(len(lines), i + 4)):
            if _price_of(lines[k]) is not None:
                break
            state = status_of(lines[k])
            if state:
                availability, label = state, lines[k]
                break
        used.update(range(j, i + 1))
        rows.append({"title": title, "price": price, "currency": "EUR", "availability": availability, "label": label})
    seen: dict[str, int] = {}
    for row in rows:                       # the same name twice (variants): keep both, with distinct links
        base = slug(row["title"])
        seen[base] = seen.get(base, 0) + 1
        row["key"] = base if seen[base] == 1 else f"{base}-{seen[base]}"
    return rows


def looks_like_check(lines: list[str]) -> str:
    """The phrase of a human check when the window shows one instead of the page (short pages only)."""
    head = fold(" ".join(lines[:40]))
    if len(lines) > 120:
        return ""
    for phrase in _CHECK:
        if phrase in head:
            return phrase
    return ""


def to_html(url: str, title: str, lines: list[str], rows: list[dict[str, Any]]) -> str:
    items = []
    for n, row in enumerate(rows, 1):
        offer: dict[str, Any] = {"@type": "Offer", "price": row["price"], "priceCurrency": row["currency"],
                                 "url": f"{url}#item-{row['key']}"}
        if row["availability"]:
            offer["availability"] = "https://schema.org/" + row["availability"]
        items.append({"@type": "ListItem", "position": n,
                      "item": {"@type": "Product", "name": row["title"], "url": f"{url}#item-{row['key']}", "offers": offer}})
    ld = json.dumps({"@context": "https://schema.org", "@type": "ItemList", "itemListElement": items}, ensure_ascii=False)
    ld = ld.replace("</", "<\\/")
    body = "\n".join(f"<p>{html.escape(line)}</p>" for line in lines)
    return (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title>"
            f"<meta property=\"og:type\" content=\"website\">"
            f"<script type=\"application/ld+json\">{ld}</script></head><body>{body}</body></html>")


# ====================================================================================== the window (Windows UI Automation)
class _Window:
    """One Chromium top-level window: its address bar, Reload button and page document, found by UI Automation."""

    def __init__(self, control: Any, address: str, auto: Any):
        self.control = control
        self.address = address
        self.auto = auto

    def _find(self, predicate: Callable[[Any], bool], depth: int = 16) -> Optional[Any]:
        for ctrl, _d in self.auto.WalkControl(self.control, maxDepth=depth):
            try:
                if predicate(ctrl):
                    return ctrl
            except Exception:  # noqa: BLE001 - a control can vanish while the page reloads
                continue
        return None

    def document(self) -> Optional[Any]:
        """The page itself: the document with the page title and no class name (the outer ones are the browser's views)."""
        return self._find(lambda c: c.ControlTypeName == "DocumentControl" and not c.ClassName and bool(c.Name))

    def reload(self) -> None:
        button = self._find(lambda c: c.ControlTypeName == "ButtonControl" and c.ClassName == "ReloadButton", depth=12)
        if button is None:
            raise OpenWindowError("no_reload", "la ventana no tiene botón de recargar visible (¿modo pantalla completa?)")
        button.GetInvokePattern().Invoke()

    def text(self) -> tuple[str, str]:
        doc = self.document()
        if doc is None:
            return "", ""
        pattern = doc.GetTextPattern()
        return (doc.Name or ""), (pattern.DocumentRange.GetText(-1) if pattern is not None else "")

    def scroll(self, percent: float) -> bool:
        doc = self.document()
        pattern = doc.GetScrollPattern() if doc is not None else None
        if pattern is None or not pattern.VerticallyScrollable:
            return False
        pattern.SetScrollPercent(-1, percent)          # -1: leave the horizontal position alone
        return True


def find_window(url: str) -> _Window:
    if not available():
        raise OpenWindowError("unavailable", "leer una ventana abierta necesita Windows y el paquete uiautomation")
    import uiautomation as auto

    auto.SetGlobalSearchTimeout(2)
    shown: list[str] = []
    for win in auto.GetRootControl().GetChildren():
        if win.ClassName != BROWSER_CLASS:
            continue
        edit = None
        for ctrl, _d in auto.WalkControl(win, maxDepth=10):
            if ctrl.ControlTypeName == "EditControl":
                edit = ctrl
                break
        if edit is None:
            continue                                   # an app window (Electron, WebView2), not a browser
        try:
            value = edit.GetValuePattern().Value or ""
        except Exception:  # noqa: BLE001
            continue
        shown.append(value)
        if same_page(url, value):
            return _Window(win, value, auto)
    hint = f" (abiertas: {', '.join(address_key(s) for s in shown[:6])})" if shown else ""
    raise OpenWindowError("not_open", f"no hay ninguna ventana de Brave, Chrome o Edge mostrando {address_key(url)} en su "
                                      f"pestaña activa{hint}")


def _runtime_id(control: Any) -> tuple:
    try:
        return tuple(control.GetRuntimeId()) if control is not None else ()
    except Exception:  # noqa: BLE001
        return ()


def _settled_text(win: _Window, timeout_s: float, *, sleep: Callable[[float], None],
                  clock: Callable[[], float]) -> tuple[str, str]:
    """Wait until the page text is there and stops changing."""
    deadline = clock() + timeout_s
    last, title, stable_since = None, "", clock()
    while True:
        try:
            title, text = win.text()
        except Exception:  # noqa: BLE001 - the document is replaced during the reload
            title, text = "", ""
        now = clock()
        if text and text == last:
            if now - stable_since >= SETTLE_S:
                return title, text
        else:
            last, stable_since = text, now
        if now >= deadline:
            if text:
                return title, text
            raise OpenWindowError("not_loaded", "la página no terminó de cargar en la ventana")
        sleep(0.4)


def read(url: str, *, reload: bool = True, scroll: bool = True, timeout_s: float = LOAD_TIMEOUT_S,
         sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Reload the open window showing ``url``, scroll it to the end and back, and read it.

    Returns ``{"address", "title", "text", "lines", "rows", "check"}``; raises :class:`OpenWindowError`.
    COM is set up for the calling thread (the scheduler's lane workers are not the thread that imported the package)."""
    if not available():
        raise OpenWindowError("unavailable", "leer una ventana abierta necesita Windows y el paquete uiautomation")
    import uiautomation as auto

    with auto.UIAutomationInitializerInThread():
        return _read(url, reload=reload, scroll=scroll, timeout_s=timeout_s, sleep=sleep, clock=clock)


def _read(url: str, *, reload: bool, scroll: bool, timeout_s: float, sleep: Callable[[float], None],
          clock: Callable[[], float]) -> dict[str, Any]:
    win = find_window(url)
    # A minimised Chromium window stops rendering after a while: a reload then never builds the new page. Show it again
    # without activating it (no focus, no keys) for the read and minimise it back afterwards.
    minimised = _is_minimised(win)
    if minimised:
        _show_window(win, SW_SHOWNOACTIVATE)
        sleep(1.0)
    try:
        return _read_shown(win, reload=reload, scroll=scroll, timeout_s=timeout_s, sleep=sleep, clock=clock)
    finally:
        if minimised:
            _show_window(win, SW_SHOWMINNOACTIVE)


SW_SHOWNOACTIVATE = 4
SW_SHOWMINNOACTIVE = 7


def _hwnd(win: _Window) -> int:
    try:
        return int(win.control.NativeWindowHandle or 0)
    except Exception:  # noqa: BLE001
        return 0


def _is_minimised(win: _Window) -> bool:
    hwnd = _hwnd(win)
    if not hwnd:
        return False
    import ctypes

    return bool(ctypes.windll.user32.IsIconic(hwnd))


def _show_window(win: _Window, command: int) -> None:
    hwnd = _hwnd(win)
    if hwnd:
        import ctypes

        ctypes.windll.user32.ShowWindow(hwnd, command)


def _read_shown(win: _Window, *, reload: bool, scroll: bool, timeout_s: float, sleep: Callable[[float], None],
                clock: Callable[[], float]) -> dict[str, Any]:
    if reload:
        before = _runtime_id(win.document())
        win.reload()
        deadline = clock() + timeout_s
        while clock() < deadline:                  # the old page stays in place until the new one commits
            sleep(0.5)
            now_id = _runtime_id(win.document())
            if now_id and now_id != before:
                break
    title, text = _settled_text(win, timeout_s, sleep=sleep, clock=clock)
    if scroll:
        try:
            if win.scroll(100):
                sleep(SCROLL_PAUSE_S)
                win.scroll(0)
                title, text = _settled_text(win, timeout_s / 2, sleep=sleep, clock=clock)
        except OpenWindowError:
            raise
        except Exception:  # noqa: BLE001 - a page that refuses scrolling is still read
            pass
    lines = clean_lines(text)
    return {"address": win.address, "title": title, "text": text, "lines": lines, "rows": parse_rows(lines),
            "check": looks_like_check(lines)}


def fetch(url: str, *, clock: Callable[[], float] = time.time, reader: Callable[..., dict[str, Any]] = read) -> FetchResult:
    """A :class:`FetchResult` for the engine: ``ok`` with the page as HTML, ``blocked`` (``captcha``) when the window shows a
    check, or an error (``error_kind`` = ``not_open`` / ``unavailable`` / ``not_loaded`` …) that is not the shop's fault."""
    started = time.monotonic()
    fr = FetchResult(url=url, final_url=url, tier=TIER, fetched_at=clock())
    try:
        page = reader(url)
    except OpenWindowError as error:
        fr.error, fr.error_kind = str(error), error.kind
        return fr
    except Exception as error:  # noqa: BLE001 - UI Automation errors are COM errors
        fr.error, fr.error_kind = f"no se pudo leer la ventana: {type(error).__name__}: {error}"[:300], "window_error"
        return fr
    fr.elapsed_ms = int((time.monotonic() - started) * 1000)
    address = page.get("address") or url
    fr.final_url = url if same_page(url, address) else ("https://" + address if "://" not in address else address)
    if page.get("check"):
        fr.blocked, fr.block_reason, fr.status = True, "captcha", 200
        fr.error = f"la ventana pide una verificación («{page['check']}»): resuélvela en esa ventana"
        return fr
    fr.status, fr.ok, fr.content_type = 200, True, "text/html; charset=utf-8"
    fr.text = to_html(url, page.get("title") or "", page.get("lines") or [], page.get("rows") or [])
    fr.note = f"read from the open window ({len(page.get('rows') or [])} rows)"
    return fr
