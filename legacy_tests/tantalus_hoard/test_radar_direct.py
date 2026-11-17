"""The chains' own listings read directly: El Corte Inglés's brand page and Amazon's search sold by Amazon. A product that
appears is a restock at the shop's own price, one that drops out of a complete listing is sold out, an invitation sale is a
reservation, and the first read is quiet."""

from __future__ import annotations

import json

from test_radar import events, radar_svc  # noqa: F401 - radar_svc is the fixture
from tantalus_hoard.model import IN_STOCK, OUT_OF_STOCK, PREORDER
from tantalus_hoard.radar import direct as dr

ECI = dr.DEFAULT_PAGES[0]
AMZ = dr.DEFAULT_PAGES[1]


def eci_page(*items: tuple[str, str, float, str]) -> str:
    """items: (code, name, price, status)."""
    state = {"_datalayer": [{"products": [{"code_a": c, "name": n, "price": {"f_price": p, "currency": "EUR"}, "status": s,
                                           "eci_provider": "El Corte Inglés", "badges": {"coming_soon": False}} for c, n, p, s in items]}],
             "products": [{"id": c, "_uri": f"/juguetes/{c}-{n.lower().replace(' ', '-')}/", "title": n} for c, n, _p, _s in items]}
    return f"<html><body><script>window.__MOONSHINE_STATE__ = {json.dumps(state)};</script></body></html>"


def amz_card(asin: str, title: str, price: str = "", note: str = "", sponsored: bool = False) -> str:
    return (f'<div data-component-type="s-search-result" data-asin="{asin}">'
            + ('<span class="puis-sponsored-label-text">Patrocinado</span>' if sponsored else "")
            + f'<h2><span>{title}</span></h2>'
            + (f'<span class="a-price"><span class="a-offscreen">{price}</span></span>' if price else "")
            + f"<span>{note}</span></div>")


def test_formats_and_languages_from_shop_titles():
    assert dr.guess_fmt("Pokémon: Minilata Celebración 30.º Aniversario: Mew") == "mini tin"
    assert dr.guess_fmt("Pokemon Mini Latas Escarlata y Purpura Destinos de Paldea") == "mini tin"
    assert dr.guess_fmt("Caja de Entrenador Élite Dominio Delta de JCC Pokémon") == "etb"
    assert dr.guess_fmt("Pokémon: Lote de Sobres de Mejora de Celebración 30.º Aniversario (6 Sobres)") == "booster bundle"
    assert dr.guess_fmt("Pokémon: Blíster de 3 Sobres de Mejora") == "blister"
    assert dr.guess_fmt("Lata Pokémon Jcc Bandai Modelos Surtidos") == "tin"
    assert dr.guess_fmt("Sobre Dominio Delta de JCC Pokémon") == "sobre"
    assert dr.guess_fmt("Pokémon: Colección Houndstone ex") == "" and dr.guess_fmt("Expositor de sobres") == ""
    assert dr.guess_lang("Delta Reign TCG Booster Pack English Pokémon") == "EN" and dr.guess_lang("Sobre de JCC") == ""
    assert dr.page_urls(ECI)[1] == "https://www.elcorteingles.es/marcas/pokemon/juguetes/2/"
    assert dr.page_urls(AMZ)[1].endswith("&page=2")


def test_parsers():
    eci = dr.parse(ECI, eci_page(("A1", "Caja de Entrenador Élite Dominio Delta", 69.99, "ADD")), ECI["url"])
    o = eci.offers[0]
    assert o.url == "https://www.elcorteingles.es/juguetes/A1-caja-de-entrenador-élite-dominio-delta/" and o.state == IN_STOCK
    assert o.price == 69.99 and o.fmt == "etb" and o.store_slug == "el-corte-ingles" and o.source == "elcorteingles.es"
    assert o.extra["first_hand"] and not eci.full
    html = "<html>" + "".join([
        amz_card("B0H29TRBMW", "Pokémon: Lata Megaluz Lunar: Mega-Gengar ex", "24,99 €", "Disponible por invitación Ver opciones"),
        amz_card("B0FTBD97SZ", "Pokémon: Colección Houndstone ex", "25,00 €", "Añadir a la cesta"),
        amz_card("B0AAAAAAAA", "Pokémon: Caja patrocinada", "99,00 €", "Añadir a la cesta", sponsored=True),
        amz_card("B0BBBBBBBB", "Pokémon: Algo agotado", "", "Actualmente no disponible")]) + "</html>"
    amz = dr.parse(AMZ, html, AMZ["url"])
    by = {x.extra["sku"]: x for x in amz.offers}
    assert set(by) == {"B0H29TRBMW", "B0FTBD97SZ", "B0BBBBBBBB"}
    assert by["B0H29TRBMW"].state == PREORDER and by["B0H29TRBMW"].extra["invite"] and by["B0H29TRBMW"].kind == "invite"
    assert by["B0FTBD97SZ"].state == IN_STOCK and by["B0FTBD97SZ"].price == 25.0
    assert by["B0FTBD97SZ"].url == "https://www.amazon.es/dp/B0FTBD97SZ"
    assert by["B0BBBBBBBB"].state == OUT_OF_STOCK
    assert dr.parse(ECI, "<html>nothing</html>", ECI["url"]).offers == []


def setup(svc, eci_html: str, amz_html: str) -> None:
    cfg = dict(svc.watcher["config"])
    cfg["radar"] = {**cfg["radar"], "sources": ["direct"]}
    svc.store.update_watcher(svc.watcher["id"], config=cfg)
    svc.radar.fetcher.pages[ECI["url"]] = eci_html
    svc.radar.fetcher.pages[AMZ["url"]] = amz_html


def again(svc, eci_html: str = None, amz_html: str = None, step: float = 900) -> None:
    if eci_html is not None:
        svc.radar.fetcher.pages[ECI["url"]] = eci_html
    if amz_html is not None:
        svc.radar.fetcher.pages[AMZ["url"]] = amz_html
    svc.db.execute("UPDATE radar_pages SET last_fetch_ts = 0")
    svc.clock_box["now"] += step
    svc.radar.run()


def test_direct_listing_restock_sold_out_and_invitation(radar_svc):
    svc = radar_svc
    etb = ("A1", "Pokémon 30 Aniversario Caja de Entrenador Élite", 69.99, "ADD")
    tin = ("A2", "Pokémon 30 Aniversario Mini Lata Mew", 16.99, "ADD")
    setup(svc, eci_page(etb), "<html>" + amz_card("B0H8SZMC6L", "Pokémon: Minilata Celebración 30.º Aniversario: Mew", "13,99 €",
                                                    "Añadir a la cesta") + "</html>")
    svc.radar.run()
    assert events(svc, "RESTOCK") == []                       # the first read is the baseline
    again(svc, eci_page(etb, tin))                            # the mini tin is put up at the chain
    restock = [e for e in events(svc, "RESTOCK") if "Mini Lata" in e["title"]]
    assert len(restock) == 1 and restock[0]["status"] == "confirmed" and restock[0]["confidence"] == 95
    assert "según su propia web" in restock[0]["summary"] and restock[0]["url"].startswith("https://www.elcorteingles.es/juguetes/A2")
    again(svc, eci_page(etb))                                 # gone from the complete listing: sold out
    row = svc.db.one("SELECT state FROM radar_offers WHERE url LIKE '%A2-%'")
    assert row["state"] == OUT_OF_STOCK
    again(svc, eci_page(etb, tin), step=2 * 3600)             # back again later: a new restock alert
    assert len([e for e in events(svc, "RESTOCK") if "Mini Lata" in e["title"] and e["status"] == "confirmed"]) == 2
    # Amazon opens an invitation sale for a product it did not sell before
    again(svc, amz_html="<html>" + amz_card("B0H8SZMC6L", "Pokémon: Minilata Celebración 30.º Aniversario: Mew", "13,99 €",
                                             "Añadir a la cesta")
          + amz_card("B0UPCUPCUP", "Pokémon: Colección Ultra Premium Celebración 30.º Aniversario", "149,99 €",
                     "Disponible por invitación") + "</html>")
    invite = [e for e in events(svc, "PREORDER_OPEN") if "Ultra Premium" in e["title"]]
    assert len(invite) == 1 and invite[0]["status"] == "confirmed" and "venta por invitación" in invite[0]["summary"]


def test_every_watcher_gets_the_listing_and_a_new_watcher_starts_quiet(radar_svc):
    svc = radar_svc
    etb = ("A1", "Pokémon 30 Aniversario Caja de Entrenador Élite", 69.99, "ADD")
    tin = ("A2", "Pokémon 30 Aniversario Mini Lata Mew", 16.99, "ADD")
    setup(svc, eci_page(etb), "<html></html>")
    svc.radar.run()
    again(svc, eci_page(etb))
    # a second watcher arrives later: the page is old for the radar, new for it
    other = svc.store.create_watcher(name="Otro", mode="availability", interval_min=20, config={
        "product": {"terms": ["pokemon"], "must": ["pokemon"]}, "radar_baseline_done": True,
        "radar": {"enabled": True, "chains": ["el-corte-ingles"], "sources": ["direct"]}})
    again(svc, eci_page(etb))
    rows = svc.db.query("SELECT watcher_id FROM radar_offers WHERE url LIKE '%A1-%'")
    assert {r["watcher_id"] for r in rows} == {svc.watcher["id"], other["id"]}       # both read it in one cycle
    assert [e for e in events(svc, "RESTOCK") if e["watcher_id"] == other["id"]] == []   # what was there is no news
    again(svc, eci_page(etb, tin))
    mine = [e for e in events(svc, "RESTOCK") if "Mini Lata" in e["title"]]
    assert {e["watcher_id"] for e in mine} == {svc.watcher["id"], other["id"]}
    assert sum(1 for e in mine if e["status"] == "confirmed") == 1                     # one alert for the two watchers
