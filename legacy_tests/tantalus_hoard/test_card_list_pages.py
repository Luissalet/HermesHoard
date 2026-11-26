"""A list page whose cards state each product's stock: one reading follows every product of the page."""

from __future__ import annotations

from bs4 import BeautifulSoup
from conftest import T0, tool

from tantalus_hoard import rules
from tantalus_hoard.engine import offer_matches
from tantalus_hoard.extract import extract, mabisy
from tantalus_hoard.extract.sites import kind_of_url, listing_context, profile_for_host
from tantalus_hoard.model import FetchResult, Offer

SHOP = "https://www.artmantoys.es"
DELTA = SHOP + "/dominio-delta_c1003728/"
PARTY = SHOP + "/celebracion-30-aniversario_c1003548/"
MAKER = "The Pokémon Company International"

ETB = (11623179, "caja-entrenador-elite-dominio-delta", "Caja entrenador élite Dominio Delta", "66,50")
BLISTER = (11623193, "blister-tres-sobres-dominio-delta", "Blister tres sobres Dominio Delta", "21,50")
BOX = (11623180, "caja-de-sobres-dominio-delta", "Caja de sobres Dominio Delta", "189,95")
PARTY_ETB = (11700001, "caja-entrenador-elite-celebracion", "Caja entrenador élite Celebración 30 aniversario", "59,95")
PARTY_TIN = (11700002, "lata-celebracion", "Lata Celebración 30 aniversario", "29,95")


def card(pid: int, slug: str, title: str, price: str, stock: bool, *, maker: str = MAKER, was: str = "", preorder: bool = False,
         launch: str = "") -> str:
    label = ('<span class="label label-existstock">En stock</span>' if stock
             else '<span class="label label-nostock">Sin stock</span>')
    old = f'<span class="price-old">{was}€</span> ' if was else ""
    attrs = ('<span class="attribute res"><strong class="name">Reserva</strong><span class="value"></span></span>'
             '<span class="attribute prev"><strong class="name">Producto en preventa</strong><span class="value">'
             f'<span class="item">{"Fecha de lanzamiento " + launch if launch else ""}</span></span></span>') if preorder else ""
    return (f'<div id="mb-product-{pid}" class="mb-product " data-id="{pid}"><div class="image-box-container">'
            f'<a title="{title}" href="/{slug}_p{pid}.htm" class="image-box"><img class="image lazy" data-src="/img/{pid}.jpg" '
            f'alt="{title}"/></a></div><p class="title"><a title="{title}" href="/{slug}_p{pid}.htm" class="name">{title}</a></p>'
            f'<a data-title="Marca" class="manufacturer" href="/maker_m1/">{maker}</a>{label}'
            f'<p class="prices">{old}<span class="price">{price}€</span></p><div class="description">caja en español</div>'
            '<span class="labels"><span class="attribute pais esp"><strong class="name">Idioma</strong><span class="value">'
            f'<span class="item esp">España</span></span></span>{attrs}</span><div class="buttons">'
            '<button class="btn-carrito" title="Añadir al carrito"><span class="text">Añadir</span></button></div></div>')


def page(title: str, *cards: str, generator: str = "Mabisy", strip: str = "") -> str:
    body = (f'<div class="mb-product-list grid-2">{"".join(cards)}</div>' if cards else
            '<div class="noproduct"><div class="mb-mensaje info">No se han encontrado productos en esta categoría</div></div>')
    return (f'<html><head><title>{title}</title><meta name="generator" content="{generator}"/></head><body>'
            f'<nav><a href="/pokemon_c1/">Pokémon</a> <a href="/lorcana_c2/">Lorcana</a></nav><h1>{title}</h1>'
            f'<div class="module"><div class="buttons top"><span class="counter-stats" data-n="{len(cards)}">'
            f'<span class="text showing">Mostrados</span> <span class="pageitems">{len(cards)}</span> productos</span></div>'
            f'{body}</div>{strip}<footer><p>Tienda de cartas coleccionables. Envíos a península y Baleares en 24 o 48 horas, '
            'con seguimiento del paquete y recogida en punto de entrega.</p></footer></body></html>')


def read(url: str, body: str, **hints):
    return extract(FetchResult(url=url, final_url=url, status=200, text=body, ok=True, content_type="text/html; charset=utf-8",
                               tier="http"), hints={"url": url, **hints})


class Shop:
    """Answers the scripted pages in turn; the last repeats. Remembers what it was asked for."""

    def __init__(self, pages):
        self.pages, self.asked = list(pages), []

    def get(self, url, **kw):
        self.asked.append((url, kw))
        body = self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        return FetchResult(url=url, final_url=url, status=200, text=body, ok=True, content_type="text/html; charset=utf-8", tier="http")

    def get_json(self, url, **kw):
        raise AssertionError(f"a list page was asked for as an API: {url}")

    def clear_block(self, host):
        pass

    def host_status(self):
        return []

    def close(self):
        pass


def test_each_card_gives_its_product_its_stock_its_price_and_its_maker():
    body = page("Dominio Delta", card(*ETB, False, preorder=True),
                card(*BLISTER, True, preorder=True, launch="06/11/2026"),
                card(*BOX, True, preorder=True, launch="04/12/2026"),
                card(10776372, "tapete-death-star", "Tapete Death Star", "14,00", True, maker="Gamegenic", was="19,95"),
                '<div class="mb-product" data-id="1"><span class="price">1,00€</span></div>')
    ex = read(DELTA, body, today="2026-11-26")
    assert ex.page_kind == "listing" and ex.methods == [mabisy.METHOD] and len(ex.offers) == 4 and ex.quality_ok
    etb, blister, box, mat = ex.offers
    assert (etb.availability, etb.buy_button, etb.price, etb.currency) == ("OUT_OF_STOCK", False, 66.5, "EUR")
    assert etb.url == SHOP + "/caja-entrenador-elite-dominio-delta_p11623179.htm" and etb.title == ETB[2]
    assert etb.brand == MAKER and etb.sku == "11623179" and etb.seller_is_retailer is True and etb.image == SHOP + "/img/11623179.jpg"
    assert blister.availability == "IN_STOCK" and blister.preorder_date is None        # its launch day has gone by: on sale
    assert (box.availability, box.preorder_date) == ("PREORDER", "2026-12-04")
    assert (mat.availability, mat.price, mat.extra["list_price"], mat.brand) == ("IN_STOCK", 14.0, 19.95, "Gamegenic")
    undated = read(DELTA, page("Dominio Delta", card(*BOX, True, preorder=True), card(*ETB, True))).offers
    assert [o.availability for o in undated] == ["PREORDER", "IN_STOCK"]
    # the shop's own label on its own page: enough to alert on, with no buy button read
    score = rules.score_confidence(blister, source_level=2, tier="http", target_store_ids=[]).score
    assert score >= rules.ALERT_THRESHOLD


def test_a_category_with_one_product_or_none_is_still_a_list():
    empty = read(PARTY, page("Celebración 30 aniversario"))
    assert empty.page_kind == "listing" and empty.offers == [] and empty.methods == [mabisy.METHOD] and empty.quality_ok
    one = read(PARTY, page("Celebración 30 aniversario", card(*PARTY_ETB, True)))
    assert one.page_kind == "listing" and [o.title for o in one.offers] == [PARTY_ETB[2]]
    # a strip of featured products elsewhere on the page is not what the category sells
    strip = f'<div class="featured"><div class="mb-product-list">{card(*ETB, True)}</div></div>'
    assert read(PARTY, page("Celebración 30 aniversario", strip=strip)).offers == []
    assert [o.title for o in read(PARTY, page("Celebración 30 aniversario", card(*PARTY_ETB, True), strip=strip)).offers] == [PARTY_ETB[2]]
    # another shop's page is none of this reader's business, whatever its markup looks like
    other = page("Celebración 30 aniversario", card(*PARTY_ETB, True), generator="WordPress")
    assert mabisy.listing(BeautifulSoup(other, "html.parser"), PARTY) is None
    assert mabisy.METHOD not in read(PARTY, other).methods
    plain = '<html><head><meta name="generator" content="Mabisy"/></head><body><h1>Contacto</h1><p>Escríbenos.</p></body></html>'
    assert mabisy.listing(BeautifulSoup(plain, "html.parser"), SHOP + "/contacto.html") is None


def test_the_maker_on_the_card_says_what_the_product_is():
    terms = ["pokemon", "delta"]
    etb = Offer(title=ETB[2], url=SHOP + "/caja-entrenador-elite-dominio-delta_p11623179.htm")
    assert not offer_matches(etb, terms, terms, [], listing_context(DELTA))       # neither the title nor the page names the game
    etb.brand = MAKER
    assert offer_matches(etb, terms, terms, [], listing_context(DELTA))
    assert not offer_matches(Offer(title="Caja de sobres Delta", brand="Ravensburger"), terms, terms, [])
    party = Offer(title=PARTY_ETB[2], brand=MAKER)
    assert offer_matches(party, ["pokemon", "30", "aniversario"], ["pokemon"], ["fundas"])
    assert offer_matches(Offer(title="Caja Delta", brand="Pokémon Fundas"), terms, terms, ["fundas"])   # a maker never excludes
    assert not offer_matches(Offer(title="Fundas Delta", brand=MAKER), terms, terms, ["fundas"])


def test_the_shop_is_known():
    profile = profile_for_host(DELTA)
    assert profile.name == "Artman Toys" and not profile.needs_browser and not profile.catalog_feed
    assert kind_of_url(SHOP + "/caja-entrenador-elite-dominio-delta_p11623179.htm") == "product"
    assert kind_of_url(DELTA) == "" and kind_of_url(DELTA + "?lp=2") == ""
    assert "30 aniversario" in listing_context(PARTY)


def watcher(svc, name: str, terms: list[str], must: list[str]):
    return tool(svc, "watcher_create", name=name, mode="availability",
                config={"product": {"terms": terms, "must": must},
                        "policies": {"seller": "retail_only", "revalidate_seconds": 0}})


def events(svc, result):
    return [svc.store.event(e) for e in result["events"]]


def later(svc, seconds: float) -> None:
    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + seconds


def test_what_the_category_had_is_the_baseline_and_each_product_is_followed_from_the_page(svc):
    shop = svc.engine.fetcher = Shop([
        page("Dominio Delta", card(*ETB, False), card(*BLISTER, True), card(*BOX, False)),
        page("Dominio Delta", card(*ETB, True), card(*BLISTER, True), card(*BOX, False)),
        page("Dominio Delta", card(*ETB, True), card(*BLISTER, True), card(*BOX, True)),
        page("Dominio Delta", card(*ETB, False), card(*BLISTER, True), card(*BOX, True)),
    ])
    w = watcher(svc, "Dominio Delta", ["pokemon", "delta"], ["pokemon", "delta"])
    t = svc.store.create_target(w["id"], DELTA, label="Artman Toys", retailer="Artman Toys")
    first = svc.engine.check_target(t["id"])
    assert first["ok"] and first["events"] == []                      # the blister was already on sale: not news
    assert shop.asked[0][0] == DELTA
    items = svc.store.target(t["id"])["extra"]["items"]
    assert len(items) == 3 and items[SHOP + "/caja-entrenador-elite-dominio-delta_p11623179.htm"]["state"] == "OUT_OF_STOCK"

    later(svc, 600)
    second = events(svc, svc.engine.check_target(t["id"]))            # the trainer box comes back
    assert [(e["type"], e["title"], e["status"]) for e in second] == [("RESTOCK", ETB[2], "confirmed")]
    assert second[0]["url"] == SHOP + "/caja-entrenador-elite-dominio-delta_p11623179.htm" and second[0]["price"] == 66.5
    assert second[0]["confidence"] >= rules.ALERT_THRESHOLD and "acaba de aparecer" not in second[0]["summary"]

    later(svc, 1200)
    third = events(svc, svc.engine.check_target(t["id"]))             # then the booster box: its own alert
    assert [(e["type"], e["title"]) for e in third] == [("RESTOCK", BOX[2])]

    later(svc, 1800)
    fourth = events(svc, svc.engine.check_target(t["id"]))            # the trainer box sells out again
    assert "RESTOCK" not in [e["type"] for e in fourth]
    assert svc.store.target(t["id"])["extra"]["items"][SHOP + "/caja-entrenador-elite-dominio-delta_p11623179.htm"]["state"] == "OUT_OF_STOCK"
    # the page already follows every product: none became a target of its own
    assert [x["url"] for x in svc.store.targets(watcher_id=w["id"])] == [DELTA]


def test_the_first_product_of_an_empty_category_is_news(svc):
    svc.engine.fetcher = Shop([
        page("Celebración 30 aniversario"),
        page("Celebración 30 aniversario", card(*PARTY_ETB, True)),
        page("Celebración 30 aniversario", card(*PARTY_ETB, True), card(*PARTY_TIN, False)),
    ])
    w = watcher(svc, "30 aniversario", ["pokemon", "30", "aniversario"], ["pokemon"])
    t = svc.store.create_target(w["id"], PARTY, label="Artman Toys", retailer="Artman Toys")
    first = svc.engine.check_target(t["id"])
    assert first["ok"] and first["events"] == [] and svc.store.target(t["id"])["status"] == "active"

    later(svc, 600)
    second = events(svc, svc.engine.check_target(t["id"]))            # the shop lists its first product, on sale
    assert [(e["type"], e["title"], e["status"]) for e in second] == [("RESTOCK", PARTY_ETB[2], "confirmed")]
    assert "acaba de aparecer en la página" in second[0]["summary"] and "primera comprobación" not in second[0]["summary"]

    later(svc, 1200)
    third = events(svc, svc.engine.check_target(t["id"]))             # and a second one, not for sale yet
    assert [(e["type"], e["title"]) for e in third] == [("NEW_SKU", PARTY_TIN[2])]


def test_a_page_target_that_starts_following_its_cards_takes_them_as_the_baseline(svc):
    svc.engine.fetcher = Shop([page("Dominio Delta", card(*ETB, False), card(*BLISTER, True)),
                               page("Dominio Delta", card(*ETB, True), card(*BLISTER, True))])
    w = watcher(svc, "Dominio Delta", ["pokemon", "delta"], ["pokemon", "delta"])
    t = svc.store.create_target(w["id"], DELTA, label="Artman Toys", retailer="Artman Toys",
                                extra={"checked_once": True, "seen_offer_urls": [], "last_known_state": "OUT_OF_STOCK"})
    assert svc.engine.check_target(t["id"])["events"] == []           # read another way before: still nothing to announce
    later(svc, 600)
    assert [(e["type"], e["title"]) for e in events(svc, svc.engine.check_target(t["id"]))] == [("RESTOCK", ETB[2])]
