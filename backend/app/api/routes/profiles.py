"""Profile / account-settings routes (Phase 1).

Avatar upload moves onto the app storage seam (MinIO/S3) — wired once the
storage bucket is configured; tracked as a Phase-1 follow-up (see
plan/phase-01-identity-access.md). Profile read/update are live here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import PrincipalDep, SessionDep
from app.core.errors import AppError
from app.models import Profile
from app.models.identity import User
from app.schemas.profile import ProfileOut, ProfileUpdateIn

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.get("/me", response_model=ProfileOut)
async def get_my_profile(principal: PrincipalDep, session: SessionDep):
    profile = await session.get(Profile, principal.user_id)
    if profile is None:
        raise AppError("NOT_FOUND", "Profile not found", status_code=404)
    return ProfileOut(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name,
        phone=profile.phone,
        avatar_url=profile.avatar_url,
    )


@router.patch("/me", response_model=ProfileOut)
async def update_my_profile(body: ProfileUpdateIn, principal: PrincipalDep, session: SessionDep):
    profile = await session.get(Profile, principal.user_id)
    if profile is None:
        raise AppError("NOT_FOUND", "Profile not found", status_code=404)
    if body.full_name is not None:
        profile.full_name = body.full_name
    if body.phone is not None:
        profile.phone = body.phone
    # keep the users row in sync (name/phone are duplicated there for auth/me)
    user = await session.get(User, principal.user_id)
    if user is not None:
        if body.full_name is not None:
            user.full_name = body.full_name
        if body.phone is not None:
            user.phone = body.phone
    return ProfileOut(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name,
        phone=profile.phone,
        avatar_url=profile.avatar_url,
    )
