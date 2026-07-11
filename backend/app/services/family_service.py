"""Family groups & gifting (Phase 10) — real on-ledger family co-investment.

A holder allocates/transfers REAL units to family members. Every family unit is in
exactly one of two disjoint states (this is what keeps the invariant + returns clean):

  * **REAL** — units physically in a member's ``ownership_ledger`` (a KYC'd user). Paid
    by Phase-6 directly, like any owner; excluded from the record-only split.
  * **PENDING** — units still in the from-holder's ledger, RESERVED for a not-yet-
    registered member, recorded as a ``pending`` ``family_transfers`` row. No value has
    moved. Materializes to a real ledger move when the member registers + KYC.

Invariant (§2): for every holder + property, ``holding ≥ reserved`` where ``reserved``
(the shared ``secondary_service.reserved_units`` helper) now also counts pending
family-transfers-out — so a unit can never be simultaneously listed (Phase 8),
exit-requested (Phase 9), or family-allocated. Checked under ``FOR UPDATE`` on the
property. A real member→member move reuses the Phase-8 atomic-transfer pattern (zero
price, no wallet legs, Σ/property conserved, fee_rate stamped so Decision-2 carries).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import (
    FamilyGroup,
    FamilyMember,
    FamilyMemberBankAccount,
    FamilyReturnAllocation,
    FamilyTransfer,
    KycVerification,
    Property,
)
from app.models.base import TransactionType
from app.models.compliance import AuditLog
from app.models.identity import User
from app.models.investments import OwnershipLedger
from app.services import notification_service, secondary_service, settings_service, wallet_service

_CENTS = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


async def _holding(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
            OwnershipLedger.user_id == user_id,
            OwnershipLedger.property_id == property_id,
        )
    )
    return int(total or 0)


def _is_real(member: FamilyMember) -> bool:
    """A member can receive REAL units/returns only if linked to a KYC-verified user."""
    return member.user_id is not None and member.is_verified


async def _already_done(session: AsyncSession, action: str, key: str) -> bool:
    """Idempotency for owner-initiated money moves (reinvest / allocate-returns):
    a replay is detected via the append-only audit row stamped with the key."""
    row = await session.scalar(
        select(AuditLog.id).where(AuditLog.action == action, AuditLog.after["key"].astext == key)
    )
    return row is not None


# --- group + members ------------------------------------------------------- #
async def get_or_create_group(
    session: AsyncSession, *, owner_id: uuid.UUID, owner_email: str | None, name: str
) -> FamilyGroup:
    group = (
        await session.execute(select(FamilyGroup).where(FamilyGroup.owner_id == owner_id))
    ).scalar_one_or_none()
    if group is not None:
        return group
    group = FamilyGroup(owner_id=owner_id, name=name)
    session.add(group)
    await session.flush()
    # The owner is the first member (Self / Owner) — a real, verified user.
    session.add(
        FamilyMember(
            family_group_id=group.id,
            user_id=owner_id,
            name="Account Owner",
            email=owner_email,
            relationship="Self (Owner)",
            is_verified=True,
        )
    )
    await write_audit(
        session,
        action="family.group.created",
        entity_type="family_group",
        entity_id=str(group.id),
        actor_id=owner_id,
    )
    return group


async def _owner_group(session: AsyncSession, owner_id: uuid.UUID) -> FamilyGroup:
    group = (
        await session.execute(select(FamilyGroup).where(FamilyGroup.owner_id == owner_id))
    ).scalar_one_or_none()
    if group is None:
        raise AppError("NO_GROUP", "Create a family group first.", status_code=404)
    return group


async def add_member(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    name: str,
    email: str | None,
    relationship: str,
    date_of_birth: dt.date | None = None,
    phone: str | None = None,
    national_id: str | None = None,
    nationality: str | None = None,
    address: str | None = None,
) -> dict:
    group = await _owner_group(session, owner_id)
    user_id: uuid.UUID | None = None
    verified = False
    if email:
        existing = (
            await session.execute(select(User).where(func.lower(User.email) == email.lower()))
        ).scalar_one_or_none()
        if existing is not None:
            user_id = existing.id
            kyc = await session.scalar(
                select(KycVerification.status).where(KycVerification.user_id == existing.id)
            )
            verified = str(kyc) == "verified"
    member = FamilyMember(
        family_group_id=group.id,
        user_id=user_id,
        name=name,
        email=email,
        relationship=relationship,
        date_of_birth=date_of_birth,
        phone=(phone or None),
        national_id=(national_id or None),
        nationality=(nationality or None),
        address=(address or None),
        is_verified=verified,
    )
    session.add(member)
    await session.flush()
    await write_audit(
        session,
        action="family.member.added",
        entity_type="family_member",
        entity_id=str(member.id),
        actor_id=owner_id,
        after={
            "name": name,
            "linked_user": str(user_id) if user_id else None,
            "verified": verified,
        },
    )
    if not verified:
        # Owner gets the in-app row; the invitee (often not a user yet — an in-app row
        # would reach no one) gets a real email, unconditionally (force, no prefs).
        await notification_service.notify(
            session,
            user_id=owner_id,
            type="family",
            title="Family member invited",
            message=f"{name} was invited. Their allocations stay pending until they verify.",
            email_category="invite" if email else None,
            email_to=email,
            force_email=bool(email),
            email_subject="You've been invited to a CapiMax family group",
            email_body=(
                f"{name}, you've been invited to join a family investment group on CapiMax "
                "PropShare. Register and verify your identity to receive your allocated units."
            ),
        )
    return _member_result(member)


async def _member_detail(session: AsyncSession, member: FamilyMember) -> dict:
    banks = (
        (
            await session.execute(
                select(FamilyMemberBankAccount)
                .where(FamilyMemberBankAccount.member_id == member.id)
                .order_by(FamilyMemberBankAccount.created_at)
            )
        )
        .scalars()
        .all()
    )
    real_units = 0
    if member.user_id is not None:
        real_units = int(
            await session.scalar(
                select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
                    OwnershipLedger.user_id == member.user_id
                )
            )
            or 0
        )
    return {**_member_result(member, [_bank_result(b) for b in banks]), "real_units": real_units}


async def update_member(
    session: AsyncSession, *, owner_id: uuid.UUID, member_id: uuid.UUID, updates: dict
) -> dict:
    """Edit a member's personal data (owner-scoped). Only provided fields change; name and
    relationship can't be blanked."""
    group = await _owner_group(session, owner_id)
    member = await _member_in_group(session, group.id, member_id)
    for key in (
        "name",
        "email",
        "relationship",
        "date_of_birth",
        "phone",
        "national_id",
        "nationality",
        "address",
    ):
        if key not in updates:
            continue
        val = updates[key]
        if isinstance(val, str):
            val = val.strip() or None
        if key in ("name", "relationship") and not val:
            continue  # required fields can't be blanked
        setattr(member, key, val)
    member.updated_at = _utcnow()
    await session.flush()
    await write_audit(
        session,
        action="family.member.updated",
        entity_type="family_member",
        entity_id=str(member.id),
        actor_id=owner_id,
    )
    return await _member_detail(session, member)


# --- member bank accounts (Task 9) ----------------------------------------- #
async def add_member_bank_account(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    member_id: uuid.UUID,
    bank_name: str,
    account_holder: str | None = None,
    iban: str | None = None,
    account_number: str | None = None,
    swift_bic: str | None = None,
    label: str | None = None,
) -> dict:
    group = await _owner_group(session, owner_id)
    await _member_in_group(session, group.id, member_id)
    if not bank_name.strip():
        raise AppError("INVALID_INPUT", "Bank name is required.", status_code=422)
    if not (iban and iban.strip()) and not (account_number and account_number.strip()):
        raise AppError("INVALID_INPUT", "Provide an IBAN or an account number.", status_code=422)
    acct = FamilyMemberBankAccount(
        member_id=member_id,
        bank_name=bank_name.strip(),
        account_holder=(account_holder or "").strip() or None,
        iban=(iban or "").strip() or None,
        account_number=(account_number or "").strip() or None,
        swift_bic=(swift_bic or "").strip() or None,
        label=(label or "").strip() or None,
    )
    session.add(acct)
    await session.flush()
    await write_audit(
        session,
        action="family.member.bank_added",
        entity_type="family_member_bank_account",
        entity_id=str(acct.id),
        actor_id=owner_id,
    )
    return _bank_result(acct)


async def list_member_bank_accounts(
    session: AsyncSession, *, owner_id: uuid.UUID, member_id: uuid.UUID
) -> list[dict]:
    group = await _owner_group(session, owner_id)
    await _member_in_group(session, group.id, member_id)
    rows = (
        (
            await session.execute(
                select(FamilyMemberBankAccount)
                .where(FamilyMemberBankAccount.member_id == member_id)
                .order_by(FamilyMemberBankAccount.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [_bank_result(b) for b in rows]


async def delete_member_bank_account(
    session: AsyncSession, *, owner_id: uuid.UUID, member_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    group = await _owner_group(session, owner_id)
    await _member_in_group(session, group.id, member_id)
    acct = await session.get(FamilyMemberBankAccount, account_id)
    if acct is None or acct.member_id != member_id:
        raise AppError("NOT_FOUND", "Bank account not found.", status_code=404)
    await session.delete(acct)
    await write_audit(
        session,
        action="family.member.bank_deleted",
        entity_type="family_member_bank_account",
        entity_id=str(account_id),
        actor_id=owner_id,
    )


# --- allocate / transfer units --------------------------------------------- #
async def create_transfer(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    from_member_id: uuid.UUID,
    to_member_id: uuid.UUID,
    property_id: uuid.UUID,
    units: int,
    idempotency_key: str,
) -> dict:
    if units < 1:
        raise AppError("INVALID_UNITS", "Transfer at least one unit.", status_code=422)
    if from_member_id == to_member_id:
        raise AppError("INVALID_TRANSFER", "Cannot transfer to the same member.", status_code=422)

    # Idempotency-Key replay -> the existing transfer (no double move).
    existing = (
        await session.execute(
            select(FamilyTransfer).where(FamilyTransfer.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _transfer_result(existing)

    group = await _owner_group(session, owner_id)
    src = await _member_in_group(session, group.id, from_member_id)
    dst = await _member_in_group(session, group.id, to_member_id)

    # The source must be a real, verified user — only real holdings can be moved/reserved.
    if not _is_real(src) or src.user_id is None:
        raise AppError(
            "SOURCE_NOT_REAL", "The sending member must be a verified user.", status_code=422
        )
    from_user = src.user_id

    # Lock the property row: serializes against listings/exits/other family moves.
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)

    free = await _holding(session, from_user, property_id) - await secondary_service.reserved_units(
        session, from_user, property_id
    )
    if units > free:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "Not enough unreserved units to transfer.",
            status_code=422,
            details={"free": free, "requested": units},
        )

    sett = await settings_service.get_family_settings(session)
    fee_pct = sett["transfer_fee_pct"]
    transfer_fee = _q(prop.unit_price * units * fee_pct / _HUNDRED)

    if _is_real(dst) and dst.user_id is not None:
        # REAL atomic move (Phase-8 pattern, zero price): seller -N / buyer +N.
        mgmt_rate = await settings_service.get_management_fee_pct(session)
        session.add(
            OwnershipLedger(
                user_id=from_user,
                property_id=property_id,
                investment_id=None,
                units=-units,
                unit_price=prop.unit_price,
                reason="family_transfer_out",
            )
        )
        session.add(
            OwnershipLedger(
                user_id=dst.user_id,
                property_id=property_id,
                investment_id=None,
                units=units,
                unit_price=prop.unit_price,
                reason="family_transfer_in",
                fee_rate=mgmt_rate,  # Decision-2: recipient carries the fee liability
            )
        )
        if transfer_fee > 0:
            await wallet_service.debit(
                session,
                user_id=from_user,
                reference_id=group.id,
                line_items=[(TransactionType.fee, transfer_fee, "Family transfer fee")],
                actor_id=owner_id,
            )
        status = "completed"
        materialized_at = _utcnow()
    else:
        # PENDING allocation: reserve, record, no ledger move (recipient not a user yet).
        dst.allocated_units = dst.allocated_units + units
        status = "pending"
        materialized_at = None

    transfer = FamilyTransfer(
        family_group_id=group.id,
        from_member_id=from_member_id,
        to_member_id=to_member_id,
        property_id=property_id,
        units=units,
        transfer_fee=transfer_fee,
        status=status,
        idempotency_key=idempotency_key,
        materialized_at=materialized_at,
    )
    session.add(transfer)
    await session.flush()
    await write_audit(
        session,
        action="family.transfer." + status,
        entity_type="family_transfer",
        entity_id=str(transfer.id),
        actor_id=owner_id,
        after={
            "from": str(from_member_id),
            "to": str(to_member_id),
            "property_id": str(property_id),
            "units": units,
            "status": status,
        },
    )
    return _transfer_result(transfer)


async def cancel_transfer(
    session: AsyncSession, *, owner_id: uuid.UUID, transfer_id: uuid.UUID
) -> dict:
    group = await _owner_group(session, owner_id)
    tr = (
        await session.execute(
            select(FamilyTransfer)
            .where(FamilyTransfer.id == transfer_id, FamilyTransfer.family_group_id == group.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if tr is None:
        raise AppError("NOT_FOUND", "Transfer not found", status_code=404)
    if tr.status != "pending":
        raise AppError(
            "INVALID_STATE", "Only a pending transfer can be cancelled.", status_code=409
        )
    tr.status = "cancelled"
    dst = await session.get(FamilyMember, tr.to_member_id)
    if dst is not None:
        dst.allocated_units = max(0, dst.allocated_units - tr.units)
    await write_audit(
        session,
        action="family.transfer.cancelled",
        entity_type="family_transfer",
        entity_id=str(tr.id),
        actor_id=owner_id,
    )
    return _transfer_result(tr)


# --- allocate returns ($) --------------------------------------------------- #
async def allocate_returns(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    member_id: uuid.UUID,
    amount: float,
    idempotency_key: str,
) -> dict:
    amount_dec = decimal.Decimal(str(amount)).quantize(_CENTS)
    if amount_dec <= 0:
        raise AppError("INVALID_AMOUNT", "Amount must be positive.", status_code=422)
    group = await _owner_group(session, owner_id)
    member = await _member_in_group(session, group.id, member_id)

    if await _already_done(session, "family.returns.allocated", idempotency_key):
        return {"member_id": str(member_id), "amount": str(amount_dec), "replayed": True}

    real = _is_real(member) and member.user_id is not None
    if real and member.user_id is not None:
        # Real wallet transfer owner -> member.
        await wallet_service.debit(
            session,
            user_id=owner_id,
            reference_id=group.id,
            line_items=[(TransactionType.family_allocation, amount_dec, "Family allocation")],
            actor_id=owner_id,
        )
        await wallet_service.credit(
            session,
            user_id=member.user_id,
            amount=amount_dec,
            reference_id=group.id,
            tx_type=TransactionType.family_allocation,
            description="Family allocation received",
            actor_id=owner_id,
        )
    # Record either way (real = audit trail; pending = the record-only claim).
    session.add(
        FamilyReturnAllocation(family_group_id=group.id, member_id=member_id, amount=amount_dec)
    )
    member.allocated_returns = member.allocated_returns + amount_dec
    group.total_returns = group.total_returns + amount_dec
    await write_audit(
        session,
        action="family.returns.allocated",
        entity_type="family_member",
        entity_id=str(member_id),
        actor_id=owner_id,
        after={"amount": str(amount_dec), "real": real, "key": idempotency_key},
    )
    return {"member_id": str(member_id), "amount": str(amount_dec), "real": real}


# --- reinvest at the family discount (§7) ----------------------------------- #
async def reinvest(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    property_id: uuid.UUID,
    amount: float,
    idempotency_key: str,
) -> dict:
    amount_dec = decimal.Decimal(str(amount)).quantize(_CENTS)
    if amount_dec <= 0:
        raise AppError("INVALID_AMOUNT", "Amount must be positive.", status_code=422)
    await _owner_group(session, owner_id)

    if await _already_done(session, "family.reinvest", idempotency_key):
        return {"property_id": str(property_id), "amount": str(amount_dec), "replayed": True}

    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    if prop.unit_price <= 0:
        raise AppError("INVALID_PROPERTY", "Property has no unit price.", status_code=409)

    sett = await settings_service.get_family_settings(session)
    discount = sett["reinvest_discount_pct"]
    effective_price = _q(prop.unit_price * (_HUNDRED - discount) / _HUNDRED)
    if effective_price <= 0:
        raise AppError("INVALID_DISCOUNT", "Effective price must be positive.", status_code=409)
    units = int(amount_dec // effective_price)  # floor(amount / effective_price)
    if units < 1:
        raise AppError(
            "AMOUNT_TOO_LOW",
            f"Minimum is one unit at the discounted price ({effective_price}).",
            status_code=422,
        )
    if units > prop.available_units:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "Not enough units available in this property.",
            status_code=409,
            details={"available_units": prop.available_units, "requested": units},
        )

    # Debit the owner's wallet the full amount; they receive `units` at the subsidy.
    mgmt_rate = await settings_service.get_management_fee_pct(session)
    wallet = await wallet_service.debit(
        session,
        user_id=owner_id,
        reference_id=property_id,
        line_items=[(TransactionType.investment, amount_dec, f"Family reinvest — {prop.title}")],
        actor_id=owner_id,
    )
    wallet.total_invested = wallet.total_invested + amount_dec
    prop.available_units = prop.available_units - units
    prop.funded_amount = prop.funded_amount + amount_dec
    session.add(
        OwnershipLedger(
            user_id=owner_id,
            property_id=property_id,
            investment_id=None,
            units=units,
            unit_price=prop.unit_price,  # nominal value of the units acquired
            reason="family_reinvest",
            fee_rate=mgmt_rate,
        )
    )
    await write_audit(
        session,
        action="family.reinvest",
        entity_type="property",
        entity_id=str(property_id),
        actor_id=owner_id,
        after={
            "amount": str(amount_dec),
            "discount_pct": str(discount),
            "effective_price": str(effective_price),
            "units": units,
            "key": idempotency_key,
        },
    )
    return {
        "property_id": str(property_id),
        "amount": str(amount_dec),
        "discount_pct": str(discount),
        "effective_price": str(effective_price),
        "units": units,
    }


# --- materialization (pending -> real on member KYC) ------------------------ #
async def materialize_for_user(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Link any pending family memberships for this (newly KYC-verified) user by email,
    then convert their pending allocations to real ledger moves + sweep accrued returns.
    Idempotent: already-materialized transfers are skipped."""
    user = await session.get(User, user_id)
    if user is None:
        return 0
    kyc = await session.scalar(
        select(KycVerification.status).where(KycVerification.user_id == user_id)
    )
    if str(kyc) != "verified":
        return 0

    # Link unlinked members matching this user's email.
    if user.email:
        members = (
            (
                await session.execute(
                    select(FamilyMember).where(
                        func.lower(FamilyMember.email) == user.email.lower(),
                        FamilyMember.user_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for m in members:
            m.user_id = user_id
            m.is_verified = True

    # Materialize pending transfers to members now linked to this user.
    linked = (
        (await session.execute(select(FamilyMember).where(FamilyMember.user_id == user_id)))
        .scalars()
        .all()
    )
    count = 0
    for member in linked:
        member.is_verified = True
        pendings = (
            (
                await session.execute(
                    select(FamilyTransfer)
                    .where(
                        FamilyTransfer.to_member_id == member.id,
                        FamilyTransfer.status == "pending",
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        mgmt_rate = await settings_service.get_management_fee_pct(session)
        for tr in pendings:
            src = await session.get(FamilyMember, tr.from_member_id) if tr.from_member_id else None
            if src is None or src.user_id is None or tr.property_id is None:
                continue
            prop = (
                await session.execute(
                    select(Property).where(Property.id == tr.property_id).with_for_update()
                )
            ).scalar_one()
            session.add(
                OwnershipLedger(
                    user_id=src.user_id,
                    property_id=tr.property_id,
                    investment_id=None,
                    units=-tr.units,
                    unit_price=prop.unit_price,
                    reason="family_transfer_out",
                )
            )
            session.add(
                OwnershipLedger(
                    user_id=user_id,
                    property_id=tr.property_id,
                    investment_id=None,
                    units=tr.units,
                    unit_price=prop.unit_price,
                    reason="family_transfer_in",
                    fee_rate=mgmt_rate,
                )
            )
            tr.status = "completed"
            tr.materialized_at = _utcnow()
            member.allocated_units = max(0, member.allocated_units - tr.units)
            count += 1
        # Sweep accrued record-only returns into the now-real member's wallet.
        if member.allocated_returns > 0:
            swept = member.allocated_returns
            sweep_owner = await _group_owner(session, member)
            await wallet_service.debit(
                session,
                user_id=sweep_owner,
                reference_id=member.id,
                line_items=[(TransactionType.family_allocation, swept, "Family returns released")],
                actor_id=user_id,
            )
            await wallet_service.credit(
                session,
                user_id=user_id,
                amount=swept,
                reference_id=member.id,
                tx_type=TransactionType.family_allocation,
                description="Family returns released on verification",
                actor_id=user_id,
            )
            member.allocated_returns = decimal.Decimal("0")
        if pendings:
            await write_audit(
                session,
                action="family.member.materialized",
                entity_type="family_member",
                entity_id=str(member.id),
                actor_id=user_id,
                after={"transfers": len(pendings)},
            )
    return count


async def _group_owner(session: AsyncSession, member: FamilyMember) -> uuid.UUID:
    group = await session.get(FamilyGroup, member.family_group_id)
    assert group is not None
    return group.owner_id


# --- reads ------------------------------------------------------------------ #
async def get_group_view(session: AsyncSession, owner_id: uuid.UUID) -> dict | None:
    group = (
        await session.execute(select(FamilyGroup).where(FamilyGroup.owner_id == owner_id))
    ).scalar_one_or_none()
    if group is None:
        return None
    members = (
        (
            await session.execute(
                select(FamilyMember).where(FamilyMember.family_group_id == group.id)
            )
        )
        .scalars()
        .all()
    )
    member_ids = [m.id for m in members]
    banks_by_member: dict[uuid.UUID, list[dict]] = {}
    if member_ids:
        bank_rows = (
            (
                await session.execute(
                    select(FamilyMemberBankAccount)
                    .where(FamilyMemberBankAccount.member_id.in_(member_ids))
                    .order_by(FamilyMemberBankAccount.created_at)
                )
            )
            .scalars()
            .all()
        )
        for b in bank_rows:
            banks_by_member.setdefault(b.member_id, []).append(_bank_result(b))
    out_members = []
    for m in members:
        real_units = 0
        if m.user_id is not None:
            real_units = int(
                await session.scalar(
                    select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
                        OwnershipLedger.user_id == m.user_id
                    )
                )
                or 0
            )
        out_members.append(
            {**_member_result(m, banks_by_member.get(m.id, [])), "real_units": real_units}
        )
    return {
        "group_id": str(group.id),
        "name": group.name,
        "total_returns": str(group.total_returns),
        "members": out_members,
    }


async def list_transfers(session: AsyncSession, owner_id: uuid.UUID) -> list[dict]:
    group = (
        await session.execute(select(FamilyGroup).where(FamilyGroup.owner_id == owner_id))
    ).scalar_one_or_none()
    if group is None:
        return []
    rows = (
        (
            await session.execute(
                select(FamilyTransfer)
                .where(FamilyTransfer.family_group_id == group.id)
                .order_by(FamilyTransfer.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_transfer_result(t) for t in rows]


# --- helpers ---------------------------------------------------------------- #
async def _member_in_group(
    session: AsyncSession, group_id: uuid.UUID, member_id: uuid.UUID
) -> FamilyMember:
    m = await session.get(FamilyMember, member_id)
    if m is None or m.family_group_id != group_id:
        raise AppError("NOT_FOUND", "Family member not found in your group.", status_code=404)
    return m


def _member_result(m: FamilyMember, bank_accounts: list[dict] | None = None) -> dict:
    return {
        "member_id": str(m.id),
        "name": m.name,
        "email": m.email,
        "relationship": m.relationship,
        "is_verified": m.is_verified,
        "is_user": m.user_id is not None,
        "pending_units": m.allocated_units,
        "allocated_returns": str(m.allocated_returns),
        "date_of_birth": m.date_of_birth.isoformat() if m.date_of_birth else None,
        "phone": m.phone,
        "national_id": m.national_id,
        "nationality": m.nationality,
        "address": m.address,
        "linked_date": m.created_at.isoformat() if m.created_at else None,
        "bank_accounts": bank_accounts or [],
    }


def _bank_result(b: FamilyMemberBankAccount) -> dict:
    return {
        "id": str(b.id),
        "label": b.label,
        "bank_name": b.bank_name,
        "account_holder": b.account_holder,
        "iban": b.iban,
        "account_number": b.account_number,
        "swift_bic": b.swift_bic,
    }


def _transfer_result(t: FamilyTransfer) -> dict:
    return {
        "transfer_id": str(t.id),
        "from_member_id": str(t.from_member_id) if t.from_member_id else None,
        "to_member_id": str(t.to_member_id),
        "property_id": str(t.property_id) if t.property_id else None,
        "units": t.units,
        "transfer_fee": str(t.transfer_fee),
        "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
