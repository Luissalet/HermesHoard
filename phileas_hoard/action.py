"""What a parcel needs from you right now, if anything: pay customs, send documents, fix the address, rearrange a failed
delivery, collect it before the pickup point sends it back.

Pure functions over a shipment row (its status, the carrier's last status text, the pickup fields). Nothing is fetched and
nothing is paid or answered: the app points at the parcel and at the carrier's tracking page, the person acts there.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, Optional

from .model import AVAILABLE_FOR_PICKUP, CUSTOMS, EXCEPTION, FAILED_ATTEMPT, FINAL

CUSTOMS_PAYMENT, CUSTOMS_DOCUMENTS, ADDRESS, PICKUP, FAILED, PROBLEM = (
    "customs_payment", "customs_documents", "address", "pickup", "failed_attempt", "exception")
KINDS = (CUSTOMS_PAYMENT, CUSTOMS_DOCUMENTS, ADDRESS, PICKUP, FAILED, PROBLEM)
NOTIFY_KINDS = (CUSTOMS_PAYMENT, CUSTOMS_DOCUMENTS, ADDRESS)   # the ones a plain status change does not already announce

_CUSTOMS = re.compile(r"\b(?:aduana|aduanas|aduanero|despacho|customs|dua|import)\b")
_PAY = re.compile(r"\b(?:pago|pagar|abonar|abona|arancel(?:es)?|impuestos?|iva|tasas?|duties|duty|import (?:tax|vat|charges?)|"
                  r"customs (?:charges?|fees?)|payment (?:required|pending|due)|pending payment|pay (?:the )?(?:duties|charges|fees)|"
                  r"pendiente de pago|importe pendiente)\b")
_DOCS = re.compile(r"\b(?:documentacion|documentos?|factura comercial|commercial invoice|documents? (?:required|needed|missing)|"
                   r"informacion adicional|additional information (?:required|needed)|nif|dni|eori)\b")
_ADDRESS = re.compile(r"\b(?:direccion (?:incorrecta|incompleta|erronea|insuficiente)|address (?:incorrect|incomplete|invalid|insufficient)|"
                      r"incorrect address|destinatario desconocido|recipient unknown|consignee unknown|unable to locate)\b")
URGENT_PICKUP_DAYS = 2


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def action_required(s: dict[str, Any], today: Optional[date] = None) -> Optional[dict[str, Any]]:
    """``{"kind", "urgent", "deadline", "days_left", "evidence"}`` or ``None`` when the parcel needs nothing from you."""
    status = s.get("status") or ""
    if status in FINAL or s.get("archived") or s.get("history_only") or (s.get("extra") or {}).get("received_ts"):
        return None
    text = fold(" ".join(str(s.get(k) or "") for k in ("status_text", "last_location")))
    evidence = str(s.get("status_text") or "")[:200]
    today = today or date.today()
    customs_context = status == CUSTOMS or bool(_CUSTOMS.search(text))
    if customs_context and _PAY.search(text):
        return {"kind": CUSTOMS_PAYMENT, "urgent": True, "deadline": "", "days_left": None, "evidence": evidence}
    if customs_context and _DOCS.search(text):
        return {"kind": CUSTOMS_DOCUMENTS, "urgent": True, "deadline": "", "days_left": None, "evidence": evidence}
    if status in (EXCEPTION, FAILED_ATTEMPT) and _ADDRESS.search(text):
        return {"kind": ADDRESS, "urgent": True, "deadline": "", "days_left": None, "evidence": evidence}
    if status == AVAILABLE_FOR_PICKUP:
        deadline, left = str(s.get("pickup_deadline") or ""), None
        if deadline:
            try:
                left = (date.fromisoformat(deadline[:10]) - today).days
            except ValueError:
                deadline = ""
        return {"kind": PICKUP, "urgent": left is not None and left <= URGENT_PICKUP_DAYS, "deadline": deadline, "days_left": left,
                "evidence": " · ".join(x for x in (str(s.get("pickup_place") or ""), str(s.get("pickup_code") or "")) if x)}
    if status == FAILED_ATTEMPT:
        return {"kind": FAILED, "urgent": True, "deadline": "", "days_left": None, "evidence": evidence}
    if status == EXCEPTION:
        return {"kind": PROBLEM, "urgent": False, "deadline": "", "days_left": None, "evidence": evidence}
    return None


def sort_key(card: dict[str, Any]) -> tuple:
    a = card.get("action") or {}
    left = a.get("days_left")
    return (0 if a.get("urgent") else 1, KINDS.index(a["kind"]) if a.get("kind") in KINDS else 9, left if left is not None else 99)
