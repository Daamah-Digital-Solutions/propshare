"""Investor-communications service (Phase 15c).

A developer (owner role) sends a per-property update; it fans out to that property's
current **net-holders** (distinct ``ownership_ledger`` users with Σ units > 0 — the
Phase-15 definition, the same audience the distribution engine pays) via the Phase-12
``notify()`` seam (in-app always; email when the recipient's ``investment_updates``
preference is on). Each target is recorded in ``developer_update_recipients`` with the
created notification id, so read-count is REAL. Idempotent per (update_id, user_id).

Metrics are counts only: ``recipient_count`` (snapshot) + ``read_count`` (notifications.read).
Email open/click/delivered are NOT tracked (no infra) and never fabricated.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import (
    DeveloperUpdate,
    DeveloperUpdateRecipient,
    Notification,
    OwnershipLedger,
    Property,
)
from app.services import notification_service

UPDATE_TYPE = "developer_update"
EMAIL_CATEGORY = "investment_updates"


async def _get_owned_property(
    session: AsyncSession, owner_id: uuid.UUID, prop_id: uuid.UUID
) -> Property:
    prop = await session.get(Property, prop_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)
    if prop.owner_id != owner_id:
        raise AppError("NOT_PROPERTY_OWNER", "You do not own this property.", status_code=403)
    return prop


async def _net_holders(session: AsyncSession, property_id: uuid.UUID) -> list[uuid.UUID]:
    """Distinct net-holders (Σ units > 0) for a property — the audience for an update."""
    res = await session.execute(
        select(OwnershipLedger.user_id)
        .where(OwnershipLedger.property_id == property_id)
        .group_by(OwnershipLedger.user_id)
        .having(func.coalesce(func.sum(OwnershipLedger.units), 0) > 0)
    )
    return sorted((r[0] for r in res.all()), key=str)


async def read_counts_map(
    session: AsyncSession, update_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """In-app read-count per update = recipients whose linked notification is read."""
    if not update_ids:
        return {}
    res = await session.execute(
        select(
            DeveloperUpdateRecipient.update_id,
            func.count().filter(Notification.read.is_(True)),
        )
        .select_from(DeveloperUpdateRecipient)
        .outerjoin(Notification, Notification.id == DeveloperUpdateRecipient.notification_id)
        .where(DeveloperUpdateRecipient.update_id.in_(update_ids))
        .group_by(DeveloperUpdateRecipient.update_id)
    )
    return {uid: int(cnt or 0) for uid, cnt in res.all()}


def serialize(upd: DeveloperUpdate, read_count: int) -> dict:
    return {
        "id": upd.id,
        "property_id": upd.property_id,
        "subject": upd.subject,
        "body": upd.body,
        "recipient_count": upd.recipient_count,
        "read_count": read_count,
        "created_at": upd.created_at,
    }


async def send_update(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    property_id: uuid.UUID,
    subject: str,
    body: str,
) -> DeveloperUpdate:
    """Create the update and fan it out to the property's net-holders (one atomic tx)."""
    await _get_owned_property(session, owner_id, property_id)
    upd = DeveloperUpdate(
        id=uuid.uuid4(),
        property_id=property_id,
        created_by=owner_id,
        subject=subject,
        body=body,
        recipient_count=0,
    )
    session.add(upd)

    holders = await _net_holders(session, property_id)
    for uid in holders:
        notification = await notification_service.notify(
            session,
            user_id=uid,
            type=UPDATE_TYPE,
            title=subject,
            message=body,
            email_category=EMAIL_CATEGORY,
        )
        session.add(
            DeveloperUpdateRecipient(update_id=upd.id, user_id=uid, notification_id=notification.id)
        )
    upd.recipient_count = len(holders)
    await session.commit()
    await session.refresh(upd)
    return upd


async def list_updates(
    session: AsyncSession, owner_id: uuid.UUID, *, property_id: uuid.UUID | None = None
) -> list[dict]:
    """The developer's sent updates (newest first), owner-scoped, with real counts."""
    if property_id is not None:
        await _get_owned_property(session, owner_id, property_id)

    q = (
        select(DeveloperUpdate)
        .join(Property, Property.id == DeveloperUpdate.property_id)
        .where(Property.owner_id == owner_id)
    )
    if property_id is not None:
        q = q.where(DeveloperUpdate.property_id == property_id)
    q = q.order_by(DeveloperUpdate.created_at.desc())

    rows = (await session.execute(q)).scalars().all()
    read_map = await read_counts_map(session, [r.id for r in rows])
    return [serialize(r, read_map.get(r.id, 0)) for r in rows]
