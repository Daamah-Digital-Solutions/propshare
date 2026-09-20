"""Operational cases (Batch F, client doc §10, §12, §33): the platform opens an internal
ticket by itself when something needs a person — ledger drift found by the nightly
reconciliation, a bank-transfer claim nobody confirmed, a withdrawal nobody paid.

Cases are ``support_tickets`` rows with ``kind = 'ops_case'`` (no user, staff-only). Each
trigger has a stable ``context.case_key``; while a case with that key is open nothing is
opened again, so the hourly sweep never floods the queue. Closing the case (from the admin
panel) re-arms it. Admins are notified in-app once per new case and the support inbox gets
one email per sweep with the new cases.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.models import EmailOutbox, SupportTicket, UserRole
from app.services import (
    manual_deposit_service,
    notification_service,
    reconciliation_service,
    settings_service,
    withdrawal_service,
)

OPEN = ("open", "in_progress", "waiting_user")


async def _open_keys(session: AsyncSession) -> set[str]:
    rows = (
        await session.execute(
            select(SupportTicket.context).where(
                SupportTicket.kind == "ops_case", SupportTicket.status.in_(OPEN)
            )
        )
    ).all()
    return {str((r[0] or {}).get("case_key")) for r in rows}


async def _open_case(
    session: AsyncSession,
    *,
    case_key: str,
    category: str,
    priority: str,
    subject: str,
    summary: str,
    context: dict[str, Any],
) -> SupportTicket:
    ticket = SupportTicket(
        kind="ops_case",
        user_id=None,
        category=category,
        priority=priority,
        status="open",
        subject=subject,
        summary=summary,
        context={**context, "case_key": case_key},
        source="system",
    )
    session.add(ticket)
    await session.flush()
    await session.refresh(ticket)
    await write_audit(
        session,
        action="ops_case.opened",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        actor_id=None,
        after={"ticket_no": ticket.ticket_no, "case_key": case_key, "category": category},
    )
    return ticket


async def stale_hours(session: AsyncSession) -> int:
    return int(await settings_service.get_setting(session, "ops_stale_hours") or 48)


async def sweep(session: AsyncSession, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """One idempotent pass: reconciliation drift + stale bank claims + stale withdrawals."""
    now = now or dt.datetime.now(dt.UTC)
    open_keys = await _open_keys(session)
    new: list[SupportTicket] = []
    hours = await stale_hours(session)
    cutoff = now - dt.timedelta(hours=hours)

    # 1) ledger drift -> one case per failing check
    report = await reconciliation_service.run(session)
    for check in report["checks"]:
        if not check["drift_count"]:
            continue
        key = f"reconciliation:{check['name']}"
        if key in open_keys:
            continue
        samples = "; ".join(
            ", ".join(f"{k}={v}" for k, v in s.items()) for s in check["samples"][:5]
        )
        new.append(
            await _open_case(
                session,
                case_key=key,
                category="reconciliation",
                priority="high",
                subject=f"Ledger drift: {check['name']} ({check['drift_count']} row(s))",
                summary=(
                    f"The nightly reconciliation found {check['drift_count']} row(s) failing the "
                    f"'{check['name']}' check. Samples: {samples or 'none'}. Nothing was "
                    "changed automatically; investigate in the admin panel."
                ),
                context={"check": check["name"], "drift_count": check["drift_count"]},
            )
        )
        open_keys.add(key)

    # 2) bank-transfer claims nobody confirmed or rejected
    for payment, _email in await manual_deposit_service.list_pending_for_admin(session):
        if payment.created_at > cutoff:
            continue
        key = f"bank_claim:{payment.id}"
        if key in open_keys:
            continue
        age = round((now - payment.created_at).total_seconds() / 3600)
        new.append(
            await _open_case(
                session,
                case_key=key,
                category="payments",
                priority="normal",
                subject=f"Bank transfer claim unconfirmed for {age}h",
                summary=(
                    f"A bank-transfer deposit claim of {payment.amount} {payment.currency} "
                    f"(reference {payment.provider_payment_id or 'n/a'}) has been pending for "
                    f"{age} hours. Confirm or reject it under Bank Deposit Claims."
                ),
                context={"payment_id": str(payment.id), "age_hours": age},
            )
        )
        open_keys.add(key)

    # 3) withdrawals waiting for a payout
    for w, _email in await withdrawal_service.list_for_admin(session, status="pending"):
        if w.created_at > cutoff:
            continue
        key = f"withdrawal:{w.id}"
        if key in open_keys:
            continue
        age = round((now - w.created_at).total_seconds() / 3600)
        new.append(
            await _open_case(
                session,
                case_key=key,
                category="withdrawals",
                priority="high",
                subject=f"Withdrawal unpaid for {age}h",
                summary=(
                    f"A {w.method} withdrawal of {w.amount} has been waiting for {age} hours. "
                    "The member's funds are on hold: mark it paid or reject it under Withdrawals."
                ),
                context={"withdrawal_id": str(w.id), "age_hours": age},
            )
        )
        open_keys.add(key)

    if new:
        admins = [
            r[0]
            for r in (
                await session.execute(select(UserRole.user_id).where(UserRole.role == "admin"))
            ).all()
        ]
        lines = [f"{t.ticket_no} · {t.subject}" for t in new]
        for admin_id in admins:
            await notification_service.notify(
                session,
                user_id=admin_id,
                type="ops_case",
                title=f"{len(new)} new operational case(s)",
                message="\n".join(lines[:10]),
            )
        inbox = get_settings().support_inbox_email
        if inbox:
            session.add(
                EmailOutbox(
                    user_id=None,
                    to_email=inbox,
                    subject=f"[Ops] {len(new)} new case(s) need a person",
                    body="\n".join(lines),
                    category="support",
                    status="pending",
                )
            )
        await session.flush()
    return {
        "opened": len(new),
        "drift_checks_failing": sum(1 for c in report["checks"] if c["drift_count"]),
        "stale_hours": hours,
    }
