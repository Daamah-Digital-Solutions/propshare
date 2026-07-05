"""Property catalog routes (Phase 3).

- GET  /properties                 PUBLIC marketplace list (active/funded only).
- GET  /properties/{id_or_slug}    PUBLIC detail (active/funded only).
- POST /properties                 owner: create a draft.
- PATCH /properties/{id}           owner: edit while draft/under_review.
- POST /properties/{id}/submit     owner: draft -> under_review.
- POST /properties/{id}/images     owner: upload an image (real storage seam).
- GET  /owner/properties           owner: all of my properties (any status).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.deps import Principal, SessionDep, require_active_role_db
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.property import (
    OwnerPropertyOut,
    PropertyCreateIn,
    PropertyDetailOut,
    PropertyListOut,
    PropertySummaryOut,
    PropertyUpdateIn,
)
from app.services import milestone_service, property_service, settings_service
from app.services.integrations import storage

router = APIRouter(prefix="/api/v1", tags=["properties"])

OwnerDep = Annotated[Principal, Depends(require_active_role_db("owner"))]


@router.get("/properties", response_model=PropertyListOut)
async def list_properties(
    session: SessionDep,
    model: str | None = None,
    property_type: str | None = None,
    country: str | None = None,
    city: str | None = None,
    status: str | None = None,
    min_yield: float | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    search: str | None = None,
    sort: str = "newest",
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await property_service.list_public(
        session,
        model=model,
        property_type=property_type,
        country=country,
        city=city,
        status=status,
        min_yield=min_yield,
        min_price=min_price,
        max_price=max_price,
        search=search,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    owner_names = await property_service._owner_names(session, rows)
    items = [PropertySummaryOut(**property_service.serialize_summary(p, owner_names)) for p in rows]
    return PropertyListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/owner/properties", response_model=list[OwnerPropertyOut])
async def my_properties(principal: OwnerDep, session: SessionDep):
    rows = await property_service.list_owner(session, principal.user_id)
    owner_names = await property_service._owner_names(session, rows)
    # Computed construction % per property (one query, no N+1) so the dashboard bars
    # are real instead of the always-0 content.constructionProgress.
    cp_map = await milestone_service.construction_progress_map(session, [p.id for p in rows])
    out = []
    for p in rows:
        data = property_service.serialize_detail(p, owner_names)
        data["construction_progress"] = cp_map.get(p.id, 0)
        out.append(OwnerPropertyOut(**data))
    return out


@router.get("/properties/{id_or_slug}", response_model=PropertyDetailOut)
async def get_property(id_or_slug: str, session: SessionDep):
    prop = await property_service.get_public_detail(session, id_or_slug)
    owner_names = await property_service._owner_names(session, [prop])
    data = property_service.serialize_detail(prop, owner_names)
    # Overlay the live, admin-configurable fee rates so the displayed platform &
    # management fees always match what the investment engine will actually charge.
    rates = await settings_service.get_fee_rates(session)
    fees = dict(data.get("fees") or {})
    fees["platform_fee"] = float(rates["platform_fee_pct"])
    fees["management_fee"] = float(rates["management_fee_pct"])
    # Group 6 — the installment-path fee (down payment + per-installment), so the
    # under-construction calculator displays the exact server-applied rate (no hardcoded 4%).
    fees["installment_fee"] = float(await settings_service.get_installment_fee_pct(session))
    data["fees"] = fees
    # Phase 15b — embed the real milestones + the construction % computed from them.
    milestones = await milestone_service.list_for_property(session, prop.id)
    data["milestones"] = [milestone_service.serialize(m) for m in milestones]
    data["construction_progress"] = milestone_service.construction_progress_from_rows(milestones)
    return PropertyDetailOut(**data)


@router.post("/properties", response_model=OwnerPropertyOut, status_code=201)
async def create_property(body: PropertyCreateIn, principal: OwnerDep, session: SessionDep):
    prop = await property_service.create(
        session, owner_id=principal.user_id, data=body.model_dump()
    )
    owner_names = await property_service._owner_names(session, [prop])
    return OwnerPropertyOut(**property_service.serialize_detail(prop, owner_names))


@router.patch("/properties/{prop_id}", response_model=OwnerPropertyOut)
async def update_property(
    prop_id: uuid.UUID, body: PropertyUpdateIn, principal: OwnerDep, session: SessionDep
):
    prop = await property_service.update(
        session,
        owner_id=principal.user_id,
        prop_id=prop_id,
        data=body.model_dump(exclude_unset=True),
    )
    owner_names = await property_service._owner_names(session, [prop])
    return OwnerPropertyOut(**property_service.serialize_detail(prop, owner_names))


@router.post("/properties/{prop_id}/submit", response_model=OwnerPropertyOut)
async def submit_property(prop_id: uuid.UUID, principal: OwnerDep, session: SessionDep):
    prop = await property_service.submit(session, owner_id=principal.user_id, prop_id=prop_id)
    owner_names = await property_service._owner_names(session, [prop])
    return OwnerPropertyOut(**property_service.serialize_detail(prop, owner_names))


@router.post("/properties/{prop_id}/images", status_code=201)
async def upload_property_image(
    prop_id: uuid.UUID,
    principal: OwnerDep,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
):
    """Owner uploads a property image (real storage seam — replaces the old 503).
    Stores the file and appends its public URL to ``properties.images``."""
    prop = await property_service.get_owned_for_update(session, principal.user_id, prop_id)
    data = await file.read()
    if not data:
        raise AppError("EMPTY_FILE", "Uploaded file is empty.", status_code=422)
    if len(data) > get_settings().storage_max_upload_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"File exceeds the {get_settings().storage_max_upload_mb} MB limit.",
            status_code=413,
        )
    import re as _re

    safe = _re.sub(r"[^A-Za-z0-9._-]+", "_", (file.filename or "image").split("/")[-1])[:120]
    key = f"property-images/{prop_id}/{uuid.uuid4().hex}-{safe}"
    storage.save(key, data, file.content_type or "application/octet-stream")
    url = storage.public_url(key)
    prop.images = [*(prop.images or []), url]
    await session.commit()
    return {"images": prop.images}
