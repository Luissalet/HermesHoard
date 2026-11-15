"""A watcher of every product of a game at the chains: a chain alerts only near the shelf price, loose boosters only log,
and an offer another watcher already alerted is not alerted twice."""

from __future__ import annotations

from test_radar import events, radar_svc, read  # noqa: F401 - radar_svc is the fixture
from tantalus_hoard.radar import stocktcg as st
from tantalus_hoard.radar.core import shelf_price

EVERYTHING = {"product": {"terms": ["pokemon"], "must": ["pokemon"], "exclude": ["funda"]},
              "policies": {"seller": "retail_only", "scalper_multiplier": 1.3},
              "radar": {"enabled": True, "chains": ["game", "carrefour"], "languages": ["ES", "EN"], "chains_at_shelf_price": True,
                        "min_price": 9, "track_chain_products": False}}


def carrefour_row(key: str, title: str, fmt: str, price: str, slug: str) -> str:
    return (f'<tr><td><div class="st-prod"><span><a href="/p/{key}">{title}</a><span class="st-lang">ES</span></span></div></td>'
            f'<td class="st-fmt"><span class="badge">30th Celebration / Celebración 30 Aniversario · {fmt}</span></td>'
            f'<td><span class="price">{price} €</span></td><td class="st-act"><a class="st-go" '
            f'href="https://www.carrefour.es/{slug}/R-1/p" data-store="carrefour">Comprar</a></td></tr>')


def restock_carrefour(svc, *rows: str) -> None:
    page = read("net_store_carrefour.html").replace("<tbody>", "<tbody>" + "".join(rows), 1)
    svc.radar.fetcher.pages[f"{st.NET}/tiendas/carrefour"] = page
    svc.db.execute("UPDATE radar_pages SET last_fetch_ts = 0")
    svc.clock_box["now"] += 600
    svc.radar.run()


def by_slug(svc, part: str) -> list[dict]:
    return [e for e in events(svc, "RESTOCK") if part in e["url"]]


def test_shelf_prices_by_format():
    assert shelf_price("ETB") == shelf_price("Elite Trainer Box") == 69.99
    assert shelf_price("Blíster") == 19.99 and shelf_price("Collection Box") is None and shelf_price("") is None


def test_chain_alerts_at_shelf_price_and_logs_resale_and_loose_boosters(radar_svc):
    svc = radar_svc
    svc.store.update_watcher(svc.watcher["id"], config=EVERYTHING)
    svc.radar.run()
    restock_carrefour(
        svc,
        carrefour_row("30th-anniversary--mini-tin", "Pokémon 30Th Aniversario Mini Latas", "Mini Tin", "16,99", "mini-latas-shelf"),
        carrefour_row("30th-anniversary--etb", "Pokémon 30Th Aniversario Caja Entrenador Élite (vendedor externo)", "ETB", "189,00", "etb-resale"),
        carrefour_row("30th-anniversary--sobre", "Pokémon 30Th Aniversario Sobre", "Sobre", "5,99", "sobre-suelto"))
    tin, etb, booster = by_slug(svc, "mini-latas-shelf"), by_slug(svc, "etb-resale"), by_slug(svc, "sobre-suelto")
    assert len(tin) == 1 and tin[0]["status"] == "confirmed"
    assert len(etb) == 1 and etb[0]["status"] == "logged" and "precio de reventa en la cadena" in etb[0]["summary"]
    assert len(booster) == 1 and booster[0]["status"] == "logged" and "por debajo de" in booster[0]["summary"]


def test_without_the_option_a_chain_alerts_at_any_price(radar_svc):
    svc = radar_svc
    svc.radar.run()
    restock_carrefour(svc, carrefour_row("30th-anniversary--etb", "Pokémon 30Th Aniversario Caja Entrenador Élite", "ETB", "189,00", "etb-resale"))
    etb = by_slug(svc, "etb-resale")
    assert len(etb) == 1 and etb[0]["status"] == "confirmed"


def test_two_watchers_seeing_the_same_offer_alert_once(radar_svc):
    svc = radar_svc
    second = svc.store.create_watcher(name="Pokémon JCC en cadenas", mode="availability", interval_min=20, config=EVERYTHING)
    svc.radar.run()
    restock_carrefour(svc, carrefour_row("30th-anniversary--mini-tin", "Pokémon 30Th Aniversario Mini Latas", "Mini Tin", "16,99", "mini-latas-shelf"))
    rows = by_slug(svc, "mini-latas-shelf")
    assert len(rows) == 2
    assert sorted(e["status"] for e in rows) == ["confirmed", "logged"]
    logged = next(e for e in rows if e["status"] == "logged")
    assert "ya avisado por «" in logged["summary"] and {e["watcher_id"] for e in rows} == {svc.watcher["id"], second["id"]}
