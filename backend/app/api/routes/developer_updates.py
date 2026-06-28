"""Investor-communications routes (Phase 15c).

Owner/developer sends a per-property update (fans out to that property's net-holders
via the Phase-12 notify()/outbox seam) and reads back the sent history with real counts.
Owner-scoped: the send/list re-check ``property.owner_id == caller`` (403 otherwise) in
addition to the action-time ``owner`` role re-check. Investors READ updates through the
existing notifications feed (``GET /notifications``) — no new investor endpoint.

- POST /owner/properties/{prop_id}/updates   send an update to the property's holders.
- GET  /owner/updates[?property_id=…]         the developer's sent history + counts.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Principal, SessionDep, require_active_role_db
from app.schemas.developer_update import DeveloperUpdateCreateIn, DeveloperUpdateOut
from app.services import developer_update_service

router = APIRouter(prefix="/api/v1", tags=["investor-communications"])

OwnerDep = Annotated[Principal, Depends(require_active_role_db("owner"))]


@router.post(
    "/owner/properties/{prop_id}/updates",
    response_model=DeveloperUpdateOut,
    status_code=201,
)
async def send_update(
    prop_id: uuid.UUID,
    body: DeveloperUpdateCreateIn,
    principal: OwnerDep,
    session: SessionDep,
):
    upd = await developer_update_service.send_update(
        session,
        owner_id=principal.user_id,
        property_id=prop_id,
        subject=body.subject,
        body=body.body,
    )
    # A freshly sent update has no reads yet.
    return DeveloperUpdateOut(**developer_update_service.serialize(upd, 0))


@router.get("/owner/updates", response_model=list[DeveloperUpdateOut])
async def list_updates(
    principal: OwnerDep,
    session: SessionDep,
    property_id: uuid.UUID | None = None,
):
    rows = await developer_update_service.list_updates(
        session, principal.user_id, property_id=property_id
    )
    return [DeveloperUpdateOut(**r) for r in rows]
