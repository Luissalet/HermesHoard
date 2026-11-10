"""An alert leaves the panel when the offer ends, says "se acabó" once, and a restock alerts again: at every level of reading
(the shop's product page and its revalidation, rows of an open window, rows only the model understood). The aggregator radar
is covered in test_radar.py and the shops' own mail in test_stock_notices.py."""

from __future__ import annotations

from conftest import T0, tool

from test_engine import URL, ScriptedFetcher, make_watcher, page
from test_open_window import FOOT, HEAD, MEW, MEWTWO, OUT, ROW, ULTRA, FakeModel, make, model_reading, page_text


def swap_clock(svc, value):
    svc.clock = svc.store.clock = svc.engine.clock = lambda: value


def sent_types(svc):
    return [s[0]["type"] for s in svc.notifier.sent]


# ------------------------------------------------------------------------------------------------ the shop's own page
def test_a_revalidation_that_reads_sold_out_ends_the_alert_and_tells(svc):
    out, inn = page("game_product_outofstock.html"), page("game_product_instock.html")
    svc.engine.fetcher = ScriptedFetcher({URL: [out, inn, out, out]})
    w = make_watcher(svc)
    t = svc.store.create_target(w["id"], URL, label="Switch 2", retailer="GAME")
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 600)
    [restock] = svc.engine.check_target(t["id"])["events"]
    swap_clock(svc, T0 + 900)
    svc.notifier.sent.clear()
    svc.engine.check_target(t["id"], revalidation=True)        # e.g. the revalidation of a price alert reads it sold out
    ended = svc.store.event(restock)
    assert ended["data"]["expired_state"] == "OUT_OF_STOCK" and sent_types(svc) == ["SOLD_OUT"]
    assert svc.dashboard()["news"] == []
    swap_clock(svc, T0 + 1500)
    svc.engine.check_target(t["id"])                           # the next ordinary check has nothing more to say
    assert sent_types(svc) == ["SOLD_OUT"]


def test_back_in_stock_after_ending_alerts_again(svc):
    out, inn = page("game_product_outofstock.html"), page("game_product_instock.html")
    svc.engine.fetcher = ScriptedFetcher({URL: [out, inn, out, inn]})
    w = make_watcher(svc, cooldown_minutes=0)
    t = svc.store.create_target(w["id"], URL, label="Switch 2", retailer="GAME")
    for step in range(4):
        swap_clock(svc, T0 + step * 600)
        svc.engine.check_target(t["id"])
    assert sent_types(svc) == ["RESTOCK", "SOLD_OUT", "RESTOCK"]
    assert len(svc.store.live_alerts(target_id=t["id"])) == 1


# ------------------------------------------------------------------------------------------------ rows of an open window
def without_mew(button_mewtwo: str = OUT) -> str:
    return HEAD + ROW.format(title=MEWTWO, price="49,99 €", button=button_mewtwo) + ROW.format(title=ULTRA, price="249,99 €", button=OUT) + FOOT


def test_a_row_that_leaves_the_list_ends_its_alert_quietly_and_alerts_again_when_back(svc):
    w, t = make(svc, [page_text(), page_text(mew="Añadir"), without_mew(), without_mew(), page_text(mew="Añadir")])
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 300)
    [restock] = svc.engine.check_target(t["id"])["events"]
    svc.notifier.sent.clear()
    swap_clock(svc, T0 + 600)
    svc.engine.check_target(t["id"])                            # one reading without the row: still on
    assert not svc.store.event(restock)["data"].get("expired_at")
    swap_clock(svc, T0 + 900)
    svc.engine.check_target(t["id"])                            # two readings: nothing vouches for it any more
    assert svc.store.event(restock)["data"]["expired_state"] == "UNKNOWN" and svc.notifier.sent == []
    swap_clock(svc, T0 + 1200)
    again = svc.engine.check_target(t["id"])
    assert [svc.store.event(e)["title"] for e in again["events"]] == [MEW] and sent_types(svc) == ["RESTOCK"]


def test_an_empty_reading_does_not_end_the_rows(svc):
    w, t = make(svc, [page_text(), page_text(mew="Añadir"), HEAD + FOOT.split("Estantería")[0], HEAD + FOOT.split("Estantería")[0]])
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 300)
    [restock] = svc.engine.check_target(t["id"])["events"]
    for step in (2, 3):
        swap_clock(svc, T0 + 300 * step)
        svc.engine.check_target(t["id"])
    assert not svc.store.event(restock)["data"].get("expired_at")


# ------------------------------------------------------------------------------------------------ a row only the model understood
def test_a_row_the_model_confirmed_ends_with_the_follow_up_when_sold_out(svc):
    w, t = make(svc, [page_text(), page_text(mew="Lo quiero"), page_text(mew="Lo quiero"), page_text()])
    svc.engine.llm = FakeModel(lambda text: model_reading(mew="in_stock" if "Lo quiero" in text else "out_of_stock",
                                                          mew_evidence="Lo quiero" if "Lo quiero" in text else OUT)(text))
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 300)
    assert svc.engine.check_target(t["id"])["events"] == []      # the model alone: read again first
    swap_clock(svc, T0 + 360)
    [restock] = svc.engine.check_target(t["id"])["events"]
    assert svc.store.event(restock)["title"] == MEW
    svc.notifier.sent.clear()
    swap_clock(svc, T0 + 660)
    svc.engine.check_target(t["id"])
    assert svc.store.event(restock)["data"]["expired_state"] == "OUT_OF_STOCK" and sent_types(svc) == ["SOLD_OUT"]
    assert tool(svc, "events_list", limit=20)["events"][0]["type"] == "SOLD_OUT"
