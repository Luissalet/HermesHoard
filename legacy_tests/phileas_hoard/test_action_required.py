"""What a parcel needs from you (customs to pay, documents, address, failed delivery, pickup deadline) and how customs moves
the estimate."""

from __future__ import annotations

from datetime import date, datetime

from phileas_hoard import eta
from phileas_hoard.action import action_required, sort_key
from phileas_hoard.bizdays import Calendar

TODAY = date(2026, 11, 10)          # a Tuesday


def ts(d: date, hour: int = 12) -> float:
    return datetime(d.year, d.month, d.day, hour).timestamp()


def test_customs_payment_documents_and_address_are_actions():
    pay = action_required({"status": "customs", "status_text": "Envío retenido en aduanas: pendiente de pago de aranceles e IVA"}, TODAY)
    assert pay["kind"] == "customs_payment" and pay["urgent"]
    docs = action_required({"status": "customs", "status_text": "Customs clearance: commercial invoice required"}, TODAY)
    assert docs["kind"] == "customs_documents"
    addr = action_required({"status": "exception", "status_text": "Dirección incorrecta, contacte con nosotros"}, TODAY)
    assert addr["kind"] == "address"
    # customs with nothing asked of you is not an action
    assert action_required({"status": "customs", "status_text": "En proceso de despacho de aduanas"}, TODAY) is None
    assert action_required({"status": "in_transit", "status_text": "En tránsito"}, TODAY) is None
    assert action_required({"status": "delivered", "status_text": "pendiente de pago"}, TODAY) is None


def test_pickup_deadline_and_failed_delivery():
    soon = action_required({"status": "available_for_pickup", "pickup_deadline": "2026-11-11", "pickup_place": "Locker Sol"}, TODAY)
    assert soon["kind"] == "pickup" and soon["urgent"] and soon["days_left"] == 1 and "Locker Sol" in soon["evidence"]
    later = action_required({"status": "available_for_pickup", "pickup_deadline": "2026-11-20"}, TODAY)
    assert not later["urgent"]
    failed = action_required({"status": "failed_attempt", "status_text": "Ausente"}, TODAY)
    assert failed["kind"] == "failed_attempt" and failed["urgent"]
    cards = [{"action": later}, {"action": failed}, {"action": soon}]
    assert [c["action"] for c in sorted(cards, key=sort_key)] == [soon, failed, later]      # urgent first, then by kind


def test_customs_moves_the_estimate():
    cal = Calendar("ES-MD")
    held = {"id": "s", "status": "customs", "carrier": "dhl", "origin_country": "CN", "status_ts": ts(date(2026, 11, 9)),
            "status_text": "Customs clearance in progress", "carrier_eta_from": "2026-11-05", "shipped_ts": ts(date(2026, 11, 2))}
    e = eta.estimate(held, [], cal, TODAY)
    used = next(b for b in e.basis if b.used)
    assert used.source == "customs" and e.eta_from >= "2026-11-11" and e.late
    pay = {**held, "status_text": "Customs: duties and taxes payment required"}
    e2 = eta.estimate(pay, [], cal, TODAY)
    assert next(b for b in e2.basis if b.used).source == "customs" and "pago" in next(b for b in e2.basis if b.used).text
    assert e2.eta_from > TODAY.isoformat()


def test_dashboard_lists_actions_first_and_the_customs_text_notifies_once(svc):
    now = svc.clock()
    sid = svc.store.create_shipment(tracking_number="JD014600006281234567", carrier="dhl", label="Placa base", status="in_transit",
                                    status_ts=now - 86400, origin_country="CN")["id"]
    other = svc.store.create_shipment(tracking_number="1Z999AA10123456784", carrier="ups", label="Teclado", status="in_transit",
                                      status_ts=now - 86400)["id"]
    svc.engine.apply_status(sid, "customs", now - 3600, source="carrier", text="Clearance event in progress")
    assert not [n for n in svc.store.notifications(limit=20) if "Aduanas" in n["title"]]   # customs alone asks nothing of you
    svc.engine.apply_status(sid, "customs", now - 60, source="carrier", text="Retenido en aduanas: pendiente de pago de aranceles")
    dash = svc.dashboard()
    assert [c["id"] for c in dash["action_required"]] == [sid] and dash["action_required"][0]["action"]["kind"] == "customs_payment"
    assert sid in [c["id"] for c in dash["attention"]] and other not in [c["id"] for c in dash["attention"]]
    assert sum("Aduanas" in n["title"] for n in svc.store.notifications(limit=20)) == 1
    svc.engine.apply_status(sid, "customs", now, source="carrier", text="Retenido en aduanas: pendiente de pago de aranceles e IVA")
    assert sum("Aduanas" in n["title"] for n in svc.store.notifications(limit=20)) == 1


def test_a_notice_without_a_known_carrier_still_reads_well(svc):
    s = {"id": "s", "label": "Placa base", "carrier": "", "status": "in_transit"}
    assert svc.engine._t("scanned_title", s) == "El transportista ya lo tiene: Placa base"
    assert svc.engine._t("stale_body", s, days=4) == "4 días de reparto sin movimiento."
