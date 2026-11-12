"""Routes the cart-runner browser extension calls. Every one takes the extension's key in ``X-Hermes-Cart-Key``.

The extension lives in the user's browser, on another origin: Hermes's front door lets these paths through the
origin rules when the key header is present (see ``hermes_hoard.app``), and the key is checked here.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import services

router = APIRouter(prefix="/api/cart/x")


def _runner(request: Request):
    svc = services(request)
    if not svc.cart.check_key(request.headers.get("x-hermes-cart-key", "")):
        raise HTTPException(401, "Invalid cart key")
    return svc.cart


class Beat(BaseModel):
    job_id: str = Field(..., max_length=40)
    state: str = Field("", max_length=40)
    name: str = Field("", max_length=200)
    price: Optional[float] = None


class Report(BaseModel):
    job_id: str = Field(..., max_length=40)
    stage: str = Field(..., max_length=20)
    detail: str = Field("", max_length=300)


@router.get("/jobs")
def jobs(request: Request) -> dict[str, Any]:
    return _runner(request).for_extension()


@router.post("/beat")
def beat(request: Request, body: Beat) -> dict[str, Any]:
    return _runner(request).beat(body.job_id, state=body.state, name=body.name, price=body.price)


@router.post("/report")
def report(request: Request, body: Report) -> dict[str, Any]:
    return _runner(request).report(body.job_id, body.stage, body.detail)
