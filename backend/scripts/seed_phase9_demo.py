# ruff: noqa: E501
"""Phase 9 ACTIVE — ready-to-test seed (idempotent, safe to re-run).

Creates everything needed to exercise the liquidity-provider ACTIVE buyback in the
browser with zero manual admin steps:

  * A dedicated Ready property ("Sample - Phase 9 Ready Demo", $100/unit) so we never
    disturb the catalog.
  * SELLER account — KYC-verified, funded wallet, and holding 60 units of that property
    (a real ownership_ledger acquisition row with fee_rate stamped at 1.0%, so a later
    rental distribution charges the seller their consented rate).
  * LP account — KYC-verified, granted the liquidity_provider role (active), with a
    large funded wallet to cover the discounted buyback price comfortably.

Idempotency: users are matched by email; the holding, the seed funding and the role
grant are each guarded so re-running never double-funds, double-grants, or
double-issues units (the wallet invariant balance == SUM(ledger) is preserved — every
funded dollar is backed by exactly one 'deposit' ledger row).

Usage (from backend/, with the venv):
    .venv\\Scripts\\python.exe scripts/seed_phase9_demo.py
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.core.db import session_scope
from app.models import (
    KycVerification,
    OwnershipLedger,
    Property,
    Transaction,
    UserRole,
    Wallet,
)
from app.models.base import AppRole, PropertyStatus, TransactionType
from app.models.identity import User
from app.services import auth_service

PASSWORD = "Passw0rd!23"
# NOTE: use a real-looking TLD — the email validator rejects reserved TLDs like .test.
SELLER_EMAIL = "seller.phase9@capimax.com"
LP_EMAIL = "lp.phase9@capimax.com"

PROP_SLUG = "demo-phase9-ready"
PROP_TITLE = "Sample - Phase 9 Ready Demo"
UNIT_PRICE = Decimal("100")
TOTAL_UNITS = 1000
SELLER_UNITS = 60
SELLER_FEE_RATE = Decimal("1.0")  # the seller's consented mgmt-fee rate
SELLER_FUNDING = Decimal("5000")
LP_FUNDING = Decimal("50000")
SEED_DEPOSIT_DESC = "phase9 seed deposit"


async def _ensure_property(session) -> Property:
    prop = (
        await session.execute(select(Property).where(Property.slug == PROP_SLUG))
    ).scalar_one_or_none()
    if prop is not None:
        return prop
    prop = Property(
        owner_id=None,
        title=PROP_TITLE,
        subtitle="Dedicated Ready property for Phase 9 ACTIVE buyback testing",
        description="Educational sample used only for liquidity-provider end-to-end testing.",
        location="Dubai Marina, UAE",
        country="UAE",
        city="Dubai",
        property_type="apartment",
        model="ready-income",
        slug=PROP_SLUG,
        status=PropertyStatus.active,
        total_value=UNIT_PRICE * TOTAL_UNITS,
        unit_price=UNIT_PRICE,
        total_units=TOTAL_UNITS,
        available_units=TOTAL_UNITS,
        minimum_investment=UNIT_PRICE,
        expected_yield=Decimal("8.0"),
        funding_progress=Decimal("0"),
        investors_count=0,
        funded_amount=Decimal("0"),
        images=[
            "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=1200&auto=format&fit=crop&q=80"
        ],
        content={"badge": "Ready - Phase 9 Demo"},
    )
    session.add(prop)
    await session.flush()
    return prop


async def _ensure_user(session, *, email: str, full_name: str) -> User:
    user = await auth_service.get_user_by_email(session, email)
    if user is None:
        user = await auth_service.register(
            session, email=email, password=PASSWORD, full_name=full_name, phone=None
        )
        await session.flush()
    return user


async def _verify_kyc(session, user_id) -> None:
    kyc = (
        await session.execute(select(KycVerification).where(KycVerification.user_id == user_id))
    ).scalar_one_or_none()
    if kyc is not None:
        kyc.status = "verified"


async def _fund_once(session, user_id, amount: Decimal) -> None:
    """Fund the wallet exactly once (guarded), keeping balance == SUM(ledger)."""
    already = (
        await session.execute(
            select(Transaction.id).where(
                Transaction.user_id == user_id, Transaction.description == SEED_DEPOSIT_DESC
            )
        )
    ).first()
    if already is not None:
        return
    session.add(
        Transaction(
            user_id=user_id,
            type=TransactionType.deposit,
            amount=amount,
            status="completed",
            description=SEED_DEPOSIT_DESC,
        )
    )
    wallet = (await session.execute(select(Wallet).where(Wallet.user_id == user_id))).scalar_one()
    wallet.balance = wallet.balance + amount


async def _grant_role(session, user_id, role: AppRole) -> None:
    exists = (
        await session.execute(
            select(UserRole.id).where(UserRole.user_id == user_id, UserRole.role == role)
        )
    ).first()
    if exists is None:
        session.add(UserRole(user_id=user_id, role=role))


async def _ensure_holding(session, *, user_id, prop: Property, units: int) -> None:
    """Give the seller a real acquisition row once (guarded), and reflect it in the
    property's running counters so units add up."""
    has = (
        await session.execute(
            select(OwnershipLedger.id).where(
                OwnershipLedger.user_id == user_id,
                OwnershipLedger.property_id == prop.id,
                OwnershipLedger.reason == "purchase",
            )
        )
    ).first()
    if has is not None:
        return
    session.add(
        OwnershipLedger(
            user_id=user_id,
            property_id=prop.id,
            investment_id=None,
            units=units,
            unit_price=prop.unit_price,
            reason="purchase",
            fee_rate=SELLER_FEE_RATE,
        )
    )
    prop.available_units = prop.available_units - units
    prop.funded_amount = prop.funded_amount + prop.unit_price * units
    prop.investors_count = prop.investors_count + 1


async def _seed() -> int:
    async with session_scope() as session:
        prop = await _ensure_property(session)

        seller = await _ensure_user(session, email=SELLER_EMAIL, full_name="Phase9 Seller")
        await _verify_kyc(session, seller.id)
        await _fund_once(session, seller.id, SELLER_FUNDING)
        await _ensure_holding(session, user_id=seller.id, prop=prop, units=SELLER_UNITS)

        lp = await _ensure_user(session, email=LP_EMAIL, full_name="Phase9 Liquidity Provider")
        await _verify_kyc(session, lp.id)
        await _fund_once(session, lp.id, LP_FUNDING)
        await _grant_role(session, lp.id, AppRole.liquidity_provider)
        lp.active_role = AppRole.liquidity_provider

    print("OK: Phase 9 demo seeded (idempotent).")
    print(f"  Property : {PROP_TITLE}  (slug={PROP_SLUG}, ${UNIT_PRICE}/unit)")
    print(
        f"  SELLER   : {SELLER_EMAIL} / {PASSWORD}  (KYC verified, {SELLER_UNITS} units held, ${SELLER_FUNDING} wallet)"
    )
    print(
        f"  LP       : {LP_EMAIL} / {PASSWORD}  (KYC verified, liquidity_provider role, ${LP_FUNDING} wallet)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_seed()))
