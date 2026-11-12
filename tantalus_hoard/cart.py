"""Cart runner: the user's own browser puts a watched product in the basket the moment it can be bought.

Hermes reads shops from a server (often a Spark), where the user's shop session does not exist. The basket lives in the
browser the user is signed in with, so the work is split: a small browser extension (``browser/cart-runner``) keeps the
product page open, adds the product to the basket when the buy button comes alive and walks the checkout up to the
page with the pay button; this module keeps the list of products to run ("jobs"), hears the extension's heartbeat and
turns each stage it reports into an alert on every channel. Paying is always the user's.

Jobs live in the settings table (``cart.jobs``, JSON) and the extension's key in ``cart.key``: no schema change.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from .errors import TantalusError
from .model import CART_READY, NEEDS_HUMAN

# shop host -> what the extension knows how to drive
SHOPS = {"elcorteingles.es": "El Corte Inglés"}
# stage -> (severity, title prefix, summary)
STAGES: dict[str, tuple[str, str, str]] = {
    "added": ("high", "En la cesta", "Añadido a tu cesta. El navegador está pasando al pago."),
    "pay": ("high", "Paga ya", "El pago está abierto en tu navegador con la dirección y la tarjeta puestas: revisa y pulsa pagar."),
    "password": ("high", "Pon la contraseña", "Está en tu cesta, pero la tienda pide la contraseña antes del pago. Entra en el navegador y ponla."),
    "delivery": ("high", "Elige la entrega y paga", "Está en tu cesta. La tienda pide elegir la entrega antes del pago."),
    "lost": ("medium", "Se agotó antes del pago", "Se añadió a la cesta pero ya no estaba al llegar al pago. Sigo vigilando."),
    "blocked": ("medium", "La tienda ha bloqueado la pestaña", "La página de la tienda responde con un bloqueo. Espero unos minutos y vuelvo a probar."),
    "signed_out": ("high", "Sesión cerrada en la tienda", "La tienda ha cerrado tu sesión: sin ella no se puede añadir a la cesta. Inicia sesión en el navegador."),
}
ALERT_STAGES = frozenset(STAGES)
STALE_AFTER_S = 300.0         # no heartbeat for this long = the browser is not watching
STALE_REPEAT_S = 3 * 3600.0   # one "not watching" alert every three hours at most
REPEAT_S = 600.0              # the same stage of the same job alerts once per ten minutes
MIN_INTERVAL_S, MAX_INTERVAL_S, DEFAULT_INTERVAL_S = 8, 600, 15


def shop_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return next((shop for shop in SHOPS if host == shop or host.endswith("." + shop)), "")


def product_ref(url: str) -> str:
    """The shop's product number in a product URL (El Corte Inglés: ``/juguetes/A202035453-nombre/`` -> ``A202035453``)."""
    m = re.search(r"/(A\d{6,})(?:-|/|$)", urlsplit(url).path)
    return m.group(1) if m else ""


class CartRunner:
    def __init__(self, store: Any, dispatch: Callable[[dict[str, Any]], Any], get: Callable[[str, Optional[str]], Optional[str]],
                 put: Callable[[str, str], None], *, clock: Callable[[], float] = time.time):
        self.store, self.dispatch, self.get, self.put, self.clock = store, dispatch, get, put, clock

    # ------------------------------------------------------------------ storage
    def key(self) -> str:
        key = self.get("cart.key", "") or ""
        if not key:
            key = secrets.token_urlsafe(24)
            self.put("cart.key", key)
        return key

    def check_key(self, given: str) -> bool:
        return bool(given) and secrets.compare_digest(str(given), self.key())

    def _load(self) -> list[dict[str, Any]]:
        try:
            jobs = json.loads(self.get("cart.jobs", "[]") or "[]")
        except ValueError:
            jobs = []
        return [j for j in jobs if isinstance(j, dict) and j.get("id")]

    def _save(self, jobs: list[dict[str, Any]]) -> None:
        self.put("cart.jobs", json.dumps(jobs, ensure_ascii=False))

    def _job(self, jobs: list[dict[str, Any]], job_id: str) -> dict[str, Any]:
        job = next((j for j in jobs if j["id"] == job_id), None)
        if job is None:
            raise TantalusError("not_found", f"No cart job {job_id}.", "cart_jobs lists them.")
        return job

    # ------------------------------------------------------------------ views
    def _view(self, job: dict[str, Any], now: float) -> dict[str, Any]:
        beat = job.get("beat_at")
        watching = bool(job.get("enabled")) and beat is not None and now - beat <= STALE_AFTER_S
        return {**job, "shop_name": SHOPS.get(job.get("shop", ""), job.get("shop", "")), "watching": watching,
                "beat_age_s": None if beat is None else int(now - beat)}

    def jobs(self) -> list[dict[str, Any]]:
        now = self.clock()
        return [self._view(j, now) for j in self._load()]

    def for_extension(self) -> dict[str, Any]:
        """What the extension needs, and nothing else."""
        return {"jobs": [{"id": j["id"], "url": j["url"], "ref": j.get("ref", ""), "shop": j.get("shop", ""), "name": j.get("name", ""),
                          "enabled": bool(j.get("enabled")), "interval_s": j.get("interval_s", DEFAULT_INTERVAL_S),
                          "delivery": j.get("delivery", "home"), "armed_at": j.get("armed_at", 0)} for j in self._load()],
                "now": self.clock()}

    # ------------------------------------------------------------------ edits
    def add(self, url: str, *, name: str = "", interval_s: int = DEFAULT_INTERVAL_S, delivery: str = "home") -> dict[str, Any]:
        url = url.strip()
        shop = shop_of(url)
        if not shop:
            raise TantalusError("invalid", "This shop has no cart runner yet.", f"Supported: {', '.join(SHOPS.values())}.")
        ref = product_ref(url)
        if not ref:
            raise TantalusError("invalid", "This is not a product page.", "Paste the page of the product itself.")
        jobs = self._load()
        existing = next((j for j in jobs if j.get("shop") == shop and j.get("ref") == ref), None)
        now = self.clock()
        if existing is not None:
            existing.update(enabled=True, armed_at=now, stage="", stage_at=None)
            self._save(jobs)
            return self._view(existing, now)
        job = {"id": "c_" + secrets.token_hex(5), "url": url, "ref": ref, "shop": shop, "name": name.strip() or ref, "enabled": True,
               "interval_s": max(MIN_INTERVAL_S, min(MAX_INTERVAL_S, int(interval_s or DEFAULT_INTERVAL_S))),
               "delivery": delivery if delivery in ("home", "any") else "home", "created_at": now, "armed_at": now,
               "beat_at": None, "state": "", "checks": 0, "stage": "", "stage_at": None, "detail": ""}
        jobs.append(job)
        self._save(jobs)
        return self._view(job, now)

    def update(self, job_id: str, *, enabled: Optional[bool] = None, interval_s: Optional[int] = None, rearm: bool = False,
               name: Optional[str] = None, delivery: Optional[str] = None) -> dict[str, Any]:
        jobs = self._load()
        job = self._job(jobs, job_id)
        if enabled is not None:
            job["enabled"] = bool(enabled)
        if interval_s is not None:
            job["interval_s"] = max(MIN_INTERVAL_S, min(MAX_INTERVAL_S, int(interval_s)))
        if name:
            job["name"] = name.strip()
        if delivery in ("home", "any"):
            job["delivery"] = delivery
        if rearm:
            job.update(armed_at=self.clock(), stage="", stage_at=None, detail="", enabled=True)
        self._save(jobs)
        return self._view(job, self.clock())

    def remove(self, job_id: str) -> dict[str, Any]:
        jobs = self._load()
        job = self._job(jobs, job_id)
        self._save([j for j in jobs if j["id"] != job_id])
        return {"removed": job["id"], "name": job.get("name", "")}

    # ------------------------------------------------------------------ the extension speaks
    def beat(self, job_id: str, *, state: str = "", name: str = "", price: Any = None) -> dict[str, Any]:
        jobs = self._load()
        job = self._job(jobs, job_id)
        job.update(beat_at=self.clock(), state=str(state)[:40], checks=int(job.get("checks") or 0) + 1)
        if name and job.get("name") in ("", job.get("ref")):
            job["name"] = str(name).strip()[:160]
        if isinstance(price, (int, float)):
            job["price"] = float(price)
        self._save(jobs)
        return {"ok": True}

    def report(self, job_id: str, stage: str, detail: str = "") -> dict[str, Any]:
        if stage not in ALERT_STAGES:
            raise TantalusError("invalid", f"Unknown stage {stage}.", f"Known: {', '.join(sorted(ALERT_STAGES))}.")
        jobs = self._load()
        job = self._job(jobs, job_id)
        now = self.clock()
        repeated = job.get("stage") == stage and job.get("stage_at") and now - job["stage_at"] < REPEAT_S
        job.update(stage=stage, stage_at=now, detail=str(detail)[:300], beat_at=now)
        self._save(jobs)
        if repeated:
            return {"ok": True, "alerted": False}
        severity, head, summary = STAGES[stage]
        event = self.store.add_event({
            "type": CART_READY, "severity": severity, "status": "confirmed", "new_state": stage, "price": job.get("price"),
            "currency": "EUR" if job.get("price") is not None else "", "confidence": 100, "url": job["url"],
            "dedupe_key": f"cart:{job['id']}:{stage}:{int(now // REPEAT_S)}", "title": f"{head}: {job.get('name') or job['ref']}",
            "summary": summary + (f" ({detail.strip()[:200]})" if detail.strip() else ""),
            "data": {"source": "cart_runner", "job_id": job["id"], "stage": stage, "shop": job.get("shop", "")}})
        results = self.dispatch(event)
        return {"ok": True, "alerted": True, "event_id": event["id"], "channels": results}

    # ------------------------------------------------------------------ nobody is watching
    def due(self, now: float) -> bool:
        return any(self._stale(j, now) for j in self._load())

    @staticmethod
    def _stale(job: dict[str, Any], now: float) -> bool:
        if not job.get("enabled") or job.get("stage") in ("pay", "password", "delivery"):
            return False
        since = job.get("beat_at") or job.get("armed_at") or now
        last_alert = job.get("stale_alert_at")
        return now - since > STALE_AFTER_S and (last_alert is None or now - last_alert > STALE_REPEAT_S)

    def run_job(self, _ref: str = "all") -> dict[str, Any]:
        now = self.clock()
        jobs = self._load()
        alerted = []
        for job in jobs:
            if not self._stale(job, now):
                continue
            job["stale_alert_at"] = now
            event = self.store.add_event({
                "type": NEEDS_HUMAN, "severity": "high", "status": "confirmed", "url": job["url"],
                "dedupe_key": f"cart:{job['id']}:stale:{int(now // STALE_REPEAT_S)}",
                "title": f"Nadie vigila la cesta: {job.get('name') or job['ref']}",
                "summary": "El navegador no da señales desde hace más de 5 minutos. Abre el navegador con la extensión de la cesta.",
                "data": {"source": "cart_runner", "job_id": job["id"], "stage": "stale"}})
            self.dispatch(event)
            alerted.append(job["id"])
        if alerted:
            self._save(jobs)
        return {"stale": alerted}
