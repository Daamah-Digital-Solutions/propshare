"""Notification routes (Phase 12) — the read path the bell + feed consume.

Authenticated users read/mutate only their OWN notifications + email preferences. Only
the email channels we actually deliver are offered (in-app is always on; SMS/push do not
exist). The admin email-dispatch endpoint drains the transactional outbox and is intended
as a Phase-13 cron target.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import AdminOrCronDep, PrincipalDep, SessionDep
from app.core.errors import AppError
from app.schemas.notifications import (
    DispatchOut,
    MarkAllOut,
    NotificationListOut,
    NotificationOut,
    OkOut,
    PreferencesIn,
    PreferencesOut,
    UnreadCountOut,
)
from app.services import email_service, notification_service

router = APIRouter(prefix="/api/v1", tags=["notifications"])


def _out(n) -> NotificationOut:
    return NotificationOut(
        id=str(n.id),
        type=n.type,
        title=n.title,
        message=n.message,
        read=n.read,
        created_at=n.created_at.isoformat() if n.created_at else "",
    )


@router.get("/notifications", response_model=NotificationListOut)
async def list_notifications(
    session: SessionDep,
    principal: PrincipalDep,
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
):
    items, total, unread = await notification_service.list_for_user(
        session, principal.user_id, limit=limit, offset=offset, unread_only=unread_only
    )
    return NotificationListOut(items=[_out(n) for n in items], total=total, unread_count=unread)


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
async def unread_count(session: SessionDep, principal: PrincipalDep):
    return UnreadCountOut(count=await notification_service.unread_count(session, principal.user_id))


@router.get("/notifications/preferences", response_model=PreferencesOut)
async def get_preferences(session: SessionDep, principal: PrincipalDep):
    return PreferencesOut(**await notification_service.get_preferences(session, principal.user_id))


@router.put("/notifications/preferences", response_model=PreferencesOut)
async def update_preferences(body: PreferencesIn, session: SessionDep, principal: PrincipalDep):
    prefs = await notification_service.update_preferences(
        session, principal.user_id, **body.model_dump(exclude_none=True)
    )
    return PreferencesOut(**prefs)


@router.post("/notifications/read-all", response_model=MarkAllOut)
async def mark_all_read(session: SessionDep, principal: PrincipalDep):
    return MarkAllOut(marked=await notification_service.mark_all_read(session, principal.user_id))


@router.post("/notifications/{notification_id}/read", response_model=OkOut)
async def mark_read(notification_id: uuid.UUID, session: SessionDep, principal: PrincipalDep):
    ok = await notification_service.mark_read(
        session, user_id=principal.user_id, notification_id=notification_id
    )
    if not ok:
        raise AppError("NOT_FOUND", "Notification not found", status_code=404)
    return OkOut(ok=True)


@router.post("/admin/notifications/dispatch-emails", response_model=DispatchOut)
async def dispatch_emails(session: SessionDep, caller: AdminOrCronDep, limit: int = 50):
    """Drain the email outbox (cron target: admin OR X-Cron-Secret). Sends pending
    emails OUT of any money tx."""
    return DispatchOut(**await email_service.dispatch_pending(session, limit=limit))
