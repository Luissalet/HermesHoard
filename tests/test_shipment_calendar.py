from datetime import date, datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from phileas_hoard.agent_tools import call_tool
from phileas_hoard.config import Config
from phileas_hoard.hoard_link.ics import parse_ics
from phileas_hoard.main import create_app
from phileas_hoard.services import Services


def test_calendar_distinguishes_estimates_deadlines_and_undated_without_mutation(tmp_path):
    now = datetime(2026, 10, 23, 12, tzinfo=timezone.utc).timestamp()
    config = Config(data_dir=tmp_path, offline=True, scheduler=False, browser=False)
    svc = Services(config, clock_fn=lambda: now)
    try:
        estimated = svc.store.create_shipment(label="Entrega; ficticia, energía", status="in_transit", eta_likely="2026-10-26", eta_from="2026-10-25", eta_to="2026-10-28", tracking_url="https://carrier.example/test")
        pickup = svc.store.create_shipment(label="Recogida ficticia", status="available_for_pickup", pickup_deadline="2026-10-27", pickup_place="Punto ficticio", pickup_code="PRIVATE-CODE")
        svc.store.create_shipment(label="Sin fecha", status="ordered")
        svc.store.create_shipment(label="Finalizado", status="delivered", eta_likely="2026-10-26")
        svc.store.create_shipment(label="Reparto hoy", status="out_for_delivery", eta_likely="2026-10-29")
        before = svc.store.shipments(archived=None, history_only=None)
        result = call_tool(svc, "shipments_ics", {"date_from":"2026-10-23", "date_to":"2026-10-31"})
        assert result["count"] == 3 and result["undated"] == 1
        events = {event["shipment_id"]:event for event in result["events"]}
        assert events[estimated["id"]]["status"] == "tentative"
        assert events[pickup["id"]]["status"] == "confirmed"
        assert "PRIVATE-CODE" not in result["ics"]
        parsed = parse_ics(result["ics"])
        assert len(parsed) == 3
        assert "DTSTART;VALUE=DATE:20261026\r\nDTEND;VALUE=DATE:20261027" in result["ics"]
        assert "STATUS:TENTATIVE" in result["ics"] and "STATUS:CONFIRMED" in result["ics"]
        repeated = call_tool(svc, "shipments_ics", {"date_from":"2026-10-23", "date_to":"2026-10-31"})
        assert [e["uid"] for e in repeated["events"]] == [e["uid"] for e in result["events"]]
        assert svc.store.shipments(archived=None, history_only=None) == before
    finally:
        svc.stop()


def test_download_endpoint_is_calendar_not_shipment_detail_and_preserves_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("HOARD_HUB_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("HOARD_FAUSTUS_URL", "http://127.0.0.1:1")
    config = Config(data_dir=tmp_path, offline=True, scheduler=False, browser=False)
    with TestClient(create_app(config), base_url="http://127.0.0.1:5199") as client:
        svc = client.app.state.services
        svc.store.create_shipment(label="Fecha futura", status="in_transit", eta_likely="2026-11-03")
        response = client.get("/api/shipments/ics?date_from=2026-11-01&date_to=2026-11-30")
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/calendar")
        assert response.headers["content-disposition"] == 'attachment; filename="hermes-deliveries.ics"'
        assert "DTSTART;VALUE=DATE:20261103" in response.text
        assert client.get("/api/shipments/ics?date_from=2026-11-30&date_to=2026-11-01").status_code == 400
