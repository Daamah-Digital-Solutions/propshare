"""Read-own tools: the signed-in user's OWN data, always scoped by ``ctx.user_id``.

Every output model is an allow-list. Deliberately absent everywhere: identity documents and
provider ids, full email/phone, family members' personal data (date of birth, national id,
phone, address, bank accounts), counterparties on trades, storage keys, raw payloads.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Property, SupportTicket, SupportTicketMessage
from app.models.identity import User
from app.services import (
    auth_service,
    broker_service,
    certificate_service,
    distribution_service,
    family_service,
    installment_service,
    investment_service,
    kyc_service,
    liquidity_service,
    mfa_service,
    notification_service,
    payment_service,
    secondary_service,
    wallet_service,
    withdrawal_service,
)
from app.services.assistant import guard
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.base import NoArgs, ToolOutput, ToolSpec, register


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def _uid(ctx: AgentContext) -> uuid.UUID:
    assert ctx.user_id is not None  # guard.authorize refuses visitors before we get here
    return ctx.user_id


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    name, domain = email.split("@", 1)
    return f"{name[:2]}***@{domain}"


def mask_tail(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return None
    return "****" + value[-keep:]


# --------------------------------------------------------------------------- #
# account / kyc
# --------------------------------------------------------------------------- #
class AccountOut(ToolOutput):
    full_name: str | None
    email_masked: str | None
    roles: list[str]
    pending_roles: list[str]
    active_role: str | None
    kyc_status: str
    email_verified: bool
    two_factor_enabled: bool


async def _get_my_account(session: AsyncSession, ctx: AgentContext, args) -> dict:
    user = await session.get(User, _uid(ctx))
    if user is None:
        raise ValueError("unknown user")
    return {
        "full_name": user.full_name,
        "email_masked": mask_email(user.email),
        "roles": list(ctx.roles),
        "pending_roles": await auth_service.pending_role_names(session, user.id),
        "active_role": ctx.active_role,
        "kyc_status": ctx.kyc_status,
        "email_verified": bool(user.email_verified),
        "two_factor_enabled": await mfa_service.is_enabled(session, user.id),
    }


register(
    ToolSpec(
        "get_my_account",
        "The signed-in user's account: name, masked email, roles, active role, "
        "verification status, whether two-factor authentication is on.",
        NoArgs,
        AccountOut,
        "read_own",
        _get_my_account,
    )
)


class KycOut(ToolOutput):
    status: str
    manual_review_required: bool
    submitted_at: str | None
    verified_at: str | None
    rejection_reason: dict[str, str] | None  # untrusted free text


async def _get_my_kyc_status(session: AsyncSession, ctx: AgentContext, args) -> dict:
    kyc = await kyc_service.get_my_kyc(session, _uid(ctx))
    return {
        "status": str(kyc.status),
        "manual_review_required": bool(kyc.manual_review_required),
        "submitted_at": _iso(kyc.submitted_at),
        "verified_at": _iso(kyc.verified_at),
        "rejection_reason": guard.wrap_untrusted(kyc.rejection_reason),
    }


register(
    ToolSpec(
        "get_my_kyc_status",
        "Identity verification (KYC) status of the signed-in user and why it was rejected, "
        "if it was. No documents or provider details.",
        NoArgs,
        KycOut,
        "read_own",
        _get_my_kyc_status,
    )
)


# --------------------------------------------------------------------------- #
# wallet / transactions / payments / withdrawals
# --------------------------------------------------------------------------- #
class WalletOut(ToolOutput):
    balance: str
    pending_balance: str
    total_invested: str
    total_returns: str
    currency: str
    as_of: str


async def _get_my_wallet(session: AsyncSession, ctx: AgentContext, args) -> dict:
    from app.core.config import get_settings

    w = await wallet_service.get_wallet(session, _uid(ctx))
    return {
        "balance": str(w.balance),
        "pending_balance": str(w.pending_balance),
        "total_invested": str(w.total_invested),
        "total_returns": str(w.total_returns),
        "currency": get_settings().wallet_currency,
        "as_of": _now(),
    }


register(
    ToolSpec(
        "get_my_wallet",
        "The signed-in user's wallet balances (available, pending, invested, returns).",
        NoArgs,
        WalletOut,
        "read_own",
        _get_my_wallet,
    )
)


class PagingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=10, ge=1, le=25)


class TransactionOut(ToolOutput):
    id: str
    type: str
    amount: str
    status: str
    payment_method: str | None
    reference_id: str | None
    description: dict[str, str] | None
    created_at: str


class TransactionsOut(ToolOutput):
    items: list[TransactionOut]
    total: int


async def _list_my_transactions(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: PagingIn = args
    rows, total = await wallet_service.list_transactions(session, _uid(ctx), limit=a.limit)
    return {
        "items": [
            {
                "id": str(t.id),
                "type": str(t.type),
                "amount": str(t.amount),
                "status": t.status,
                "payment_method": str(t.payment_method) if t.payment_method else None,
                "reference_id": str(t.reference_id) if t.reference_id else None,
                "description": guard.wrap_untrusted(t.description),
                "created_at": _iso(t.created_at),
            }
            for t in rows
        ],
        "total": int(total),
    }


register(
    ToolSpec(
        "list_my_transactions",
        "Latest wallet transactions of the signed-in user (deposits, investments, returns, "
        "withdrawals, fees).",
        PagingIn,
        TransactionsOut,
        "read_own",
        _list_my_transactions,
    )
)


class PaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_id: str = Field(min_length=36, max_length=36)


class PaymentOut(ToolOutput):
    id: str
    provider: str
    amount: str
    amount_captured: str | None
    currency: str
    status: str
    purpose: str
    payment_method: str | None
    related_investment_id: str | None
    created_at: str
    updated_at: str


async def _get_payment_status(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: PaymentIn = args
    p = await payment_service.get_payment(
        session, user_id=_uid(ctx), payment_id=uuid.UUID(a.payment_id)
    )
    return {
        "id": str(p.id),
        "provider": p.provider,
        "amount": str(p.amount),
        "amount_captured": str(p.amount_captured) if p.amount_captured is not None else None,
        "currency": p.currency,
        "status": p.status,
        "purpose": p.purpose,
        "payment_method": p.payment_method,
        "related_investment_id": str(p.related_investment_id) if p.related_investment_id else None,
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
    }


register(
    ToolSpec(
        "get_payment_status",
        "Status of one of the signed-in user's payments (card/crypto deposit or purchase) "
        "by payment id.",
        PaymentIn,
        PaymentOut,
        "read_own",
        _get_payment_status,
    )
)


class WithdrawalOut(ToolOutput):
    id: str
    amount: str
    method: str
    status: str
    speed: str
    fee: str
    net_amount: str
    destination_masked: str | None
    failure_reason: dict[str, str] | None
    created_at: str
    completed_at: str | None


class WithdrawalsOut(ToolOutput):
    items: list[WithdrawalOut]


def _mask_destination(dest: Any) -> str | None:
    if not isinstance(dest, dict):
        return None
    for key in ("iban", "account_number", "address", "wallet_address", "email"):
        v = dest.get(key)
        if v:
            return mask_tail(str(v))
    label = dest.get("label") or dest.get("bank_name")
    return str(label) if label else None


async def _list_my_withdrawals(session: AsyncSession, ctx: AgentContext, args) -> dict:
    rows = await withdrawal_service.list_my_withdrawals(session, _uid(ctx))
    return {
        "items": [
            {
                "id": str(w.id),
                "amount": str(w.amount),
                "method": w.method,
                "status": w.status,
                "speed": w.speed or "standard",
                "fee": str(w.fee or 0),
                "net_amount": str(w.amount - (w.fee or 0)),
                "destination_masked": _mask_destination(w.destination),
                "failure_reason": guard.wrap_untrusted(w.failure_reason),
                "created_at": _iso(w.created_at),
                "completed_at": _iso(w.completed_at),
            }
            for w in rows[:25]
        ]
    }


register(
    ToolSpec(
        "list_my_withdrawals",
        "The signed-in user's withdrawal requests: status, speed (standard or instant), "
        "fee and the net amount paid out. Destinations are masked.",
        NoArgs,
        WithdrawalsOut,
        "read_own",
        _list_my_withdrawals,
    )
)


# --------------------------------------------------------------------------- #
# investments / portfolio / returns / installments
# --------------------------------------------------------------------------- #
class InvestmentOut(ToolOutput):
    id: str
    property_id: str
    property_title: str | None
    property_slug: str | None
    units: int
    amount: str
    status: str
    payment_method: str | None
    created_at: str


class InvestmentsOut(ToolOutput):
    items: list[InvestmentOut]


async def _titles(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, Property]:
    if not ids:
        return {}
    rows = (await session.execute(select(Property).where(Property.id.in_(ids)))).scalars()
    return {p.id: p for p in rows}


async def _list_my_investments(session: AsyncSession, ctx: AgentContext, args) -> dict:
    rows = await investment_service.list_my_investments(session, _uid(ctx))
    props = await _titles(session, {r.property_id for r in rows})
    return {
        "items": [
            {
                "id": str(i.id),
                "property_id": str(i.property_id),
                "property_title": props[i.property_id].title if i.property_id in props else None,
                "property_slug": props[i.property_id].slug if i.property_id in props else None,
                "units": i.units,
                "amount": str(i.amount),
                "status": str(i.status),
                "payment_method": str(i.payment_method) if i.payment_method else None,
                "created_at": _iso(i.created_at),
            }
            for i in rows[:50]
        ]
    }


register(
    ToolSpec(
        "list_my_investments",
        "The signed-in user's investments (property, units, amount, status).",
        NoArgs,
        InvestmentsOut,
        "read_own",
        _list_my_investments,
    )
)


class PortfolioOut(ToolOutput):
    invested: str
    current_value: str
    total_returns: str
    properties: int
    units: int
    sold: str
    as_of: str


async def _get_my_portfolio(session: AsyncSession, ctx: AgentContext, args) -> dict:
    return {**(await investment_service.portfolio_summary(session, _uid(ctx))), "as_of": _now()}


register(
    ToolSpec(
        "get_my_portfolio",
        "Portfolio totals of the signed-in user: invested (everything bought so far), current "
        "value (holdings at each property's current unit price; a running installment plan "
        "counts as its position: all its units at that price less the principal still to "
        "pay), sold (what selling units and positions brought in), returns (distributions), "
        "number of properties and units. The gain so far is current_value + sold - invested.",
        NoArgs,
        PortfolioOut,
        "read_own",
        _get_my_portfolio,
    )
)


class ReturnItem(ToolOutput):
    distribution_id: str
    property_id: str
    kind: str
    period_key: str
    period_end: str
    units: int
    gross_amount: str
    management_fee: str
    net_amount: str


class ReturnsOut(ToolOutput):
    items: list[ReturnItem]
    monthly: list[dict[str, str]]
    total_net: str
    total_fees: str


async def _list_my_returns(session: AsyncSession, ctx: AgentContext, args) -> dict:
    data = await distribution_service.my_returns(session, _uid(ctx))
    keep = ReturnItem.model_fields.keys()
    return {
        "items": [{k: it[k] for k in keep if k in it} for it in data.get("items", [])[:50]],
        "monthly": data.get("monthly", []),
        "total_net": str(data.get("total_net", "0")),
        "total_fees": str(data.get("total_fees", "0")),
    }


register(
    ToolSpec(
        "list_my_returns",
        "Rental distributions the signed-in user received, with a monthly summary.",
        NoArgs,
        ReturnsOut,
        "read_own",
        _list_my_returns,
    )
)


class PlanPayment(ToolOutput):
    seq: int
    kind: str
    due_date: str | None
    total_amount: str
    vest_units: int
    status: str
    paid_at: str | None


class PlanOut(ToolOutput):
    id: str
    property_title: str | None
    property_slug: str | None
    units_total: int
    unit_price: str
    down_payment_pct: int
    duration_months: int
    fee_rate: str
    vested_units: int
    status: str
    next_due: PlanPayment | None
    payments: list[PlanPayment]
    # a running plan as a position, at the property's current unit price: what all its units
    # are worth, the principal still to pay, and the holder's part (equity = value - remaining
    # = cost + gain). cost = what the user has put in: the installments paid, or, for a plan
    # taken over from another investor (taken_over = true), what they paid for it plus their
    # own installments since. entry_price = the price per unit the user got in at (the plan's
    # unit_price, or the price they bought the position at); gain = units x (price now -
    # entry_price). for_sale = listed on the secondary market
    position_value: str | None = None
    remaining_principal: str | None = None
    equity: str | None = None
    entry_price: str | None = None
    cost: str | None = None
    gain: str | None = None
    taken_over: bool = False
    for_sale: bool = False


class PlansOut(ToolOutput):
    items: list[PlanOut]


async def _list_my_installment_plans(session: AsyncSession, ctx: AgentContext, args) -> dict:
    plans = await installment_service.list_plans(session, _uid(ctx))
    out = []
    for p in plans[:20]:
        pays = [
            {
                "seq": x["seq"],
                "kind": x["kind"],
                "due_date": _iso(x["due_date"]),
                "total_amount": x["total_amount"],
                "vest_units": x["vest_units"],
                "status": x["status"],
                "paid_at": _iso(x["paid_at"]),
            }
            for x in p["payments"]
        ]
        pending = [x for x in pays if x["status"] not in ("paid",)]
        out.append(
            {
                "id": str(p["id"]),
                "property_title": p["property_title"],
                "property_slug": p["property_slug"],
                "units_total": p["units_total"],
                "unit_price": p["unit_price"],
                "down_payment_pct": p["down_payment_pct"],
                "duration_months": p["duration_months"],
                "fee_rate": p["fee_rate"],
                "vested_units": p["vested_units"],
                "status": p["status"],
                "next_due": pending[0] if pending else None,
                "payments": pays,
                "position_value": (p.get("position") or {}).get("value"),
                "remaining_principal": (p.get("position") or {}).get("remaining_principal"),
                "equity": (p.get("position") or {}).get("equity"),
                "entry_price": (p.get("position") or {}).get("entry_price"),
                "cost": (p.get("position") or {}).get("cost"),
                "gain": (p.get("position") or {}).get("gain"),
                "taken_over": p.get("acquired_at") is not None,
                "for_sale": p.get("listing_id") is not None,
            }
        )
    return {"items": out}


register(
    ToolSpec(
        "list_my_installment_plans",
        "The signed-in user's installment plans with their payment schedules and next due "
        "payment, and for a running plan what the position is worth now (all its units at the "
        "current unit price, less what is still to pay) and whether it is listed for sale.",
        NoArgs,
        PlansOut,
        "read_own",
        _list_my_installment_plans,
    )
)


# --------------------------------------------------------------------------- #
# holdings / secondary / liquidity
# --------------------------------------------------------------------------- #
class HeldBackOut(ToolOutput):
    listed: int
    lp_exit: int
    family_pending: int
    gift: int
    installment_plan: int
    pledged: int


class HoldingOut(ToolOutput):
    property_id: str
    title: str | None
    location: str | None
    units: int
    sellable_units: int
    # why the other units cannot be sold right now, by reason
    held_back: HeldBackOut
    # the resale lock-up still running on this holding (ISO date), if any
    lockup_until: str | None
    unit_price: str  # the price of a unit NOW
    value: str  # units x unit_price
    launch_price: str | None  # the price the listing started at
    price_change_pct: str | None  # unit_price against the launch price
    price_updated_at: str | None  # when the platform last gave the property a new price
    average_cost: str | None  # what these units cost the user per unit, on average
    # printed on the investment certificate; the number to enter at Capimax Verify
    certificate_reference: str


class PositionOut(ToolOutput):
    """A running installment plan as a position the user could sell, whole."""

    plan_id: str
    property_title: str | None
    units: int  # every unit of the plan, paid for or not
    vested_units: int
    # the price per unit the user got in at: the price the plan locked, or the price they
    # bought the position at from another investor
    entry_price: str
    unit_price: str  # the price of a unit now
    value: str  # units x unit_price
    # what the user has put in: the installments paid, or what they paid for the position
    # plus their own installments since
    cost: str
    remaining_principal: str  # what a buyer would take over, on the schedule's dates
    installments_left: int
    next_due: str | None
    gain: str  # units x (unit_price - entry_price)
    you_would_receive: str  # value - remaining_principal = cost + gain, at the current price
    listed: bool  # already offered on the secondary market
    blocked: str | None  # pledged | lockup | listed: why it cannot be listed now, if anything


class HoldingsOut(ToolOutput):
    items: list[HoldingOut]
    positions: list[PositionOut]
    note: str


_HELD_BACK_NOTE = (
    "sellable_units can be listed on the secondary market or offered to a liquidity provider "
    "now. held_back says why the rest cannot be listed one by one: listed = already on sale in "
    "an active listing; lp_exit = in an open liquidity-provider exit request; family_pending = "
    "promised to a family member who has not registered yet; gift = in a scheduled gift; "
    "installment_plan = vested under an installment plan that is still running: these are sold "
    "with the plan, whole, as one POSITION (see positions; prepare_sale with position=true): "
    "the buyer pays the seller what the seller put in plus the price change on all the plan's "
    "units since (you_would_receive = cost + gain) and takes over the remaining installments. "
    "A position already includes its vested units, which are also in items: never add a "
    "position to its holding (for the total value use get_my_portfolio). cost counts the "
    "principal paid, not the installment fees, which are not returned by a sale; "
    "pledged = pledged to Nova "
    "Finance for a Nova Sukuk certificate until staff release the pledge. lockup_until = the "
    "resale lock-up ends then. unit_price is the price now: the platform gives a property under "
    "construction a new price as it is revalued (price_change_pct is the move since launch); "
    "the gain on a holding is (unit_price - average_cost) x units."
)


async def _get_my_holdings(session: AsyncSession, ctx: AgentContext, args) -> dict:
    uid = _uid(ctx)
    rows = await secondary_service.my_holdings(session, uid)
    items = []
    for r in rows[:50]:
        lock = await secondary_service.lockup_until(session, uid, uuid.UUID(r["property_id"]))
        items.append(
            {
                "property_id": r["property_id"],
                "title": r["title"],
                "location": r["location"],
                "units": r["units"],
                "sellable_units": r["sellable_units"],
                "held_back": r["held_back"],
                "lockup_until": lock.date().isoformat() if lock else None,
                "unit_price": r["unit_price"],
                "value": f"{decimal.Decimal(r['unit_price']) * r['units']:.2f}",
                "launch_price": r.get("launch_price"),
                "price_change_pct": r.get("price_change_pct"),
                "price_updated_at": _iso(r.get("price_updated_at")),
                "average_cost": r.get("average_cost"),
                "certificate_reference": certificate_service.certificate_reference(
                    r["property_id"], uid
                ),
            }
        )
    positions = [
        {
            "plan_id": str(p["plan_id"]),
            "property_title": p["property_title"],
            "units": p["units"],
            "vested_units": p["vested_units"],
            "entry_price": p["entry_price"],
            "unit_price": p["unit_price"],
            "value": p["value"],
            "cost": p["cost"],
            "remaining_principal": p["remaining_principal"],
            "installments_left": p["installments_left"],
            "next_due": _iso(p["next_due"]),
            "gain": p["gain"],
            "you_would_receive": p["cash"],
            "listed": p["listing_id"] is not None,
            "blocked": p["blocked"],
        }
        for p in (await secondary_service.my_positions(session, uid))[:20]
    ]
    return {"items": items, "positions": positions, "note": _HELD_BACK_NOTE}


register(
    ToolSpec(
        "get_my_holdings",
        "Units the signed-in user holds per property: the unit price now, what it was at launch "
        "and what the holding cost; how many can be sold now and, for the rest, why not "
        "(already listed, in an exit request, on an installment plan still running, a pledge, "
        "a lock-up); the running installment plans as positions that can be sold whole (what "
        "the user would receive, what the buyer takes over); plus the reference printed on "
        "each property's investment certificate.",
        NoArgs,
        HoldingsOut,
        "read_own",
        _get_my_holdings,
    )
)


class ListingOut(ToolOutput):
    listing_id: str
    property_title: str | None
    units_for_sale: int
    units_remaining: int
    price_per_unit: str
    status: str
    created_at: str | None
    # an installment plan position (sold whole): what the buyer pays the seller, and the
    # principal the buyer takes over
    is_position: bool = False
    buyer_pays_you: str | None = None
    buyer_takes_over: str | None = None


class ListingsOut(ToolOutput):
    items: list[ListingOut]


async def _list_my_secondary_listings(session: AsyncSession, ctx: AgentContext, args) -> dict:
    rows = await secondary_service.list_my_listings(session, _uid(ctx))
    keep = ("property_title", "units_for_sale", "units_remaining", "price_per_unit", "status")
    return {
        "items": [
            {
                **{k: r.get(k) for k in keep},
                "listing_id": str(r["listing_id"]),
                "created_at": r.get("created_at"),
                "is_position": r.get("plan_id") is not None,
                "buyer_pays_you": (r.get("position") or {}).get("cash"),
                "buyer_takes_over": (r.get("position") or {}).get("remaining_principal"),
            }
            for r in rows[:50]
        ]
    }


register(
    ToolSpec(
        "list_my_secondary_listings",
        "The signed-in user's own secondary-market sale listings and their status.",
        NoArgs,
        ListingsOut,
        "read_own",
        _list_my_secondary_listings,
    )
)


class ExitRequestOut(ToolOutput):
    request_id: str
    property_title: str | None
    units: int
    units_remaining: int
    unit_price: str
    lp_price: str
    seller_net: str
    status: str
    created_at: str | None
    expires_at: str | None


class ExitRequestsOut(ToolOutput):
    items: list[ExitRequestOut]


async def _list_my_liquidity_requests(session: AsyncSession, ctx: AgentContext, args) -> dict:
    rows = await liquidity_service.list_my_exit_requests(session, _uid(ctx))
    keep = ExitRequestOut.model_fields.keys()
    return {
        "items": [
            {k: (str(r[k]) if k == "request_id" else r.get(k)) for k in keep} for r in rows[:50]
        ]
    }


register(
    ToolSpec(
        "list_my_liquidity_requests",
        "The signed-in user's liquidity-provider exit requests and their status.",
        NoArgs,
        ExitRequestsOut,
        "read_own",
        _list_my_liquidity_requests,
    )
)


# --------------------------------------------------------------------------- #
# notifications / family / role application / broker / tickets
# --------------------------------------------------------------------------- #
class NotificationOut(ToolOutput):
    id: str
    title: dict[str, str] | None
    message: dict[str, str] | None
    type: str
    read: bool
    created_at: str


class NotificationsOut(ToolOutput):
    items: list[NotificationOut]
    unread: int


async def _list_my_notifications(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: PagingIn = args
    rows, _total, unread = await notification_service.list_for_user(
        session, _uid(ctx), limit=a.limit
    )
    return {
        "items": [
            {
                "id": str(n.id),
                "title": guard.wrap_untrusted(n.title),
                "message": guard.wrap_untrusted(n.message),
                "type": n.type,
                "read": bool(n.read),
                "created_at": _iso(n.created_at),
            }
            for n in rows
        ],
        "unread": int(unread),
    }


register(
    ToolSpec(
        "list_my_notifications",
        "Latest notifications of the signed-in user and the unread count.",
        PagingIn,
        NotificationsOut,
        "read_own",
        _list_my_notifications,
    )
)


class FamilyMemberOut(ToolOutput):
    name: str
    relationship: str | None
    is_verified: bool
    is_user: bool
    pending_units: int


class FamilyOut(ToolOutput):
    has_group: bool
    name: str | None
    total_returns: str | None
    members: list[FamilyMemberOut]


async def _get_my_family_group(session: AsyncSession, ctx: AgentContext, args) -> dict:
    view = await family_service.get_group_view(session, _uid(ctx))
    if not view:
        return {"has_group": False, "name": None, "total_returns": None, "members": []}
    return {
        "has_group": True,
        "name": view.get("name"),
        "total_returns": view.get("total_returns"),
        "members": [
            {
                "name": m.get("name"),
                "relationship": m.get("relationship"),
                "is_verified": bool(m.get("is_verified")),
                "is_user": bool(m.get("is_user")),
                "pending_units": int(m.get("pending_units") or 0),
            }
            for m in view.get("members", [])
        ],
    }


register(
    ToolSpec(
        "get_my_family_group",
        "The signed-in user's family investment group: name, members (names and "
        "relationships only) and allocated units.",
        NoArgs,
        FamilyOut,
        "read_own",
        _get_my_family_group,
    )
)


class RoleApplicationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern="^(broker|liquidity_provider)$")


class RoleApplicationOut(ToolOutput):
    role: str
    status: str | None
    submitted_at: str | None
    documents: list[dict[str, str]]


async def _get_my_role_application(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: RoleApplicationIn = args
    req = await auth_service.get_pending_application(session, user_id=_uid(ctx), role=a.role)
    if req is None:
        return {"role": a.role, "status": None, "submitted_at": None, "documents": []}
    app = req.application if isinstance(req.application, dict) else {}
    return {
        "role": a.role,
        "status": req.status,
        "submitted_at": _iso(getattr(req, "created_at", None)),
        "documents": [{"label": str(d.get("label", ""))} for d in (app.get("documents") or [])],
    }


register(
    ToolSpec(
        "get_my_role_application",
        "Status of the signed-in user's pending application for the broker or liquidity "
        "provider role.",
        RoleApplicationIn,
        RoleApplicationOut,
        "read_own",
        _get_my_role_application,
    )
)


class BrokerOut(ToolOutput):
    referral_code: str | None
    commission_rate: str
    total_referrals: int
    total_commission: str


async def _get_my_broker_dashboard(session: AsyncSession, ctx: AgentContext, args) -> dict:
    data = await broker_service.dashboard(session, _uid(ctx))
    code = await broker_service.get_or_create_code(session, _uid(ctx))
    return {
        "referral_code": getattr(code, "code", None),
        "commission_rate": data["commission_rate"],
        "total_referrals": data["total_referrals"],
        "total_commission": data["total_commission"],
    }


register(
    ToolSpec(
        "get_my_broker_dashboard",
        "Broker figures for the signed-in broker: referral code, referral count, "
        "commission rate and total.",
        NoArgs,
        BrokerOut,
        "read_own",
        _get_my_broker_dashboard,
        roles=("broker",),
    )
)


class TicketMessageOut(ToolOutput):
    author_type: str
    body: dict[str, str] | None
    created_at: str


class TicketOut(ToolOutput):
    ticket_no: str
    status: str
    category: str | None
    priority: str
    subject: dict[str, str] | None
    created_at: str
    updated_at: str
    messages: list[TicketMessageOut]


class TicketsOut(ToolOutput):
    items: list[TicketOut]


def _ticket_dict(t: SupportTicket, msgs: list[SupportTicketMessage]) -> dict:
    return {
        "ticket_no": t.ticket_no,
        "status": t.status,
        "category": t.category,
        "priority": t.priority,
        "subject": guard.wrap_untrusted(t.subject),
        "created_at": _iso(t.created_at),
        "updated_at": _iso(t.updated_at),
        "messages": [
            {
                "author_type": m.author_type,
                "body": guard.wrap_untrusted(m.body),
                "created_at": _iso(m.created_at),
            }
            for m in msgs
            if not m.internal  # staff-only notes never reach the user or the model
        ],
    }


async def _list_my_tickets(session: AsyncSession, ctx: AgentContext, args) -> dict:
    rows = (
        (
            await session.execute(
                select(SupportTicket)
                # only real support tickets: the assistant's own knowledge-gap records are the
                # team's, and the user's ticket pages would not open them either
                .where(SupportTicket.user_id == _uid(ctx), SupportTicket.kind == "support")
                .order_by(SupportTicket.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_ticket_dict(t, []) for t in rows]}


register(
    ToolSpec(
        "list_my_tickets",
        "The signed-in user's support tickets and their status.",
        NoArgs,
        TicketsOut,
        "read_own",
        _list_my_tickets,
    )
)


class TicketIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_no: str = Field(pattern=r"^CPX-\d{6}$")


async def _get_my_ticket(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: TicketIn = args
    t = await session.scalar(
        select(SupportTicket).where(
            SupportTicket.ticket_no == a.ticket_no,
            SupportTicket.user_id == _uid(ctx),
            SupportTicket.kind == "support",
        )
    )
    if t is None:
        from app.core.errors import AppError

        raise AppError("NOT_FOUND", "No such ticket on this account.", status_code=404)
    msgs = (
        (
            await session.execute(
                select(SupportTicketMessage)
                .where(SupportTicketMessage.ticket_id == t.id)
                .order_by(SupportTicketMessage.created_at)
            )
        )
        .scalars()
        .all()
    )
    return _ticket_dict(t, list(msgs))


register(
    ToolSpec(
        "get_my_ticket",
        "One of the signed-in user's support tickets with its message thread (staff notes "
        "excluded).",
        TicketIn,
        TicketOut,
        "read_own",
        _get_my_ticket,
    )
)
