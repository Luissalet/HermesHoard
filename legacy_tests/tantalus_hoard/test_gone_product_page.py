"""A sold-out product whose shop answers "410 Gone" and still serves the page: it is a reading, not a failure."""

from __future__ import annotations

import json

from conftest import T0, tool

from tantalus_hoard.extract import extract
from tantalus_hoard.model import FetchResult

URL = "https://www.elcorteingles.es/juguetes/A1234-caja-de-entrenador-elite-de-celebracion/"
TITLE = "Caja de Entrenador Élite de Celebración de JCC Pokémon"


def product_page(control: str, price=None, soon: bool = False) -> str:
    state = {"_internals": {"req": {"moonshine": {"route": {"name": "product_detail"}}}}, "id": "A1234", "title": TITLE,
             "brand": {"name": "Pokémon"}, "badges": {"coming_soon": soon}, "_single_sku": {"gtin": "0196214144866", "provider": "eci"},
             "price": {"currency": "EUR", "f_price": price},
             "_my_colors": [{"title": "default", "variants": [{"add_to_cart": control, "status": control, "gtin": "0196214144866",
                                                               "flags": {"coming_soon": soon}}]}]}
    label = "Añadir a la cesta" if control == "ADD" else "AGOTADO"
    off = "" if control == "ADD" else ' aria-disabled="true"'
    # The page around it talks about buying other things, as the real one does.
    return (f"<html><head><title>{TITLE} · El Corte Inglés</title></head><body><h1>{TITLE}</h1>"
            f'<button id="add_to_cart_main_button"{off}>{label}</button>'
            "<p>En tienda: consulta la disponibilidad de este producto. Disponible para envío a domicilio en otros artículos.</p>"
            f"<script>window.__MOONSHINE_STATE__ = {json.dumps(state)};</script></body></html>")


def gone(body: str) -> FetchResult:
    return FetchResult(url=URL, final_url=URL, status=410, text=body, ok=False, error="HTTP 410", error_kind="http",
                       content_type="text/html", tier="http")


class Shop:
    """Answers the scripted (status, body) pairs for the one URL; the last repeats."""

    def __init__(self, answers):
        self.answers = list(answers)

    def get(self, url, **_kw):
        status, body = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if status == 410:
            return gone(body)
        return FetchResult(url=url, final_url=url, status=200, text=body, ok=True, content_type="text/html", tier="http")

    def get_json(self, url, **kw):
        return self.get(url, **kw), None

    def clear_block(self, host):
        pass

    def host_status(self):
        return []

    def close(self):
        pass


def test_the_embedded_state_of_a_product_page_says_sold_out_or_buyable():
    sold = extract(gone(product_page("NOT_AVAILABLE")), hints={"url": URL})
    assert sold.page_kind == "product" and "site:state" in sold.methods
    [offer] = sold.offers
    assert offer.availability == "OUT_OF_STOCK" and offer.sku == "A1234" and offer.ean == "0196214144866"
    assert offer.seller == "El Corte Inglés" and offer.title == TITLE and offer.price is None
    live = extract(FetchResult(url=URL, final_url=URL, status=200, text=product_page("ADD", 69.99), ok=True, content_type="text/html",
                               tier="http"), hints={"url": URL})
    assert live.offers[0].availability == "IN_STOCK" and live.offers[0].price == 69.99
    soon = extract(gone(product_page("NOT_AVAILABLE", soon=True)), hints={"url": URL})
    assert soon.offers[0].availability == "COMING_SOON"


def test_a_sold_out_page_answered_as_gone_is_read_and_its_return_is_seen(svc):
    svc.engine.fetcher = Shop([(410, product_page("NOT_AVAILABLE")), (410, product_page("NOT_AVAILABLE")), (200, product_page("ADD", 69.99))])
    w = tool(svc, "watcher_create", name="Pokémon", mode="availability",
             config={"product": {"terms": ["pokemon"]}, "policies": {"seller": "retail_only", "revalidate_seconds": 0}})
    t = svc.store.create_target(w["id"], URL, label=TITLE, retailer="El Corte Inglés")
    first = svc.engine.check_target(t["id"])
    assert first["ok"] and first["state"] == "OUT_OF_STOCK" and first["events"] == []
    row = svc.store.target(t["id"])
    assert row["status"] == "active" and not row["fail_count"] and not row["last_error"]
    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 600
    assert svc.engine.check_target(t["id"])["state"] == "OUT_OF_STOCK"
    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 1200
    back = svc.engine.check_target(t["id"])
    assert back["state"] == "IN_STOCK" and back["price"] == 69.99
    assert [svc.store.event(e)["type"] for e in back["events"]] == ["RESTOCK"]


def test_a_gone_page_never_vouches_for_stock(svc):
    svc.engine.fetcher = Shop([(410, product_page("ADD", 69.99))])
    w = tool(svc, "watcher_create", name="Pokémon", mode="availability", config={"product": {"terms": ["pokemon"]}})
    t = svc.store.create_target(w["id"], URL, label=TITLE, retailer="El Corte Inglés")
    r = svc.engine.check_target(t["id"])
    assert not r["ok"] and r["events"] == [] and svc.store.target(t["id"])["status"] == "error"
