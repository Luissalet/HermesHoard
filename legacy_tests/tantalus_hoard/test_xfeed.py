"""Stock tips posted on X: the timeline JSON, what counts as a tip, the quiet first read, the age limit and the alert."""

from __future__ import annotations

from datetime import datetime, timezone

from conftest import T0, tool
from tantalus_hoard import xfeed
from tantalus_hoard.info import InfoSentry, judge_rules
from tantalus_hoard.model import InfoFinding


def stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%a %b %d %H:%M:%S +0000 %Y")


def tweet(pid: str, text: str, *, author: str = "stockhunter", ts: float = T0 - 60, urls=(), quoted=None, retweet=None,
          reply: bool = False, wrap: bool = False, note: str = "") -> dict:
    t = {"__typename": "Tweet", "rest_id": pid,
         "core": {"user_results": {"result": {"core": {"screen_name": author}, "legacy": {"screen_name": author}}}},
         "legacy": {"id_str": pid, "created_at": stamp(ts), "full_text": text + " https://t.co/abc",
                    "entities": {"urls": [{"url": "https://t.co/x", "expanded_url": u} for u in urls]},
                    "in_reply_to_status_id_str": "1" if reply else None}}
    if note:
        t["note_tweet"] = {"note_tweet_results": {"result": {"text": note}}}
    if quoted:
        t["quoted_status_result"] = {"result": quoted}
    if retweet:
        t["legacy"]["retweeted_status_result"] = {"result": retweet}
    return {"__typename": "TweetWithVisibilityResults", "tweet": t} if wrap else t


def timeline(*tweets: dict, pinned: dict | None = None) -> dict:
    entries = [{"entryId": f"tweet-{i}", "content": {"itemContent": {"tweet_results": {"result": t}}}} for i, t in enumerate(tweets)]
    instr = [{"type": "TimelineAddEntries", "entries": entries}]
    if pinned:
        instr.insert(0, {"type": "TimelinePinEntry", "entry": {"content": {"itemContent": {"tweet_results": {"result": pinned}}}}})
    return {"data": {"user": {"result": {"timeline": {"timeline": {"instructions": instr}}}}}}


# ------------------------------------------------------------------ sources and JSON
def test_parse_source():
    assert xfeed.parse_source("@Aka_Maskk") == ("user", "Aka_Maskk")
    assert xfeed.parse_source("POKESTOCK_ES") == ("user", "POKESTOCK_ES")
    assert xfeed.parse_source("https://x.com/Aka_Maskk/status/123") == ("user", "Aka_Maskk")
    assert xfeed.parse_source("https://twitter.com/i/lists/1234567") == ("list", "1234567")
    assert xfeed.parse_source("https://x.com/home") == ("", "")
    assert xfeed.parse_source("no es una cuenta") == ("", "")
    assert xfeed.source_url("@a_b") == "https://x.com/a_b"


def test_timeline_parsing_unwraps_retweets_quotes_and_long_posts():
    original = tweet("50", "UPC noche disponible invitación", author="pokestock", urls=["https://link.amazon/B0gvuNpr7"])
    quoted = tweet("40", "Latas en Carrefour", author="other", urls=["https://www.carrefour.es/latas/R-1/p"])
    data = timeline(
        tweet("60", "acaban de restockear todo esto otra vez", quoted=quoted, wrap=True),
        tweet("55", "", retweet=original, author="stockhunter"),
        tweet("45", "corto", note="un texto largo que X guarda aparte en note_tweet"),
        pinned=tweet("10", "fijado", ts=T0 - 86400 * 30))
    posts = {p["id"]: p for p in xfeed.parse_timeline(data)}
    assert set(posts) == {"60", "50", "45", "10"}
    assert posts["60"]["quoted"]["urls"] == ["https://www.carrefour.es/latas/R-1/p"]
    assert posts["50"]["author"] == "pokestock" and posts["50"]["retweet_by"] == "stockhunter"
    assert posts["45"]["text"] == "un texto largo que X guarda aparte en note_tweet"
    assert posts["60"]["text"] == "acaban de restockear todo esto otra vez"     # the trailing t.co link is dropped
    linked = xfeed.parse_timeline(timeline(tweet("70", "Houndstone en Amazon 25€ https://t.co/x", urls=["https://amazon.es/dp/B0"])))[0]
    assert linked["text"] == "Houndstone en Amazon 25€ https://amazon.es/dp/B0"     # a link reads as where it goes
    assert posts["60"]["url"] == "https://x.com/stockhunter/status/60"
    assert xfeed.parse_timeline({"unexpected": [1, 2, {"tweet_results": {"result": {"legacy": "?"}}}]}) == []


# ------------------------------------------------------------------ tips
def sig(text, urls=(), quoted=None, reply=False):
    return xfeed.tip_signal(xfeed.parse_timeline(timeline(tweet("1", text, urls=urls, quoted=quoted, reply=reply)))[0])


def test_what_is_a_tip():
    assert sig("Colección Houndstone ex en Amazon 25€", ["https://amazon.es/dp/B0FTBD97SZ"])["tip"]
    s = sig("Han puesto stock de las latas bugeadas del carrefour", ["https://www.carrefour.es/pokemon-mini-latas/R-1/p"])
    assert s["tip"] and s["score"] == 85 and "carrefour" in s["shops"]
    assert sig("UPC día disponible invitación", ["https://link.amazon/B0epkK8d8"])["shops"] == ["amazon"]
    eci = sig("ECI está sacando bastante stock en productos de Dominio Delta esta mañana, id comprobando su web")
    assert eci["tip"] and eci["score"] == 70
    assert sig("acaban de restockear todo esto otra vez",
               quoted=tweet("2", "Blister", urls=["https://www.elcorteingles.es/x/A1/"]))["tip"]
    # chatter is not a tip
    assert not sig("Primer donativo del carrefour confirmado")["tip"]
    assert not sig("a veces el stock es fake y luego no deja comprar")["tip"]
    assert not sig("mirad este vídeo", ["https://youtube.com/watch?v=1"])["tip"]
    assert not sig("@pokestock_es qué tal")["tip"]              # 'stock' inside a name is no stock word
    assert xfeed.parse_price("Colección en Amazon 25€") == 25.0 and xfeed.parse_price("a 14,99 €") == 14.99


def test_tipster_judge_skips_news_terms_but_keeps_excludes():
    watcher = {"name": "X", "config": {"info": {"x_tipsters": True, "must_terms": ["pokemon"], "exclude_terms": ["sorteo"]}}}
    p = xfeed.parse_timeline(timeline(tweet("1", "Colección Houndstone ex en Amazon 25€", urls=["https://amazon.es/dp/B0"])))[0]
    f = InfoFinding(url="https://amazon.es/dp/B0", title="t", snippet=xfeed.full_text(p), kind="x_post")
    f.x_signal = xfeed.tip_signal(p)
    g = InfoFinding(url="https://x.com/a/status/2", title="t", snippet="SORTEO de una caja", kind="x_post")
    g.x_signal = {"tip": True, "score": 85.0, "reasons": []}
    judge_rules([f, g], watcher)
    assert f.material and f.verdict == "confirmed" and f.reason.startswith("tip")
    assert g.verdict == "irrelevant" and not g.material


# ------------------------------------------------------------------ the sentry
class Reader:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, match):
        self.calls.append((url, match))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def test_sentry_baseline_then_only_new_and_fresh_posts():
    reader = Reader({"data": [timeline(tweet("1", "viejo"))], "logged_in": True},
                    {"data": [timeline(tweet("3", "Houndstone en Amazon 25€", urls=["https://amazon.es/dp/B0"]),
                                       tweet("2", "de hace un día", urls=["https://amazon.es/dp/B1"], ts=T0 - 86400),
                                       tweet("1", "viejo"))], "logged_in": True})
    s = InfoSentry(None, clock=lambda: T0, x_reader=reader)
    w = {"name": "X", "config": {"info": {"x_tipsters": True}}}
    row = {"id": "s1", "kind": "x", "value": "@stockhunter"}
    found, upd = s.check_source(row, w)
    assert found == [] and upd["x_session"] == "ok" and upd["last_hash"].startswith("x:")
    assert reader.calls[0][0] == "https://x.com/stockhunter" and "/UserOriginalsTimeline" in reader.calls[0][1]
    found, upd2 = s.check_source({**row, **upd}, w)
    assert [f.title for f in found] == ["@stockhunter en X: Houndstone en Amazon 25€"]
    assert found[0].url == "https://amazon.es/dp/B0" and "Publicación: https://x.com/stockhunter/status/3" in found[0].snippet
    assert sorted(upd2["last_text"].splitlines()) == ["1", "2", "3"]          # the old post is remembered, not alerted


def test_sentry_reports_a_missing_session():
    s = InfoSentry(None, clock=lambda: T0, x_reader=Reader({"data": [], "logged_in": False, "error": "no timeline data"}))
    found, upd = s.check_source({"id": "s", "kind": "x", "value": "@a"}, {"name": "X", "config": {}})
    assert found == [] and upd["x_session"] == "login" and "Conectar X" in upd["last_error"]
    found, upd = s.check_source({"id": "s", "kind": "x", "value": "https://x.com/home"}, {"name": "X", "config": {}})
    assert "not an X account" in upd["last_error"]


# ------------------------------------------------------------------ end to end: the fast lane raises the alert
def test_x_lane_alerts_once_with_the_shop_link(svc):
    reader = Reader({"data": [timeline(tweet("1", "hola"))], "logged_in": True})
    svc.info.x_reader = reader
    w = tool(svc, "watcher_create", name="Chivatazos de stock en X", mode="information", interval_min=60,
             config={"sources": [{"kind": "x", "value": "@stockhunter"}, {"kind": "page", "value": "https://example.com/n"}],
                     "info": {"x_tipsters": True}})
    wid = w["watcher"]["id"] if "watcher" in w else w["id"]
    assert svc.x.due(T0)
    first = tool(svc, "x_read")
    assert first["sources"] == 1 and first["events"] == 0 and first["session"] == "ok"
    reader.answers = [{"data": [timeline(tweet("2", "Han puesto stock de las latas del carrefour a 14,99 €",
                                               urls=["https://www.carrefour.es/latas/R-1/p"]),
                                         tweet("1", "hola"))], "logged_in": True}]
    second = tool(svc, "x_read")
    assert second["events"] == 1 and second["tips"] == 1
    ev = [e for e in svc.store.events(limit=20) if e["type"] == "INFO_CHANGE"][0]
    assert ev["severity"] == "high" and ev["status"] == "confirmed" and ev["url"] == "https://www.carrefour.es/latas/R-1/p"
    assert ev["price"] == 14.99 and "Publicación: https://x.com/stockhunter/status/2" in ev["summary"]
    assert svc.notifier.sent and svc.notifier.sent[-1][0]["severity"] == "high"
    assert tool(svc, "x_read")["events"] == 0                      # the same post never alerts twice
    st = tool(svc, "x_status")
    assert st["session"] == "ok" and st["sources"][0]["source"] == "@stockhunter"
    # the slow news sweep leaves X to the fast lane
    calls = len(reader.calls)
    svc.engine.run_information(wid)
    assert len(reader.calls) == calls


def test_x_login_without_a_screen_says_what_to_do(svc, monkeypatch):
    monkeypatch.setattr(xfeed, "find_display", lambda preferred=":5": "")
    out = tool(svc, "x_login")
    assert out["opened"] is False and out["needs_desktop"] and "Escritorio" in out["message"]


def test_find_display(monkeypatch, tmp_path):
    monkeypatch.setattr(xfeed.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(xfeed, "Path", lambda p: tmp_path)
    assert xfeed.find_display(":5") == ""
    (tmp_path / "X2").touch()
    assert xfeed.find_display(":5") == ":2"
    (tmp_path / "X5").touch()
    assert xfeed.find_display(":5") == ":5"
    monkeypatch.setenv("DISPLAY", ":9")
    assert xfeed.find_display(":5") == ":9"


def test_without_a_session_the_lane_stops_early_and_waits_longer(svc):
    reader = Reader({"data": [], "logged_in": False, "error": "no X session in the browser profile"})
    svc.info.x_reader = reader
    tool(svc, "watcher_create", name="X", mode="information", interval_min=60,
         config={"sources": [{"kind": "x", "value": "@a"}, {"kind": "x", "value": "@b"}], "info": {"x_tipsters": True}})
    out = tool(svc, "x_read")
    assert out["session"] == "login" and len(reader.calls) == 1
    assert float(svc.db.get_setting("x.next_run_ts")) >= T0 + xfeed.LOGIN_RETRY_S
    assert not svc.x.due(T0 + 300) and svc.x.due(T0 + xfeed.LOGIN_RETRY_S + 1)


def test_plain_window_opens_the_profile_without_automation(svc, monkeypatch, tmp_path):
    import threading
    import tantalus_hoard.fetch as fetch_mod
    from tantalus_hoard.hoard_link.web import browser as browser_mod

    class Worker:
        def __init__(self):
            self.calls = 0

        def call(self, fn, timeout=None):
            self.calls += 1

    class Rung:
        profile_dir = tmp_path / "profile"
        _gate = threading.Lock()
        _worker = Worker()

        def _release_in_worker(self):
            pass

    class Proc:
        def wait(self, timeout=None):
            return 0

    seen = {}
    monkeypatch.setattr(fetch_mod.sys, "platform", "linux")
    monkeypatch.setattr(browser_mod, "system_browsers", lambda: [])
    monkeypatch.setattr(browser_mod, "find_chromium", lambda: "/x/chromium-1248/chrome-linux/chrome")
    monkeypatch.setattr(svc.fetcher, "_rung", lambda: Rung())
    out = svc.fetcher.open_plain_window("https://x.com/i/flow/login", popen=lambda args, **kw: seen.setdefault("args", args) and Proc())
    args = seen["args"]
    assert out["plain"] and out["closed_by_user"] and args[0].endswith("/chrome")
    assert f"--user-data-dir={Rung.profile_dir}" in args and "--password-store=basic" in args and args[-1] == "https://x.com/i/flow/login"
    assert not any("automation" in a or "remote-debugging" in a for a in args) and "--no-sandbox" in args
    assert Rung._worker.calls == 1 and not Rung._gate.locked()
