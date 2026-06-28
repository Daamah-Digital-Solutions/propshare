"""Admin property moderation (Phase 3).

Promotes an owner's submitted draft to ``active`` (go-live), rejects it back to
``draft`` with a reason, or closes a property. Every action is gated by the
action-time DB admin re-check (AdminDep) and written to the audit log.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import AdminDep, SessionDep
from app.models import Property
from app.models.base import PropertyStatus
from app.schemas.property import OwnerPropertyOut, PropertyModerateIn, PropertySummaryOut
from app.services import property_service

router = APIRouter(prefix="/api/v1/admin/properties", tags=["admin"])


@router.get("", response_model=list[PropertySummaryOut])
async def list_for_moderation(session: SessionDep, _admin: AdminDep, status: str = "under_review"):
    stmt = select(Property)
    if status in {s.value for s in PropertyStatus}:
        stmt = stmt.where(Property.status == PropertyStatus(status))
    stmt = stmt.order_by(Property.created_at.asc())
    rows = list((await session.execute(stmt)).scalars().all())
    owner_names = await property_service._owner_names(session, rows)
    return [PropertySummaryOut(**property_service.serialize_summary(p, owner_names)) for p in rows]


@router.post("/{prop_id}/approve", response_model=OwnerPropertyOut)
async def approve(prop_id: uuid.UUID, session: SessionDep, admin: AdminDep):
    prop = await property_service.admin_moderate(
        session, actor_id=admin.user_id, prop_id=prop_id, action="approve"
    )
    owner_names = await property_service._owner_names(session, [prop])
    return OwnerPropertyOut(**property_service.serialize_detail(prop, owner_names))


@router.post("/{prop_id}/reject", response_model=OwnerPropertyOut)
async def reject(
    prop_id: uuid.UUID, body: PropertyModerateIn, session: SessionDep, admin: AdminDep
):
    prop = await property_service.admin_moderate(
        session, actor_id=admin.user_id, prop_id=prop_id, action="reject", reason=body.reason
    )
    owner_names = await property_service._owner_names(session, [prop])
    return OwnerPropertyOut(**property_service.serialize_detail(prop, owner_names))


@router.post("/{prop_id}/close", response_model=OwnerPropertyOut)
async def close(prop_id: uuid.UUID, body: PropertyModerateIn, session: SessionDep, admin: AdminDep):
    prop = await property_service.admin_moderate(
        session, actor_id=admin.user_id, prop_id=prop_id, action="close", reason=body.reason
    )
    owner_names = await property_service._owner_names(session, [prop])
    return OwnerPropertyOut(**property_service.serialize_detail(prop, owner_names))
