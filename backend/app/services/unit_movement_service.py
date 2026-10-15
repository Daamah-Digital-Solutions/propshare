"""Unit movements: a member's own lines of the ownership ledger, said in words.

The investments page showed what a member holds but not how the units got there: units that
arrived by a family transfer looked exactly like units bought, and the member who sent them
saw only a smaller number (client, 2026-10-07: "it does the whole job but leaves no trace").
Every row of ``ownership_ledger`` that belongs to the caller is listed with what it was and,
for a movement between two people (a family transfer, an inheritance), who the other one was.

The ledger is the only source: nothing here is computed or stored a second time. The same
lines, for a period the member chooses, make the unit statement (``build_statement``,
rendered by ``unit_statement_render``; client, 2026-10-15: the wallet has a statement, the
units had none).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import (
    EstateBeneficiary,
    EstateEvent,
    EstateTransfer,
    FamilyMember,
    FamilyTransfer,
    OwnershipLedger,
    Property,
)
from app.models.identity import User

# every reason written to the ledger, as a member reads it
LABELS: dict[str, str] = {
    "purchase": "Purchase",
    "reinvest": "Bought with reinvested returns",
    "family_reinvest": "Bought at the family discount",
    "installment_vest": "Units released by an installment payment",
    "family_transfer_in": "Received from a family member",
    "family_transfer_out": "Transferred to a family member",
    "gift_transfer_in": "Gift received",
    "gift_transfer_out": "Gift sent",
    "estate_transfer_in": "Received as a designated beneficiary",
    "estate_transfer_out": "Transferred to a designated beneficiary",
    "secondary_purchase": "Bought on the secondary market",
    "secondary_sale": "Sold on the secondary market",
    "lp_buyback": "Sold to a liquidity provider",
    "lp_acquire": "Acquired as a liquidity provider",
}
_OTHER = "Units adjusted"


async def _account_names(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    res = await session.execute(select(User.id, User.full_name).where(User.id.in_(ids)))
    return {uid: (name or "").strip() for uid, name in res.all()}


async def list_for_user(session: AsyncSession, user_id: uuid.UUID, *, limit: int = 100) -> dict:
    """The caller's unit movements, newest first: ``{"items": [...], "total": n}``."""
    rows = (
        (
            await session.execute(
                select(OwnershipLedger)
                .where(OwnershipLedger.user_id == user_id)
                .order_by(OwnershipLedger.created_at.desc(), OwnershipLedger.id)
                .limit(min(max(limit, 1), 500))
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return {"items": [], "total": 0}
    titles = await _titles(session, {r.property_id for r in rows})
    other = await _counterparties(session, user_id, rows)
    items = [
        {
            "id": str(r.id),
            "at": r.created_at.isoformat() if r.created_at else None,
            "property_id": str(r.property_id),
            "property_title": titles.get(r.property_id, (None, None))[0],
            "units": r.units,
            "direction": "in" if r.units >= 0 else "out",
            "reason": r.reason,
            "label": LABELS.get(r.reason, _OTHER),
            "counterparty": other.get(r.ref_id) if r.ref_id else None,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


async def _titles(
    session: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[str | None, str | None]]:
    """``{property id: (title, slug)}``."""
    if not ids:
        return {}
    res = await session.execute(
        select(Property.id, Property.title, Property.slug).where(Property.id.in_(ids))
    )
    return {pid: (title, slug) for pid, title, slug in res.all()}


async def _counterparties(
    session: AsyncSession, user_id: uuid.UUID, rows: Sequence[OwnershipLedger]
) -> dict[uuid.UUID, str]:
    """For the rows that moved units between two people, the other person's name, by the
    ``ref_id`` of the row (the transfer both ledger rows point at)."""
    other: dict[uuid.UUID, str] = {}
    family_refs = {r.ref_id for r in rows if r.ref_id and r.reason.startswith("family_transfer")}
    if family_refs:
        transfers = (
            (
                await session.execute(
                    select(FamilyTransfer).where(FamilyTransfer.id.in_(family_refs))
                )
            )
            .scalars()
            .all()
        )
        member_ids = {t.to_member_id for t in transfers}
        member_ids |= {t.from_member_id for t in transfers if t.from_member_id}
        members = {
            m.id: m
            for m in (
                await session.execute(select(FamilyMember).where(FamilyMember.id.in_(member_ids)))
            )
            .scalars()
            .all()
        }
        sender_ids = (
            members[t.from_member_id].user_id for t in transfers if t.from_member_id in members
        )
        accounts = await _account_names(session, {uid for uid in sender_ids if uid is not None})
        for t in transfers:
            src = members.get(t.from_member_id) if t.from_member_id else None
            dst = members.get(t.to_member_id)
            if src is not None and src.user_id == user_id:
                # sent by the caller: the name they gave the member in their own group
                other[t.id] = (dst.name if dst else "") or "a family member"
            else:
                # received: the sender's account name, never their email address
                name = accounts.get(src.user_id, "") if src and src.user_id else ""
                other[t.id] = name or "a family member"

    estate_refs = {r.ref_id for r in rows if r.ref_id and r.reason.startswith("estate_transfer")}
    if estate_refs:
        res = await session.execute(
            select(EstateTransfer.id, EstateEvent.subject_user_id, EstateBeneficiary.full_name)
            .join(EstateEvent, EstateEvent.id == EstateTransfer.estate_event_id)
            .outerjoin(EstateBeneficiary, EstateBeneficiary.id == EstateTransfer.beneficiary_id)
            .where(EstateTransfer.id.in_(estate_refs))
        )
        found = res.all()
        holders = await _account_names(session, {subject for _id, subject, _name in found})
        for transfer_id, subject, beneficiary_name in found:
            if subject == user_id:
                other[transfer_id] = beneficiary_name or "a designated beneficiary"
            else:
                other[transfer_id] = holders.get(subject, "") or "the account holder"
    return other


# --- the unit statement ------------------------------------------------------------ #
@dataclasses.dataclass(frozen=True)
class UnitRow:
    at: dt.datetime
    property_title: str
    label: str
    counterparty: str
    units: int  # signed: units in > 0, units out < 0
    balance: int  # units held in this property after the row
    reference: str


@dataclasses.dataclass(frozen=True)
class PropertyLine:
    property_title: str
    opening: int
    units_in: int
    units_out: int  # positive number
    closing: int


@dataclasses.dataclass(frozen=True)
class UnitStatement:
    ref: str
    holder: str
    email: str
    start: dt.date
    end: dt.date
    generated_at: dt.datetime
    units_in: int
    units_out: int  # positive number
    rows: list[UnitRow]
    properties: list[PropertyLine]


def _property_name(pid: uuid.UUID, titles: dict) -> str:
    # imported here, like the statement's period rules below: that module is the wallet's
    from app.services.statement_service import _humanize, english

    title, slug = titles.get(pid, (None, None))
    return english(title) or _humanize(slug) or f"Property {str(pid)[:8].upper()}"


async def build_statement(
    session: AsyncSession, user_id: uuid.UUID, start: dt.date, end: dt.date
) -> UnitStatement:
    """Every unit movement of the caller in the period (whole UTC days, both included), each
    with the units held in its property afterwards, and per property the units held at the
    start, what came in, what went out and what was held at the end. Only the caller's own
    ledger lines are read."""
    from app.services.statement_service import MAX_ROWS, english, validate_period

    validate_period(start, end)
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("NOT_FOUND", "User not found.", status_code=404)
    lo = dt.datetime.combine(start, dt.time.min, tzinfo=dt.UTC)
    hi = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC)

    count = await session.scalar(
        select(func.count())
        .select_from(OwnershipLedger)
        .where(
            OwnershipLedger.user_id == user_id,
            OwnershipLedger.created_at >= lo,
            OwnershipLedger.created_at < hi,
        )
    )
    if count and count > MAX_ROWS:
        raise AppError(
            "PERIOD_TOO_LONG",
            f"This period has more than {MAX_ROWS} movements. Please choose a shorter period.",
            status_code=422,
        )
    rows = (
        (
            await session.execute(
                select(OwnershipLedger)
                .where(
                    OwnershipLedger.user_id == user_id,
                    OwnershipLedger.created_at >= lo,
                    OwnershipLedger.created_at < hi,
                )
                .order_by(OwnershipLedger.created_at, OwnershipLedger.id)
            )
        )
        .scalars()
        .all()
    )
    # units held in each property when the period starts
    opening: dict[uuid.UUID, int] = {
        pid: int(units)
        for pid, units in (
            await session.execute(
                select(OwnershipLedger.property_id, func.sum(OwnershipLedger.units))
                .where(OwnershipLedger.user_id == user_id, OwnershipLedger.created_at < lo)
                .group_by(OwnershipLedger.property_id)
            )
        ).all()
    }
    titles = await _titles(session, {r.property_id for r in rows} | set(opening))
    other = await _counterparties(session, user_id, rows)

    running = dict(opening)
    moved_in: dict[uuid.UUID, int] = {}
    moved_out: dict[uuid.UUID, int] = {}
    lines: list[UnitRow] = []
    for r in rows:
        running[r.property_id] = running.get(r.property_id, 0) + r.units
        if r.units >= 0:
            moved_in[r.property_id] = moved_in.get(r.property_id, 0) + r.units
        else:
            moved_out[r.property_id] = moved_out.get(r.property_id, 0) - r.units
        name = other.get(r.ref_id) if r.ref_id else None
        lines.append(
            UnitRow(
                at=r.created_at,
                property_title=_property_name(r.property_id, titles),
                label=LABELS.get(r.reason, _OTHER),
                counterparty=(english(name) or "a named person") if name else "",
                units=r.units,
                balance=running[r.property_id],
                reference=str(r.ref_id or r.id)[:8].upper(),
            )
        )
    # every property held at the start or moved in the period (one held all along included)
    properties = sorted(
        (
            PropertyLine(
                property_title=_property_name(pid, titles),
                opening=opening.get(pid, 0),
                units_in=moved_in.get(pid, 0),
                units_out=moved_out.get(pid, 0),
                closing=running.get(pid, 0),
            )
            for pid in running
            if opening.get(pid, 0) or moved_in.get(pid) or moved_out.get(pid)
        ),
        key=lambda line: line.property_title.lower(),
    )
    return UnitStatement(
        ref=f"UST-{str(user_id)[:4].upper()}-{start:%Y%m%d}-{end:%Y%m%d}",
        holder=english(user.full_name) or user.email,
        email=user.email,
        start=start,
        end=end,
        generated_at=dt.datetime.now(dt.UTC),
        units_in=sum(moved_in.values()),
        units_out=sum(moved_out.values()),
        rows=lines,
        properties=properties,
    )


def statement_filename(stmt: UnitStatement, fmt: str) -> str:
    return f"capimax-unit-statement-{stmt.start.isoformat()}-to-{stmt.end.isoformat()}.{fmt}"
