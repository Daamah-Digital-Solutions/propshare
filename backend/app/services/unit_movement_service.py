"""Unit movements: a member's own lines of the ownership ledger, said in words.

The investments page showed what a member holds but not how the units got there: units that
arrived by a family transfer looked exactly like units bought, and the member who sent them
saw only a smaller number (client, 2026-10-07: "it does the whole job but leaves no trace").
Every row of ``ownership_ledger`` that belongs to the caller is listed with what it was and,
for a movement between two people (a family transfer, an inheritance), who the other one was.

The ledger is the only source: nothing here is computed or stored a second time.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    titles = {
        pid: title
        for pid, title in (
            await session.execute(
                select(Property.id, Property.title).where(
                    Property.id.in_({r.property_id for r in rows})
                )
            )
        ).all()
    }

    # who the other person was: the transfer a ledger row points at (ref_id) names both sides
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

    items = [
        {
            "id": str(r.id),
            "at": r.created_at.isoformat() if r.created_at else None,
            "property_id": str(r.property_id),
            "property_title": titles.get(r.property_id),
            "units": r.units,
            "direction": "in" if r.units >= 0 else "out",
            "reason": r.reason,
            "label": LABELS.get(r.reason, _OTHER),
            "counterparty": other.get(r.ref_id) if r.ref_id else None,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}
