"""Portfolio preparation tools: a secondary-market sale or an installment payment, prepared
inside the chat up to the user's own click (owner's principle: the assistant prepares
everything, the user presses the last button).

Nothing here lists, sells or pays. ``prepare_sale`` applies the listing endpoint's rules
(ownership, units already reserved, lock-up, price bounds, verification) and works out what
the seller receives and what a buyer pays on top; ``prepare_installment_payment`` finds the
next unpaid installment and checks the wallet covers it. The server turns each result into a
card whose link opens the platform's own form, pre-filled, where the user confirms.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.errors import AppError
from app.models import Property
from app.services import installment_service, secondary_service, settings_service, wallet_service
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.base import ToolOutput, ToolSpec, register
from app.services.assistant.tools.wallet import kyc_note

_CENTS = decimal.Decimal("0.01")


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


def _now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def pick_by_name(query: str, rows: list[dict], *, what: str) -> dict:
    """The row the user means, from their own list: an exact id or slug, else the title words
    (all of them, in any order). Ambiguous or unknown names are errors the model relays."""
    q = query.strip().lower()
    for row in rows:
        if q and q in (str(row["id"]).lower(), (row.get("slug") or "").lower()):
            return row
    words = [w for w in re.split(r"[^\w]+", q) if w]
    hits = [r for r in rows if words and all(w in (r.get("title") or "").lower() for w in words)]
    exact = [r for r in hits if (r.get("title") or "").lower() == q]
    if len(exact) == 1 or len(hits) == 1:
        return (exact or hits)[0]
    titles = ", ".join(sorted({str(r.get("title")) for r in (hits or rows)}))
    if hits:
        raise AppError("AMBIGUOUS", f"'{query}' matches {titles}; say which one.", status_code=422)
    if not rows:
        raise AppError("NOTHING_HELD", f"You have no {what} yet.", status_code=404)
    raise AppError(
        "NOT_FOUND", f"No {what} matches '{query}'. You have: {titles}.", status_code=404
    )


# --------------------------------------------------------------------------- #
# prepare_sale (secondary market listing)
# --------------------------------------------------------------------------- #
class SalePrepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property: str = Field(
        min_length=1, max_length=160, description="The property held: its name, slug or id"
    )
    units: int = Field(ge=1, le=1_000_000, description="Units to list for sale")
    price_per_unit: float | None = Field(
        default=None,
        gt=0,
        le=100_000_000,
        description="Asking price per unit in USD; empty = the reference price",
    )


class SalePrepOut(ToolOutput):
    property_title: str
    property_id: str
    property_slug: str | None
    units: int
    price_per_unit: str
    reference_price: str  # the property's unit price
    vs_reference_pct: str  # asking price against the reference, e.g. "10.00" or "-5.00"
    you_receive: str  # units x price: the resale fee is paid by the buyer, on top
    resale_fee_pct: str
    buyer_fee: str
    buyer_pays: str
    units_held: int
    sellable_units: int
    ready: bool  # nothing blocks the Create Listing button
    notes: list[str]
    as_of: str


async def _prepare_sale(session, ctx: AgentContext, args) -> dict:
    a: SalePrepIn = args
    assert ctx.user_id is not None  # prepare_only: guard.authorize refuses visitors
    holdings = await secondary_service.my_holdings(session, ctx.user_id)
    slugs = dict(
        (
            await session.execute(
                select(Property.id, Property.slug).where(
                    Property.id.in_([uuid.UUID(h["property_id"]) for h in holdings] or [None])
                )
            )
        ).all()
    )
    rows = [
        {**h, "id": h["property_id"], "slug": slugs.get(uuid.UUID(h["property_id"]))}
        for h in holdings
    ]
    held = pick_by_name(a.property, rows, what="units in that property")
    prop = await session.get(Property, uuid.UUID(held["property_id"]))
    reference = decimal.Decimal(str(prop.unit_price))
    price = _q(decimal.Decimal(str(a.price_per_unit))) if a.price_per_unit else _q(reference)

    blocking: list[str] = []
    info: list[str] = []
    if a.price_per_unit is None:
        info.append(
            "No price was given, so this uses the reference price; change it before listing."
        )
    if a.units > held["sellable_units"]:
        reserved = held["units"] - held["sellable_units"]
        blocking.append(
            f"You can list up to {held['sellable_units']} units of this property"
            + (f" ({reserved} are already listed or reserved)." if reserved else ".")
        )
    sett = await settings_service.get_secondary_settings(session)
    lockup_days = int(sett["lockup_days"] or 0)
    if lockup_days > 0:
        first = await secondary_service._earliest_acquisition(session, ctx.user_id, prop.id)
        if first is not None and dt.datetime.now(dt.UTC) < first + dt.timedelta(days=lockup_days):
            unlock = (first + dt.timedelta(days=lockup_days)).date().isoformat()
            blocking.append(f"These units are in a {lockup_days}-day lock-up until {unlock}.")
    for bound, pct, word in (
        ("min", sett["price_min_pct"], "at least"),
        ("max", sett["price_max_pct"], "at most"),
    ):
        if pct is None:
            continue
        limit = _q(reference * pct / decimal.Decimal(100))
        if (bound == "min" and price < limit) or (bound == "max" and price > limit):
            blocking.append(
                f"The price must be {word} {limit:.2f} ({pct}% of the reference price)."
            )
    if kyc := kyc_note(ctx.kyc_status):
        blocking.append(kyc)

    fee_pct = decimal.Decimal(str(sett["resale_fee_pct"] or "0"))
    gross = _q(price * a.units)
    buyer_fee = _q(gross * fee_pct / decimal.Decimal(100))
    vs_reference = _q((price - reference) / reference * 100) if reference else decimal.Decimal(0)
    return {
        "property_title": prop.title,
        "property_id": str(prop.id),
        "property_slug": prop.slug,
        "units": a.units,
        "price_per_unit": f"{price:.2f}",
        "reference_price": f"{reference:.2f}",
        "vs_reference_pct": f"{vs_reference:.2f}",
        "you_receive": f"{gross:.2f}",
        "resale_fee_pct": f"{fee_pct.normalize():f}",
        "buyer_fee": f"{buyer_fee:.2f}",
        "buyer_pays": f"{(gross + buyer_fee):.2f}",
        "units_held": held["units"],
        "sellable_units": held["sellable_units"],
        "ready": not blocking,
        "notes": blocking + info,
        "as_of": _now(),
    }


register(
    ToolSpec(
        "prepare_sale",
        "Prepare a secondary-market listing of units the signed-in user holds: checks sellable "
        "units, lock-up, price limits and verification, and works out what the seller receives "
        "(the buyer pays the resale fee on top). The user then sees a sale card whose button "
        "opens the listing form pre-filled, stopping at their own Create Listing click.",
        SalePrepIn,
        SalePrepOut,
        "prepare_only",
        _prepare_sale,
    )
)


# --------------------------------------------------------------------------- #
# prepare_installment_payment
# --------------------------------------------------------------------------- #
class InstallmentPrepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property: str | None = Field(
        default=None,
        max_length=160,
        description="Which plan, by property name or slug; empty = the next one due of any plan",
    )


class InstallmentPrepOut(ToolOutput):
    property_title: str
    property_slug: str | None
    payment_id: str
    label: str  # "Month 3", "Final (Month 12)"
    due_date: str
    status: str  # scheduled | overdue
    base_amount: str
    fee_amount: str
    total_amount: str
    vest_units: int  # units that vest when it is paid
    unpaid_after: int  # installments still to pay after this one
    wallet_balance: str
    ready: bool  # nothing blocks the Pay button
    notes: list[str]
    auto_charge: str
    as_of: str


def _label(p: dict) -> str:
    if p["kind"] == "final":
        return f"Final (Month {p['seq']})"
    return f"Month {p['seq']}"


async def _prepare_installment_payment(session, ctx: AgentContext, args) -> dict:
    a: InstallmentPrepIn = args
    assert ctx.user_id is not None  # prepare_only: guard.authorize refuses visitors
    plans = [p for p in await installment_service.list_plans(session, ctx.user_id)]
    active = [p for p in plans if p["status"] == "active"]
    if a.property:
        rows = [{**p, "title": p["property_title"], "slug": p["property_slug"]} for p in active]
        active = [pick_by_name(a.property, rows, what="active installment plan")]
    # down payments are charged when a plan is created (seq 0): only later ones are payable
    due = [
        (p, pay)
        for p in active
        for pay in p["payments"]
        if pay["seq"] > 0 and pay["status"] in ("scheduled", "overdue")
    ]
    if not due:
        raise AppError(
            "NOTHING_DUE",
            "No installment is waiting to be paid." if plans else "You have no installment plans.",
            status_code=404,
        )
    plan, pay = min(due, key=lambda x: (x[1]["due_date"], x[1]["seq"]))
    total = decimal.Decimal(pay["total_amount"])
    wallet = await wallet_service.get_wallet(session, ctx.user_id)
    blocking: list[str] = []
    info: list[str] = []
    if wallet.balance < total:
        blocking.append(
            f"Your wallet has {wallet.balance:.2f}; add at least {(total - wallet.balance):.2f} "
            "before paying."
        )
    if kyc := kyc_note(ctx.kyc_status):
        blocking.append(kyc)
    if pay["status"] == "overdue":
        info.append(
            "This installment is overdue. It is retried automatically; there is no late fee."
        )
    unpaid_after = sum(
        1
        for x in plan["payments"]
        if x["seq"] > pay["seq"] and x["status"] in ("scheduled", "overdue")
    )
    return {
        "property_title": plan["property_title"],
        "property_slug": plan["property_slug"],
        "payment_id": str(pay["id"]),
        "label": _label(pay),
        "due_date": pay["due_date"].isoformat(),
        "status": pay["status"],
        "base_amount": pay["base_amount"],
        "fee_amount": pay["fee_amount"],
        "total_amount": pay["total_amount"],
        "vest_units": pay["vest_units"],
        "unpaid_after": unpaid_after,
        "wallet_balance": f"{wallet.balance:.2f}",
        "ready": not blocking,
        "notes": blocking + info,
        "auto_charge": "If nothing is done, it is charged from the wallet automatically on the "
        "due date.",
        "as_of": _now(),
    }


register(
    ToolSpec(
        "prepare_installment_payment",
        "Prepare paying the signed-in user's next installment now (optionally of one plan): the "
        "amount with its fee, the due date, the units it vests and whether the wallet covers "
        "it. The user then sees an installment card whose button opens the plan's payment "
        "confirmation, stopping at their own Pay click. Nothing is charged.",
        InstallmentPrepIn,
        InstallmentPrepOut,
        "prepare_only",
        _prepare_installment_payment,
    )
)
