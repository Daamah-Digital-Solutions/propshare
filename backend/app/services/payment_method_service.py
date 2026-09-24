"""Saved payment methods (Group 3) — PCI-safe tokenized card storage.

Raw card data NEVER touches this server: the SPA collects + tokenizes the card via a
Stripe SetupIntent (Stripe.js/Elements); here we only keep TOKENS (Stripe customer id +
payment_method id) and safe display metadata (brand/last4/exp) that we fetch SERVER-SIDE
from Stripe (never trusting the client for it). All Stripe calls go through the gateway
seam, which 503s when Stripe is unconfigured.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import PaymentCustomer, SavedPaymentMethod
from app.models.identity import User
from app.services.integrations.payments import stripe_gateway

PROVIDER = "stripe"
logger = logging.getLogger(__name__)


async def checkout_customer(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    """The investor's Stripe customer when they have saved a card, so hosted Checkout lists it."""
    return (
        await session.execute(
            select(SavedPaymentMethod.provider_customer_id)
            .where(SavedPaymentMethod.user_id == user_id)
            .limit(1)
        )
    ).scalar_one_or_none()


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


def _publishable_key() -> str:
    """The key the browser opens Stripe's card form with. It must be from the same mode as
    the server key: a test key cannot open a live setup (and vice versa), so a mismatch is
    reported as unavailable instead of failing inside the card form."""
    settings = get_settings()
    key = settings.stripe_publishable_key
    if not key or key.startswith("pk_live_") != settings.stripe_livemode:
        # say why in the server log (no key material): otherwise it is just an unexplained 503
        logger.warning(
            "card saving unavailable: STRIPE_PUBLISHABLE_KEY %s",
            "is not set" if not key else "is not the same mode (live/test) as STRIPE_SECRET_KEY",
        )
        raise AppError(
            "PAYMENTS_NOT_CONFIGURED", "Saving cards is not available yet.", status_code=503
        )
    return key


async def _replace_customer(session: AsyncSession, user_id: uuid.UUID) -> str:
    """The stored customer is unknown to the current key (test/live or account switched):
    give the investor a new one under this key."""
    row = await session.get(PaymentCustomer, user_id)
    user = await session.get(User, user_id)
    customer_id = await stripe_gateway.create_customer(email=user.email if user else "")
    row.customer_id = customer_id
    await session.commit()
    return customer_id


async def create_setup_intent(session: AsyncSession, user_id: uuid.UUID) -> dict:
    publishable_key = _publishable_key()  # before any Stripe call: no orphan customers
    customer_id = await _ensure_customer(session, user_id)
    await session.commit()  # keep the customer even if the setup fails: one per investor
    try:
        si = await stripe_gateway.create_setup_intent(customer_id=customer_id)
    except AppError as exc:
        if not stripe_gateway.is_unknown_customer(exc):
            raise
        customer_id = await _replace_customer(session, user_id)
        si = await stripe_gateway.create_setup_intent(customer_id=customer_id)
    return {"client_secret": si["client_secret"], "publishable_key": publishable_key}


async def list_methods(session: AsyncSession, user_id: uuid.UUID) -> list[SavedPaymentMethod]:
    res = await session.execute(
        select(SavedPaymentMethod)
        .where(SavedPaymentMethod.user_id == user_id)
        .order_by(SavedPaymentMethod.is_default.desc(), SavedPaymentMethod.created_at.desc())
    )
    return list(res.scalars().all())


async def add(
    session: AsyncSession, user_id: uuid.UUID, setup_intent_id: str
) -> SavedPaymentMethod:
    """Record the card a finished SetupIntent saved. Everything comes from Stripe: the setup
    must belong to this user's Stripe customer and have succeeded, and the card is the one it
    produced (Stripe already attached it to the customer)."""
    owner = await session.get(PaymentCustomer, user_id)
    if owner is None:
        raise AppError("NOT_FOUND", "Card setup not found.", status_code=404)
    customer_id = owner.customer_id
    si = await stripe_gateway.retrieve_setup_intent(setup_intent_id)
    if si["customer"] != customer_id:
        raise AppError("FORBIDDEN", "This card setup belongs to another account.", status_code=403)
    if si["status"] != "succeeded" or not si["payment_method"]:
        raise AppError(
            "CARD_SETUP_INCOMPLETE",
            "The card was not saved: its setup did not finish.",
            status_code=409,
            details={"status": si["status"]},
        )
    payment_method_id = si["payment_method"]
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

    meta = await stripe_gateway.retrieve_payment_method(payment_method_id)
    # They saved it to pay with it: let hosted Checkout offer it. Best effort — the card is
    # already saved at Stripe; without this it just is not pre-listed at checkout.
    user = await session.get(User, user_id)
    try:
        await stripe_gateway.offer_again_at_checkout(
            payment_method_id,
            name=None if meta.get("billing_name") else (user.full_name if user else None),
            email=None if meta.get("billing_email") else (user.email if user else None),
        )
    except AppError as exc:
        logger.warning(
            "saved card not offered at checkout",
            extra={"user_id": str(user_id), "reason": exc.message},
        )

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
    try:
        await session.commit()
    except IntegrityError:
        # the same setup posted twice at once (a retry): the other request saved it first
        await session.rollback()
        saved = (
            await session.execute(
                select(SavedPaymentMethod).where(
                    SavedPaymentMethod.provider == PROVIDER,
                    SavedPaymentMethod.provider_payment_method_id == payment_method_id,
                )
            )
        ).scalar_one()
        if saved.user_id != user_id:
            raise AppError(
                "FORBIDDEN", "This payment method belongs to another user.", status_code=403
            ) from None
        return saved
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
    except AppError as exc:
        logger.warning(
            "removed card not detached at Stripe",
            extra={"user_id": str(user_id), "reason": exc.message},
        )
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
