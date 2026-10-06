"""Investment routes (Phase 5).

- POST /investments       buy units in a property. KYC-gated; Idempotency-Key
                          required. method=wallet (atomic, instant) or card/crypto
                          (reserve units -> hosted checkout -> webhook confirms).
- GET  /investments       the caller's investments (newest first).
- GET  /investments/{id}  one of the caller's investments.

Money is server-authoritative: the client sends a property + USD amount + method;
the server computes units, fees and the charge. Direct-pay is finalized ONLY by a
signed webhook (see routes/payments.py), never on a browser redirect.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.api.deps import AdminOrCronDep, KycVerifiedDep, PrincipalDep, SessionDep
from app.api.routes._sukuk_form import certificate_upload
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Investment
from app.schemas.distribution import MyReturnsOut
from app.schemas.investment import (
    InvestmentCreateIn,
    InvestmentCreateOut,
    InvestmentListOut,
    InvestmentOut,
    PaymentOptionsOut,
    PortfolioOut,
    PronovaSettingsOut,
    ReinvestIn,
    ReinvestOut,
    ReinvestSettingsOut,
    SukukCertificateOut,
)
from app.services import (
    certificate_service,
    distribution_service,
    installment_service,
    investment_service,
    payment_service,
    settings_service,
    sukuk_service,
)

router = APIRouter(prefix="/api/v1/investments", tags=["investments"])


def _serialize(inv: Investment) -> InvestmentOut:
    return InvestmentOut(
        id=inv.id,
        property_id=inv.property_id,
        status=str(inv.status),
        units=inv.units,
        amount=str(inv.amount),
        platform_fee=str(inv.platform_fee_amount or "0"),
        total_charged=str(inv.total_charged or inv.amount),
        confirmed_via=inv.confirmed_via,
        created_at=inv.created_at,
        confirmed_at=inv.confirmed_at,
    )


@router.post("", response_model=InvestmentCreateOut)
async def create_investment(
    body: InvestmentCreateIn,
    request: Request,
    session: SessionDep,
    principal: KycVerifiedDep,
):
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "An Idempotency-Key header is required for investments.",
            status_code=400,
        )
    app_base = get_settings().app_base_url.rstrip("/")
    api_base = str(request.base_url).rstrip("/")
    result = await investment_service.create_investment(
        session,
        user_id=principal.user_id,
        property_id=body.property_id,
        amount=body.amount,
        method=body.method,
        idempotency_key=idempotency_key,
        expected_unit_price=body.expected_unit_price,
        # Back to the Investments tab, which follows the payment until the units are confirmed
        # (the service appends the payment id).
        success_url=f"{app_base}/dashboard?tab=investments&invest=success",
        cancel_url=f"{app_base}/dashboard?tab=investments&invest=cancelled",
        ipn_url=f"{api_base}/api/v1/payments/webhooks/nowpayments",
        pay_currency=body.pay_currency if body.method == "crypto" else None,
    )
    return InvestmentCreateOut(**result)


@router.post("/maintenance/expire-reservations")
async def expire_reservations(caller: AdminOrCronDep, session: SessionDep) -> dict:
    """Release units held by direct-pay reservations that lapsed unpaid. Cron target
    (admin OR X-Cron-Secret); idempotent (SKIP LOCKED), also runs on demand."""
    count = await investment_service.expire_reservations(session)
    # installment plans whose down-payment checkout was not paid in time (0032)
    plans = await installment_service.expire_pending_plans(session)
    return {"expired": count, "expired_plans": plans}


@router.get("", response_model=InvestmentListOut)
async def my_investments(principal: PrincipalDep, session: SessionDep):
    rows = await investment_service.list_my_investments(session, principal.user_id)
    return InvestmentListOut(items=[_serialize(i) for i in rows], total=len(rows))


@router.get("/portfolio", response_model=PortfolioOut)
async def my_portfolio(principal: PrincipalDep, session: SessionDep):
    """Server-authoritative portfolio summary from the ownership ledger + wallet —
    invested / current value / total returns / properties / units. No client math."""
    return PortfolioOut(**await investment_service.portfolio_summary(session, principal.user_id))


@router.get("/reinvest-settings", response_model=ReinvestSettingsOut)
async def reinvest_settings(session: SessionDep):
    """The live, admin-configurable reinvest discount rate (so the UI shows the real,
    server-honored discount — never a client literal). PUBLIC config: no auth required so the
    rate always loads even before the SPA has minted its access token."""
    pct = await settings_service.get_reinvest_discount_pct(session)
    return ReinvestSettingsOut(discount_pct=str(pct))


@router.get("/pronova-settings", response_model=PronovaSettingsOut)
async def pronova_settings(session: SessionDep):
    """The live, admin-configurable Pronova pay discount (% off the total payable), so the UI
    shows the real, server-honored rate — the server applies it to the charge at purchase.
    PUBLIC config: no auth required (was 401-ing when the query fired before the token was
    attached, so the discount silently failed to display even though the charge was discounted)."""
    pct = await settings_service.get_pronova_discount_pct(session)
    return PronovaSettingsOut(discount_pct=str(pct))


@router.post("/reinvest", response_model=ReinvestOut)
async def reinvest(
    body: ReinvestIn, request: Request, session: SessionDep, principal: KycVerifiedDep
):
    """Reinvest returns from the wallet at the server-applied reinvest discount (KYC-gated;
    Idempotency-Key required). The server computes the discounted units/price."""
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "An Idempotency-Key header is required for reinvest.",
            status_code=400,
        )
    result = await investment_service.reinvest_from_wallet(
        session,
        user_id=principal.user_id,
        property_id=body.property_id,
        amount=body.amount,
        idempotency_key=idempotency_key,
    )
    return ReinvestOut(**result)


@router.get("/returns", response_model=MyReturnsOut)
async def my_returns(principal: PrincipalDep, session: SessionDep):
    """The caller's distributed returns (history + monthly aggregation for charts)."""
    return MyReturnsOut(**await distribution_service.my_returns(session, principal.user_id))


@router.get("/certificates.zip")
async def my_certificates_zip(principal: PrincipalDep, session: SessionDep):
    """A single .zip of the caller's certificates — one PDF per property they currently hold
    (live from the ownership ledger; 404 if they hold none)."""
    filename, data = await certificate_service.build_all_zip(session, user_id=principal.user_id)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/certificate/{property_id}")
async def my_certificate(property_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    """A PDF certificate of the caller's CURRENT net holding in a property (live from the
    ownership ledger; 404 if they hold none). Generated on demand — always current."""
    filename, pdf = await certificate_service.build_for_holding(
        session, user_id=principal.user_id, property_id=property_id
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/property/{property_id}/documents.zip")
async def my_property_documents_zip(
    property_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
):
    """One .zip of EVERYTHING for a single property the caller holds: their live ownership
    certificate PLUS every published property document (SPV, agreements, valuation/financial
    reports, legal, insurance, audit…). 404 if the property has neither for the caller."""
    filename, data = await certificate_service.build_property_bundle_zip(
        session, user_id=principal.user_id, property_id=property_id
    )
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/payment-options", response_model=PaymentOptionsOut)
async def payment_options(session: SessionDep):
    """The ways to pay for a property — the SAME list on every property — and which are live
    now (a rail whose provider is not set up is shown as not available, never hidden). Public:
    the property page shows them before sign-in."""
    pct = await settings_service.get_pronova_discount_pct(session)
    return PaymentOptionsOut(**payment_service.purchase_options(), pronova_discount_pct=str(pct))


@router.post("/sukuk", response_model=SukukCertificateOut, status_code=201)
async def buy_with_sukuk(
    request: Request,
    session: SessionDep,
    principal: KycVerifiedDep,
    property_id: Annotated[uuid.UUID, Form()],
    amount: Annotated[float, Form(gt=0)],
    file: Annotated[UploadFile, File()],
    certificate_no: Annotated[str | None, Form()] = None,
    issuer: Annotated[str | None, Form()] = None,
    certificate_value: Annotated[str | None, Form()] = None,
    valid_until: Annotated[str | None, Form()] = None,
):
    """Buy units paying with a Nova Sukuk certificate (PDF): the units are held while staff
    review it; approved, they are the buyer's (pledged to Nova Finance). Idempotency-Key."""
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "An Idempotency-Key header is required for investments.",
            status_code=400,
        )
    cert = await certificate_upload(file, certificate_no, issuer, certificate_value, valid_until)
    result = await sukuk_service.submit_purchase(
        session,
        user_id=principal.user_id,
        property_id=property_id,
        amount=amount,
        idempotency_key=idempotency_key,
        cert=cert,
    )
    return SukukCertificateOut(**result)


@router.get("/sukuk", response_model=list[SukukCertificateOut])
async def my_sukuk_certificates(principal: PrincipalDep, session: SessionDep):
    """The caller's Nova Sukuk certificates (purchases and plan down payments) and their
    review: waiting, approved (pledged), not accepted (with staff's reason) or released."""
    rows = await sukuk_service.list_mine(session, principal.user_id)
    return [SukukCertificateOut(**r) for r in rows]


@router.get("/{investment_id}", response_model=InvestmentOut)
async def my_investment(investment_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    inv = await investment_service.get_my_investment(
        session, user_id=principal.user_id, investment_id=investment_id
    )
    return _serialize(inv)
