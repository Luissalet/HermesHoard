"""The radar cycle is short (sealed stock sells out in minutes) and can be tuned from the settings."""

from types import SimpleNamespace

from tantalus_hoard.radar import core


def radar(settings, release_rows=0):
    r = core.Radar.__new__(core.Radar)
    r.db = SimpleNamespace(one=lambda sql, params: {"n": release_rows})
    r.get = lambda key, default=None: settings.get(key, default)
    r.clock = lambda: 1_800_000_000.0
    return r


def test_short_default_cycles():
    assert radar({}).interval_min() == core.INTERVAL_MIN <= 3
    assert radar({}, release_rows=1).interval_min() == core.RELEASE_DAY_INTERVAL_MIN <= 2
    assert core.PRODUCT_REFRESH_MIN <= 10 and core.HOT_PRODUCT_REFRESH_MIN <= 5


def test_settings_override_with_a_one_minute_floor():
    assert radar({"radar.interval_min": "6"}).interval_min() == 6
    assert radar({"radar.release_interval_min": "4"}, release_rows=1).interval_min() == 4
    assert radar({"radar.interval_min": "0.1"}).interval_min() == core.MIN_INTERVAL_MIN
    assert radar({"radar.interval_min": "abc"}).interval_min() == core.INTERVAL_MIN
