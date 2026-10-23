"""Downloadable shipment dates from stored facts, without carrier or mail requests."""
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from .errors import PhileasError
from .hoard_link.ics import build_ics
from .model import ACTIVE, AVAILABLE_FOR_PICKUP, OUT_FOR_DELIVERY
from .numbers import carrier_name


def _day(value):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def calendar(svc, date_from=None, date_to=None):
    today = datetime.fromtimestamp(svc.clock()).date()
    date_from = date_from or today
    date_to = date_to or date_from + timedelta(days=90)
    if date_to < date_from:
        raise PhileasError("invalid", "La fecha final debe ser igual o posterior a la inicial.")
    es = svc.setting("ui.language") != "en"
    shipments = svc.store.shipments(archived=False, history_only=False, active=True, limit=2000)
    events, undated, outside = [], 0, 0
    for shipment in shipments:
        status = shipment.get("status")
        if status not in ACTIVE:
            continue
        pickup = status == AVAILABLE_FOR_PICKUP
        day = _day(shipment.get("pickup_deadline")) if pickup else today if status == OUT_FOR_DELIVERY else _day(shipment.get("eta_likely"))
        if day is None:
            undated += 1
            continue
        if not date_from <= day <= date_to:
            outside += 1
            continue
        name = shipment.get("label") or shipment.get("item") or shipment.get("merchant") or shipment.get("tracking_number") or shipment["id"]
        kind = "pickup_deadline" if pickup else "delivery_estimate"
        prefix = ("Fecha límite de recogida: " if es else "Pickup deadline: ") if pickup else ("Entrega estimada: " if es else "Estimated delivery: ")
        note = ("Plazo de recogida registrado." if es else "Recorded pickup deadline.") if pickup else ("Fecha estimada; no confirma la entrega." if es else "Estimated date; delivery is not confirmed.")
        description = [note, carrier_name(shipment.get("carrier") or "")]
        if not pickup and shipment.get("eta_from") and shipment.get("eta_to"):
            description.append(f"{'Intervalo estimado' if es else 'Estimated range'}: {shipment['eta_from']} → {shipment['eta_to']}")
        if shipment.get("tracking_url"):
            description.append(shipment["tracking_url"])
        event = {"uid": f"{shipment['id']}-{kind}@hermes-hoard", "shipment_id": shipment["id"],
                 "title": prefix + name, "start": day.isoformat(), "all_day": True, "kind": kind,
                 "status": "confirmed" if pickup else "tentative", "transp": "transparent",
                 "description": "\n".join(part for part in description if part),
                 "url": f"http://127.0.0.1:{svc.config.port}/shipments/#/envio/{quote(shipment['id'])}"}
        if pickup and shipment.get("pickup_place"):
            event["location"] = shipment["pickup_place"]
        events.append(event)
    events.sort(key=lambda event: (event["start"], event["title"]))
    name = "Entregas y recogidas" if es else "Deliveries and pickups"
    return {"filename": "hermes-deliveries.ics", "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
            "events": events, "count": len(events), "undated": undated, "outside_range": outside,
            "selection_limit": 2000, "at_selection_limit": len(shipments) == 2000,
            "download_url": "/shipments/api/shipments/ics?" + urlencode({"date_from": date_from.isoformat(), "date_to": date_to.isoformat()}),
            "ics": build_ics(events, name=name, prodid="-//Hermes Hoard//Shipments//EN", now=datetime.fromtimestamp(svc.clock(), timezone.utc))}
