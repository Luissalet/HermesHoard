"""Faustus looks at the open window too: its verdict is asked over the copilot contract and put in common with Hermes's."""

from __future__ import annotations

import json

import httpx

from conftest import T0
from test_open_window import MEW, MEWTWO, OUT, ULTRA, URL, make, page_text, swap_clock

from tantalus_hoard.faustus_eye import FaustusEye, parse_answer


def verdict_rows(**status):
    rows = []
    for short, title, price in (("mew", MEW, 49.99), ("mewtwo", MEWTWO, 49.99), ("ultra", ULTRA, 249.99)):
        st = status.get(short, "out_of_stock")
        rows.append({"title": title, "price": price, "status": st, "evidence": "Añadir" if st == "in_stock" else OUT,
                     "where": status.get(short + "_where", "lista")})
    return rows


class FakeFaustus:
    """The copilot contract of Faustus: a conversation, then a streamed turn whose text ends with the JSON verdict."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.turns: list[dict] = []
        self.conversations = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/hoard-copilot/conversations":
            self.conversations += 1
            return httpx.Response(200, json={"session_id": f"s{self.conversations}", "model": "deepseek-v4.1-flash"})
        if request.url.path == "/api/chat_stream":
            self.turns.append(json.loads(request.content))
            answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
            text = "Miro la pestaña…" + json.dumps(answer, ensure_ascii=False)
            body = "".join(f"data: {json.dumps({'delta': text[i:i + 40]})}\n\n" for i in range(0, len(text), 40)) + "data: [DONE]\n\n"
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(404)


def attach(svc, answers):
    fake = FakeFaustus(answers)
    eye = FaustusEye(svc.store, clock=lambda: svc.clock(), transport=httpx.MockTransport(fake.handler), run_inline=True)
    svc.engine.faustus_eye = eye
    return fake, eye


def test_parse_answer_takes_the_last_json_with_rows():
    text = 'Pienso… {"x": 1} y al final {"rows": [{"title": "A", "status": "in_stock"}], "notes": "ok"}'
    assert parse_answer(text)["rows"][0]["title"] == "A"
    assert parse_answer("sin json") is None


def test_each_check_asks_faustus_with_hermes_reading_and_agreement_counts(svc):
    w, t = make(svc, [page_text(), page_text(), page_text(mew="Añadir")])
    fake, eye = attach(svc, [{"rows": verdict_rows(), "notes": ""}, {"rows": verdict_rows(mew="in_stock"), "notes": "ficha ok"}])
    svc.engine.check_target(t["id"])                       # Hermes reads, then Faustus looks (inline in tests)
    assert len(fake.turns) == 1 and URL in fake.turns[0]["message"] and MEW in fake.turns[0]["message"]
    assert fake.turns[0]["mode"] == "agent" and eye.latest(t["id"])["ok"]
    swap_clock(svc, T0 + 300)
    svc.engine.check_target(t["id"])                       # merges look 1 (all out: agrees), asks look 2
    swap_clock(svc, T0 + 600)
    res = svc.engine.check_target(t["id"])                 # Hermes reads Mew buyable; look 2 said the same
    [event] = [svc.store.event(e) for e in res["events"]]
    assert event["type"] == "RESTOCK" and event["title"] == MEW
    assert "Faustus lo ve igual" in " ".join(event["data"]["evidence"])
    assert any(f["key"] == "faustus_agrees" for f in event["data"]["factors"])
    check = svc.store.target(t["id"])["extra"]["faustus_check"]
    assert check["merged"] and check["agree"] == 3


def test_faustus_seeing_it_on_the_product_page_alerts_after_two_looks(svc):
    w, t = make(svc, [page_text()])                          # the list keeps saying "Agotado"
    fake, eye = attach(svc, [{"rows": verdict_rows(mew="in_stock", mew_where="ficha"), "notes": "la ficha deja añadir"}])
    svc.engine.check_target(t["id"])                       # look 1 stored; Faustus sees Mew buyable -> next check now
    assert svc.store.target(t["id"])["next_check_ts"] <= T0
    swap_clock(svc, T0 + 30)
    first = svc.engine.check_target(t["id"])               # merges look 1: one look only -> no alert, read again soon
    assert first["events"] == [] and svc.store.target(t["id"])["extra"]["faustus_check"]["flagged"] == 1
    swap_clock(svc, T0 + 90)
    second = svc.engine.check_target(t["id"])              # merges look 2 (asked at the previous check): confirmed
    [event] = [svc.store.event(e) for e in second["events"]]
    assert event["type"] == "RESTOCK" and event["title"] == MEW and event["status"] == "confirmed"
    assert any(f["key"] == "faustus_twice" for f in event["data"]["factors"])
    assert "Faustus (ficha)" in " ".join(event["data"]["evidence"])


def test_faustus_unavailable_is_said_and_hermes_keeps_watching(svc):
    w, t = make(svc, [page_text(), page_text(mew="Añadir")])
    fake, eye = attach(svc, [{"rows": [], "notes": "la extensión no está conectada"}])
    svc.engine.check_target(t["id"])
    swap_clock(svc, T0 + 300)
    [event] = [svc.store.event(e) for e in svc.engine.check_target(t["id"])["events"]]
    assert event["type"] == "RESTOCK" and event["title"] == MEW
    check = svc.store.target(t["id"])["extra"]["faustus_check"]
    assert not check["merged"] and "extensión" in check["reason"]


def test_a_new_faustus_conversation_every_few_looks(svc):
    w, t = make(svc, [page_text()])
    fake, eye = attach(svc, [{"rows": verdict_rows(), "notes": ""}])
    for i in range(8):
        swap_clock(svc, T0 + 300 * i)
        svc.engine.check_target(t["id"])
    assert fake.conversations == 2 and len(fake.turns) == 8
