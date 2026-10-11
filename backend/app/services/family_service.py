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

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
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
from app.models.base import PropertyStatus, TransactionType
from app.models.compliance import AuditLog
from app.models.identity import User
from app.models.investments import OwnershipLedger
from app.services import (
    account_service,
    investment_service,
    notification_service,
    secondary_service,
    settings_service,
    wallet_service,
)

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


# --- traces: who is told, and how they are named (client, 2026-10-07) ------- #
# Every family action tells BOTH sides, in their notifications and by email: the member who
# did it and the member it was done for. What happened is also read back from the tables
# themselves (``list_activity``), so the page shows it whether or not a message was read.
_plain = notification_service.plain_text  # a typed name, safe inside a message we send


async def _display_name(session: AsyncSession, user_id: uuid.UUID | None) -> str:
    """How a member is named to the other side: their name, never their email address."""
    if user_id is None:
        return "A family member"
    name = await session.scalar(select(User.full_name).where(User.id == user_id))
    return _plain(name) or "A family member"


def _units(n: int) -> str:
    return f"{n} unit" if n == 1 else f"{n} units"


def _site(path: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}{path}"


async def _tell_user(
    session: AsyncSession, user_id: uuid.UUID, *, title: str, message: str, tab: str = "family"
) -> None:
    """A member's own feed, plus an email (unless they turned investment emails off) that
    ends with where to see it."""
    await notification_service.notify(
        session,
        user_id=user_id,
        type="family",
        title=title,
        message=message,
        email_category="investment_updates",
        email_body=f"{message}\n\nSee it in your dashboard: {_site(f'/dashboard?tab={tab}')}",
    )


async def _tell_member(
    session: AsyncSession,
    member: FamilyMember,
    *,
    actor_id: uuid.UUID,
    title: str,
    message: str,
    tab: str = "family",
    how_to_receive: bool = True,
) -> None:
    """Tell the member something was done for them. With an account: their feed and an
    email. Without one: an email to the address the owner entered, with how to register
    when there is something to receive (there is no feed to write to). The member acting is
    told separately, never twice."""
    if member.user_id is not None:
        if member.user_id != actor_id:
            await _tell_user(session, member.user_id, title=title, message=message, tab=tab)
        return
    register = (
        "To receive it: create your Capimax PropShare account with this email address (or "
        "sign in, if you have one), confirm the address from the email we send you, and "
        f"verify your identity: {_site('/auth')}\n\n"
        if how_to_receive
        else ""
    )
    notification_service.email_external(
        session,
        to_email=member.email,
        subject=title,
        body=(
            f"Hello {_plain(member.name) or 'there'},\n\n{message}\n\n{register}"
            "If you did not expect this message, you can ignore it."
        ),
        category="invite",
    )


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
        # an account that never confirmed this address is not the member's for certain: the
        # member stays without an account until it does (account_service)
        existing = await account_service.confirmed_by_address(session, email)
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
    # Both sides are told, whatever the member's state (client, 2026-10-07: adding a member
    # left no trace when the email already had a verified account).
    shown = _plain(name) or "A family member"
    role = _plain(relationship, 60)
    if verified:
        how = (
            "They are linked to their verified account: what you transfer to them reaches "
            "them at once."
        )
    elif user_id is not None:
        how = (
            "Their account is not verified yet: what you allocate to them stays pending "
            "until they verify their identity."
        )
    elif email:
        how = (
            "They were invited by email: what you allocate to them stays pending until "
            "they register and verify their identity."
        )
    else:
        how = (
            "They have no email on file: add one so they can register and receive what "
            "you allocate to them."
        )
    await _tell_user(
        session,
        owner_id,
        title="Family member added",
        message=f"You added {shown} ({role}) to your family group. {how}",
    )
    owner_name = await _display_name(session, owner_id)
    await _tell_member(
        session,
        member,
        actor_id=owner_id,
        title="You were added to a family group",
        message=(
            f"{owner_name} added you to their family investment group on Capimax PropShare "
            f"as {role}. Units or returns they transfer to you appear in your account, and "
            "you are told each time."
            + ("" if verified or user_id is None else " Verify your identity to receive them.")
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
    group = await session.get(FamilyGroup, member.family_group_id)
    real_units = await _shown_units(session, group, member) if group is not None else 0
    return {
        **_member_result(member, [_bank_result(b) for b in banks]),
        "real_units": real_units,
        "is_self": group is not None and member.user_id == group.owner_id,
    }


async def _shown_units(session: AsyncSession, group: FamilyGroup, member: FamilyMember) -> int:
    """The units the group's page shows for a member. The owner: what they hold. Anyone else:
    what reached them through THIS group's transfers. A member is added by their email
    address without being asked, so the rest of their portfolio is not the owner's to see."""
    if member.user_id is None:
        return 0
    if member.user_id == group.owner_id:
        total = await session.scalar(
            select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
                OwnershipLedger.user_id == member.user_id
            )
        )
        return int(total or 0)
    done = (FamilyTransfer.family_group_id == group.id) & (FamilyTransfer.status == "completed")
    received = await session.scalar(
        select(func.coalesce(func.sum(FamilyTransfer.units), 0)).where(
            done, FamilyTransfer.to_member_id == member.id
        )
    )
    sent = await session.scalar(
        select(func.coalesce(func.sum(FamilyTransfer.units), 0)).where(
            done, FamilyTransfer.from_member_id == member.id
        )
    )
    return max(0, int(received or 0) - int(sent or 0))


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
    await _refuse_closed(session, dst)

    # The source must be a real, verified user — only real holdings can be moved/reserved.
    if not _is_real(src) or src.user_id is None:
        raise AppError(
            "SOURCE_NOT_REAL", "The sending member must be a verified user.", status_code=422
        )
    # ...and it must be the member acting. A group's owner adds members by email with no say
    # from them: letting the owner pick any member as the sender let an investor add another
    # investor's address and move that investor's units to themselves.
    if src.user_id != owner_id:
        raise AppError(
            "NOT_YOUR_UNITS",
            "You can only transfer units you hold yourself.",
            status_code=403,
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
    # the transfer's id is set here so the two ledger rows can point at it (ref_id): a
    # movement on the investments page then names the other person
    transfer_id = uuid.uuid4()

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
                ref_id=transfer_id,
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
                ref_id=transfer_id,
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
        id=transfer_id,
        family_group_id=group.id,
        from_member_id=from_member_id,
        to_member_id=to_member_id,
        property_id=property_id,
        units=units,
        # the fee actually charged: an allocation that is still pending is charged nothing
        transfer_fee=transfer_fee if status == "completed" else decimal.Decimal("0"),
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

    to_name = _plain(dst.name) or "a family member"
    sender_name = await _display_name(session, owner_id)
    what = f"{_units(units)} of {prop.title}"
    if status == "completed":
        fee_note = (
            f" A transfer fee of ${transfer_fee} was charged to your wallet."
            if transfer_fee > 0
            else ""
        )
        await _tell_user(
            session,
            owner_id,
            title="Units transferred to a family member",
            message=(
                f"You transferred {what} to {to_name}. They are in their account now.{fee_note}"
            ),
        )
        await _tell_member(
            session,
            dst,
            actor_id=owner_id,
            title="You received units from a family member",
            message=f"{sender_name} transferred {what} to you. They are in your account now.",
            tab="investments",
        )
    else:
        await _tell_user(
            session,
            owner_id,
            title="Units allocated to a family member",
            message=(
                f"You allocated {what} to {to_name}. They stay in your account, reserved "
                f"for them, until {to_name} registers and verifies their identity."
            ),
        )
        await _tell_member(
            session,
            dst,
            actor_id=owner_id,
            title="Units are waiting for you",
            message=(
                f"{sender_name} allocated {what} to you on Capimax PropShare. They move to "
                "your account once your identity is verified."
            ),
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
    title = (
        await session.scalar(select(Property.title).where(Property.id == tr.property_id))
        if tr.property_id
        else None
    )
    what = f"{_units(tr.units)} of {title or 'a property'}"
    await _tell_user(
        session,
        owner_id,
        title="Family allocation cancelled",
        message=(
            f"You cancelled the allocation of {what} to "
            f"{_plain(dst.name) if dst is not None else 'a family member'}. "
            "The units are free in your account again."
        ),
    )
    if dst is not None:
        sender_name = await _display_name(session, owner_id)
        await _tell_member(
            session,
            dst,
            actor_id=owner_id,
            title="A family allocation to you was cancelled",
            message=f"{sender_name} cancelled the allocation of {what} to you.",
            how_to_receive=False,
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
    await _refuse_closed(session, member)

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
    if not real:
        # not paid yet: owed, and released to their wallet when they verify. Money already
        # paid above is never added here, or the release would pay it a second time.
        member.pending_returns = member.pending_returns + amount_dec
    group.total_returns = group.total_returns + amount_dec
    await write_audit(
        session,
        action="family.returns.allocated",
        entity_type="family_member",
        entity_id=str(member_id),
        actor_id=owner_id,
        after={"amount": str(amount_dec), "real": real, "key": idempotency_key},
    )

    to_name = _plain(member.name) or "a family member"
    sender_name = await _display_name(session, owner_id)
    if real:
        await _tell_user(
            session,
            owner_id,
            title="Returns sent to a family member",
            message=f"You sent ${amount_dec:,.2f} from your wallet to {to_name}.",
        )
        await _tell_member(
            session,
            member,
            actor_id=owner_id,
            title="You received money from a family member",
            message=f"{sender_name} sent ${amount_dec:,.2f} to your wallet.",
            tab="wallet",
        )
    else:
        await _tell_user(
            session,
            owner_id,
            title="Returns allocated to a family member",
            message=(
                f"You allocated ${amount_dec:,.2f} to {to_name}. It stays in your wallet "
                f"until {to_name} registers and verifies their identity."
            ),
        )
        await _tell_member(
            session,
            member,
            actor_id=owner_id,
            title="Money is waiting for you",
            message=(
                f"{sender_name} allocated ${amount_dec:,.2f} to you on Capimax PropShare. "
                "It moves to your wallet once your identity is verified."
            ),
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
    # the same doors as any purchase paid in full (investment_service.reinvest_from_wallet):
    # an open listing, not a sample, and one that is sold in full at all
    if prop.status != PropertyStatus.active:
        raise AppError(
            "PROPERTY_NOT_OPEN", "This property is not open for investment.", status_code=409
        )
    investment_service.refuse_sample(prop)
    investment_service.require_full_payment(prop)
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
    await _tell_user(
        session,
        owner_id,
        title="Family reinvestment completed",
        message=(
            f"You bought {_units(units)} of {prop.title} for ${amount_dec:,.2f} at the "
            f"family discount ({discount.normalize():f}% off), paid from your wallet."
        ),
        tab="investments",
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
    """Link any pending family memberships for this KYC-verified user by their CONFIRMED
    email, then convert their pending allocations to real ledger moves + sweep accrued
    returns. Runs when the identity is verified and when the address is confirmed
    (account_service.release_waiting). Idempotent: already-materialized transfers are
    skipped."""
    user = await session.get(User, user_id)
    if user is None:
        return 0
    kyc = await session.scalar(
        select(KycVerification.status).where(KycVerification.user_id == user_id)
    )
    if str(kyc) != "verified":
        return 0

    # Link unlinked members matching this user's email: only an address the account
    # confirmed (anyone can sign up with any address).
    if user.email and user.email_verified:
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
                    ref_id=tr.id,
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
                    ref_id=tr.id,
                )
            )
            tr.status = "completed"
            tr.materialized_at = _utcnow()
            member.allocated_units = max(0, member.allocated_units - tr.units)
            count += 1
            what = f"{_units(tr.units)} of {prop.title}"
            await _tell_user(
                session,
                user_id,
                title="Units from a family member are in your account",
                message=(
                    f"{await _display_name(session, src.user_id)} had allocated {what} to "
                    "you. Now that your identity is verified, they are in your account."
                ),
                tab="investments",
            )
            if src.user_id != user_id:
                await _tell_user(
                    session,
                    src.user_id,
                    title="A family allocation was completed",
                    message=(
                        f"{_plain(member.name) or 'A family member'} verified their identity: "
                        f"the {what} you allocated to them moved to their account."
                    ),
                )
        # Release what this member is still owed (record-only allocations made while they
        # could not be paid) into their wallet.
        await _release_owed(session, member, user_id=user_id)
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


async def _refuse_closed(session: AsyncSession, member: FamilyMember) -> None:
    """Nothing is sent into a closed account: what is in it waits for its holder's
    beneficiaries, and what arrives later would not be part of that."""
    if member.user_id is None:
        return
    closed = await session.scalar(select(User.closed_at).where(User.id == member.user_id))
    if closed is not None:
        raise AppError(
            "ACCOUNT_CLOSED",
            f"{_plain(member.name) or 'This member'}'s account is closed: nothing can be "
            "transferred or allocated to it.",
            status_code=409,
        )


async def _group_owner(session: AsyncSession, member: FamilyMember) -> uuid.UUID:
    group = await session.get(FamilyGroup, member.family_group_id)
    assert group is not None
    return group.owner_id


async def _release_owed(session: AsyncSession, member: FamilyMember, *, user_id: uuid.UUID) -> None:
    """Move what a now-verified member is still owed from the group owner's wallet to
    theirs. ONLY ``pending_returns``: money already paid to a verified member is counted in
    ``allocated_returns`` too, and is never moved a second time."""
    owed = member.pending_returns
    if owed <= 0:
        return
    payer = await _group_owner(session, member)
    who = _plain(member.name) or "A family member"
    if payer == user_id:  # owed to themselves: nothing to move
        member.pending_returns = decimal.Decimal("0")
        return
    try:
        # a savepoint: a payer whose wallet cannot cover it must not undo the units moved
        # before this, nor fail the identity verification this runs inside
        async with session.begin_nested():
            await wallet_service.debit(
                session,
                user_id=payer,
                reference_id=member.id,
                line_items=[(TransactionType.family_allocation, owed, "Family returns released")],
                actor_id=user_id,
            )
            await wallet_service.credit(
                session,
                user_id=user_id,
                amount=owed,
                reference_id=member.id,
                tx_type=TransactionType.family_allocation,
                description="Family returns released on verification",
                actor_id=user_id,
            )
    except AppError:
        # still owed: released the next time this runs with the money there
        await _tell_user(
            session,
            payer,
            title="Family returns could not be released",
            message=(
                f"{who} verified their identity, but your wallet does not hold the "
                f"${owed:,.2f} you allocated to them. Add funds: it is released to them "
                "the next time their allocations are checked."
            ),
            tab="wallet",
        )
        return
    member.pending_returns = decimal.Decimal("0")
    await _tell_user(
        session,
        user_id,
        title="Family returns are in your wallet",
        message=(
            f"${owed:,.2f} that {await _display_name(session, payer)} allocated to you is "
            "now in your wallet."
        ),
        tab="wallet",
    )
    await _tell_user(
        session,
        payer,
        title="Family returns were released",
        message=(
            f"{who} verified their identity: the ${owed:,.2f} you allocated to them moved "
            "from your wallet to theirs."
        ),
        tab="wallet",
    )


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
        out_members.append(
            {
                **_member_result(m, banks_by_member.get(m.id, [])),
                "real_units": await _shown_units(session, group, m),
                # the owner's own row: the only one units can be transferred from
                "is_self": m.user_id == group.owner_id,
            }
        )
    return {
        "group_id": str(group.id),
        "name": group.name,
        "total_returns": str(group.total_returns),
        "members": out_members,
    }


async def list_transfers(session: AsyncSession, owner_id: uuid.UUID) -> list[dict]:
    """The transfers of the caller's own group, newest first, each with the names, the
    property and the dates a history line needs."""
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
    members = {
        m.id: m
        for m in (
            await session.execute(
                select(FamilyMember).where(FamilyMember.family_group_id == group.id)
            )
        )
        .scalars()
        .all()
    }
    titles = await _property_titles(session, {t.property_id for t in rows if t.property_id})
    out = []
    for t in rows:
        src = members.get(t.from_member_id) if t.from_member_id else None
        dst = members.get(t.to_member_id)
        out.append(
            {
                **_transfer_result(t),
                "from_name": src.name if src else None,
                "to_name": dst.name if dst else None,
                "member_name": dst.name if dst else None,
                "property_title": titles.get(t.property_id) if t.property_id else None,
                "completed_at": (
                    t.materialized_at.isoformat()
                    if t.materialized_at and t.status == "completed"
                    else None
                ),
            }
        )
    return out


async def _property_titles(session: AsyncSession, ids: set) -> dict:
    if not ids:
        return {}
    res = await session.execute(select(Property.id, Property.title).where(Property.id.in_(ids)))
    return {pid: title for pid, title in res.all()}


async def list_activity(session: AsyncSession, user_id: uuid.UUID, *, limit: int = 200) -> dict:
    """Everything the family feature did with this member, newest first, whichever side they
    were on: members they added and groups they were added to, units transferred or
    allocated, returns allocated. Read from the tables themselves, so the page shows what
    happened whether or not a notification was read (client, 2026-10-07).

    In the caller's own group every line is theirs to see. In a group they were added to,
    only the lines they are part of, and the other side is named by their account name."""
    own = (
        await session.execute(select(FamilyGroup).where(FamilyGroup.owner_id == user_id))
    ).scalar_one_or_none()
    mine = (
        (await session.execute(select(FamilyMember).where(FamilyMember.user_id == user_id)))
        .scalars()
        .all()
    )
    my_rows = {m.id for m in mine}
    joined = [m for m in mine if own is None or m.family_group_id != own.id]

    group_ids = {m.family_group_id for m in joined} | ({own.id} if own else set())
    if not group_ids:
        return {"items": [], "memberships": []}
    groups = {
        g.id: g
        for g in (await session.execute(select(FamilyGroup).where(FamilyGroup.id.in_(group_ids))))
        .scalars()
        .all()
    }

    in_own = FamilyTransfer.family_group_id == own.id if own else None
    with_me = or_(
        FamilyTransfer.to_member_id.in_(my_rows), FamilyTransfer.from_member_id.in_(my_rows)
    )
    transfers = (
        (
            await session.execute(
                select(FamilyTransfer)
                .where(or_(in_own, with_me) if in_own is not None else with_me)
                .order_by(FamilyTransfer.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    alloc_in_own = FamilyReturnAllocation.family_group_id == own.id if own else None
    alloc_mine = FamilyReturnAllocation.member_id.in_(my_rows)
    allocations = (
        (
            await session.execute(
                select(FamilyReturnAllocation)
                .where(or_(alloc_in_own, alloc_mine) if alloc_in_own is not None else alloc_mine)
                .order_by(FamilyReturnAllocation.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    member_ids = {t.to_member_id for t in transfers} | {a.member_id for a in allocations}
    member_ids |= {t.from_member_id for t in transfers if t.from_member_id}
    members = {m.id: m for m in mine}
    if own:
        for m in (
            (
                await session.execute(
                    select(FamilyMember).where(FamilyMember.family_group_id == own.id)
                )
            )
            .scalars()
            .all()
        ):
            members[m.id] = m
    missing = member_ids - set(members)
    if missing:
        for m in (
            (await session.execute(select(FamilyMember).where(FamilyMember.id.in_(missing))))
            .scalars()
            .all()
        ):
            members[m.id] = m

    accounts: dict[uuid.UUID, str] = {}

    async def account_name(uid: uuid.UUID | None) -> str:
        if uid is None:
            return "A family member"
        if uid not in accounts:
            accounts[uid] = await _display_name(session, uid)
        return accounts[uid]

    async def named(member: FamilyMember | None, group: FamilyGroup | None) -> str:
        """The other person on a line. In the caller's own group: the name the caller gave
        them. In someone else's group: that person's account name."""
        if member is None:
            return "A family member"
        if own is not None and group is not None and group.id == own.id:
            return member.name
        return await account_name(member.user_id)

    titles = await _property_titles(session, {t.property_id for t in transfers if t.property_id})
    items: list[dict] = []

    for t in transfers:
        group = groups.get(t.family_group_id)
        src = members.get(t.from_member_id) if t.from_member_id else None
        dst = members.get(t.to_member_id)
        sent = src is not None and src.user_id == user_id
        received = dst is not None and dst.user_id == user_id
        direction = "out" if sent else ("in" if received else "other")
        other = dst if sent or not received else src
        items.append(
            {
                "id": f"transfer:{t.id}",
                "kind": "transfer",
                "direction": direction,
                "at": t.created_at.isoformat() if t.created_at else None,
                "counterparty": await named(other, group),
                "from_name": None if sent else await named(src, group),
                "property_id": str(t.property_id) if t.property_id else None,
                "property_title": titles.get(t.property_id) if t.property_id else None,
                "units": t.units,
                "amount": None,
                "fee": str(_q(t.transfer_fee)) if t.transfer_fee and t.transfer_fee > 0 else None,
                "status": t.status,
                "completed_at": (
                    t.materialized_at.isoformat()
                    if t.materialized_at and t.status == "completed"
                    else None
                ),
                "relationship": None,
            }
        )

    for a in allocations:
        group = groups.get(a.family_group_id)
        member = members.get(a.member_id)
        to_me = member is not None and member.user_id == user_id
        mine_to_give = group is not None and group.owner_id == user_id
        if mine_to_give:
            direction, other_name = "out", (member.name if member else "A family member")
        else:
            direction = "in" if to_me else "other"
            other_name = await account_name(group.owner_id if group else None)
        items.append(
            {
                "id": f"returns:{a.id}",
                "kind": "returns",
                "direction": direction,
                "at": a.created_at.isoformat() if a.created_at else None,
                "counterparty": "yourself" if mine_to_give and to_me else other_name,
                "from_name": None,
                "property_id": None,
                "property_title": None,
                "units": None,
                "amount": str(_q(a.amount)),
                "fee": None,
                # recorded = a share of a distribution kept for a member who is not verified
                # yet (the platform wrote it); allocated = the owner allocated it
                "status": "recorded" if a.distribution_id is not None else "allocated",
                "completed_at": None,
                "relationship": None,
            }
        )

    if own:
        for m in members.values():
            if m.family_group_id != own.id or m.user_id == user_id:
                continue
            items.append(
                {
                    "id": f"member:{m.id}",
                    "kind": "member",
                    "direction": "out",
                    "at": m.created_at.isoformat() if m.created_at else None,
                    "counterparty": m.name,
                    "from_name": None,
                    "property_id": None,
                    "property_title": None,
                    "units": None,
                    "amount": None,
                    "fee": None,
                    "status": "verified" if m.is_verified else "pending",
                    "completed_at": None,
                    "relationship": m.relationship,
                }
            )

    memberships = []
    for m in joined:
        group = groups.get(m.family_group_id)
        owner_name = await account_name(group.owner_id if group else None)
        memberships.append(
            {
                "group_name": group.name if group else "Family group",
                "owner_name": owner_name,
                "relationship": m.relationship,
                "since": m.created_at.isoformat() if m.created_at else None,
                "is_verified": m.is_verified,
            }
        )
        items.append(
            {
                "id": f"member:{m.id}",
                "kind": "member",
                "direction": "in",
                "at": m.created_at.isoformat() if m.created_at else None,
                "counterparty": owner_name,
                "from_name": None,
                "property_id": None,
                "property_title": None,
                "units": None,
                "amount": None,
                "fee": None,
                "status": "verified" if m.is_verified else "pending",
                "completed_at": None,
                "relationship": m.relationship,
            }
        )

    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return {"items": items[:limit], "memberships": memberships}


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
        "pending_returns": str(m.pending_returns or 0),
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
