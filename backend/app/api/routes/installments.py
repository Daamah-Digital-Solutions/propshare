"""Installment plan routes (Group 6) — owner-scoped, KYC-gated, idempotent.

- GET  /api/v1/installments               the caller's own plans + schedules.
- POST /api/v1/installments               create a plan (reserves the allocation + charges the
  down payment atomically from the wallet). Idempotency-Key required.
- POST /api/v1/installments/payments/{id}/pay   pay a specific due/overdue installment early
  (manual catch-up). Idempotency-Key required.

Creating/paying moves money + reserves units, so both are KYC-gated + Idempotency-Key.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.api.deps import KycVerifiedDep, PrincipalDep, SessionDep
from app.core.errors import AppError
from app.schemas.installments import InstallmentPlanCreateIn, InstallmentPlanOut
from app.services import installment_service

router = APIRouter(prefix="/api/v1/installments", tags=["installments"])


def _idem(request: Request) -> str:
    key = request.headers.get("Idempotency-Key")
    if not key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED", "An Idempotency-Key header is required.", status_code=400
        )
    return key


@router.get("", response_model=list[InstallmentPlanOut])
async def list_plans(session: SessionDep, principal: PrincipalDep):
    return await installment_service.list_plans(session, principal.user_id)


@router.post("", response_model=InstallmentPlanOut, status_code=201)
async def create_plan(
    body: InstallmentPlanCreateIn, request: Request, session: SessionDep, principal: KycVerifiedDep
):
    return await installment_service.create_plan(
        session,
        investor_id=principal.user_id,
        property_id=body.property_id,
        amount=body.amount,
        duration_months=body.duration_months,
        idempotency_key=_idem(request),
    )


@router.post("/payments/{payment_id}/pay", response_model=InstallmentPlanOut)
async def pay_installment(
    payment_id: uuid.UUID, request: Request, session: SessionDep, principal: KycVerifiedDep
):
    return await installment_service.pay_installment(
        session,
        investor_id=principal.user_id,
        payment_id=payment_id,
        idempotency_key=_idem(request),
    )
