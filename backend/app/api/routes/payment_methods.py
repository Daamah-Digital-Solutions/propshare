"""Saved payment-method routes (Group 3) — PCI-safe tokenized cards.

All endpoints are the caller's own vault (PrincipalDep). Raw card data never reaches the
server: the SPA tokenizes via the SetupIntent; we store only tokens + safe metadata. Stripe
calls 503 cleanly when unconfigured.

- GET    /wallet/payment-methods               list the caller's saved methods.
- POST   /wallet/payment-methods/setup-intent  start tokenization (SetupIntent client secret).
- POST   /wallet/payment-methods               save a tokenized method {payment_method_id}.
- DELETE /wallet/payment-methods/{id}          remove a saved method (detaches at Stripe).
- POST   /wallet/payment-methods/{id}/default  mark a method as default.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import PrincipalDep, SessionDep
from app.schemas.payment_method import (
    AddPaymentMethodIn,
    SavedPaymentMethodOut,
    SetupIntentOut,
)
from app.services import payment_method_service

router = APIRouter(prefix="/api/v1/wallet/payment-methods", tags=["payment-methods"])


@router.get("", response_model=list[SavedPaymentMethodOut])
async def list_methods(principal: PrincipalDep, session: SessionDep):
    rows = await payment_method_service.list_methods(session, principal.user_id)
    return [SavedPaymentMethodOut(**payment_method_service.serialize(m)) for m in rows]


@router.post("/setup-intent", response_model=SetupIntentOut)
async def setup_intent(principal: PrincipalDep, session: SessionDep):
    return SetupIntentOut(
        **await payment_method_service.create_setup_intent(session, principal.user_id)
    )


@router.post("", response_model=SavedPaymentMethodOut, status_code=201)
async def add_method(body: AddPaymentMethodIn, principal: PrincipalDep, session: SessionDep):
    m = await payment_method_service.add(session, principal.user_id, body.payment_method_id)
    return SavedPaymentMethodOut(**payment_method_service.serialize(m))


@router.delete("/{method_id}", status_code=204)
async def delete_method(method_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    await payment_method_service.delete(session, principal.user_id, method_id)


@router.post("/{method_id}/default", response_model=SavedPaymentMethodOut)
async def set_default(method_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    m = await payment_method_service.set_default(session, principal.user_id, method_id)
    return SavedPaymentMethodOut(**payment_method_service.serialize(m))
