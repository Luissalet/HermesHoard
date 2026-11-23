"""A shop's catalogue feed: one reading follows every product of a collection, sold out or not."""

from __future__ import annotations

import html
import json

from conftest import T0, tool

from tantalus_hoard.extract import adapter_for, catalog, extract
from tantalus_hoard.model import FetchResult

PAGE = "https://todohits.com/collections/pokemon?filter.v.availability=1"
FEED = "https://todohits.com/collections/pokemon/products.json?limit=250&page=1"


def product(handle: str, title: str, price: str, *available: bool, was=None) -> dict:
    return {"id": abs(hash(handle)) % 10**9, "handle": handle, "title": title, "vendor": "ForeverTCG", "product_type": "POKÉMON",
            "tags": ["idioma_español"], "images": [{"src": f"https://cdn.example/{handle}.jpg"}],
            "variants": [{"title": "Default Title" if len(available) == 1 else f"Modelo {n + 1}", "available": a, "price": price,
                          "compare_at_price": was} for n, a in enumerate(available)]}


def feed(*products: dict) -> str:
    return json.dumps({"products": list(products)})


def as_browser_page(body: str) -> str:
    """A JSON document as the browser hands it over."""
    return f'<html><head><meta name="color-scheme" content="light dark"></head><body><pre>{html.escape(body)}</pre></body></html>'


ETB = ("etb-dominio-delta-pokemon-espanol", "ETB Dominio Delta | Elite Trainer Box | POKÉMON | Español", "64.99")
BOX = ("booster-box-dominio-delta-pokemon-espanol", "Booster Box Dominio Delta | POKÉMON | Español", "194.99")
TIN = ("mini-lata-30-aniversario-pokemon-espanol", "Mini Lata 30 Aniversario | POKÉMON | Español", "19.99")
BUNDLE = ("booster-bundle-dominio-delta-pokemon-espanol", "Booster Bundle Dominio Delta | POKÉMON | Español", "42.99")


class Shop:
    """Answers the scripted feed bodies in turn; the last repeats. Remembers what it was asked for."""

    def __init__(self, bodies):
        self.bodies, self.asked = list(bodies), []

    def get(self, url, **kw):
        self.asked.append((url, kw))
        body = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        return FetchResult(url=url, final_url=url, status=200, text=as_browser_page(body), ok=True, content_type="application/json",
                           tier="browser")

    def get_json(self, url, **kw):
        raise AssertionError(f"the feed was asked for as an API, past its shop's rung: {url}")

    def clear_block(self, host):
        pass

    def host_status(self):
        return []

    def close(self):
        pass


def test_a_collection_page_of_a_shop_with_a_feed_is_read_from_the_feed():
    api = adapter_for(PAGE, {"adapter": "auto"})
    assert api["adapter"] == "catalog" and api["url"] == FEED and api["min_interval_s"] == 60.0
    assert api["accept"] == "html" and api["tier"] == "browser"       # read like a page, by the rung this shop needs
    assert catalog.adapter_url("https://todohits.com/collections/pokemon?page=3").endswith("&page=3")
    assert catalog.adapter_url("https://todohits.com/products/etb-dominio-delta-pokemon-espanol") is None
    assert catalog.adapter_url("https://todohits.com/collections/pokemon/products/etb-dominio-delta") is None
    assert adapter_for("https://www.collectowny.com/collections/pokemon", {}) is None    # no feed seen to answer there
    assert adapter_for("https://unknown-shop.example/collections/pokemon", {}) is None


def test_the_feed_gives_one_offer_per_product_with_its_stock_and_price():
    body = feed(product(*ETB, True), product(*BOX, False), product(*TIN, False, True, False, was="24.99"),
                product("sobre-jp", "[Reserva] Sobre 30 Aniversario | POKÉMON | Japonés", "10.99", True),
                {"handle": "", "title": "broken"})
    ex = extract(FetchResult(url=FEED, final_url=FEED, status=200, text=body, ok=True, content_type="application/json", tier="http"),
                 hints={"url": PAGE, "adapter": "catalog"})
    assert ex.page_kind == "listing" and ex.methods == ["api:catalog"] and len(ex.offers) == 4
    etb, box, tin, pre = ex.offers
    assert (etb.availability, etb.price, etb.currency, etb.buy_button) == ("IN_STOCK", 64.99, "EUR", True)
    assert etb.url == "https://todohits.com/products/etb-dominio-delta-pokemon-espanol" and etb.seller == "TodoHits"
    assert etb.seller_is_retailer is True and etb.title == ETB[1]
    assert (box.availability, box.buy_button, box.price) == ("OUT_OF_STOCK", False, 194.99)
    assert tin.availability == "IN_STOCK" and tin.extra["variants_available"] == 1 and tin.extra["compare_at_price"] == 24.99
    assert any("Modelo 2" in e for e in tin.evidence)
    assert pre.availability == "PREORDER"
    shown = extract(FetchResult(url=FEED, final_url=FEED, status=200, text=as_browser_page(body), ok=True,
                                content_type="application/json", tier="browser"), hints={"url": PAGE, "adapter": "catalog"})
    assert [o.to_dict() for o in shown.offers] == [o.to_dict() for o in ex.offers]       # the same feed, shown by a browser
    assert catalog.unwrap("<html><body><pre>not json</pre></body></html>") == ""
    empty = extract(FetchResult(url=FEED, final_url=FEED, status=200, text='{"products": []}', ok=True,
                                content_type="application/json", tier="http"), hints={"url": PAGE})
    assert empty.page_kind == "listing" and empty.offers == []


def delta_watcher(svc):
    return tool(svc, "watcher_create", name="Dominio Delta", mode="availability",
                config={"product": {"terms": ["pokemon", "delta"], "must": ["pokemon", "delta"]},
                        "policies": {"seller": "retail_only", "revalidate_seconds": 0}})


def kinds(svc, result):
    return [(svc.store.event(e)["type"], svc.store.event(e)["title"]) for e in result["events"]]


def test_what_the_catalogue_had_is_the_baseline_and_each_product_coming_back_is_its_own_alert(svc):
    shop = svc.engine.fetcher = Shop([
        feed(product(*ETB, True), product(*BOX, False), product(*BUNDLE, False), product(*TIN, False)),
        feed(product(*ETB, True), product(*BOX, True), product(*BUNDLE, False), product(*TIN, True)),
        feed(product(*ETB, True), product(*BOX, True), product(*BUNDLE, True), product(*TIN, True)),
        feed(product(*ETB, True), product(*BOX, False), product(*BUNDLE, True), product(*TIN, True)),
    ])
    w = delta_watcher(svc)
    t = svc.store.create_target(w["id"], PAGE, label="TodoHits", retailer="TodoHits")
    first = svc.engine.check_target(t["id"])
    assert first["ok"] and first["events"] == []                      # the ETB was already on sale: not news
    assert shop.asked[0][0] == FEED and shop.asked[0][1]["tier"] == "browser"
    items = svc.store.target(t["id"])["extra"]["items"]
    assert len(items) == 3 and items["https://todohits.com/products/" + BOX[0]]["state"] == "OUT_OF_STOCK"   # the tin is not this watcher's

    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 600
    second = svc.engine.check_target(t["id"])                         # the box comes back (and a tin nobody asked about)
    assert kinds(svc, second) == [("RESTOCK", BOX[1])]
    event = svc.store.event(second["events"][0])
    assert event["url"] == "https://todohits.com/products/" + BOX[0] and event["price"] == 194.99

    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 1200
    third = svc.engine.check_target(t["id"])                          # then the bundle: its own alert, the box says nothing new
    assert kinds(svc, third) == [("RESTOCK", BUNDLE[1])]

    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 1800
    fourth = svc.engine.check_target(t["id"])                         # the box sells out again
    assert ("RESTOCK", BOX[1]) not in kinds(svc, fourth)
    assert svc.store.target(t["id"])["extra"]["items"]["https://todohits.com/products/" + BOX[0]]["state"] == "OUT_OF_STOCK"
    # the feed already follows every product: none became a target of its own
    assert [x["url"] for x in svc.store.targets(watcher_id=w["id"])] == [PAGE]


def test_a_product_the_shop_adds_later_is_announced_once(svc):
    svc.engine.fetcher = Shop([
        feed(product(*ETB, True)),
        feed(product(*ETB, True), product(*BOX, True)),
        feed(product(*ETB, True), product(*BOX, True), product(*BUNDLE, False)),
    ])
    w = delta_watcher(svc)
    t = svc.store.create_target(w["id"], PAGE, label="TodoHits", retailer="TodoHits")
    assert svc.engine.check_target(t["id"])["events"] == []
    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 600
    assert kinds(svc, svc.engine.check_target(t["id"])) == [("RESTOCK", BOX[1])]          # listed and buyable: one alert, not two
    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 1200
    listed = svc.engine.check_target(t["id"])                                               # listed, not for sale yet
    assert [k for k, _ in kinds(svc, listed)] == ["NEW_SKU"]


def test_two_watchers_on_one_collection_share_a_reading(svc):
    shop = svc.engine.fetcher = Shop([feed(product(*ETB, True), product(*TIN, False))])
    delta = delta_watcher(svc)
    tins = tool(svc, "watcher_create", name="30 aniversario", mode="availability",
                config={"product": {"terms": ["pokemon", "30", "aniversario"]}, "policies": {"revalidate_seconds": 0}})
    a = svc.store.create_target(delta["id"], PAGE, label="TodoHits", retailer="TodoHits")
    b = svc.store.create_target(tins["id"], PAGE, label="TodoHits", retailer="TodoHits")
    assert svc.engine.check_target(a["id"])["ok"] and svc.engine.check_target(b["id"])["ok"]
    assert len(shop.asked) == 1                                          # one request, two watchers
    assert list(svc.store.target(b["id"])["extra"]["items"]) == ["https://todohits.com/products/" + TIN[0]]
    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 600
    svc.engine.check_target(a["id"])
    assert len(shop.asked) == 2                                          # a later reading is a new request


def test_a_page_target_that_starts_reading_the_feed_takes_it_as_the_baseline(svc):
    svc.engine.fetcher = Shop([feed(product(*ETB, True), product(*BOX, False)), feed(product(*ETB, True), product(*BOX, True))])
    w = delta_watcher(svc)
    t = svc.store.create_target(w["id"], PAGE, label="TodoHits", retailer="TodoHits",
                                extra={"checked_once": True, "seen_offer_urls": [], "last_known_state": "OUT_OF_STOCK"})
    assert svc.engine.check_target(t["id"])["events"] == []              # read as a page before: still nothing to announce
    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 600
    assert kinds(svc, svc.engine.check_target(t["id"])) == [("RESTOCK", BOX[1])]


class Limited(Shop):
    """Says "too many requests" the first times it is asked."""

    def __init__(self, bodies, refusals):
        super().__init__(bodies)
        self.refusals = refusals

    def get(self, url, **kw):
        if self.refusals:
            self.refusals -= 1
            self.asked.append((url, kw))
            return FetchResult(url=url, final_url=url, status=429, text="", ok=False, blocked=True, block_reason="http_429",
                               error="blocked: HTTP 429 too many requests", error_kind="blocked", tier="browser")
        return super().get(url, **kw)


def test_a_brief_too_many_requests_is_asked_again_after_its_hold(svc):
    svc.engine.fetcher = Limited([feed(product(*ETB, True))], refusals=1)
    w = delta_watcher(svc)
    t = svc.store.create_target(w["id"], PAGE, label="TodoHits", retailer="TodoHits")
    refused = svc.engine.check_target(t["id"])
    row = svc.store.target(t["id"])
    assert not refused["ok"] and refused["events"] == []
    assert row["status"] == "active" and 120 <= row["next_check_ts"] - T0 <= 200       # after the shop's hold, not hours later
    svc.clock = svc.store.clock = svc.engine.clock = lambda: T0 + 180
    assert svc.engine.check_target(t["id"])["ok"] and svc.store.target(t["id"])["fail_count"] == 0


def test_too_many_requests_again_and_again_is_a_wall(svc):
    svc.engine.fetcher = Limited([feed(product(*ETB, True))], refusals=99)
    w = delta_watcher(svc)
    t = svc.store.create_target(w["id"], PAGE, label="TodoHits", retailer="TodoHits")
    for n in range(6):
        svc.clock = svc.store.clock = svc.engine.clock = lambda n=n: T0 + 200 * n
        last = svc.engine.check_target(t["id"])
    row = svc.store.target(t["id"])
    assert row["status"] == "needs_human" and row["next_check_ts"] - (T0 + 1000) > 3600
    assert [svc.store.event(e)["type"] for e in last["events"]] == ["NEEDS_HUMAN"]
