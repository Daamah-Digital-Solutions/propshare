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

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.api.deps import AdminOrCronDep, KycVerifiedDep, PrincipalDep, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Investment
from app.schemas.distribution import MyReturnsOut
from app.schemas.investment import (
    InvestmentCreateIn,
    InvestmentCreateOut,
    InvestmentListOut,
    InvestmentOut,
    PortfolioOut,
    PronovaSettingsOut,
    ReinvestIn,
    ReinvestOut,
    ReinvestSettingsOut,
)
from app.services import (
    certificate_service,
    distribution_service,
    investment_service,
    settings_service,
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
        success_url=f"{app_base}/dashboard?invest=success",
        cancel_url=f"{app_base}/dashboard?invest=cancelled",
        ipn_url=f"{api_base}/api/v1/payments/webhooks/nowpayments",
    )
    return InvestmentCreateOut(**result)


@router.post("/maintenance/expire-reservations")
async def expire_reservations(caller: AdminOrCronDep, session: SessionDep) -> dict:
    """Release units held by direct-pay reservations that lapsed unpaid. Cron target
    (admin OR X-Cron-Secret); idempotent (SKIP LOCKED), also runs on demand."""
    count = await investment_service.expire_reservations(session)
    return {"expired": count}


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


@router.get("/{investment_id}", response_model=InvestmentOut)
async def my_investment(investment_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    inv = await investment_service.get_my_investment(
        session, user_id=principal.user_id, investment_id=investment_id
    )
    return _serialize(inv)
