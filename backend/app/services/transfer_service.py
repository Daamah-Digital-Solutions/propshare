"""Transfers: property units or wallet balance to another person (client, 2026-10-28, as on
Capimax BRX).

An investor sends units of a property they hold, or an amount from their wallet, to anyone by
email, now or on a date up to a year ahead. The engine:

  create   check it (a confirmed email and verified identity for the sender; free units /
           enough balance; not to themselves), HOLD it at once — units are reserved against the
           holding by the shared reserved-units rule (``secondary_service``), an amount leaves
           the wallet with any fee — and deliver it right away when it is due today.
  deliver  when the recipient's email is confirmed and their identity verified: units move on
           the ownership ledger (``transfer_out`` / ``transfer_in``), an amount is credited to
           their wallet; both are told. Otherwise it WAITS and the recipient is invited; it is
           handed over the moment they verify (``account_service.release_waiting``).
  close    cancelled (by the sender before delivery, or by the team), expired (not received
           within CLAIM_DAYS) or failed: everything held goes back to the sender, once (the
           row lock, the status check, and a unique index on the money-in row).

Every transfer has a number, ``TR-`` and ten characters; the member's Transfers tab, the
admin's Transfers desk, the wallet statement and the unit movements all show it.

Units of a running installment plan (0042, asset ``plan``): the sender gives some of the plan's
units, or all, to another person, who pays their share of the installments still to come (the
part becomes the recipient's own plan with the same dates; all of it, the plan itself). The
recipient takes on payments, so such a transfer goes out at once and only to someone whose
email is confirmed and identity verified; it never waits or runs on a later date. It is free of
units-of-the-ledger holds (it is delivered in the same request) and changes hands only when no
installment of the plan is overdue. The fee is on what the units are worth less the principal
that comes with them.
"""

from __future__ import annotations

import datetime as dt
import decimal
import secrets
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import InstallmentPlan, KycVerification, Property, User, Wallet
from app.models.base import TransactionType
from app.models.investments import OwnershipLedger
from app.models.transfers import OPEN, Transfer
from app.services import (
    account_service,
    installment_service,
    notification_service,
    secondary_service,
    settings_service,
    wallet_service,
)

CLAIM_DAYS = 30  # how long a waiting transfer waits for its recipient
MAX_DAYS_AHEAD = 365  # the latest delivery date that can be chosen
REMINDER_DAYS = 7  # the sender is reminded this long before a scheduled transfer
MESSAGE_MAX = 500
NAME_MAX = 120
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CENTS = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)

STATUS_LABELS = {
    "scheduled": "Scheduled",
    "waiting": "Waiting for the recipient",
    "delivered": "Delivered",
    "cancelled": "Cancelled — returned",
    "expired": "Expired — returned",
    "failed": "Failed — returned",
}


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


def _money(value: decimal.Decimal) -> str:
    return f"${value:,.2f}"


def _new_reference() -> str:
    return "TR-" + "".join(secrets.choice(_ALPHABET) for _ in range(10))


def describe(t: Transfer) -> str:
    """What was sent, as people read it: "5 units of Marina Loft" or "$250.00"."""
    if t.asset == "units":
        return f"{t.units} unit{'s' if t.units != 1 else ''} of {t.property_title or 'a property'}"
    if t.asset == "plan":
        return (
            f"{t.units} unit{'s' if t.units != 1 else ''} of {t.property_title or 'a property'} "
            "on an installment plan"
        )
    return _money(t.amount)


async def _name(session: AsyncSession, user_id: uuid.UUID) -> str:
    """How a member is named to the other side: their account name, never their email. It
    goes into emails to any address, so typed text never becomes a link there."""
    name = await session.scalar(select(User.full_name).where(User.id == user_id))
    return notification_service.plain_text(name, NAME_MAX) or "A Capimax PropShare member"


async def _kyc_verified(session: AsyncSession, user_id: uuid.UUID) -> bool:
    status = await session.scalar(
        select(KycVerification.status).where(KycVerification.user_id == user_id)
    )
    return str(status) == "verified"


async def _ready(session: AsyncSession, user: User | None) -> bool:
    """A recipient receives once their email is confirmed and their identity verified (and
    the account is open)."""
    return (
        user is not None
        and user.closed_at is None
        and bool(user.email_verified)
        and await _kyc_verified(session, user.id)
    )


async def _holding(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
            OwnershipLedger.user_id == user_id, OwnershipLedger.property_id == property_id
        )
    )
    return int(total or 0)


async def _balance(session: AsyncSession, user_id: uuid.UUID) -> decimal.Decimal:
    bal = await session.scalar(select(Wallet.balance).where(Wallet.user_id == user_id))
    return decimal.Decimal(bal) if bal is not None else decimal.Decimal("0")


# --- what the sender can send ---------------------------------------------------------- #
async def options(session: AsyncSession, user_id: uuid.UUID) -> dict:
    """The sender's free units per property, wallet balance, the fee rate and the rules."""
    rows = (
        await session.execute(
            select(
                OwnershipLedger.property_id,
                func.sum(OwnershipLedger.units).label("units"),
                Property.title,
                Property.unit_price,
            )
            .join(Property, Property.id == OwnershipLedger.property_id)
            .where(OwnershipLedger.user_id == user_id)
            .group_by(OwnershipLedger.property_id, Property.title, Property.unit_price)
            .having(func.sum(OwnershipLedger.units) > 0)
            .order_by(Property.title)
        )
    ).all()
    positions = []
    for pid, held, title, unit_price in rows:
        free = int(held) - await secondary_service.reserved_units(session, user_id, pid)
        positions.append(
            {
                "property_id": pid,
                "property_title": title,
                "units": int(held),
                "free_units": max(0, free),
                "unit_price": str(_q(decimal.Decimal(unit_price or 0))),
            }
        )
    plans = []
    for plan in (
        (
            await session.execute(
                select(InstallmentPlan)
                .where(InstallmentPlan.investor_id == user_id, InstallmentPlan.status == "active")
                .order_by(InstallmentPlan.created_at)
            )
        )
        .scalars()
        .all()
    ):
        prop = await session.get(Property, plan.property_id)
        if prop is None:
            continue
        payments = await installment_service._payments_for(session, plan.id)
        late = installment_service.overdue_payments(payments)
        plans.append(
            {
                "plan_id": plan.id,
                "property_id": plan.property_id,
                "property_title": prop.title,
                "units": plan.units_total,
                "free_units": await installment_service.free_plan_units(session, plan),
                "unit_price": str(_q(decimal.Decimal(prop.unit_price or 0))),
                "overdue_amount": str(
                    _q(sum((p.total_amount for p in late), decimal.Decimal("0")))
                ),
                "pledged": await secondary_service._nova_pledged(session, plan.id),
            }
        )
    return {
        "positions": positions,
        # 0042: running installment plans, part of which can be sent
        "plans": plans,
        "balance": str(_q(await _balance(session, user_id))),
        "fee_pct": str(await settings_service.get_transfer_fee_pct(session)),
        "claim_days": CLAIM_DAYS,
        "max_days_ahead": MAX_DAYS_AHEAD,
    }


# --- check and price (the review step, and the first half of create) ------------------- #
async def _check(session: AsyncSession, *, sender: User, data: dict, lock: bool) -> dict:
    """Everything about a transfer that can be known before it is sent, or the reason it
    cannot be. ``lock`` holds the property row (create) so the free-units check stands."""
    email = (data.get("recipient_email") or "").strip().lower()
    if not email or "@" not in email:
        raise AppError("RECIPIENT_EMAIL_REQUIRED", "Enter the recipient's email.", status_code=422)
    if email == (sender.email or "").strip().lower():
        raise AppError("SELF_TRANSFER", "You cannot send a transfer to yourself.", status_code=422)
    today = _utcnow().date()
    deliver_on = data.get("deliver_on") or today
    if deliver_on < today:
        raise AppError("DATE_IN_PAST", "Choose today or a later date.", status_code=422)
    if (deliver_on - today).days > MAX_DAYS_AHEAD:
        raise AppError(
            "DATE_TOO_FAR", f"Choose a date within {MAX_DAYS_AHEAD} days.", status_code=422
        )
    fee_pct = await settings_service.get_transfer_fee_pct(session)
    out: dict = {
        "recipient_email": email,
        "recipient_name": notification_service.plain_text(data.get("recipient_name"), NAME_MAX)
        or None,
        "message": notification_service.plain_text(data.get("message"), MESSAGE_MAX) or None,
        "occasion": data.get("occasion") or None,
        "deliver_on": deliver_on,
        "fee_pct": fee_pct,
    }
    asset = data.get("asset")
    if asset == "units":
        units = int(data.get("units") or 0)
        if units <= 0:
            raise AppError("UNITS_REQUIRED", "Enter how many units to send.", status_code=422)
        property_id = data.get("property_id")
        q = select(Property).where(Property.id == property_id)
        prop = (await session.execute(q.with_for_update() if lock else q)).scalar_one_or_none()
        if prop is None:
            raise AppError("NOT_FOUND", "Property not found.", status_code=404)
        held = await _holding(session, sender.id, prop.id)
        free = held - await secondary_service.reserved_units(session, sender.id, prop.id)
        if units > free:
            raise AppError(
                "INSUFFICIENT_UNITS",
                f"You can send up to {max(0, free)} unit{'s' if free != 1 else ''} of this "
                "property now (the rest are listed, reserved or on a running plan).",
                status_code=422,
                details={"free": max(0, free), "requested": units},
            )
        unit_price = _q(decimal.Decimal(prop.unit_price or 0))
        value = _q(unit_price * units)
        fee = _q(value * fee_pct / _HUNDRED)
        out.update(
            asset="units",
            property_id=prop.id,
            property_title=prop.title,
            units=units,
            unit_price=unit_price,
            amount=value,
            fee=fee,
            charged=fee,  # what leaves the wallet now
        )
    elif asset == "plan":
        out.update(await _check_plan(session, sender=sender, data=data, lock=lock, out=out))
    elif asset == "balance":
        try:
            amount = _q(decimal.Decimal(str(data.get("amount") or "0")))
        except (ArithmeticError, ValueError) as exc:
            raise AppError("INVALID_AMOUNT", "Enter an amount.", status_code=422) from exc
        if amount <= 0:
            raise AppError("INVALID_AMOUNT", "Enter an amount.", status_code=422)
        fee = _q(amount * fee_pct / _HUNDRED)
        out.update(
            asset="balance",
            property_id=None,
            property_title=None,
            units=None,
            unit_price=None,
            amount=amount,
            fee=fee,
            charged=amount + fee,
        )
    else:
        raise AppError(
            "INVALID_ASSET", "Choose units, plan units or wallet balance.", status_code=422
        )
    balance = await _balance(session, sender.id)
    if out["charged"] > balance:
        raise AppError(
            "INSUFFICIENT_FUNDS",
            f"Your wallet balance is {_money(balance)}; this needs {_money(out['charged'])}"
            + (f" (including the {_money(out['fee'])} fee)." if out["fee"] > 0 else "."),
            status_code=422,
        )
    return out


async def _check_plan(
    session: AsyncSession, *, sender: User, data: dict, lock: bool, out: dict
) -> dict:
    """``_check`` for units of a running installment plan (0042): the sender's plan, units it
    has free, nothing overdue, today, and a recipient who can take payments on."""
    units = int(data.get("units") or 0)
    if units <= 0:
        raise AppError("UNITS_REQUIRED", "Enter how many units to send.", status_code=422)
    try:
        plan_id = uuid.UUID(str(data.get("plan_id")))
    except (TypeError, ValueError) as exc:
        raise AppError("NOT_FOUND", "Installment plan not found.", status_code=404) from exc
    if lock:
        # the installment module's lock order: the plan's payments, the plan, the property
        plan, payments = await installment_service._lock_plan_rows(session, plan_id)
    else:
        plan = await session.get(InstallmentPlan, plan_id)
        payments = await installment_service._payments_for(session, plan_id) if plan else []
    if plan is None or plan.investor_id != sender.id:
        raise AppError("NOT_FOUND", "Installment plan not found.", status_code=404)
    if plan.status != "active":
        raise AppError(
            "PLAN_NOT_RUNNING",
            "This plan is no longer running. A paid-off plan's units are ordinary units: send "
            "them like any others.",
            status_code=409,
        )
    q = select(Property).where(Property.id == plan.property_id)
    prop = (await session.execute(q.with_for_update() if lock else q)).scalar_one()
    if await secondary_service._nova_pledged(session, plan.id):
        raise AppError("UNITS_PLEDGED", secondary_service._PLEDGED_MESSAGE, status_code=409)
    if out["deliver_on"] != _utcnow().date():
        raise AppError(
            "PLAN_TRANSFER_TODAY",
            "Units of an installment plan are sent today: their installments go on, so they "
            "cannot wait for a later date.",
            status_code=422,
        )
    installment_service.require_no_overdue(payments)
    free = await installment_service.free_plan_units(session, plan)
    if units > free:
        raise AppError(
            "INSUFFICIENT_UNITS",
            f"You can send up to {free} unit{'s' if free != 1 else ''} of this plan now (the "
            "rest are listed or offered to a liquidity provider).",
            status_code=422,
            details={"free": free, "requested": units},
        )
    recipient = await account_service.confirmed_by_address(session, out["recipient_email"])
    if not await _ready(session, recipient):
        raise AppError(
            "RECIPIENT_NOT_READY",
            "Units of an installment plan can only go to a member whose email is confirmed and "
            "identity verified, because they take over the installments. Ask them to finish "
            "that first.",
            status_code=422,
        )
    unit_price = _q(decimal.Decimal(prop.unit_price or 0))
    fig = installment_service.part_figures(plan, payments, units, unit_price)
    # what is given: the units' value less the principal that comes with them
    amount = max(fig["equity"], decimal.Decimal("0.00"))
    fee = _q(amount * out["fee_pct"] / _HUNDRED)
    return {
        "asset": "plan",
        "plan_id": plan.id,
        "property_id": prop.id,
        "property_title": prop.title,
        "units": units,
        "plan_units": plan.units_total,
        "unit_price": unit_price,
        "amount": amount,
        "fee": fee,
        "charged": fee,
        "plan_figures": fig,
    }


async def _sender(session: AsyncSession, sender_id: uuid.UUID) -> User:
    sender = await session.get(User, sender_id)
    if sender is None:
        raise AppError("NOT_FOUND", "Account not found.", status_code=404)
    account_service.ensure_open(sender)
    if not sender.email_verified:
        raise AppError(
            "EMAIL_NOT_CONFIRMED", "Confirm your email address before sending.", status_code=403
        )
    if not await _kyc_verified(session, sender_id):
        raise AppError("KYC_REQUIRED", "Identity verification required.", status_code=403)
    return sender


async def quote(session: AsyncSession, *, sender_id: uuid.UUID, data: dict) -> dict:
    """The review step: what will be sent and held, the fee, and when, without sending."""
    sender = await _sender(session, sender_id)
    c = await _check(session, sender=sender, data=data, lock=False)
    return {
        "asset": c["asset"],
        "recipient_email": c["recipient_email"],
        "recipient_name": c["recipient_name"],
        "property_id": c["property_id"],
        "property_title": c["property_title"],
        "units": c["units"],
        "unit_price": str(c["unit_price"]) if c["unit_price"] is not None else None,
        "amount": str(c["amount"]),
        "fee": str(c["fee"]),
        "fee_pct": str(c["fee_pct"]),
        "charged": str(c["charged"]),
        "deliver_on": c["deliver_on"],
        "message": c["message"],
        "occasion": c["occasion"],
        "claim_days": CLAIM_DAYS,
        "plan": _plan_quote(c),
    }


def _plan_quote(c: dict) -> dict | None:
    """For units of a plan: what the recipient takes on (their share of the payments)."""
    fig = c.get("plan_figures")
    if fig is None:
        return None
    return {
        "plan_id": c["plan_id"],
        "units": c["units"],
        "plan_units": c["plan_units"],
        "vested_units": fig["vested_units"],
        "value": str(fig["value"]),
        "paid_principal": str(fig["paid_principal"]),
        "remaining_principal": str(fig["remaining_principal"]),
        "remaining_fees": str(fig["remaining_fees"]),
        "installments_left": fig["installments_left"],
        "next_due": fig["next_due"],
        "schedule": installment_service.schedule_rows(fig["schedule"]),
    }


# --- create -------------------------------------------------------------------------- #
async def create(
    session: AsyncSession, *, sender_id: uuid.UUID, data: dict, idempotency_key: str
) -> dict:
    """Send it: hold what is sent, and deliver it now when it is due today. The same
    Idempotency-Key returns the first transfer and sends nothing more."""
    key = (idempotency_key or "").strip()[:200]
    if not key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED", "An Idempotency-Key header is required.", status_code=400
        )
    # two requests with the same key at once: the second waits, then finds the first
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"transfer:{sender_id}:{key}")))
    )
    existing = (
        await session.execute(
            select(Transfer).where(Transfer.sender_id == sender_id, Transfer.idempotency_key == key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return await serialize(session, existing, viewer_id=sender_id)

    sender = await _sender(session, sender_id)
    c = await _check(session, sender=sender, data=data, lock=True)
    try:
        expected = data.get("expected_charged")
        expected = None if expected in (None, "") else _q(decimal.Decimal(str(expected)))
    except (ArithmeticError, ValueError):
        expected = decimal.Decimal("-1")  # unreadable: never matches, so it is reviewed again
    if expected is not None and expected != c["charged"]:
        raise AppError(
            "QUOTE_CHANGED",
            "The amount or the fee changed since you reviewed it: review the transfer again.",
            status_code=409,
            details={"charged": str(c["charged"])},
        )
    recipient = await account_service.confirmed_by_address(session, c["recipient_email"])
    t = Transfer(
        id=uuid.uuid4(),
        reference=_new_reference(),
        sender_id=sender_id,
        recipient_id=recipient.id if recipient else None,
        recipient_email=c["recipient_email"],
        recipient_name=c["recipient_name"],
        asset=c["asset"],
        property_id=c["property_id"],
        property_title=c["property_title"],
        plan_id=c.get("plan_id"),
        units=c["units"],
        unit_price=c["unit_price"],
        amount=c["amount"],
        fee=c["fee"],
        fee_pct=c["fee_pct"],
        message=c["message"],
        occasion=c["occasion"],
        deliver_on=c["deliver_on"],
        status="scheduled",
        idempotency_key=key,
    )
    session.add(t)
    await session.flush()  # the units are held from here (the reserved-units rule)
    items: list[tuple[TransactionType, decimal.Decimal, str | None]] = []
    to = t.recipient_name or t.recipient_email
    if t.asset == "balance":
        items.append((TransactionType.transfer, t.amount, f"Transfer {t.reference} to {to}"))
    if t.fee > 0:
        items.append((TransactionType.fee, t.fee, f"Transfer fee {t.reference}"))
    if items:
        await wallet_service.debit(
            session, user_id=sender_id, reference_id=t.id, line_items=items, actor_id=sender_id
        )
    await write_audit(
        session,
        action="transfer.created",
        entity_type="transfer",
        entity_id=str(t.id),
        actor_id=sender_id,
        after={
            "reference": t.reference,
            "asset": t.asset,
            "what": describe(t),
            "to": t.recipient_email,
            "fee": str(t.fee),
            "deliver_on": t.deliver_on.isoformat(),
        },
    )
    if t.deliver_on <= _utcnow().date():
        await _deliver(session, t, now=_utcnow())
    else:
        await notification_service.notify(
            session,
            user_id=sender_id,
            type="transfer",
            title=f"Transfer {t.reference} scheduled",
            message=(
                f"{describe(t)} to {to} is held for you and goes out on "
                f"{t.deliver_on.strftime('%d %b %Y')}. You can cancel it before then."
            ),
        )
    await session.flush()
    return await serialize(session, t, viewer_id=sender_id)


# --- deliver ------------------------------------------------------------------------- #
async def _deliver(session: AsyncSession, t: Transfer, *, now: dt.datetime) -> str:
    """Hand an open, due transfer over, or park it until the recipient verifies. The caller
    holds the transfer row (FOR UPDATE, or it was just created)."""
    if t.status not in OPEN or t.deliver_on > now.date():
        return t.status
    recipient = await account_service.confirmed_by_address(session, t.recipient_email)
    if recipient is not None and recipient.id != t.recipient_id:
        t.recipient_id = recipient.id
    if recipient is not None and recipient.id == t.sender_id:
        await _close(session, t, "failed", "The recipient is the sender.", now=now)
        return t.status
    if t.asset == "plan" and not await _ready(session, recipient):
        # installments do not wait: such a transfer never parks (checked when it is made)
        await _close(
            session,
            t,
            "failed",
            "The recipient's account is not ready to take over installments.",
            now=now,
        )
        return t.status
    if not await _ready(session, recipient):
        if t.status != "waiting":
            t.status = "waiting"
            t.invited_at = now
            t.expires_at = now + dt.timedelta(days=CLAIM_DAYS)
            await _tell_waiting(session, t)
            await write_audit(
                session,
                action="transfer.waiting",
                entity_type="transfer",
                entity_id=str(t.id),
                after={"reference": t.reference, "expires_at": t.expires_at.isoformat()},
            )
        return t.status
    assert recipient is not None
    try:
        async with session.begin_nested():
            if t.asset == "units":
                await _move_units(session, t, recipient.id)
            elif t.asset == "plan":
                await _move_plan(session, t, recipient.id)
            else:
                await wallet_service.credit(
                    session,
                    user_id=recipient.id,
                    amount=t.amount,
                    reference_id=t.id,
                    tx_type=TransactionType.transfer,
                    description=(
                        f"Transfer {t.reference} from {await _name(session, t.sender_id)}"
                    ),
                    actor_id=t.sender_id,
                )
    except AppError as exc:
        await _close(session, t, "failed", exc.message, now=now)
        return t.status
    t.status = "delivered"
    t.delivered_at = now
    t.recipient_id = recipient.id
    await _tell_delivered(session, t, recipient.id)
    await write_audit(
        session,
        action="transfer.delivered",
        entity_type="transfer",
        entity_id=str(t.id),
        after={"reference": t.reference, "recipient": str(recipient.id), "what": describe(t)},
    )
    return t.status


async def _move_units(session: AsyncSession, t: Transfer, recipient_id: uuid.UUID) -> None:
    prop = (
        await session.execute(
            select(Property).where(Property.id == t.property_id).with_for_update()
        )
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("PROPERTY_GONE", "The property no longer exists.", status_code=409)
    held = await _holding(session, t.sender_id, prop.id)
    # this transfer's own units are among the reserved ones: everything reserved must still
    # be held for these to leave
    if held < await secondary_service.reserved_units(session, t.sender_id, prop.id):
        raise AppError(
            "UNITS_NO_LONGER_HELD",
            "The sender no longer holds these units.",
            status_code=409,
        )
    mgmt_rate = await settings_service.get_management_fee_pct(session)
    price = decimal.Decimal(prop.unit_price or 0)
    session.add(
        OwnershipLedger(
            user_id=t.sender_id,
            property_id=prop.id,
            investment_id=None,
            units=-int(t.units or 0),
            unit_price=price,
            reason="transfer_out",
            ref_id=t.id,
        )
    )
    session.add(
        OwnershipLedger(
            user_id=recipient_id,
            property_id=prop.id,
            investment_id=None,
            units=int(t.units or 0),
            unit_price=price,
            reason="transfer_in",
            fee_rate=mgmt_rate,  # the recipient carries the management fee, as with gifts
            ref_id=t.id,
        )
    )
    await session.flush()


async def _move_plan(session: AsyncSession, t: Transfer, recipient_id: uuid.UUID) -> None:
    """Units of the sender's running plan become the recipient's: a new plan of their own
    with its share of every payment, or (all its units) the plan itself."""
    assert t.plan_id is not None
    plan, payments = await installment_service._lock_plan_rows(session, t.plan_id)
    if plan is None or plan.investor_id != t.sender_id or plan.status != "active":
        raise AppError("PLAN_NOT_RUNNING", "The plan is no longer running.", status_code=409)
    prop = (
        await session.execute(
            select(Property).where(Property.id == plan.property_id).with_for_update()
        )
    ).scalar_one()
    if int(t.units or 0) > await installment_service.free_plan_units(session, plan):
        raise AppError(
            "UNITS_NO_LONGER_HELD",
            "The plan no longer has these units free.",
            status_code=409,
        )
    price = _q(decimal.Decimal(prop.unit_price or 0))
    taken = await installment_service.take_plan_units(
        session,
        plan=plan,
        payments=payments,
        units=int(t.units or 0),
        to_user_id=recipient_id,
        entry_price=price,
        ledger_price=price,
        reasons=("transfer_out", "transfer_in"),
        ref_id=t.id,
        actor_id=t.sender_id,
    )
    t.new_plan_id = taken.id
    await session.flush()


# --- close: cancelled / expired / failed ------------------------------------------------ #
async def _close(
    session: AsyncSession,
    t: Transfer,
    status: str,
    reason: str,
    *,
    now: dt.datetime,
    actor_id: uuid.UUID | None = None,
) -> None:
    """Close an open transfer and give back what was held: the units are released by the
    status, the amount and any fee are credited back (once: the unique money-in index)."""
    if t.status not in OPEN:
        return
    back = (t.amount if t.asset == "balance" else decimal.Decimal("0")) + t.fee
    if back > 0:
        await wallet_service.credit(
            session,
            user_id=t.sender_id,
            amount=back,
            reference_id=t.id,
            tx_type=TransactionType.transfer,
            description=f"Transfer {t.reference} returned",
            actor_id=actor_id,
        )
    t.status = status
    t.closed_at = now
    t.closed_reason = reason[:300]
    t.closed_by = actor_id if actor_id != t.sender_id else None
    if actor_id != t.sender_id:  # the sender who cancelled it knows
        await notification_service.notify(
            session,
            user_id=t.sender_id,
            type="transfer",
            title=f"Transfer {t.reference} returned to you",
            message=f"{describe(t)} to {t.recipient_name or t.recipient_email}: {reason}",
            email_category="investment_updates",
        )
    await write_audit(
        session,
        action=f"transfer.{status}",
        entity_type="transfer",
        entity_id=str(t.id),
        actor_id=actor_id,
        after={"reference": t.reference, "reason": reason[:300], "returned": str(back)},
    )


async def _locked(session: AsyncSession, transfer_id: uuid.UUID) -> Transfer:
    t = (
        await session.execute(select(Transfer).where(Transfer.id == transfer_id).with_for_update())
    ).scalar_one_or_none()
    if t is None:
        raise AppError("NOT_FOUND", "Transfer not found.", status_code=404)
    return t


async def cancel(session: AsyncSession, *, sender_id: uuid.UUID, transfer_id: uuid.UUID) -> dict:
    """The sender takes back a transfer that has not been delivered."""
    t = await _locked(session, transfer_id)
    if t.sender_id != sender_id:
        raise AppError("NOT_FOUND", "Transfer not found.", status_code=404)
    if t.status not in OPEN:
        raise AppError(
            "NOT_OPEN",
            f"This transfer is already {STATUS_LABELS[t.status].lower()}.",
            status_code=409,
        )
    await _close(session, t, "cancelled", "Cancelled by you.", now=_utcnow(), actor_id=sender_id)
    await session.flush()
    return await serialize(session, t, viewer_id=sender_id)


# --- the team (admin Transfers desk) ---------------------------------------------------- #
async def admin_cancel(
    session: AsyncSession, *, transfer_id: uuid.UUID, actor_id: uuid.UUID | None, reason: str
) -> Transfer:
    reason = notification_service.plain_text(reason, 250)
    if len(reason) < 3:
        raise AppError(
            "REASON_REQUIRED", "Say why it is cancelled (the sender reads it).", status_code=422
        )
    t = await _locked(session, transfer_id)
    if t.status not in OPEN:
        raise AppError("NOT_OPEN", "This transfer is already closed.", status_code=409)
    await _close(
        session,
        t,
        "cancelled",
        f"Cancelled by Capimax PropShare: {reason}",
        now=_utcnow(),
        actor_id=actor_id,
    )
    return t


async def admin_deliver(
    session: AsyncSession, *, transfer_id: uuid.UUID, actor_id: uuid.UUID | None
) -> Transfer:
    """Try the delivery now (a waiting transfer whose recipient has just verified, or a due one
    the next run has not reached)."""
    t = await _locked(session, transfer_id)
    if t.status not in OPEN:
        raise AppError("NOT_OPEN", "This transfer is already closed.", status_code=409)
    now = _utcnow()
    if t.deliver_on > now.date():
        raise AppError(
            "NOT_DUE",
            f"It is scheduled for {t.deliver_on.strftime('%d %b %Y')}: the sender chose that date.",
            status_code=409,
        )
    recipient = await account_service.confirmed_by_address(session, t.recipient_email)
    if not await _ready(session, recipient):
        raise AppError(
            "RECIPIENT_NOT_READY",
            "The recipient has not confirmed their email and verified their identity yet.",
            status_code=409,
        )
    await _deliver(session, t, now=now)
    await write_audit(
        session,
        action="transfer.deliver_now",
        entity_type="transfer",
        entity_id=str(t.id),
        actor_id=actor_id,
        after={"status": t.status},
    )
    return t


async def list_for_admin(
    session: AsyncSession,
    *,
    status: str | None = None,
    asset: str | None = None,
    search: str | None = None,
    limit: int = 300,
) -> list[tuple[Transfer, str | None]]:
    q = (
        select(Transfer, User.email)
        .outerjoin(User, User.id == Transfer.sender_id)
        .order_by(Transfer.created_at.desc())
        .limit(limit)
    )
    if status:
        q = q.where(Transfer.status == status)
    if asset:
        q = q.where(Transfer.asset == asset)
    if search:
        s = f"%{search.strip().lower()}%"
        q = q.where(
            or_(
                func.lower(Transfer.reference).like(s),
                func.lower(Transfer.recipient_email).like(s),
                func.lower(User.email).like(s),
            )
        )
    return [(t, email) for t, email in (await session.execute(q)).all()]


async def close_open_for(session: AsyncSession, *, user_id: uuid.UUID, reason: str) -> int:
    """Cancel every transfer this member sent that has not been delivered (their estate is
    being settled): the units and money come back to their holding and wallet first, so they
    are divided with the rest."""
    rows = (
        (
            await session.execute(
                select(Transfer)
                .where(Transfer.sender_id == user_id, Transfer.status.in_(OPEN))
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    for t in rows:
        await _close(session, t, "cancelled", reason, now=_utcnow())
    return len(rows)


# --- handover when a recipient verifies; the cron ------------------------------------- #
async def release_for_user(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """The account just confirmed its email or got its identity verified: deliver the due
    transfers addressed to it. Repeats nothing (only open, due transfers are touched)."""
    user = await session.get(User, user_id)
    if not await _ready(session, user):
        return 0
    assert user is not None
    rows = (
        (
            await session.execute(
                select(Transfer)
                .where(
                    func.lower(Transfer.recipient_email) == user.email.strip().lower(),
                    Transfer.status == "waiting",
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    now = _utcnow()
    delivered = 0
    for t in rows:
        if await _deliver(session, t, now=now) == "delivered":
            delivered += 1
    return delivered


async def run_due(session: AsyncSession, *, now: dt.datetime | None = None) -> dict:
    """Deliver the transfers whose date has come, then return the ones nobody received in
    time. Rows locked by another run are skipped (SKIP LOCKED)."""
    now = now or _utcnow()
    # the sender is reminded once of what goes out in the next days (they can still cancel)
    soon = (
        (
            await session.execute(
                select(Transfer)
                .where(
                    Transfer.status == "scheduled",
                    Transfer.reminder_sent_at.is_(None),
                    Transfer.deliver_on > now.date(),
                    Transfer.deliver_on <= now.date() + dt.timedelta(days=REMINDER_DAYS),
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for t in soon:
        await notification_service.notify(
            session,
            user_id=t.sender_id,
            type="transfer",
            title=f"Transfer {t.reference} goes out soon",
            message=(
                f"{describe(t)} to {t.recipient_name or t.recipient_email} goes out on "
                f"{t.deliver_on.strftime('%d %b %Y')}. "
                "You can still cancel it on the Transfers tab."
            ),
            email_category="investment_updates",
        )
        t.reminder_sent_at = now
    due = (
        (
            await session.execute(
                select(Transfer)
                .where(Transfer.status == "scheduled", Transfer.deliver_on <= now.date())
                .order_by(Transfer.created_at)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    out = {"delivered": 0, "waiting": 0, "failed": 0, "expired": 0}
    for t in due:
        status = await _deliver(session, t, now=now)
        if status in out:
            out[status] += 1
    # a recipient who became ready without the handover reaching them (it failed, or a path
    # missed it) receives now; nobody qualified is ever sent back
    waiting = (
        (
            await session.execute(
                select(Transfer)
                .where(Transfer.status == "waiting")
                .order_by(Transfer.created_at)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for t in waiting:
        if await _deliver(session, t, now=now) == "delivered":
            out["delivered"] += 1
    stale = (
        (
            await session.execute(
                select(Transfer)
                .where(Transfer.status == "waiting", Transfer.expires_at < now)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for t in stale:
        await _close(
            session,
            t,
            "expired",
            f"Not received within {CLAIM_DAYS} days, so it was returned to you.",
            now=now,
        )
        out["expired"] += 1
    return out


# --- the people involved are told ------------------------------------------------------ #
async def _tell_waiting(session: AsyncSession, t: Transfer) -> None:
    to = t.recipient_name or t.recipient_email
    await notification_service.notify(
        session,
        user_id=t.sender_id,
        type="transfer",
        title=f"Transfer {t.reference} is waiting for {to}",
        message=(
            f"{describe(t)} is held for {to}. We invited them: it reaches them as soon as they "
            f"confirm their email and verify their identity. If they do not within {CLAIM_DAYS} "
            "days it comes back to you, and you can cancel it before then."
        ),
        email_category="investment_updates",
    )
    sender = await _name(session, t.sender_id)
    base = get_settings().app_base_url.rstrip("/")
    expires = t.expires_at.strftime("%d %b %Y") if t.expires_at else ""
    body = (
        f"{sender} sent you {describe(t)} on Capimax PropShare (transfer {t.reference}).\n\n"
        + (f'Their message: "{t.message}"\n\n' if t.message else "")
        + "To receive it, sign in (or create your account) with this email address, confirm it, "
        f"and verify your identity by {expires}. It is handed to you as soon as you do; "
        "after that date it goes back to the sender.\n\n"
        f"{base}/auth\n"
    )
    # an account is told in-app only once it confirmed this address (anyone can register
    # an address they do not own); otherwise the email goes to the address itself
    member = await account_service.confirmed_by_address(session, t.recipient_email)
    if member is not None and member.closed_at is None:
        await notification_service.notify(
            session,
            user_id=member.id,
            type="transfer",
            title=f"{sender} sent you a transfer",
            message=(
                f"{describe(t)} is waiting for you. Confirm your email and verify your identity "
                f"by {expires} to receive it."
            ),
            email_category="investment_updates",
            force_email=True,
            email_subject=f"{sender} sent you a transfer on Capimax PropShare",
            email_body=body,
        )
    elif member is None:
        notification_service.email_external(
            session,
            to_email=t.recipient_email,
            subject=f"{sender} sent you a transfer on Capimax PropShare",
            body=body,
            category="invite",
        )


async def _tell_delivered(session: AsyncSession, t: Transfer, recipient_id: uuid.UUID) -> None:
    sender = await _name(session, t.sender_id)
    where = "your holdings" if t.asset == "units" else "your wallet"
    if t.asset == "plan":
        plan = await session.get(InstallmentPlan, t.new_plan_id) if t.new_plan_id else None
        left = []
        if plan is not None:
            left = [
                p
                for p in await installment_service._payments_for(session, plan.id)
                if p.status != "paid"
            ]
        owed = _q(sum((p.total_amount for p in left), decimal.Decimal("0")))
        next_due = min((p.due_date for p in left), default=None)
        body = (
            f"{describe(t)} is now yours (transfer {t.reference}), as an installment plan in "
            f"your name: {len(left)} installment(s) remain ({_money(owed)} with fees), charged "
            "from your wallet on their dates."
            + (f" The next one is due on {next_due.isoformat()}." if next_due else "")
            + " The plan and its schedule are in your dashboard."
        )
    else:
        body = f"{describe(t)} is now in {where} (transfer {t.reference})."
    await notification_service.notify(
        session,
        user_id=recipient_id,
        type="transfer",
        title=f"You received a transfer from {sender}",
        message=body + (f' Their message: "{t.message}"' if t.message else ""),
        email_category="investment_updates",
    )
    await notification_service.notify(
        session,
        user_id=t.sender_id,
        type="transfer",
        title=f"Transfer {t.reference} delivered",
        message=f"{describe(t)} reached {t.recipient_name or t.recipient_email}.",
        email_category="investment_updates",
    )


# --- reading --------------------------------------------------------------------------- #
async def serialize(session: AsyncSession, t: Transfer, *, viewer_id: uuid.UUID) -> dict:
    sent = t.sender_id == viewer_id
    return {
        "id": t.id,
        "reference": t.reference,
        "direction": "sent" if sent else "received",
        # the sender sees who they wrote to; the recipient sees the sender's name, not email
        "counterparty": (
            (t.recipient_name or t.recipient_email) if sent else await _name(session, t.sender_id)
        ),
        "recipient_email": t.recipient_email if sent else None,
        "asset": t.asset,
        "property_id": t.property_id,
        "property_title": t.property_title,
        # 0042: units of an installment plan: the sender's plan, and the plan the recipient got
        "plan_id": t.plan_id if sent else None,
        "new_plan_id": t.new_plan_id if not sent else None,
        "units": t.units,
        "unit_price": str(t.unit_price) if t.unit_price is not None else None,
        "amount": str(t.amount),
        "fee": str(t.fee) if sent else "0.00",
        "message": t.message,
        "occasion": t.occasion,
        "deliver_on": t.deliver_on,
        "status": t.status,
        "status_label": STATUS_LABELS.get(t.status, t.status),
        "expires_at": t.expires_at,
        "delivered_at": t.delivered_at,
        "closed_reason": t.closed_reason if sent else None,
        "created_at": t.created_at,
        "can_cancel": sent and t.status in OPEN,
    }


async def list_for_user(session: AsyncSession, user_id: uuid.UUID, *, limit: int = 200) -> list:
    """The member's transfers: every one they sent, and the ones delivered to them."""
    rows = (
        (
            await session.execute(
                select(Transfer)
                .where(
                    or_(
                        Transfer.sender_id == user_id,
                        (Transfer.recipient_id == user_id) & (Transfer.status == "delivered"),
                    )
                )
                .order_by(Transfer.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [await serialize(session, t, viewer_id=user_id) for t in rows]
