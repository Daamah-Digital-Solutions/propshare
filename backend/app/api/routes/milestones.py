"""Property-milestone routes (Phase 15b).

Owner/developer CRUD over a property's milestones, owner-scoped: every write
re-checks ``property.owner_id == caller`` via ``milestone_service`` (returns
``403 NOT_PROPERTY_OWNER`` otherwise), in addition to the action-time ``owner``
role re-check. The PUBLIC read is embedded in ``GET /properties/{id_or_slug}``
(no separate public path) — see ``properties.py``.

- GET    /owner/properties/{prop_id}/milestones                 list (any status, owned).
- POST   /owner/properties/{prop_id}/milestones                 create (appends).
- PATCH  /owner/properties/{prop_id}/milestones/{milestone_id}  update.
- DELETE /owner/properties/{prop_id}/milestones/{milestone_id}  delete.
- POST   /owner/properties/{prop_id}/milestones/reorder         reorder (full set).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Principal, SessionDep, require_active_role_db
from app.schemas.milestone import (
    MilestoneCreateIn,
    MilestoneOut,
    MilestoneReorderIn,
    MilestoneUpdateIn,
)
from app.services import milestone_service

router = APIRouter(prefix="/api/v1", tags=["milestones"])

OwnerDep = Annotated[Principal, Depends(require_active_role_db("owner"))]


@router.get("/owner/properties/{prop_id}/milestones", response_model=list[MilestoneOut])
async def list_owner_milestones(prop_id: uuid.UUID, principal: OwnerDep, session: SessionDep):
    rows = await milestone_service.list_owned(session, principal.user_id, prop_id)
    return [MilestoneOut(**milestone_service.serialize(r)) for r in rows]


@router.post(
    "/owner/properties/{prop_id}/milestones",
    response_model=MilestoneOut,
    status_code=201,
)
async def create_milestone(
    prop_id: uuid.UUID,
    body: MilestoneCreateIn,
    principal: OwnerDep,
    session: SessionDep,
):
    m = await milestone_service.create(session, principal.user_id, prop_id, body.model_dump())
    return MilestoneOut(**milestone_service.serialize(m))


@router.post(
    "/owner/properties/{prop_id}/milestones/reorder",
    response_model=list[MilestoneOut],
)
async def reorder_milestones(
    prop_id: uuid.UUID,
    body: MilestoneReorderIn,
    principal: OwnerDep,
    session: SessionDep,
):
    rows = await milestone_service.reorder(session, principal.user_id, prop_id, body.ordered_ids)
    return [MilestoneOut(**milestone_service.serialize(r)) for r in rows]


@router.patch(
    "/owner/properties/{prop_id}/milestones/{milestone_id}",
    response_model=MilestoneOut,
)
async def update_milestone(
    prop_id: uuid.UUID,
    milestone_id: uuid.UUID,
    body: MilestoneUpdateIn,
    principal: OwnerDep,
    session: SessionDep,
):
    m = await milestone_service.update(
        session, principal.user_id, prop_id, milestone_id, body.model_dump(exclude_unset=True)
    )
    return MilestoneOut(**milestone_service.serialize(m))


@router.delete(
    "/owner/properties/{prop_id}/milestones/{milestone_id}",
    status_code=204,
)
async def delete_milestone(
    prop_id: uuid.UUID,
    milestone_id: uuid.UUID,
    principal: OwnerDep,
    session: SessionDep,
):
    await milestone_service.delete(session, principal.user_id, prop_id, milestone_id)
