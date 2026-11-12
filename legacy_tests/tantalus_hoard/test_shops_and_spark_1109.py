"""Night of 2026-11-08/09 on Spark3: a Juguetilandia restock never alerted (unknown host -> confidence 40), Carrefour pages
tried to start Chrome every few minutes, toasts "failed" on Linux, and two fake shops from paid ads had to stay out."""

import pytest

from tantalus_hoard import engine as eng
from tantalus_hoard import rules
from tantalus_hoard.agent_tools import _refuse_scam, added_source_level
from tantalus_hoard.discovery import _scam
from tantalus_hoard.errors import TantalusError
from tantalus_hoard.extract.sites import is_scam_host, source_level_for_host, window_ok
from tantalus_hoard.model import IN_STOCK, Offer
from tantalus_hoard.notify import Notifier

JUGUETILANDIA = "https://www.juguetilandia.com/producto/pokemon-tcg-celebracion-30-aniversario-caja-coleccion-premium-ditto-138600.htm"
CARREFOUR = "https://www.carrefour.es/pokemon-30th-aniversario-mini-latas-ingles-6-anos-unboxing/VC4A-34535252/p"


def test_juguetilandia_restock_from_microdata_reaches_the_alert_threshold():
    level = source_level_for_host(JUGUETILANDIA)
    assert level == 1
    offer = Offer(availability=IN_STOCK, price=74.99, currency="EUR", method="microdata", url=JUGUETILANDIA)
    conf = rules.score_confidence(offer, source_level=level, tier="http", target_store_ids=[])
    assert conf.score >= rules.ALERT_THRESHOLD          # 45 own page + 30 structured state + 10 coherent = 85 (was 40)


def test_reviewed_shops_have_profiles_and_cloudflare_ones_read_in_a_window():
    for url in ("https://www.tiendacpu.com/es/tcg/14041-pokemon-tcg-paldea-adventure-chest-es",
                "https://www.tradeinn.com/kidinn/es/x/142851518/p", "https://www.hipergol.com/", "https://herofreaks.com/comprar/x/",
                "https://alfriki.com/products/lata", "https://collectorage.com/shop/cartas-tcg/pokemon/"):
        assert source_level_for_host(url) == 1, url
    assert window_ok("https://www.hipergol.com/") and window_ok("https://herofreaks.com/comprar/x/")
    assert not window_ok("https://www.tiendacpu.com/es/tcg/14041-x")


def test_targets_the_person_adds_on_an_unknown_shop_count_as_its_own_page():
    assert added_source_level("https://tienda-desconocida.example/producto/123") == 1
    assert added_source_level("https://www.ebay.es/itm/123") == 4            # a known marketplace keeps its level
    assert added_source_level(JUGUETILANDIA) == 1


def test_fake_shops_are_refused_everywhere():
    for url in ("https://managermodf.shop/products/charizard", "https://xeagdyat.shop/products/151", "https://shop.xeagdyat.shop/x"):
        assert is_scam_host(url) and _scam(url)
        with pytest.raises(TantalusError):
            _refuse_scam(url)
    assert not is_scam_host("https://www.hipergol.com/")
    _refuse_scam("https://www.hipergol.com/")


class FakeStore:
    def __init__(self):
        self.updates = []

    def update_target(self, target_id, **fields):
        self.updates.append((target_id, fields))


class FakeEngine:
    def __init__(self):
        self.store = FakeStore()
        self.clock = lambda: 1000.0

    def fetch_target(self, target, watcher):
        raise AssertionError("fetched")


def test_window_only_shops_pause_off_windows_and_clear_the_browser_errors(monkeypatch):
    monkeypatch.setattr(eng, "WINDOWS_HOST", False)
    fake = FakeEngine()
    target = {"id": "t1", "url": CARREFOUR, "fetch_tier": "auto", "status": "error", "fail_count": 152}
    res = eng.Engine._check(fake, target, {"id": "w1", "config": {}}, revalidation=False)
    assert res["paused"] is True and res["events"] == []
    (tid, fields), = fake.store.updates
    assert fields["status"] == "active" and fields["fail_count"] == 0 and "Windows" in fields["last_error"]
    assert fields["next_check_ts"] == 1000.0 + eng.PAUSED_RECHECK_S


def test_window_only_shops_still_read_on_windows_and_plain_shops_read_on_the_spark(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setattr(eng, "WINDOWS_HOST", True)
    with pytest.raises(AssertionError, match="fetched"):
        eng.Engine._check(fake, {"id": "t2", "url": CARREFOUR, "fetch_tier": "auto"}, {"id": "w1", "config": {}}, revalidation=False)
    monkeypatch.setattr(eng, "WINDOWS_HOST", False)
    with pytest.raises(AssertionError, match="fetched"):
        eng.Engine._check(fake, {"id": "t3", "url": JUGUETILANDIA, "fetch_tier": "auto"}, {"id": "w1", "config": {}}, revalidation=False)
    with pytest.raises(AssertionError, match="fetched"):      # the person forced plain http on a window shop: respect it
        eng.Engine._check(fake, {"id": "t4", "url": CARREFOUR, "fetch_tier": "http"}, {"id": "w1", "config": {}}, revalidation=False)


class Cfg:
    def secret(self, name):
        return ""


def test_toast_off_windows_is_skipped_not_failed():
    values = {"notify.via": "own", "notify.email.faustus_dir": "/nonexistent/faustus"}
    n = Notifier(Cfg(), lambda key, default=None: values.get(key, default), clock=lambda: 42.0, platform="linux")
    event = {"id": "e1", "type": "RESTOCK", "severity": "high", "title": "x", "summary": "y", "url": ""}
    (toast,) = n.send(event, ["toast"])
    assert toast["skipped"] is True and toast["error"] == "not windows"


def test_a_short_rate_limit_does_not_cost_half_an_hour(tmp_path):
    from tantalus_hoard.db import Database
    from tantalus_hoard.extract.sites import profile_for_host, rate_limit_hold_s
    from tantalus_hoard.fetch.hoststate import SqlHostState

    assert profile_for_host("https://www.collectowny.com/products/x").name == "Collectowny"
    assert profile_for_host("cartadia.com").name == "Cartadia" and rate_limit_hold_s("cartadia.com") == 120.0
    assert rate_limit_hold_s("game.es") == 0.0
    state = SqlHostState(Database(tmp_path / "t.db"), short_hold=rate_limit_hold_s, clock=lambda: 1000.0)
    state.update("collectowny.com", blocked_until_ts=1000.0 + 1800, block_reason="http_429")
    assert state.get("collectowny.com")["blocked_until_ts"] == 1120.0
    state.update("game.es", blocked_until_ts=1000.0 + 1800, block_reason="http_429")
    assert state.get("game.es")["blocked_until_ts"] == 2800.0
    state.update("cartadia.com", blocked_until_ts=1000.0 + 1800, block_reason="cloudflare")
    assert state.get("cartadia.com")["blocked_until_ts"] == 2800.0
