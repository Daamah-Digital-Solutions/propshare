"""Admin: user listing + role management (Scenario B, D12).

Role assignment is admin-only — there is NO self-service path to broker/
liquidity_provider/admin. ``admin`` is granted only by an existing admin (the
first admin is seeded via scripts/seed_admin.py). Every route is gated by the
action-time DB admin re-check (AdminDep → require_admin_db).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import AdminDep, SessionDep
from app.models.identity import RoleGrantRequest, User
from app.schemas.admin import AdminUserOut, GrantRoleIn, RoleDecisionIn, RoleRequestOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(session: SessionDep, _admin: AdminDep, limit: int = 50, offset: int = 0):
    res = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(min(limit, 200)).offset(offset)
    )
    users = res.scalars().all()
    out: list[AdminUserOut] = []
    for u in users:
        roles = await auth_service.get_roles(session, u.id)
        out.append(
            AdminUserOut(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                email_verified=u.email_verified,
                roles=roles,
                active_role=str(u.active_role) if u.active_role is not None else None,
                created_at=u.created_at,
            )
        )
    return out


@router.post("/users/{user_id}/roles", status_code=204)
async def grant_role(user_id: uuid.UUID, body: GrantRoleIn, session: SessionDep, _admin: AdminDep):
    await auth_service.admin_grant_role(session, target_user_id=user_id, role=body.role)


@router.delete("/users/{user_id}/roles/{role}", status_code=204)
async def revoke_role(user_id: uuid.UUID, role: str, session: SessionDep, _admin: AdminDep):
    await auth_service.admin_revoke_role(session, target_user_id=user_id, role=role)


@router.get("/role-requests", response_model=list[RoleRequestOut])
async def list_role_requests(session: SessionDep, _admin: AdminDep, status: str = "pending"):
    res = await session.execute(
        select(RoleGrantRequest)
        .where(RoleGrantRequest.status == status)
        .order_by(RoleGrantRequest.created_at.asc())
    )
    return [
        RoleRequestOut(
            id=r.id,
            user_id=r.user_id,
            role=str(r.role),
            status=r.status,
            created_at=r.created_at,
        )
        for r in res.scalars().all()
    ]


@router.post("/role-requests/{request_id}/decision", response_model=RoleRequestOut)
async def decide_role_request(
    request_id: uuid.UUID,
    body: RoleDecisionIn,
    session: SessionDep,
    admin: AdminDep,
):
    req = await auth_service.decide_role_request(
        session, request_id=request_id, approve=body.approve, actor_id=admin.user_id
    )
    return RoleRequestOut(
        id=req.id,
        user_id=req.user_id,
        role=str(req.role),
        status=req.status,
        created_at=req.created_at,
    )
