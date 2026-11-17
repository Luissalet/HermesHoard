"""Faustus's look at a window follows Faustus to the Spark when the Hub's "Run on" moved it there."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tantalus_hoard import faustus_eye
from tantalus_hoard.hoard_link import where


def _serve(routes: dict[str, dict]):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = routes.get(self.path)
            self.send_response(200 if body is not None else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body or {}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture(autouse=True)
def _fresh():
    where.forget()
    yield
    where.forget()


def test_the_look_goes_to_the_spark_when_this_pc_has_no_faustus(monkeypatch):
    spark, spark_url = _serve({"/api/health": {"status": "healthy"}})
    hub, hub_url = _serve({"/api/placement": {"location": "sparks", "job": {"running": False}, "urls": {"faustus": spark_url}}})
    monkeypatch.setattr(faustus_eye, "DEFAULT_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("HOARD_HUB_URL", hub_url)
    try:
        assert faustus_eye.faustus_origin() == spark_url
    finally:
        spark.shutdown()
        hub.shutdown()


def test_the_look_stays_on_this_pc_when_the_hub_is_silent(monkeypatch):
    monkeypatch.setattr(faustus_eye, "DEFAULT_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("HOARD_HUB_URL", "http://127.0.0.1:2")
    assert faustus_eye.faustus_origin() == "http://127.0.0.1:1"
