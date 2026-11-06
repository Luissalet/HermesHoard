"""A failure of this computer's network (DNS, no connection) is retried at about the normal cadence, not at the
escalating backoff earned by a shop's own refusals."""

from tantalus_hoard.engine import network_error


def test_network_failures_are_recognised():
    assert network_error("unresolvable host www.carrefour.es: [Errno 11001] getaddrinfo failed")
    assert network_error("browser error: Page.goto: net::ERR_FAILED at https://www.game.es/")
    assert network_error("browser error: net::ERR_NAME_NOT_RESOLVED")
    assert network_error("ConnectTimeout: timed out")


def test_shop_refusals_are_not_network_failures():
    for reason in ("robots", "cloudflare", "blocked", "http 403", "no product found", ""):
        assert not network_error(reason)
