from fastapi.testclient import TestClient

from phileas_hoard.config import Config
from phileas_hoard.main import create_app


def test_ui_merge_keeps_identity_conflicts_and_moves_links_without_touching_other_shipments(tmp_path, monkeypatch):
    monkeypatch.setenv("HOARD_EVENTS", "0")
    monkeypatch.setenv("HOARD_HUB_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("HOARD_FAUSTUS_URL", "http://127.0.0.1:9")
    config = Config(data_dir=tmp_path, data_dir_configured=True, offline=True, scheduler=False, browser=False)
    with TestClient(create_app(config), base_url="http://127.0.0.1:5199") as client:
        svc = client.app.state.services
        keep = svc.store.create_shipment(label="Conservar", tracking_number="KEEP123", notes="Nota propia", status="ordered")
        drop = svc.store.create_shipment(label="Duplicado", tracking_number="DROP456", carrier="correos", tracking_url="https://carrier.invalid/qa",
            order_ref="pedido-qa", sub_ref="parte-2", item='Café "QA"', merchant_url="https://shop.invalid/qa", notes="No concatenar", status="delivered")
        other = svc.store.create_shipment(label="Intacto", archived=True)
        for row in (keep, drop):
            svc.store.add_event(row["id"], ts=1, status="ordered", description="Evento común", key="shared")
            svc.store.add_event(row["id"], ts=2, status="in_transit", description=row["label"], key=row["id"])
            svc.store.save_mail({"message_id": row["id"], "ts": 1, "subject": row["label"]}, kind="shipping", score=100, facts={}, shipment_id=row["id"], state="linked")
            svc.store.add_notification(shipment_id=row["id"], type_="fixture", severity="low", title=row["label"], body="No enviado", results=[], dedupe=row["id"])
        before = svc.store.shipments(archived=None, history_only=None)
        request = {"name": "shipment_merge", "arguments": {"keep": keep["id"], "drop": drop["id"]}}
        assert client.post("/api/ui/call", json=request).status_code == 400
        assert svc.store.shipments(archived=None, history_only=None) == before
        request["arguments"]["confirm"] = True
        response = client.post("/api/ui/call", json=request)
        assert response.status_code == 200
        assert response.json()["shipment"]["id"] == keep["id"]
        saved = svc.store.shipment(keep["id"])
        assert saved["tracking_number"] == "KEEP123"
        assert (saved["label"], saved["notes"], saved["status"]) == ("Conservar", "Nota propia", "ordered")
        for field in ("carrier", "tracking_url", "order_ref", "sub_ref", "item", "merchant_url"):
            assert saved[field] == drop[field]
        assert svc.store.shipment(other["id"]) == other
        assert svc.db.one("SELECT id FROM shipments WHERE id=?", (drop["id"],)) is None
        assert len(svc.store.events(keep["id"])) == 3
        assert len(svc.db.query("SELECT * FROM shipment_mails WHERE shipment_id=?", (keep["id"],))) == 2
        assert len(svc.db.query("SELECT * FROM mails WHERE shipment_id=?", (keep["id"],))) == 2
        assert len(svc.db.query("SELECT * FROM notifications WHERE shipment_id=?", (keep["id"],))) == 2
