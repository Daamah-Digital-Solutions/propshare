"""Platform receiving bank accounts (Task 3) — the accounts users deposit *to*.

Admin-managed (add/edit/remove freely from the admin panel). ``list_active`` is what a
depositing user sees; the admin sees everything. No money moves here — a bank-transfer
deposit is a manual claim (see manual_deposit_service) that an admin confirms.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import PlatformBankAccount

_EDITABLE = (
    "bank_name",
    "account_holder",
    "iban",
    "account_number",
    "swift_bic",
    "currency",
    "country",
    "instructions",
    "is_active",
    "sort_order",
)


async def list_active(session: AsyncSession) -> list[PlatformBankAccount]:
    res = await session.execute(
        select(PlatformBankAccount)
        .where(PlatformBankAccount.is_active.is_(True))
        .order_by(PlatformBankAccount.sort_order, PlatformBankAccount.created_at)
    )
    return list(res.scalars().all())


async def list_all(session: AsyncSession) -> list[PlatformBankAccount]:
    res = await session.execute(
        select(PlatformBankAccount).order_by(
            PlatformBankAccount.sort_order, PlatformBankAccount.created_at
        )
    )
    return list(res.scalars().all())


async def create(
    session: AsyncSession, *, actor_id: uuid.UUID, **fields: object
) -> PlatformBankAccount:
    bank_name = str(fields.get("bank_name") or "").strip()
    account_holder = str(fields.get("account_holder") or "").strip()
    if not bank_name or not account_holder:
        raise AppError(
            "INVALID_INPUT", "Bank name and account holder are required.", status_code=422
        )
    iban = str(fields.get("iban") or "").strip()
    account_number = str(fields.get("account_number") or "").strip()
    if not iban and not account_number:
        raise AppError("INVALID_INPUT", "Provide an IBAN or an account number.", status_code=422)
    acct = PlatformBankAccount(
        bank_name=bank_name,
        account_holder=account_holder,
        iban=iban or None,
        account_number=account_number or None,
        swift_bic=str(fields.get("swift_bic") or "").strip() or None,
        currency=str(fields.get("currency") or "USD").strip() or "USD",
        country=str(fields.get("country") or "").strip() or None,
        instructions=str(fields.get("instructions") or "").strip() or None,
        is_active=bool(fields["is_active"]) if fields.get("is_active") is not None else True,
        sort_order=int(fields.get("sort_order") or 0),
    )
    session.add(acct)
    await session.flush()
    await write_audit(
        session,
        action="platform_bank_account.created",
        entity_type="platform_bank_account",
        entity_id=str(acct.id),
        actor_id=actor_id,
        after={"bank_name": acct.bank_name},
    )
    return acct


async def update(
    session: AsyncSession, *, actor_id: uuid.UUID, account_id: uuid.UUID, **fields: object
) -> PlatformBankAccount:
    acct = await session.get(PlatformBankAccount, account_id)
    if acct is None:
        raise AppError("NOT_FOUND", "Platform bank account not found.", status_code=404)
    for key in _EDITABLE:
        if key not in fields or fields[key] is None:
            continue
        val = fields[key]
        if key == "is_active":
            acct.is_active = bool(val)
        elif key == "sort_order":
            acct.sort_order = int(val)  # type: ignore[arg-type]
        else:
            text = str(val).strip()
            # Required text fields can't be blanked; optional ones may be cleared.
            if key in ("bank_name", "account_holder"):
                if text:
                    setattr(acct, key, text)
            else:
                setattr(acct, key, text or None)
    await session.flush()
    await write_audit(
        session,
        action="platform_bank_account.updated",
        entity_type="platform_bank_account",
        entity_id=str(acct.id),
        actor_id=actor_id,
    )
    return acct


async def delete(session: AsyncSession, *, actor_id: uuid.UUID, account_id: uuid.UUID) -> None:
    acct = await session.get(PlatformBankAccount, account_id)
    if acct is None:
        raise AppError("NOT_FOUND", "Platform bank account not found.", status_code=404)
    await session.delete(acct)
    await write_audit(
        session,
        action="platform_bank_account.deleted",
        entity_type="platform_bank_account",
        entity_id=str(account_id),
        actor_id=actor_id,
    )
