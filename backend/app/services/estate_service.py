"""Estate / inheritance (Group 4) — beneficiary register + admin-verified execution.

Owner decisions (legal risk accepted — see DECISIONS.md / plan/phase-estate-design.md):
  * Allocation is FREE (holder-set %, sum ≤ 100) — NOT enforced to Sharia fara'id.
  * Execution happens ONLY after an admin records a verified death (death-certificate
    document via the Group-2 storage seam) — never client-asserted, never auto-inactivity.

Execution reuses the Phase-8/Phase-10 atomic-transfer pattern: lock the property `FOR
UPDATE`, split the deceased's AVAILABLE units (net − reserved, so listings/LP-exits are
respected) across beneficiaries by free % via the exact Hamilton apportionment (an
``_unalloc`` bucket keeps any unallocated remainder with the estate), move units on the
append-only ``ownership_ledger`` (fee_rate stamped — Decision-2 carries), and record an
``estate_transfers`` row. Non-user beneficiaries get a PENDING row that materializes to a
real move on their registration+KYC (mirrors Phase-10). Idempotent: one ``estate_events``
row per deceased (UNIQUE), guarded by status so a second confirm never re-transfers.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Hashable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import (
    EstateBeneficiary,
    EstateEvent,
    EstateTransfer,
    KycVerification,
    Property,
)
from app.models.identity import User
from app.models.investments import OwnershipLedger
from app.services import secondary_service, settings_service
from app.services.distribution_service import hamilton


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def _holding(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
            OwnershipLedger.user_id == user_id, OwnershipLedger.property_id == property_id
        )
    )
    return int(total or 0)


async def _user_kyc_verified(session: AsyncSession, user_id: uuid.UUID) -> bool:
    status = await session.scalar(
        select(KycVerification.status).where(KycVerification.user_id == user_id)
    )
    return str(status) == "verified"


# --- beneficiary register (owner/holder-scoped) ----------------------------- #
def serialize(b: EstateBeneficiary) -> dict:
    return {
        "id": b.id,
        "full_name": b.full_name,
        "relationship": b.relationship,
        "email": b.email,
        "phone": b.phone,
        "allocation_pct": b.allocation_pct,
        "notes": b.notes,
        "status": b.status,
        "is_user": b.beneficiary_user_id is not None,
        "meta": b.meta or {},
        "created_at": b.created_at,
    }


async def list_beneficiaries(session: AsyncSession, owner_id: uuid.UUID) -> list[EstateBeneficiary]:
    res = await session.execute(
        select(EstateBeneficiary)
        .where(EstateBeneficiary.owner_id == owner_id)
        .order_by(EstateBeneficiary.created_at)
    )
    return list(res.scalars().all())


async def _current_sum(
    session: AsyncSession, owner_id: uuid.UUID, *, exclude_id: uuid.UUID | None = None
) -> int:
    q = select(func.coalesce(func.sum(EstateBeneficiary.allocation_pct), 0)).where(
        EstateBeneficiary.owner_id == owner_id
    )
    if exclude_id is not None:
        q = q.where(EstateBeneficiary.id != exclude_id)
    return int(await session.scalar(q) or 0)


async def _resolve_user(session: AsyncSession, email: str | None) -> tuple[uuid.UUID | None, str]:
    """Match a beneficiary email to a KYC'd user (active) or leave pending (Phase-10 model)."""
    if not email:
        return None, "pending"
    user = (
        await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()
    if user is None:
        return None, "pending"
    verified = await _user_kyc_verified(session, user.id)
    return (user.id, "active") if verified else (user.id, "pending")


async def add_beneficiary(
    session: AsyncSession, owner_id: uuid.UUID, data: dict
) -> EstateBeneficiary:
    if not (data.get("full_name") or "").strip():
        raise AppError("INVALID_BENEFICIARY", "Full name is required.", status_code=422)
    pct = int(data.get("allocation_pct") or 0)
    if pct < 0 or pct > 100:
        raise AppError("INVALID_ALLOCATION", "Allocation must be 0–100%.", status_code=422)
    if await _current_sum(session, owner_id) + pct > 100:
        raise AppError(
            "ALLOCATION_EXCEEDS_100",
            "Total beneficiary allocation cannot exceed 100%.",
            status_code=422,
            details={"current": await _current_sum(session, owner_id), "requested": pct},
        )
    user_id, status = await _resolve_user(session, data.get("email"))
    b = EstateBeneficiary(
        owner_id=owner_id,
        full_name=data["full_name"].strip(),
        relationship=data.get("relationship"),
        email=data.get("email"),
        phone=data.get("phone"),
        allocation_pct=pct,
        notes=data.get("notes"),
        meta=data.get("meta") or {},
        beneficiary_user_id=user_id,
        status=status,
    )
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return b


async def _get_owned(
    session: AsyncSession, owner_id: uuid.UUID, beneficiary_id: uuid.UUID
) -> EstateBeneficiary:
    b = await session.get(EstateBeneficiary, beneficiary_id)
    if b is None or b.owner_id != owner_id:
        raise AppError("NOT_FOUND", "Beneficiary not found.", status_code=404)
    return b


async def update_beneficiary(
    session: AsyncSession, owner_id: uuid.UUID, beneficiary_id: uuid.UUID, data: dict
) -> EstateBeneficiary:
    b = await _get_owned(session, owner_id, beneficiary_id)
    if "allocation_pct" in data and data["allocation_pct"] is not None:
        pct = int(data["allocation_pct"])
        if pct < 0 or pct > 100:
            raise AppError("INVALID_ALLOCATION", "Allocation must be 0–100%.", status_code=422)
        if await _current_sum(session, owner_id, exclude_id=beneficiary_id) + pct > 100:
            raise AppError(
                "ALLOCATION_EXCEEDS_100",
                "Total beneficiary allocation cannot exceed 100%.",
                status_code=422,
            )
        b.allocation_pct = pct
    for field in ("full_name", "relationship", "email", "phone", "notes"):
        if field in data and data[field] is not None:
            setattr(b, field, data[field])
    if "meta" in data and data["meta"] is not None:
        b.meta = data["meta"]
    if "email" in data:
        b.beneficiary_user_id, b.status = await _resolve_user(session, data.get("email"))
    b.updated_at = _utcnow()
    await session.commit()
    await session.refresh(b)
    return b


async def remove_beneficiary(
    session: AsyncSession, owner_id: uuid.UUID, beneficiary_id: uuid.UUID
) -> None:
    b = await _get_owned(session, owner_id, beneficiary_id)
    await session.delete(b)
    await session.commit()


# --- admin-verified death + execution --------------------------------------- #
async def verify_death_and_execute(
    session: AsyncSession,
    *,
    admin_id: uuid.UUID | None,
    subject_user_id: uuid.UUID,
    certificate_document_id: uuid.UUID,
) -> dict:
    """Admin records a verified death (certificate already stored) and executes transfers.
    Idempotent: a second confirm on an already-executed event is a no-op."""
    event = (
        await session.execute(
            select(EstateEvent)
            .where(EstateEvent.subject_user_id == subject_user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if event is not None and event.status == "executed":
        return {
            "estate_event_id": str(event.id),
            "executed": True,
            "replayed": True,
            "transfers": 0,
        }
    if event is None:
        event = EstateEvent(
            subject_user_id=subject_user_id,
            status="verified",
            death_certificate_document_id=certificate_document_id,
            verified_by=admin_id,
            verified_at=_utcnow(),
        )
        session.add(event)
        await session.flush()

    bens = await list_beneficiaries(session, subject_user_id)
    bens = [b for b in bens if b.allocation_pct > 0]
    total_alloc = sum(b.allocation_pct for b in bens)
    transfers = 0

    if bens and total_alloc > 0:
        # properties the deceased currently net-holds
        rows = await session.execute(
            select(OwnershipLedger.property_id)
            .where(OwnershipLedger.user_id == subject_user_id)
            .group_by(OwnershipLedger.property_id)
            .having(func.coalesce(func.sum(OwnershipLedger.units), 0) > 0)
        )
        prop_ids = [r[0] for r in rows.all()]
        mgmt_rate = await settings_service.get_management_fee_pct(session)

        for pid in prop_ids:
            prop = (
                await session.execute(select(Property).where(Property.id == pid).with_for_update())
            ).scalar_one()
            net = await _holding(session, subject_user_id, pid)
            reserved = await secondary_service.reserved_units(session, subject_user_id, pid)
            available = net - reserved
            if available <= 0:
                continue
            # Exact apportionment; the unallocated remainder stays with the estate.
            weights: list[tuple[Hashable, int]] = [(str(b.id), b.allocation_pct) for b in bens]
            if total_alloc < 100:
                weights.append(("_unalloc", 100 - total_alloc))
            split = hamilton(available, weights)
            for b in bens:
                units = int(split.get(str(b.id), 0))
                if units <= 0:
                    continue
                is_real = b.beneficiary_user_id is not None and b.status == "active"
                if is_real:
                    session.add(
                        OwnershipLedger(
                            user_id=subject_user_id,
                            property_id=pid,
                            investment_id=None,
                            units=-units,
                            unit_price=prop.unit_price,
                            reason="estate_transfer_out",
                        )
                    )
                    session.add(
                        OwnershipLedger(
                            user_id=b.beneficiary_user_id,
                            property_id=pid,
                            investment_id=None,
                            units=units,
                            unit_price=prop.unit_price,
                            reason="estate_transfer_in",
                            fee_rate=mgmt_rate,
                        )
                    )
                    status = "completed"
                    materialized_at: dt.datetime | None = _utcnow()
                else:
                    # PENDING: units stay in the deceased's ledger until the heir KYCs.
                    status = "pending"
                    materialized_at = None
                session.add(
                    EstateTransfer(
                        estate_event_id=event.id,
                        beneficiary_id=b.id,
                        property_id=pid,
                        units=units,
                        status=status,
                        materialized_at=materialized_at,
                    )
                )
                transfers += 1

    event.status = "executed"
    event.executed_at = _utcnow()
    await write_audit(
        session,
        action="estate.executed",
        entity_type="estate_event",
        entity_id=str(event.id),
        actor_id=admin_id,
        after={"subject": str(subject_user_id), "transfers": transfers},
    )
    await session.commit()
    await session.refresh(event)
    return {
        "estate_event_id": str(event.id),
        "executed": True,
        "replayed": False,
        "transfers": transfers,
    }


# --- materialization (pending -> real on beneficiary KYC) ------------------- #
async def materialize_for_user(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Link pending estate beneficiaries for this newly-KYC'd user (by email) and convert
    their pending estate transfers to real ledger moves. Idempotent."""
    user = await session.get(User, user_id)
    if user is None or not await _user_kyc_verified(session, user_id):
        return 0

    if user.email:
        unlinked = (
            (
                await session.execute(
                    select(EstateBeneficiary).where(
                        func.lower(EstateBeneficiary.email) == user.email.lower(),
                        EstateBeneficiary.beneficiary_user_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for b in unlinked:
            b.beneficiary_user_id = user_id

    linked = (
        (
            await session.execute(
                select(EstateBeneficiary).where(EstateBeneficiary.beneficiary_user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    mgmt_rate = await settings_service.get_management_fee_pct(session)
    count = 0
    for b in linked:
        b.status = "active"
        pendings = (
            (
                await session.execute(
                    select(EstateTransfer)
                    .where(
                        EstateTransfer.beneficiary_id == b.id,
                        EstateTransfer.status == "pending",
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        for tr in pendings:
            event = await session.get(EstateEvent, tr.estate_event_id)
            if event is None or tr.property_id is None:
                continue
            deceased = event.subject_user_id
            prop = (
                await session.execute(
                    select(Property).where(Property.id == tr.property_id).with_for_update()
                )
            ).scalar_one()
            if await _holding(session, deceased, tr.property_id) < tr.units:
                continue  # defensive: estate units already moved
            session.add(
                OwnershipLedger(
                    user_id=deceased,
                    property_id=tr.property_id,
                    investment_id=None,
                    units=-tr.units,
                    unit_price=prop.unit_price,
                    reason="estate_transfer_out",
                )
            )
            session.add(
                OwnershipLedger(
                    user_id=user_id,
                    property_id=tr.property_id,
                    investment_id=None,
                    units=tr.units,
                    unit_price=prop.unit_price,
                    reason="estate_transfer_in",
                    fee_rate=mgmt_rate,
                )
            )
            tr.status = "completed"
            tr.materialized_at = _utcnow()
            count += 1
    return count
