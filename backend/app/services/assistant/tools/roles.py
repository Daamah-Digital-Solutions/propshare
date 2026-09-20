"""Role tools (Batch A, plan Phase 2): owners/developers, brokers, liquidity providers,
family groups, scheduled gifts and notification preferences — all read-only, all scoped to
the signed-in user, all behind the role that owns the data.

Same rule as ``account.py``: output models are allow-lists. Family members' personal data,
clients' identities, storage keys and provider ids never appear here.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Document, Property
from app.services import (
    broker_service,
    developer_update_service,
    family_service,
    gift_service,
    liquidity_service,
    milestone_service,
    notification_service,
    property_service,
)
from app.services.assistant import guard
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.base import NoArgs, ToolOutput, ToolSpec, register


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _uid(ctx: AgentContext) -> uuid.UUID:
    assert ctx.user_id is not None
    return ctx.user_id


def _pct(total: int, available: int) -> float:
    return round((total - available) / total * 100, 2) if total else 0.0


# --------------------------------------------------------------------------- #
# Owner / developer
# --------------------------------------------------------------------------- #
class OwnedProperty(ToolOutput):
    id: str
    slug: str | None
    title: str
    status: str
    model: str
    unit_price: float | None
    total_units: int
    available_units: int
    units_sold: int
    funding_progress_pct: float
    expected_completion: str | None
    construction_progress_pct: int | None
    created_at: str | None


class MyPropertiesOut(ToolOutput):
    items: list[OwnedProperty]
    as_of: str


async def _list_my_properties(session: AsyncSession, ctx: AgentContext, args) -> dict:
    props = await property_service.list_owner(session, _uid(ctx))
    progress = await milestone_service.construction_progress_map(session, [p.id for p in props])
    return {
        "items": [
            {
                "id": str(p.id),
                "slug": p.slug,
                "title": p.title,
                "status": str(p.status),
                "model": str(p.model),
                "unit_price": float(p.unit_price) if p.unit_price is not None else None,
                "total_units": int(p.total_units or 0),
                "available_units": int(p.available_units or 0),
                "units_sold": int((p.total_units or 0) - (p.available_units or 0)),
                "funding_progress_pct": _pct(int(p.total_units or 0), int(p.available_units or 0)),
                "expected_completion": _iso(p.expected_completion),
                "construction_progress_pct": progress.get(p.id),
                "created_at": _iso(p.created_at),
            }
            for p in props
        ],
        "as_of": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
    }


register(
    ToolSpec(
        "list_my_properties",
        "The signed-in owner's or developer's own listings with status (draft, pending "
        "review, active, funded, closed), units sold, funding progress and construction "
        "progress. Owners and developers only.",
        NoArgs,
        MyPropertiesOut,
        "read_own",
        _list_my_properties,
        roles=("owner", "admin"),
    )
)


class PropertyIdIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: str = Field(description="Id of one of the caller's own properties")


class MilestoneRow(ToolOutput):
    title: str
    status: str
    progress_pct: int | None
    target_date: str | None
    completed_at: str | None


class UpdateRow(ToolOutput):
    subject: dict | None
    recipient_count: int
    read_count: int
    created_at: str | None


class DocumentRow(ToolOutput):
    title: str
    type: str
    created_at: str | None


class MyPropertyDetailOut(ToolOutput):
    property: OwnedProperty
    milestones: list[MilestoneRow]
    updates: list[UpdateRow]
    documents: list[DocumentRow]


async def _get_my_property(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: PropertyIdIn = args
    try:
        pid = uuid.UUID(a.property_id)
    except ValueError as exc:
        raise AppError("INVALID_INPUT", "property_id is not a valid id.", status_code=422) from exc
    props = {p.id: p for p in await property_service.list_owner(session, _uid(ctx))}
    prop = props.get(pid)
    if prop is None:
        raise AppError("NOT_FOUND", "That property is not one of yours.", status_code=404)
    summary = (await _list_my_properties(session, ctx, args))["items"]
    mine = next(x for x in summary if x["id"] == str(pid))
    milestones = await milestone_service.list_owned(session, _uid(ctx), pid)
    updates = await developer_update_service.list_updates(session, _uid(ctx), property_id=pid)
    docs = (
        (
            await session.execute(
                select(Document)
                .where(Document.property_id == pid)
                .order_by(Document.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "property": mine,
        "milestones": [
            {
                "title": m.title,
                "status": str(m.status),
                "progress_pct": m.progress_pct,
                "target_date": _iso(m.target_date),
                "completed_at": _iso(m.completed_at),
            }
            for m in milestones
        ],
        "updates": [
            {
                "subject": guard.wrap_untrusted(u.get("subject")),
                "recipient_count": int(u.get("recipient_count") or 0),
                "read_count": int(u.get("read_count") or 0),
                "created_at": _iso(u.get("created_at")),
            }
            for u in updates
        ],
        "documents": [
            {"title": d.title, "type": str(d.type), "created_at": _iso(d.created_at)} for d in docs
        ],
    }


register(
    ToolSpec(
        "get_my_property",
        "One of the caller's own listings in detail: funding, construction milestones, the "
        "developer updates already sent (with read counts) and the documents on file. "
        "Owners and developers only.",
        PropertyIdIn,
        MyPropertyDetailOut,
        "read_own",
        _get_my_property,
        roles=("owner", "admin"),
    )
)


# --------------------------------------------------------------------------- #
# Broker
# --------------------------------------------------------------------------- #
class ReferralRow(ToolOutput):
    client_masked: str
    created_at: str | None
    commission_to_date: str


class CommissionRow(ToolOutput):
    revenue_event_type: str
    revenue_amount: str
    commission_rate: str
    commission_amount: str
    created_at: str | None


class BrokerActivityOut(ToolOutput):
    referrals: list[ReferralRow]
    commissions: list[CommissionRow]
    commissions_total_count: int


async def _get_my_broker_activity(session: AsyncSession, ctx: AgentContext, args) -> dict:
    refs = await broker_service.list_referrals(session, _uid(ctx))
    rows, total = await broker_service.list_commissions(session, _uid(ctx), limit=20)
    return {
        "referrals": [
            {
                "client_masked": r["client_masked"],
                "created_at": r.get("created_at"),
                "commission_to_date": r["commission_to_date"],
            }
            for r in refs[:50]
        ],
        "commissions": [
            {
                "revenue_event_type": c["revenue_event_type"],
                "revenue_amount": c["revenue_amount"],
                "commission_rate": c["commission_rate"],
                "commission_amount": c["commission_amount"],
                "created_at": c.get("created_at"),
            }
            for c in rows
        ],
        "commissions_total_count": int(total),
    }


register(
    ToolSpec(
        "get_my_broker_activity",
        "The signed-in broker's referred clients (masked) with commission earned per client, "
        "and the latest commission entries. Brokers only.",
        NoArgs,
        BrokerActivityOut,
        "read_own",
        _get_my_broker_activity,
        roles=("broker",),
    )
)


# --------------------------------------------------------------------------- #
# Liquidity provider
# --------------------------------------------------------------------------- #
class LpPositionRow(ToolOutput):
    request_id: str | None
    property_title: str | None
    units: int | None
    lp_price: str | None
    status: str | None
    created_at: str | None


class LpPositionsOut(ToolOutput):
    items: list[LpPositionRow]


async def _list_my_lp_positions(session: AsyncSession, ctx: AgentContext, args) -> dict:
    rows = await liquidity_service.list_my_positions(session, _uid(ctx))
    return {
        "items": [
            {
                "request_id": _iso(r.get("request_id")),
                "property_title": r.get("property_title"),
                "units": r.get("units"),
                "lp_price": _iso(r.get("lp_price")),
                "status": r.get("status"),
                "created_at": _iso(r.get("created_at") or r.get("funded_at")),
            }
            for r in rows[:50]
        ]
    }


register(
    ToolSpec(
        "list_my_lp_positions",
        "The signed-in liquidity provider's funded exit requests (acquisition history). "
        "Liquidity providers only.",
        NoArgs,
        LpPositionsOut,
        "read_own",
        _list_my_lp_positions,
        roles=("liquidity_provider",),
    )
)


# --------------------------------------------------------------------------- #
# Family transfers, scheduled gifts, notification preferences
# --------------------------------------------------------------------------- #
class TransferRow(ToolOutput):
    id: str | None
    member_name: str | None
    property_title: str | None
    units: int | None
    status: str | None
    created_at: str | None


class TransfersOut(ToolOutput):
    items: list[TransferRow]


async def _list_my_family_transfers(session: AsyncSession, ctx: AgentContext, args) -> dict:
    rows = await family_service.list_transfers(session, _uid(ctx))
    return {
        "items": [
            {
                "id": _iso(r.get("id") or r.get("transfer_id")),
                "member_name": r.get("member_name") or r.get("name"),
                "property_title": r.get("property_title"),
                "units": r.get("units"),
                "status": r.get("status"),
                "created_at": _iso(r.get("created_at")),
            }
            for r in rows[:50]
        ]
    }


register(
    ToolSpec(
        "list_my_family_transfers",
        "Unit transfers the signed-in user made inside their family group (member, property, "
        "units, status). No member personal data.",
        NoArgs,
        TransfersOut,
        "read_own",
        _list_my_family_transfers,
    )
)


class GiftRow(ToolOutput):
    id: str
    recipient_name: str | None
    asset_type: str
    property_title: str | None
    units: int | None
    amount: str | None
    scheduled_for: str | None
    recurring: bool
    status: str
    failure_reason: dict | None


class GiftsOut(ToolOutput):
    items: list[GiftRow]


async def _list_my_scheduled_gifts(session: AsyncSession, ctx: AgentContext, args) -> dict:
    gifts = await gift_service.list_gifts(session, _uid(ctx))
    titles: dict[uuid.UUID, str] = {}
    pids = [g.property_id for g in gifts if g.property_id]
    if pids:
        rows = await session.execute(
            select(Property.id, Property.title).where(Property.id.in_(pids))
        )
        titles = {r[0]: r[1] for r in rows.all()}
    return {
        "items": [
            {
                "id": str(g.id),
                "recipient_name": g.recipient_name,
                "asset_type": str(g.asset_type),
                "property_title": titles.get(g.property_id) if g.property_id else None,
                "units": g.units,
                "amount": str(g.amount) if g.amount is not None else None,
                "scheduled_for": _iso(g.scheduled_for),
                "recurring": bool(g.recurring),
                "status": str(g.status),
                "failure_reason": guard.wrap_untrusted(g.failure_reason),
            }
            for g in gifts[:50]
        ]
    }


register(
    ToolSpec(
        "list_my_scheduled_gifts",
        "The signed-in user's scheduled gifts (units or wallet amount) with recipient name, "
        "date, recurrence and status. Cancelling one is a confirmable action.",
        NoArgs,
        GiftsOut,
        "read_own",
        _list_my_scheduled_gifts,
    )
)


class PrefsOut(ToolOutput):
    email_investment_updates: bool
    email_returns: bool
    email_security_alerts: bool
    email_new_properties: bool


async def _get_my_notification_preferences(session: AsyncSession, ctx: AgentContext, args) -> dict:
    return await notification_service.get_preferences(session, _uid(ctx))


register(
    ToolSpec(
        "get_my_notification_preferences",
        "Which email notifications the signed-in user receives (investment updates, returns, "
        "security alerts, new properties). Changing them is a confirmable action.",
        NoArgs,
        PrefsOut,
        "read_own",
        _get_my_notification_preferences,
    )
)
