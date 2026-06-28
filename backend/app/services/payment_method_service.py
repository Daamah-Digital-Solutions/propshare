"""Saved payment methods (Group 3) — PCI-safe tokenized card storage.

Raw card data NEVER touches this server: the SPA collects + tokenizes the card via a
Stripe SetupIntent (Stripe.js/Elements); here we only keep TOKENS (Stripe customer id +
payment_method id) and safe display metadata (brand/last4/exp) that we fetch SERVER-SIDE
from Stripe (never trusting the client for it). All Stripe calls go through the gateway
seam, which 503s when Stripe is unconfigured.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import PaymentCustomer, SavedPaymentMethod
from app.models.identity import User
from app.services.integrations.payments import stripe_gateway

PROVIDER = "stripe"


def serialize(m: SavedPaymentMethod) -> dict:
    # Tokens are intentionally NOT exposed to the client — only safe display metadata.
    return {
        "id": m.id,
        "type": m.type,
        "brand": m.brand,
        "last4": m.last4,
        "exp_month": m.exp_month,
        "exp_year": m.exp_year,
        "is_default": m.is_default,
        "created_at": m.created_at,
    }


async def _ensure_customer(session: AsyncSession, user_id: uuid.UUID) -> str:
    existing = await session.get(PaymentCustomer, user_id)
    if existing is not None:
        return existing.customer_id
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("NOT_FOUND", "User not found.", status_code=404)
    customer_id = await stripe_gateway.create_customer(email=user.email)
    session.add(PaymentCustomer(user_id=user_id, provider=PROVIDER, customer_id=customer_id))
    await session.flush()
    return customer_id


async def create_setup_intent(session: AsyncSession, user_id: uuid.UUID) -> dict:
    customer_id = await _ensure_customer(session, user_id)
    si = await stripe_gateway.create_setup_intent(customer_id=customer_id)
    await session.commit()
    return {
        "client_secret": si["client_secret"],
        "publishable_key": get_settings().stripe_publishable_key,
    }


async def list_methods(session: AsyncSession, user_id: uuid.UUID) -> list[SavedPaymentMethod]:
    res = await session.execute(
        select(SavedPaymentMethod)
        .where(SavedPaymentMethod.user_id == user_id)
        .order_by(SavedPaymentMethod.is_default.desc(), SavedPaymentMethod.created_at.desc())
    )
    return list(res.scalars().all())


async def add(
    session: AsyncSession, user_id: uuid.UUID, payment_method_id: str
) -> SavedPaymentMethod:
    customer_id = await _ensure_customer(session, user_id)
    # Idempotent: re-adding the same tokenized method returns the existing row.
    existing = (
        await session.execute(
            select(SavedPaymentMethod).where(
                SavedPaymentMethod.provider == PROVIDER,
                SavedPaymentMethod.provider_payment_method_id == payment_method_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.user_id != user_id:
            raise AppError(
                "FORBIDDEN", "This payment method belongs to another user.", status_code=403
            )
        return existing

    await stripe_gateway.attach_payment_method(
        payment_method_id=payment_method_id, customer_id=customer_id
    )
    meta = await stripe_gateway.retrieve_payment_method(payment_method_id)

    has_default = (
        await session.execute(
            select(SavedPaymentMethod.id).where(
                SavedPaymentMethod.user_id == user_id, SavedPaymentMethod.is_default.is_(True)
            )
        )
    ).first() is not None

    method = SavedPaymentMethod(
        user_id=user_id,
        provider=PROVIDER,
        provider_customer_id=customer_id,
        provider_payment_method_id=payment_method_id,
        type=meta.get("type") or "card",
        brand=meta.get("brand"),
        last4=meta.get("last4"),
        exp_month=meta.get("exp_month"),
        exp_year=meta.get("exp_year"),
        is_default=not has_default,  # first saved method becomes the default
    )
    session.add(method)
    await session.commit()
    await session.refresh(method)
    return method


async def _get_owned(
    session: AsyncSession, user_id: uuid.UUID, method_id: uuid.UUID
) -> SavedPaymentMethod:
    m = await session.get(SavedPaymentMethod, method_id)
    if m is None or m.user_id != user_id:
        raise AppError("NOT_FOUND", "Payment method not found.", status_code=404)
    return m


async def delete(session: AsyncSession, user_id: uuid.UUID, method_id: uuid.UUID) -> None:
    m = await _get_owned(session, user_id, method_id)
    was_default = m.is_default
    # Best-effort detach at Stripe; the local row is the source of truth for the UI.
    try:
        await stripe_gateway.detach_payment_method(m.provider_payment_method_id)
    except AppError:
        pass
    await session.delete(m)
    await session.flush()
    if was_default:
        nxt = (
            await session.execute(
                select(SavedPaymentMethod)
                .where(SavedPaymentMethod.user_id == user_id)
                .order_by(SavedPaymentMethod.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if nxt is not None:
            nxt.is_default = True
    await session.commit()


async def set_default(
    session: AsyncSession, user_id: uuid.UUID, method_id: uuid.UUID
) -> SavedPaymentMethod:
    target = await _get_owned(session, user_id, method_id)
    rows = await list_methods(session, user_id)
    for m in rows:
        m.is_default = m.id == target.id
    await session.commit()
    await session.refresh(target)
    return target
