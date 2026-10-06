"""Installment plan routes (Group 6) — owner-scoped, KYC-gated, idempotent.

- GET  /api/v1/installments               the caller's own plans + schedules.
- POST /api/v1/installments               create a plan (reserves the allocation + charges the
  down payment atomically from the wallet). Idempotency-Key required.
- POST /api/v1/installments/payments/{id}/pay   pay a specific due/overdue installment early
  (manual catch-up). Idempotency-Key required.
- POST /api/v1/installments/sukuk         create a plan whose down payment a Nova Sukuk
  certificate covers (multipart; staff review it). Idempotency-Key required.
- GET  /api/v1/installments/{id}/schedule.pdf | .xlsx   the caller's plan as a branded PDF or
  an Excel workbook.

The down payment is paid from the wallet (method=wallet: the plan starts at once), or through a
hosted checkout — card (Apple / Google Pay), crypto or Pronova — whose webhook starts the plan.

Creating/paying moves money + reserves units, so both are KYC-gated + Idempotency-Key.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, Response, UploadFile

from app.api.deps import KycVerifiedDep, PrincipalDep, SessionDep
from app.api.routes._sukuk_form import certificate_upload
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.installments import InstallmentPlanCreateIn, InstallmentPlanOut
from app.schemas.investment import SukukCertificateOut
from app.services import installment_service, sukuk_service

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
    app_base = get_settings().app_base_url.rstrip("/")
    api_base = str(request.base_url).rstrip("/")
    return await installment_service.create_plan(
        session,
        investor_id=principal.user_id,
        property_id=body.property_id,
        amount=body.amount,
        duration_months=body.duration_months,
        idempotency_key=_idem(request),
        method=body.method,
        expected_unit_price=body.expected_unit_price,
        pay_currency=body.pay_currency if body.method == "crypto" else None,
        # back to the Installments tab, which follows the payment until the plan starts
        # (the service appends the payment id)
        success_url=f"{app_base}/dashboard?tab=installments&plan=success",
        cancel_url=f"{app_base}/dashboard?tab=installments&plan=cancelled",
        ipn_url=f"{api_base}/api/v1/payments/webhooks/nowpayments",
    )


@router.post("/sukuk", response_model=SukukCertificateOut, status_code=201)
async def create_plan_with_sukuk(
    request: Request,
    session: SessionDep,
    principal: KycVerifiedDep,
    property_id: Annotated[uuid.UUID, Form()],
    amount: Annotated[float, Form(gt=0)],
    duration_months: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
    certificate_no: Annotated[str | None, Form()] = None,
    issuer: Annotated[str | None, Form()] = None,
    certificate_value: Annotated[str | None, Form()] = None,
    valid_until: Annotated[str | None, Form()] = None,
):
    """A plan whose down payment a Nova Sukuk certificate (PDF) covers: its units are held
    while staff review it; approved, the plan starts and the next installments come from the
    wallet on their dates."""
    cert = await certificate_upload(file, certificate_no, issuer, certificate_value, valid_until)
    result = await sukuk_service.submit_plan(
        session,
        user_id=principal.user_id,
        property_id=property_id,
        amount=amount,
        duration_months=duration_months,
        idempotency_key=_idem(request),
        cert=cert,
    )
    return SukukCertificateOut(**result)


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


@router.get("/{plan_id}/schedule.pdf")
async def schedule_pdf(plan_id: uuid.UUID, session: SessionDep, principal: PrincipalDep):
    """Download the caller's installment plan as a branded PDF (official design + logo, full
    schedule + details). Generated on demand from live data; 404 if not the caller's plan."""
    filename, pdf = await installment_service.build_schedule_pdf(
        session, investor_id=principal.user_id, plan_id=plan_id
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{plan_id}/schedule.xlsx")
async def schedule_xlsx(plan_id: uuid.UUID, session: SessionDep, principal: PrincipalDep):
    """The same plan as an Excel workbook (amounts as numbers, due dates as dates); 404 if not
    the caller's plan."""
    filename, data = await installment_service.build_schedule_xlsx(
        session, investor_id=principal.user_id, plan_id=plan_id
    )
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
