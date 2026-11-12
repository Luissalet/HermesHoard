"""Cart runner: jobs, the extension's keyed routes through Hermes's front door, stage alerts and the stale watch."""
import pytest
from fastapi.testclient import TestClient

from hermes_hoard.app import create_app
from tantalus_hoard.cart import CartRunner, product_ref, shop_of
from tantalus_hoard.errors import TantalusError

URL = "https://www.elcorteingles.es/juguetes/A202035453-caja-coleccion-premium/"
EXTENSION = {"Origin": "chrome-extension://abcdefghijklmnop", "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "cors"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("TANTALUS_OFFLINE", "PHILEAS_OFFLINE"):
        monkeypatch.setenv(key, "1")
    for key in ("TANTALUS_BROWSER", "PHILEAS_BROWSER"):
        monkeypatch.setenv(key, "0")
    monkeypatch.setenv("HOARD_HUB_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("HOARD_FAUSTUS_URL", "http://127.0.0.1:1")


class Events:
    def __init__(self):
        self.rows = []

    def add_event(self, event):
        row = {**event, "id": f"e{len(self.rows)}"}
        self.rows.append(row)
        return row


def runner(clock):
    settings, events, sent = {}, Events(), []
    cart = CartRunner(events, lambda event: sent.append(event) or [{"channel": "ntfy", "ok": True}],
                      lambda key, default=None: settings.get(key, default), settings.__setitem__, clock=lambda: clock[0])
    return cart, events, sent


def test_urls():
    assert shop_of(URL) == "elcorteingles.es" and product_ref(URL) == "A202035453"
    assert shop_of("https://www.example.com/juguetes/A202035453-x/") == ""
    assert product_ref("https://www.elcorteingles.es/juguetes/kidults/") == ""


def test_lists_take_named_products_up_to_a_total():
    clock = [1000.0]
    cart, _events, _sent = runner(clock)
    listing = "https://www.carrefour.es/mis-listas-y-productos/mis-listas/104450805"
    assert shop_of(listing) == "carrefour.es" and product_ref(listing) == "list-104450805"
    assert product_ref("https://www.carrefour.es/caja-premium/VC4A-12345678/p") == ""   # that shop is driven from a list
    assert product_ref("https://www.carrefour.es/supermercado/") == ""
    with pytest.raises(TantalusError):
        cart.add(listing)                                                     # a list without products to take
    job = cart.add(listing, match=["Premium  Ditto", "lata sylveon", "premium ditto"], max_total=92.98)
    assert job["kind"] == "list" and job["match"] == ["premium ditto", "lata sylveon"] and job["max_total"] == 92.98
    assert job["interval_s"] == 90                                            # the shop's calmer default
    sent = cart.for_extension()["jobs"][0]
    assert sent["kind"] == "list" and sent["match"] == ["premium ditto", "lata sylveon"] and sent["max_total"] == 92.98
    assert sent["third_party"] is False and cart.update(job["id"], third_party=True)["third_party"] is True
    assert cart.update(job["id"], match=["lata greninja"], max_total=0)["max_total"] is None
    assert cart.jobs()[0]["match"] == ["lata greninja"]
    assert cart.update(job["id"], match=[])["match"] == ["lata greninja"]      # a list never ends up with nothing to take


def test_jobs_stages_and_repeats():
    clock = [1000.0]
    cart, events, sent = runner(clock)
    with pytest.raises(TantalusError):
        cart.add("https://www.example.com/p/A202035453-x/")
    with pytest.raises(TantalusError):
        cart.add("https://www.elcorteingles.es/juguetes/")
    job = cart.add(URL, interval_s=3)
    assert job["interval_s"] == 8 and job["delivery"] == "home" and not job["watching"]
    assert cart.add(URL)["id"] == job["id"] and len(cart.jobs()) == 1          # the same product re-arms, it is not doubled
    cart.beat(job["id"], state="OUT_OF_STOCK", name="Caja Ditto", price=57.99)
    seen = cart.jobs()[0]
    assert seen["watching"] and seen["name"] == "Caja Ditto" and seen["price"] == 57.99 and seen["checks"] == 1
    first = cart.report(job["id"], "added")
    assert first["alerted"] and events.rows[0]["type"] == "CART_READY" and events.rows[0]["severity"] == "high"
    assert events.rows[0]["title"] == "En la cesta: Caja Ditto" and sent[0]["id"] == "e0"
    assert not cart.report(job["id"], "added")["alerted"]                      # the same stage does not ring twice
    assert cart.report(job["id"], "pay")["alerted"] and events.rows[1]["title"].startswith("Paga ya")
    with pytest.raises(TantalusError):
        cart.report(job["id"], "bought")
    armed = cart.update(job["id"], rearm=True)
    assert armed["stage"] == "" and armed["armed_at"] == 1000.0
    assert cart.for_extension()["jobs"][0].keys() >= {"id", "url", "ref", "enabled", "interval_s", "delivery", "armed_at"}
    assert cart.remove(job["id"])["removed"] == job["id"] and cart.jobs() == []


def test_nobody_watching_alerts_once():
    clock = [1000.0]
    cart, events, sent = runner(clock)
    job = cart.add(URL)
    assert not cart.due(clock[0])
    clock[0] += 400
    assert cart.due(clock[0]) and cart.run_job()["stale"] == [job["id"]]
    assert events.rows[0]["type"] == "NEEDS_HUMAN" and not cart.due(clock[0])
    cart.beat(job["id"], state="OUT_OF_STOCK")
    clock[0] += 200
    assert not cart.due(clock[0])
    cart.update(job["id"], enabled=False)
    clock[0] += 4 * 3600
    assert not cart.due(clock[0])                                              # a paused job is nobody's emergency


def test_extension_routes_open_with_the_key_only(tmp_path):
    app = create_app(tmp_path, port=5221)
    with TestClient(app, base_url="http://127.0.0.1:5221") as c:
        assert c.put("/api/modules/products", json={"enabled": True}).status_code == 200

        def tool(name, arguments=None):
            response = c.post("/products/api/ui/call", json={"name": name, "arguments": arguments or {}})
            assert response.status_code == 200, response.text
            return response.json()

        job = tool("cart_job_add", {"url": URL, "name": "Caja Ditto"})["job"]
        key = tool("cart_jobs")["extension"]["key"]
        # from another origin without the key: the origin rules answer, as for any other route
        assert c.get("/products/api/cart/x/jobs", headers=EXTENSION).status_code == 403
        assert c.get("/products/api/dashboard", headers={**EXTENSION, "X-Hermes-Cart-Key": key}).status_code == 403
        assert c.get("/products/api/cart/x/jobs", headers={**EXTENSION, "X-Hermes-Cart-Key": "nope"}).status_code == 401
        keyed = {**EXTENSION, "X-Hermes-Cart-Key": key}
        listed = c.get("/products/api/cart/x/jobs", headers=keyed)
        assert listed.status_code == 200 and listed.json()["jobs"][0]["ref"] == "A202035453"
        assert c.post("/products/api/cart/x/beat", headers=keyed, json={"job_id": job["id"], "state": "OUT_OF_STOCK"}).json() == {"ok": True}
        reported = c.post("/products/api/cart/x/report", headers=keyed, json={"job_id": job["id"], "stage": "pay"})
        assert reported.status_code == 200 and reported.json()["alerted"]
        after = tool("cart_jobs")["jobs"][0]
        assert after["stage"] == "pay" and after["watching"]
        events = tool("events_list", {"types": ["CART_READY"]})
        assert any(e["title"] == "Paga ya: Caja Ditto" for e in events["events"])
