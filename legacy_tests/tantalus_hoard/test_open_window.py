"""Fetch tier ``open_window``: a list read from a browser window the person already has open, each row followed on its own."""

from __future__ import annotations

from conftest import T0, tool

from tantalus_hoard.extract import extract
from tantalus_hoard.fetch import open_window as ow
from tantalus_hoard.model import FetchResult

URL = "https://www.carrefour.es/mis-listas-y-productos/mis-listas/104450805"

# What UI Automation reads from the real page (11-2026), icon glyphs and object marks included.
HEAD = "skip to content\n￼\n\nMenú\nFolletos\n￼\n줞\n\nAyuda y contacto\n\nMis favoritos\n￼\nMi cuenta\n\nCesta\n" \
       "Carrefour.es \n줠 Mis listas y productos \n줠 Mis listas \n줠Favoritos\nLista “Favoritos”\n" \
       "Puedes añadir los productos que quieras a tu cesta.\n"
ROW = "￼\n{title}\nMáximo 1 unidad por pedido\n Envío Gratis*\n{price}\n\n{button}\n"
FOOT = "￼\nEstantería 75x50x24,5 cm MUEBLES PITARCH Eko - Roble\n26,90 €\n\nAñadir \n\n줛\nEntrega y recogida de pedidos\n" \
       "Garantía de frescura\nTarjeta ClubPASS\nContacto\nPreguntas frecuentes\n"
MEW = "Pokémon Caja 30Th Aniversario, Caja Colección con Figura Mew, +6 Años"
MEWTWO = "Pokémon Caja 30Th Aniversario, Caja Colección con Figura Mewtwo, +6 Años"
ULTRA = "Pokémon Caja Ultra Premium 30Th Aniversario, +6 Años (Unboxing)"
OUT = "Agotado temporalmente"


def page_text(mew: str = OUT, mewtwo: str = OUT, ultra: str = OUT) -> str:
    return (HEAD + ROW.format(title=MEW, price="49,99 €", button=mew) + ROW.format(title=MEWTWO, price="49,99 €", button=mewtwo)
            + ROW.format(title=ULTRA, price="249,99 €", button=ultra) + FOOT)


def reader_for(text: str, address: str = "carrefour.es/mis-listas-y-productos/mis-listas/104450805"):
    def reader(url):
        lines = ow.clean_lines(text)
        return {"address": address, "title": "Carrefour Supermercado compra online", "text": text, "lines": lines,
                "rows": ow.parse_rows(lines), "check": ow.looks_like_check(lines)}
    return reader


class WindowFetcher:
    """The engine's fetcher with scripted window reads (one per check, the last one repeats)."""

    def __init__(self, reads):
        self.reads = list(reads)
        self.tiers: list[str] = []

    def get(self, url, *, tier="auto", **_kw):
        self.tiers.append(tier)
        nxt = self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]
        if isinstance(nxt, FetchResult):
            return nxt
        return ow.fetch(url, clock=lambda: T0, reader=reader_for(nxt))

    def get_json(self, url, **kw):
        return self.get(url, **kw), None

    def clear_block(self, host):
        pass

    def host_status(self):
        return []

    def close(self):
        pass


def swap_clock(svc, value):
    svc.clock = svc.store.clock = svc.engine.clock = lambda: value


def make(svc, reads):
    svc.engine.fetcher = WindowFetcher(reads)
    w = tool(svc, "watcher_create", name="Carrefour favoritos", mode="availability",
             config={"product": {"terms": ["pokemon"], "must": ["pokemon"]},
                     "policies": {"seller": "retail_only", "revalidate_seconds": 0, "cooldown_minutes": 20,
                                  "alert_on": ["RESTOCK", "SALE_OPEN", "PREORDER_OPEN"]}})
    t = svc.store.create_target(w["id"], URL, label="Carrefour · Favoritos", retailer="Carrefour", fetch_tier="open_window",
                                interval_min=5)
    return w, t


# ------------------------------------------------------------------------------------------------ reading the text
def test_rows_of_the_real_favourites_page():
    rows = ow.parse_rows(ow.clean_lines(page_text(mewtwo="Añadir ", ultra="Próximamente")))
    assert [r["title"] for r in rows] == [MEW, MEWTWO, ULTRA, "Estantería 75x50x24,5 cm MUEBLES PITARCH Eko - Roble"]
    assert [r["price"] for r in rows] == [49.99, 49.99, 249.99, 26.9]
    assert [r["availability"] for r in rows] == ["OutOfStock", "InStock", "ComingSoon", "InStock"]
    assert len({r["key"] for r in rows}) == 4


def test_page_becomes_a_listing_with_one_link_per_row():
    fr = ow.fetch(URL, reader=reader_for(page_text(mew="Añadir")))
    assert fr.ok and fr.tier == "open_window" and not fr.blocked
    ex = extract(fr, hints={"url": URL})
    assert ex.page_kind == "listing" and len(ex.offers) == 4
    mew = next(o for o in ex.offers if o.title == MEW)
    assert mew.availability == "IN_STOCK" and mew.price == 49.99 and mew.url.startswith(URL + "#item-")
    assert next(o for o in ex.offers if o.title == ULTRA).availability == "OUT_OF_STOCK"


def test_coming_soon_row_maps_to_coming_soon():
    ex = extract(ow.fetch(URL, reader=reader_for(page_text(ultra="Próximamente"))), hints={"url": URL})
    assert next(o for o in ex.offers if o.title == ULTRA).availability == "COMING_SOON"


def test_a_check_in_the_window_is_a_block_not_a_page():
    text = "Un momento…\nVerifica que eres un humano completando la acción a continuación.\ncarrefour.es necesita revisar la seguridad"
    fr = ow.fetch(URL, reader=reader_for(text))
    assert not fr.ok and fr.blocked and fr.block_reason == "captcha"


def test_window_not_open_is_an_error_of_its_own():
    def reader(url):
        raise ow.OpenWindowError("not_open", "no hay ninguna ventana")
    fr = ow.fetch(URL, reader=reader)
    assert not fr.ok and not fr.blocked and fr.error_kind == "not_open"


def test_address_matching_ignores_scheme_www_and_slash():
    assert ow.same_page(URL, "carrefour.es/mis-listas-y-productos/mis-listas/104450805/")
    assert ow.same_page(URL, "https://carrefour.es/mis-listas-y-productos/mis-listas/104450805?x=1")
    assert not ow.same_page(URL, "carrefour.es/mis-listas-y-productos/mis-listas/999")


# ------------------------------------------------------------------------------------------------ the engine
def test_each_row_alerts_on_its_own_and_ends_on_its_own(svc):
    w, t = make(svc, [page_text(), page_text(mew="Añadir"), page_text(mew="Añadir", mewtwo="Añadir"), page_text(mewtwo="Añadir")])
    first = svc.engine.check_target(t["id"])
    assert first["ok"] and first["events"] == [] and svc.engine.fetcher.tiers == ["open_window"]

    swap_clock(svc, T0 + 300)
    second = svc.engine.check_target(t["id"])
    [restock] = [svc.store.event(e) for e in second["events"]]
    assert restock["type"] == "RESTOCK" and restock["status"] == "confirmed" and restock["title"] == MEW
    assert restock["url"].startswith(URL + "#item-") and restock["price"] == 49.99
    assert svc.notifier.sent[-1][0]["title"] == MEW

    swap_clock(svc, T0 + 600)
    third = svc.engine.check_target(t["id"])           # Mew still there, Mewtwo arrives: one alert, for Mewtwo
    [second_restock] = [svc.store.event(e) for e in third["events"]]
    assert second_restock["type"] == "RESTOCK" and second_restock["title"] == MEWTWO

    swap_clock(svc, T0 + 900)
    svc.engine.check_target(t["id"])                    # Mew sold out: its alert ends with a follow-up, Mewtwo's stays
    sold = [e for e in tool(svc, "events_list", limit=50)["events"] if e["type"] == "SOLD_OUT"]
    assert sold and all(MEW == e["title"] for e in sold)
    live_urls = {e["url"] for e in svc.store.live_alerts(target_id=t["id"])}
    assert live_urls == {second_restock["url"]}


def test_closed_window_tells_once_and_keeps_the_interval(svc):
    missing = FetchResult(url=URL, final_url=URL, tier="open_window", error="no hay ninguna ventana", error_kind="not_open")
    w, t = make(svc, [missing])
    res = svc.engine.check_target(t["id"])
    assert not res["ok"] and not res["blocked"]
    [event] = [svc.store.event(e) for e in res["events"]]
    assert event["type"] == "NEEDS_HUMAN" and event["severity"] == "high" and event["status"] == "confirmed"
    target = svc.store.target(t["id"])
    assert target["status"] == "error" and target["next_check_ts"] - T0 <= 5 * 60 * 1.11
    swap_clock(svc, T0 + 300)
    assert svc.engine.check_target(t["id"])["events"] == []       # told already: not again for a while


def test_check_in_the_window_asks_the_person(svc):
    check = FetchResult(url=URL, final_url=URL, tier="open_window", blocked=True, block_reason="captcha", status=200,
                        error="la ventana pide una verificación")
    w, t = make(svc, [check])
    res = svc.engine.check_target(t["id"])
    assert res["blocked"]
    [event] = [svc.store.event(e) for e in res["events"]]
    assert "verificación" in event["summary"] and event["severity"] == "high"
    assert svc.store.target(t["id"])["status"] == "needs_human"
