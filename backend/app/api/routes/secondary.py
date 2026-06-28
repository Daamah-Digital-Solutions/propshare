"""Secondary-market routes (Phase 8) — investor-to-investor unit resale.

- POST   /secondary/listings            list units you own (KYC-gated).
- GET    /secondary/listings            browse active listings (optional ?property_id).
- POST   /secondary/listings/{id}/cancel  cancel your own active listing.
- POST   /secondary/listings/{id}/buy   buy units off a listing (KYC-gated,
                                        Idempotency-Key required, wallet-funded).
- GET    /secondary/listings/mine       your own listings (any status).
- GET    /secondary/holdings            your net unit holdings (sellable units).
- GET    /secondary/settings            live resale-fee/lock-up/price-bound knobs
                                        (so the UI shows the rate the server charges).

Money is server-authoritative and the buy is one atomic wallet-to-wallet transfer
(see secondary_service): the client never sends a fee or total.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.api.deps import KycVerifiedDep, PrincipalDep, SessionDep
from app.core.errors import AppError
from app.schemas.secondary import (
    BuyIn,
    CancelOut,
    HoldingListOut,
    HoldingOut,
    ListingCreateIn,
    ListingListOut,
    ListingOut,
    SecondarySettingsOut,
    TradeOut,
)
from app.services import secondary_service, settings_service

router = APIRouter(prefix="/api/v1/secondary", tags=["secondary"])


@router.post("/listings", response_model=ListingOut)
async def create_listing(body: ListingCreateIn, session: SessionDep, principal: KycVerifiedDep):
    result = await secondary_service.create_listing(
        session,
        seller_id=principal.user_id,
        property_id=body.property_id,
        units=body.units,
        price_per_unit=body.price_per_unit,
    )
    return ListingOut(**result)


@router.get("/listings", response_model=ListingListOut)
async def browse_listings(
    session: SessionDep, principal: PrincipalDep, property_id: uuid.UUID | None = None
):
    rows = await secondary_service.list_active_listings(session, property_id=property_id)
    return ListingListOut(items=[ListingOut(**r) for r in rows], total=len(rows))


@router.get("/listings/mine", response_model=ListingListOut)
async def my_listings(session: SessionDep, principal: PrincipalDep):
    rows = await secondary_service.list_my_listings(session, principal.user_id)
    return ListingListOut(items=[ListingOut(**r) for r in rows], total=len(rows))


@router.post("/listings/{listing_id}/cancel", response_model=CancelOut)
async def cancel_listing(listing_id: uuid.UUID, session: SessionDep, principal: PrincipalDep):
    result = await secondary_service.cancel_listing(
        session, seller_id=principal.user_id, listing_id=listing_id
    )
    return CancelOut(**result)


@router.post("/listings/{listing_id}/buy", response_model=TradeOut)
async def buy_units(
    listing_id: uuid.UUID,
    body: BuyIn,
    request: Request,
    session: SessionDep,
    principal: KycVerifiedDep,
):
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "An Idempotency-Key header is required for purchases.",
            status_code=400,
        )
    result = await secondary_service.buy_listing(
        session,
        buyer_id=principal.user_id,
        listing_id=listing_id,
        units=body.units,
        idempotency_key=idempotency_key,
    )
    return TradeOut(**result)


@router.get("/holdings", response_model=HoldingListOut)
async def my_holdings(session: SessionDep, principal: PrincipalDep):
    rows = await secondary_service.my_holdings(session, principal.user_id)
    return HoldingListOut(items=[HoldingOut(**r) for r in rows], total=len(rows))


@router.get("/settings", response_model=SecondarySettingsOut)
async def secondary_settings(session: SessionDep, principal: PrincipalDep):
    sett = await settings_service.get_secondary_settings(session)
    return SecondarySettingsOut(
        resale_fee_pct=str(sett["resale_fee_pct"]),
        lockup_days=int(sett["lockup_days"] or 0),
        price_min_pct=str(sett["price_min_pct"]) if sett["price_min_pct"] is not None else None,
        price_max_pct=str(sett["price_max_pct"]) if sett["price_max_pct"] is not None else None,
    )
