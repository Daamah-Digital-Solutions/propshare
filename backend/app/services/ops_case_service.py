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
from app.models import EmailOutbox, Payment, SupportTicket, UserRole
from app.services import (
    manual_deposit_service,
    notification_service,
    payment_service,
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


async def card_payment_stale_hours(session: AsyncSession) -> int:
    """Hours a CARD payment may stay pending before a case is opened. Stripe expires an unpaid
    checkout after 24 hours and the lookup then marks the payment failed, so one still pending
    past that means the lookup itself cannot reach Stripe (key permissions, outage) — never
    merely a member who closed the checkout page."""
    return int(await settings_service.get_setting(session, "ops_payment_stale_hours") or 25)


async def _payment_case_keys(session: AsyncSession) -> set[str]:
    """Every stuck-payment case ever opened, open or closed: a payment gets ONE case. Once staff
    close it (checked, or an abandoned checkout) the hourly sweep does not open it again."""
    rows = (
        await session.execute(
            select(SupportTicket.context).where(
                SupportTicket.kind == "ops_case",
                SupportTicket.context["case_key"].astext.like("provider_payment:%"),
            )
        )
    ).all()
    return {str((r[0] or {}).get("case_key")) for r in rows}


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
        ref = manual_deposit_service.claim_reference(payment) or "none given"
        new.append(
            await _open_case(
                session,
                case_key=key,
                category="payments",
                priority="normal",
                subject=f"Bank transfer claim unconfirmed for {age}h",
                summary=(
                    f"A bank-transfer deposit claim of {payment.amount} {payment.currency} "
                    f"(reference {ref}) has been pending for {age} hours. Confirm or reject it "
                    "under Bank Deposit Claims."
                ),
                context={"payment_id": str(payment.id), "age_hours": age},
            )
        )
        open_keys.add(key)

    # 3) withdrawals waiting for a payout (in review, or approved but never sent)
    for w, _email in await withdrawal_service.list_awaiting_payout(session):
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

    # 4) card / crypto payments no webhook settled. The Stripe lookup settles or fails every
    #    card payment it can (an unpaid checkout expires after 24 h and is then marked failed),
    #    so a card payment still pending past ``card_payment_stale_hours`` means the lookup
    #    cannot reach Stripe — a real problem. Crypto is not looked up: an invoice still
    #    pending after ``ops_stale_hours`` is usually abandoned, so its case is low-key. One
    #    case per payment, ever: a closed case is not reopened.
    await payment_service.reconcile_pending(session, now=now)
    card_cutoff = now - dt.timedelta(hours=await card_payment_stale_hours(session))
    seen_keys = await _payment_case_keys(session)
    stuck = (
        (
            await session.execute(
                select(Payment)
                .where(
                    Payment.status == "pending",
                    Payment.provider.in_(payment_service.WEBHOOK_PROVIDERS),
                    # the younger of the two thresholds; each provider's own one is applied below
                    Payment.created_at <= max(card_cutoff, cutoff),
                    Payment.created_at >= now - payment_service.SYNC_MAX_AGE,
                )
                .order_by(Payment.created_at)
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    for payment in stuck:
        key = f"provider_payment:{payment.id}"
        if key in seen_keys:
            continue
        card = payment.provider == "stripe"
        if card and payment.created_at > card_cutoff:
            continue
        if not card and payment.created_at > cutoff:
            continue
        age = round((now - payment.created_at).total_seconds() / 3600)
        what = "purchase" if payment.purpose == "investment" else "deposit"
        ref = payment.provider_payment_id or "none"
        if card:
            subject = f"Card {what} still pending {age}h after checkout"
            summary = (
                f"A card {what} of {payment.amount} {payment.currency} (Stripe checkout {ref}) "
                f"is still pending {age} hours after it started, although Stripe expires an "
                "unpaid checkout after 24 hours: the platform could not get its outcome from "
                "Stripe. Check that the Stripe key can read Checkout Sessions and that the "
                "deposits webhook delivers, then press 'Check with Stripe' on it under Payments."
            )
        else:
            subject = f"Crypto {what} invoice pending for {age}h"
            summary = (
                f"A crypto {what} of {payment.amount} {payment.currency} (NOWPayments invoice "
                f"{ref}) has been pending for {age} hours. Most are simply abandoned invoices: "
                "if the member did not pay, close this case. If they say they paid, find the "
                "payment in the NOWPayments dashboard and check its IPN deliveries."
            )
        new.append(
            await _open_case(
                session,
                case_key=key,
                category="payments",
                priority="high" if card else "normal",
                subject=subject,
                summary=summary,
                context={
                    "payment_id": str(payment.id),
                    "provider": payment.provider,
                    "provider_payment_id": payment.provider_payment_id,
                    "age_hours": age,
                },
            )
        )
        seen_keys.add(key)

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
