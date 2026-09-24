"""Staff copilot tools (Batch A, plan §29): READ-ONLY operational queues for admins.

Nothing here decides anything: the queues point staff to the admin panel where every action
is taken (and audited). Identities are masked; amounts, statuses, ages and references only.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import (
    AssistantConversation,
    Investment,
    KycVerification,
    Property,
    SupportTicket,
    User,
    Wallet,
)
from app.services import (
    auth_service,
    manual_deposit_service,
    reconciliation_service,
    withdrawal_service,
)
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.account import mask_email
from app.services.assistant.tools.base import NoArgs, ToolOutput, ToolSpec, register

ADMIN = ("admin",)


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _age_hours(ts: dt.datetime | None) -> float | None:
    if ts is None:
        return None
    return round((dt.datetime.now(dt.UTC) - ts).total_seconds() / 3600, 1)


# --------------------------------------------------------------------------- #
class OpsOverviewOut(ToolOutput):
    kyc_pending: int
    kyc_manual_review: int
    bank_deposits_pending: int
    withdrawals_awaiting: int
    tickets_open: int
    tickets_waiting_user: int
    knowledge_gaps_open: int
    properties_pending_review: int
    assistant_conversations_today: int
    as_of: str


async def _get_ops_overview(session: AsyncSession, ctx: AgentContext, args) -> dict:
    async def count(stmt) -> int:
        return int(await session.scalar(stmt) or 0)

    today = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    deposits = await manual_deposit_service.list_pending_for_admin(session)
    withdrawals = await withdrawal_service.list_awaiting_payout(session)
    return {
        # verification started and waiting for the provider's (or a person's) decision
        "kyc_pending": await count(
            select(func.count())
            .select_from(KycVerification)
            .where(KycVerification.status == "submitted")
        ),
        "kyc_manual_review": await count(
            select(func.count())
            .select_from(KycVerification)
            .where(KycVerification.manual_review_required.is_(True))
        ),
        "bank_deposits_pending": len(deposits),
        "withdrawals_awaiting": len(withdrawals),
        "tickets_open": await count(
            select(func.count())
            .select_from(SupportTicket)
            .where(
                SupportTicket.kind == "support", SupportTicket.status.in_(("open", "in_progress"))
            )
        ),
        "tickets_waiting_user": await count(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.kind == "support", SupportTicket.status == "waiting_user")
        ),
        "knowledge_gaps_open": await count(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.kind == "knowledge_gap", SupportTicket.status == "open")
        ),
        "properties_pending_review": await count(
            select(func.count()).select_from(Property).where(Property.status == "under_review")
        ),
        "assistant_conversations_today": await count(
            select(func.count())
            .select_from(AssistantConversation)
            .where(AssistantConversation.created_at >= today)
        ),
        "as_of": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
    }


register(
    ToolSpec(
        "get_ops_overview",
        "Staff only: today's operational queues in numbers (KYC waiting, bank deposits to "
        "confirm, withdrawals awaiting payout, open tickets, knowledge gaps, listings "
        "pending review). Read-only; actions happen in the admin panel.",
        NoArgs,
        OpsOverviewOut,
        "read_own",
        _get_ops_overview,
        roles=ADMIN,
    )
)


# --------------------------------------------------------------------------- #
class QueueRow(ToolOutput):
    id: str
    user_masked: str | None
    amount: str | None
    method: str | None
    status: str
    reference: str | None
    age_hours: float | None
    created_at: str | None


class QueueOut(ToolOutput):
    queue: str
    items: list[QueueRow]
    total: int


class QueueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queue: str = Field(
        description="One of: bank_deposits, withdrawals, kyc, tickets, knowledge_gaps, ops_cases"
    )
    limit: int = Field(default=10, ge=1, le=25)


async def _list_queue(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: QueueIn = args
    items: list[dict] = []
    if a.queue == "bank_deposits":
        rows = await manual_deposit_service.list_pending_for_admin(session)
        items = [
            {
                "id": str(p.id),
                "user_masked": mask_email(email),
                "amount": str(p.amount),
                "method": p.payment_method or "bank_transfer",
                "status": str(p.status),
                "reference": manual_deposit_service.claim_reference(p),
                "age_hours": _age_hours(p.created_at),
                "created_at": _iso(p.created_at),
            }
            for p, email in rows
        ]
    elif a.queue == "withdrawals":
        rows = await withdrawal_service.list_awaiting_payout(session)
        items = [
            {
                "id": str(w.id),
                "user_masked": mask_email(email),
                "amount": str(w.amount),
                "method": w.method,
                "status": str(w.status),
                "reference": None,
                "age_hours": _age_hours(w.created_at),
                "created_at": _iso(w.created_at),
            }
            for w, email in rows
        ]
    elif a.queue == "kyc":
        rows = (
            await session.execute(
                select(KycVerification, User.email)
                .join(User, User.id == KycVerification.user_id)
                .where(
                    (KycVerification.manual_review_required.is_(True))
                    | (KycVerification.status == "submitted")
                )
                .order_by(KycVerification.submitted_at.asc().nulls_last())
            )
        ).all()
        items = [
            {
                "id": str(k.id),
                "user_masked": mask_email(email),
                "amount": None,
                "method": "manual_review" if k.manual_review_required else "in_review",
                "status": str(k.status),
                "reference": None,
                "age_hours": _age_hours(k.submitted_at),
                "created_at": _iso(k.submitted_at),
            }
            for k, email in rows
        ]
    elif a.queue in ("tickets", "knowledge_gaps", "ops_cases"):
        kind = {"tickets": "support", "knowledge_gaps": "knowledge_gap", "ops_cases": "ops_case"}[
            a.queue
        ]
        rows = (
            await session.execute(
                select(SupportTicket, User.email)
                .join(User, User.id == SupportTicket.user_id, isouter=True)
                .where(
                    SupportTicket.kind == kind,
                    SupportTicket.status.in_(("open", "in_progress")),
                )
                .order_by(SupportTicket.created_at.asc())
            )
        ).all()
        items = [
            {
                "id": str(t.id),
                "user_masked": mask_email(email or t.contact_email),
                "amount": None,
                "method": t.category,
                "status": f"{t.status} ({t.priority})",
                "reference": t.ticket_no,
                "age_hours": _age_hours(t.created_at),
                "created_at": _iso(t.created_at),
            }
            for t, email in rows
        ]
    else:
        raise AppError(
            "INVALID_INPUT",
            "queue must be one of bank_deposits, withdrawals, kyc, tickets, knowledge_gaps, "
            "ops_cases.",
            status_code=422,
        )
    return {"queue": a.queue, "items": items[: a.limit], "total": len(items)}


register(
    ToolSpec(
        "list_ops_queue",
        "Staff only: the oldest items waiting in one operational queue (bank deposits to "
        "confirm, withdrawals to pay, KYC to review, open tickets, knowledge gaps) with "
        "masked user, amount, age and reference. Read-only.",
        QueueIn,
        QueueOut,
        "read_own",
        _list_queue,
        roles=ADMIN,
    )
)


# --------------------------------------------------------------------------- #
class LookupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(description="Exact email address of the member to look up")


class LookupOut(ToolOutput):
    found: bool
    user_masked: str | None
    full_name: str | None
    roles: list[str]
    active_role: str | None
    email_verified: bool | None
    kyc_status: str | None
    kyc_manual_review: bool | None
    wallet_balance: str | None
    wallet_pending: str | None
    investments: int | None
    open_tickets: int | None
    member_since: str | None


async def _lookup_member(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: LookupIn = args
    user = await auth_service.get_user_by_email(session, a.email.strip().lower())
    if user is None:
        return {
            "found": False,
            "user_masked": None,
            "full_name": None,
            "roles": [],
            "active_role": None,
            "email_verified": None,
            "kyc_status": None,
            "kyc_manual_review": None,
            "wallet_balance": None,
            "wallet_pending": None,
            "investments": None,
            "open_tickets": None,
            "member_since": None,
        }
    kyc = await session.scalar(select(KycVerification).where(KycVerification.user_id == user.id))
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user.id))
    investments = await session.scalar(
        select(func.count()).select_from(Investment).where(Investment.user_id == user.id)
    )
    tickets = await session.scalar(
        select(func.count())
        .select_from(SupportTicket)
        .where(
            SupportTicket.user_id == user.id,
            SupportTicket.kind == "support",
            SupportTicket.status.in_(("open", "in_progress")),
        )
    )
    return {
        "found": True,
        "user_masked": mask_email(user.email),
        "full_name": user.full_name,
        "roles": list(await auth_service.get_roles(session, user.id)),
        "active_role": str(user.active_role) if user.active_role is not None else None,
        "email_verified": bool(user.email_verified),
        "kyc_status": str(kyc.status) if kyc else None,
        "kyc_manual_review": bool(kyc.manual_review_required) if kyc else None,
        "wallet_balance": str(wallet.balance) if wallet else None,
        "wallet_pending": str(wallet.pending_balance) if wallet else None,
        "investments": int(investments or 0),
        "open_tickets": int(tickets or 0),
        "member_since": _iso(user.created_at),
    }


register(
    ToolSpec(
        "lookup_member",
        "Staff only: a member's account facts by exact email (masked email, roles, "
        "verification, wallet balances, number of investments and open tickets). No "
        "documents, no ids, no transactions.",
        LookupIn,
        LookupOut,
        "read_own",
        _lookup_member,
        roles=ADMIN,
    )
)


# --------------------------------------------------------------------------- #
class CheckRow(ToolOutput):
    name: str
    drift_count: int


class ReconciliationOut(ToolOutput):
    ok: bool
    checks: list[CheckRow]
    as_of: str


async def _run_reconciliation_check(session: AsyncSession, ctx: AgentContext, args) -> dict:
    report = await reconciliation_service.run(session)
    return {
        "ok": bool(report["ok"]),
        "checks": [
            {"name": c["name"], "drift_count": int(c["drift_count"])} for c in report["checks"]
        ],
        "as_of": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
    }


register(
    ToolSpec(
        "run_reconciliation_check",
        "Staff only: run the read-only ledger reconciliation (wallet balances, pending "
        "balances, units per property, non-negative ownership, family transfers, "
        "distribution splits) and report drift counts per check. Changes nothing.",
        NoArgs,
        ReconciliationOut,
        "read_own",
        _run_reconciliation_check,
        roles=ADMIN,
    )
)


__all__ = ["ADMIN"]
