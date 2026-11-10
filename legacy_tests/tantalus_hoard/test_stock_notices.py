"""The shops' own stock mail -> alerts of the watched targets: classification, matching, alerts and their whole lifecycle."""

from __future__ import annotations

import pytest

from conftest import T0, tool

from tantalus_hoard import engine as engine_mod
from tantalus_hoard.errors import TantalusError
from tantalus_hoard.mail import notices as notices_mod
from tantalus_hoard.mail.notices import classify, name_score, registrable, shop_domains, words
from tantalus_hoard.mail.source import NoticeSource
from test_engine import ScriptedFetcher, page

HOUR = 3600
URL = "https://www.game.es/juguetes/pokemon-caja-ultra-premium-30-aniversario/238751"
TITLE = "Pokémon Caja Ultra Premium 30 Aniversario"


class Mailbox:
    """Stands in for the Faustus mail helper (read-only): scripted mails, honours the skip list."""

    def __init__(self):
        self.messages: list[dict] = []
        self.requests: list[dict] = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if request["action"] == "scan":
            skip = set(request.get("skip") or [])
            return {"ok": True, "error": "", "accounts": [], "messages": [m for m in self.messages if m["message_id"] not in skip]}
        return {"ok": True, "error": "", "accounts": []}


@pytest.fixture
def box(svc):
    mailbox = Mailbox()
    svc.notices.source = NoticeSource(runner=mailbox)
    return mailbox


def swap_clock(svc, value):
    svc.clock = svc.store.clock = svc.engine.clock = svc.notices.clock = lambda: value


def mail(mid, subject, text="", *, sender="noticias@mail-game.net", age_s=HOUR / 2, links=None):
    return {"message_id": mid, "subject": subject, "from_address": sender, "ts": T0 - age_s, "text": text,
            "links": links if links is not None else [{"url": URL + "?utm_source=mail&utm_campaign=alerta", "label": "Comprar"}],
            "images": []}


def watched(svc, *, state="OUT_OF_STOCK", url=URL, label=TITLE, **policies):
    base = {"seller": "retail_only", "revalidate_seconds": 0, "cooldown_minutes": 20}
    base.update(policies)
    w = tool(svc, "watcher_create", name="Pokémon TCG", mode="availability",
             config={"product": {"terms": ["pokemon"]}, "policies": base})
    t = svc.store.create_target(w["id"], url, label=label, retailer="GAME")
    svc.store.update_target(t["id"], last_state=state, last_check_ts=T0 - 2 * HOUR, next_check_ts=T0 + 900, last_price=149.99,
                            last_currency="EUR",
                            extra={"last_known_state": state, "checked_once": True})
    return w, svc.store.target(t["id"])


# ------------------------------------------------------------------------------------------------ pure rules
def test_classify_reads_subject_phrases_and_only_personal_bodies():
    assert classify("¡Vuelve a estar disponible! Caja Ultra Premium", "")["kind"] == "available"
    assert classify("Ya puedes reservar la Caja de Combate", "")["kind"] == "preorder"
    assert classify("Un artículo de tu lista de deseos ha bajado de precio", "")["kind"] == "price_drop"
    assert classify("Lo sentimos: se ha agotado", "")["kind"] == "sold_out"
    assert classify("Back in stock: Pokémon Ultra Premium Collection", "")["kind"] == "available"
    # a phrase only in the body counts only when the mail is personal
    assert classify("Novedades de la semana", "El catálogo ya disponible en tienda")["kind"] == ""
    hit = classify("Tu alerta de stock", "El producto de tu lista de deseos vuelve a estar disponible.")
    assert hit["kind"] == "available" and hit["personal"] and hit["where"] == "body"
    # "próximamente disponible" is the opposite of a notice
    assert classify("Próximamente disponible: Caja Ultra Premium", "")["kind"] == ""


def test_sender_domains_and_names():
    assert registrable("mail.game.es") == "game.es" and registrable("shop.example.co.uk") == "example.co.uk"
    assert "mail-game.net" in shop_domains(URL) and "game.es" in shop_domains(URL)
    hay = set(words("Ya disponible: Pokémon Caja Ultra Premium 30 Aniversario en GAME"))
    assert name_score(TITLE, hay)[0] >= 90
    assert name_score("Pokémon Caja Colección Figura Mewtwo", set(words("Caja Colección Figura Mew Pokémon")))[0] == 0


# ------------------------------------------------------------------------------------------------ alerts
def test_a_restock_mail_from_the_shop_raises_the_restock_alert_and_asks_the_page(svc, box):
    w, t = watched(svc)
    box.messages = [mail("<a>", "¡Ya está disponible! Pokémon Caja Ultra Premium")]
    out = tool(svc, "stock_notices_scan")["result"]
    assert out["ok"] and out["notices"] == 1 and out["matched"] == 1 and out["alerts"] == 1
    [event] = svc.store.events(types=["RESTOCK"], limit=5)
    assert event["status"] == "confirmed" and event["target_id"] == t["id"] and event["data"]["source"] == "mail_notice"
    assert event["data"]["match_how"] == "link" and "aviso de la tienda por correo" in event["summary"]
    assert svc.notifier.sent[-1][0]["id"] == event["id"]
    [notice] = tool(svc, "stock_notices", status="matched")["notices"]
    assert notice["status"] == "alerted" and notice["event_id"] == event["id"] and notice["alert_type"] == "RESTOCK"
    assert svc.store.target(t["id"])["next_check_ts"] == T0                      # the page gets a look now
    assert svc.store.target(t["id"])["extra"]["mail_notice"]["event_id"] == event["id"]
    # the same mail is never read twice
    assert tool(svc, "stock_notices_scan")["result"]["scanned"] == 0


def test_coming_soon_turns_into_sale_open_and_reservations_into_preorder_open(svc, box):
    watched(svc, state="COMING_SOON")
    box.messages = [mail("<b>", "Ya a la venta: Pokémon Caja Ultra Premium 30 Aniversario", links=[])]
    tool(svc, "stock_notices_scan")
    [event] = svc.store.events(types=["SALE_OPEN"], limit=5)
    assert event["data"]["sale_kind"] == "sale" and event["data"]["match_how"] == "name"


def test_reservations_open_and_price_drop(svc, box):
    w, t = watched(svc)
    box.messages = [mail("<c>", "Reservas abiertas: Pokémon Caja Ultra Premium 30 Aniversario")]
    tool(svc, "stock_notices_scan")
    assert [e["type"] for e in svc.store.events(types=["PREORDER_OPEN"], limit=5)] == ["PREORDER_OPEN"]
    box.messages.append(mail("<d>", "Ha bajado de precio un producto de tu lista de deseos",
                             "Pokémon Caja Ultra Premium 30 Aniversario\nAntes 149,99 € Ahora 129,99 €"))
    tool(svc, "stock_notices_scan")
    [drop] = svc.store.events(types=["PRICE_DROP"], limit=5)
    assert drop["price"] == 129.99 and drop["old_price"] == 149.99 and drop["data"]["drop_pct"] == 13.3


def test_only_the_shops_own_mail_counts(svc, box):
    watched(svc)
    box.messages = [mail("<e>", "¡Vuelve a estar disponible! Pokémon Caja Ultra Premium", sender="ofertas@chollos-tcg.com")]
    out = tool(svc, "stock_notices_scan")["result"]
    assert out["notices"] == 1 and out["alerts"] == 0 and not svc.store.events(types=["RESTOCK"], limit=5)
    [notice] = tool(svc, "stock_notices", status="unmatched")["notices"]
    assert notice["note"] == "no_target_for_shop"


def test_an_unmatched_notice_can_be_assigned_by_hand_and_alerts(svc, box):
    w, t = watched(svc)
    box.messages = [mail("<f>", "¡Ya disponible! El regalo perfecto para estas fiestas", links=[])]
    tool(svc, "stock_notices_scan")
    [notice] = tool(svc, "stock_notices", status="unmatched")["notices"]
    out = tool(svc, "stock_notice_set", notice_id=notice["id"], action="assign", target_id=t["id"])
    assert out["alert"]["type"] == "RESTOCK" and out["notice"]["match_how"] == "manual"
    assert tool(svc, "stock_notices", status="unmatched")["notices"] == []
    with pytest.raises(TantalusError):
        tool(svc, "stock_notice_set", notice_id=9999, action="ignore")


def test_an_old_mail_is_recorded_without_an_alert(svc, box):
    watched(svc)
    box.messages = [mail("<g>", "¡Vuelve a estar disponible! Pokémon Caja Ultra Premium", age_s=30 * HOUR)]
    out = tool(svc, "stock_notices_scan")["result"]
    assert out["alerts"] == 0 and tool(svc, "stock_notices")["notices"][0]["status"] == "old"


def test_a_page_alert_still_live_is_not_announced_twice(svc, box):
    w, t = watched(svc)
    live = svc.store.add_event({"watcher_id": w["id"], "target_id": t["id"], "type": "RESTOCK", "status": "confirmed", "url": URL,
                                "title": TITLE, "detected_at": T0 - 600})
    box.messages = [mail("<h>", "¡Vuelve a estar disponible! Pokémon Caja Ultra Premium")]
    assert tool(svc, "stock_notices_scan")["result"]["alerts"] == 0
    notice = tool(svc, "stock_notices")["notices"][0]
    assert notice["event_id"] == live["id"] and notice["note"] == "already_announced"


# ------------------------------------------------------------------------------------------------ the lifecycle
def test_the_page_reading_sold_out_ends_a_mail_alert_with_the_follow_up(svc, box):
    w, t = watched(svc, url="https://www.game.es/consolas/switch-2", label="Nintendo Switch 2")
    box.messages = [mail("<i>", "¡Vuelve a estar disponible! Nintendo Switch 2",
                         links=[{"url": "https://www.game.es/consolas/switch-2", "label": ""}])]
    tool(svc, "stock_notices_scan")
    [restock] = svc.store.events(types=["RESTOCK"], limit=5)
    svc.engine.fetcher = ScriptedFetcher({t["url"]: [page("game_product_outofstock.html")]})
    swap_clock(svc, T0 + 600)
    svc.notifier.sent.clear()
    svc.engine.check_target(t["id"])                      # the page was sold out before and still is: the mail alert ends
    assert svc.store.event(restock["id"])["data"]["expired_state"] == "OUT_OF_STOCK"
    assert [s[0]["type"] for s in svc.notifier.sent] == ["SOLD_OUT"]
    assert svc.dashboard()["news"] == []


def test_a_mail_alert_no_page_confirms_ends_quietly(svc, box):
    watched(svc)
    box.messages = [mail("<j>", "¡Vuelve a estar disponible! Pokémon Caja Ultra Premium")]
    tool(svc, "stock_notices_scan")
    [restock] = svc.store.events(types=["RESTOCK"], limit=5)
    swap_clock(svc, T0 + 13 * HOUR)
    svc.notifier.sent.clear()
    assert tool(svc, "stock_notices_scan")["result"]["expired"] == 1
    assert svc.store.event(restock["id"])["data"]["expired_state"] == "UNKNOWN" and not svc.notifier.sent


def test_a_sold_out_mail_ends_the_alert_and_a_new_restock_mail_alerts_again(svc, box):
    w, t = watched(svc)
    box.messages = [mail("<k>", "¡Vuelve a estar disponible! Pokémon Caja Ultra Premium")]
    tool(svc, "stock_notices_scan")
    [first] = svc.store.events(types=["RESTOCK"], limit=5)
    swap_clock(svc, T0 + HOUR)
    svc.notifier.sent.clear()
    box.messages.append(mail("<l>", "Lo sentimos, se ha agotado: Pokémon Caja Ultra Premium", age_s=-HOUR / 2))
    out = tool(svc, "stock_notices_scan")["result"]
    assert out["ended"] == 1 and svc.store.event(first["id"])["data"]["expired_state"] == "OUT_OF_STOCK"
    assert [s[0]["type"] for s in svc.notifier.sent] == ["SOLD_OUT"]
    swap_clock(svc, T0 + 3 * HOUR)
    box.messages.append(mail("<m>", "¡Vuelve a estar disponible! Pokémon Caja Ultra Premium", age_s=-2 * HOUR))
    tool(svc, "stock_notices_scan")
    assert len(svc.store.events(types=["RESTOCK"], limit=5)) == 2


# ------------------------------------------------------------------------------------------------ open windows and the Spark
MEW = "Pokémon Caja 30Th Aniversario, Caja Colección con Figura Mew, +6 Años"
MEWTWO = "Pokémon Caja 30Th Aniversario, Caja Colección con Figura Mewtwo, +6 Años"
LIST = "https://www.carrefour.es/mis-listas-y-productos/mis-listas/104450805"


def window_target(svc):
    w, t = watched(svc, url=LIST, label="Carrefour · Favoritos")
    items = {LIST + "#item-mew": {"state": "OUT_OF_STOCK", "price": 49.99, "title": MEW, "seen": T0},
             LIST + "#item-mewtwo": {"state": "OUT_OF_STOCK", "price": 49.99, "title": MEWTWO, "seen": T0}}
    svc.store.update_target(t["id"], fetch_tier="open_window", extra={**t["extra"], "items": items})
    return w, svc.store.target(t["id"])


def test_a_mail_about_one_row_of_an_open_window_alerts_for_that_row(svc, box):
    w, t = window_target(svc)
    box.messages = [mail("<n>", "¡Ya disponible! Caja Colección con Figura Mewtwo Pokémon 30Th Aniversario",
                         sender="info@carrefour.es", links=[])]
    tool(svc, "stock_notices_scan")
    [event] = svc.store.events(types=["RESTOCK"], limit=5)
    assert event["url"] == LIST + "#item-mewtwo" and event["data"]["item_key"] == LIST + "#item-mewtwo" and event["title"] == MEWTWO


def test_on_a_spark_the_window_waits_but_the_mail_still_alerts(svc, box, monkeypatch):
    monkeypatch.setattr(notices_mod, "WINDOWS_HOST", False)
    monkeypatch.setattr(engine_mod, "WINDOWS_HOST", False)
    w, t = window_target(svc)
    box.messages = [mail("<o>", "Vuelve a estar en stock: Caja Colección Figura Mew Pokémon 30Th Aniversario",
                         sender="info@carrefour.es", links=[])]
    tool(svc, "stock_notices_scan")
    assert [e["title"] for e in svc.store.events(types=["RESTOCK"], limit=5)] == [MEW]
    assert svc.store.target(t["id"])["next_check_ts"] == T0 + 900                # the window stays paused here
    shops = tool(svc, "stock_notices")["status"]["shops"]
    assert shops[0]["shop"] == "carrefour.es" and shops[0]["paused_here"] == 1 and "carrefour.com" in shops[0]["senders"]


def test_settings_and_rules(svc, box):
    svc.set_settings({"mail.notices.domains": "news.tienda-tcg.com=tienda-tcg.es", "mail.notices.max_age_hours": "24"})
    assert svc.settings()["mail.notices.domains"] == "tienda-tcg.com=tienda-tcg.es"
    with pytest.raises(TantalusError):
        svc.set_settings({"mail.notices.domains": "nada"})
    with pytest.raises(TantalusError):
        svc.set_settings({"mail.notices.interval_min": "1"})
    rules = tool(svc, "stock_notices")["rules"]
    assert "vuelve a estar disponible" in rules["kinds"]["available"] and rules["alert_for"]["preorder"] == ["PREORDER_OPEN", "SALE_OPEN"]
