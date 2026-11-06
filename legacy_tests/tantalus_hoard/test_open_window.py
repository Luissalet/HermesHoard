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


# ------------------------------------------------------------------------------------------------ the model reads it too
class FakeModel:
    """Stands for the family model: answers the rows it is given (a function of the page text)."""

    def __init__(self, rows_for=None, up=True):
        self.rows_for = rows_for or (lambda text: [])
        self.up = up
        self.calls = 0

    def available(self):
        return (True, "") if self.up else (False, "no model link")

    def json(self, system, user, **_kw):
        self.calls += 1
        return {"rows": self.rows_for(user)}


def model_reading(**status):
    """The model's answer for the three Pokémon rows: ``status`` by short name (mew, mewtwo, ultra), evidence as on the page."""
    words = {"out_of_stock": OUT, "in_stock": "Añadir", "coming_soon": "Próximamente"}

    def rows(_text):
        out = []
        for short, title, price in (("mew", MEW, 49.99), ("mewtwo", MEWTWO, 49.99), ("ultra", ULTRA, 249.99)):
            st = status.get(short, "out_of_stock")
            out.append({"title": title, "price": price, "status": st, "evidence": status.get(short + "_evidence", words.get(st, ""))})
        return out
    return rows


def test_model_agreeing_adds_a_second_reading_to_the_alert(svc):
    w, t = make(svc, [page_text(), page_text(mew="Añadir")])
    svc.engine.llm = FakeModel(model_reading(mew="in_stock"))
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 300)
    res = svc.engine.check_target(t["id"])
    [event] = [svc.store.event(e) for e in res["events"]]
    assert event["type"] == "RESTOCK" and event["title"] == MEW and event["confidence"] >= 95
    assert "el modelo lo lee igual" in " ".join(event["data"]["evidence"])
    check = svc.store.target(t["id"])["extra"]["model_check"]
    assert check["ok"] and check["agree"] == 3 and check["disagree"] == 0


def test_a_button_only_the_model_understands_alerts_after_a_second_reading(svc):
    w, t = make(svc, [page_text(), page_text(mew="Lo quiero"), page_text(mew="Lo quiero")])
    svc.engine.llm = FakeModel(model_reading(mew="in_stock", mew_evidence="Lo quiero"))
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 300)
    first = svc.engine.check_target(t["id"])
    assert first["events"] == []                                          # the model alone: no alert yet
    assert svc.store.target(t["id"])["next_check_ts"] == T0 + 300 + 60    # but the window is read again in a minute
    swap_clock(svc, T0 + 360)
    second = svc.engine.check_target(t["id"])
    [event] = [svc.store.event(e) for e in second["events"]]
    assert event["type"] == "RESTOCK" and event["title"] == MEW and event["status"] == "confirmed"
    assert any(f["key"] == "model_twice" for f in event["data"]["factors"])


def test_model_words_that_are_not_on_the_page_are_ignored(svc):
    w, t = make(svc, [page_text(), page_text(mew="Lo quiero")])
    svc.engine.llm = FakeModel(model_reading(mew="in_stock", mew_evidence="Comprar ahora con envío urgente"))
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 300)
    res = svc.engine.check_target(t["id"])
    assert res["events"] == [] and svc.store.target(t["id"])["next_check_ts"] > T0 + 300 + 120


def test_disagreement_keeps_the_literal_button_and_notes_it(svc):
    w, t = make(svc, [page_text(), page_text(mew="Añadir")])
    svc.engine.llm = FakeModel(model_reading(mew="out_of_stock"))
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 300)
    [event] = [svc.store.event(e) for e in svc.engine.check_target(t["id"])["events"]]
    assert event["type"] == "RESTOCK" and event["title"] == MEW
    assert "el modelo lo lee como out_of_stock" in " ".join(event["data"]["evidence"])
    assert svc.store.target(t["id"])["extra"]["model_check"]["disagree"] == 1


def test_without_a_model_the_rules_still_watch(svc):
    w, t = make(svc, [page_text(), page_text(mew="Añadir")])
    svc.engine.llm = FakeModel(up=False)
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 300)
    [event] = [svc.store.event(e) for e in svc.engine.check_target(t["id"])["events"]]
    assert event["type"] == "RESTOCK" and event["title"] == MEW
    check = svc.store.target(t["id"])["extra"]["model_check"]
    assert not check["ok"] and "no disponible" in check["reason"]
