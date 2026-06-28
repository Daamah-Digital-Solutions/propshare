"""FastAPI dependencies: authentication context + RBAC (Scenario B).

- ``current_principal``      decodes the access token (no DB) — for read endpoints.
- ``require_role(...)``       active role must be one of the given roles AND in the
                              authorized set carried by the token.
- ``require_active_role_db``  ⚠️ owner-mandated: in addition to the token check,
                              RE-QUERIES user_roles at action time so a role revoked
                              mid-session cannot act within a still-valid token TTL.
                              Use on every money/privileged endpoint.
- ``require_kyc_verified``    blocks until KYC status == 'verified'.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.models import KycVerification, UserRole
from app.models.base import AppRole

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    roles: tuple[str, ...]
    active_role: str | None


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise AppError("UNAUTHENTICATED", "Missing bearer token", status_code=401)
    return header[7:].strip()


async def current_principal(request: Request) -> Principal:
    payload = decode_access_token(_extract_bearer(request))
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise AppError("TOKEN_INVALID", "Malformed token subject", status_code=401) from exc
    roles = tuple(str(r) for r in (payload.get("roles") or []))
    return Principal(user_id=user_id, roles=roles, active_role=payload.get("active_role"))


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require_role(*allowed: str) -> Callable[[Principal], Awaitable[Principal]]:
    """Token-level gate: the active role must be one of ``allowed`` (and authorized).
    Suitable for read/non-money endpoints. Money/privileged endpoints should use
    ``require_active_role_db`` for the action-time DB re-check.
    """

    async def _dep(principal: PrincipalDep) -> Principal:
        if principal.active_role is None or principal.active_role not in allowed:
            raise AppError(
                "FORBIDDEN",
                f"Requires active role in {sorted(allowed)}",
                status_code=403,
                details={"active_role": principal.active_role},
            )
        if principal.active_role not in principal.roles:
            raise AppError("TOKEN_INVALID", "active_role not in authorized roles", status_code=401)
        return principal

    return _dep


def require_active_role_db(*allowed: str) -> Callable[..., Awaitable[Principal]]:
    """⚠️ Action-time DB re-verification (owner-mandated for money/privileged ops).

    Confirms the token's active role is *currently* present in user_roles, so a
    revoked role cannot act within a still-valid access token's TTL.
    """

    async def _dep(principal: PrincipalDep, session: SessionDep) -> Principal:
        if principal.active_role is None or principal.active_role not in allowed:
            raise AppError(
                "FORBIDDEN",
                f"Requires active role in {sorted(allowed)}",
                status_code=403,
                details={"active_role": principal.active_role},
            )
        res = await session.execute(
            select(UserRole.id).where(
                UserRole.user_id == principal.user_id,
                UserRole.role == AppRole(principal.active_role),
            )
        )
        if res.first() is None:
            raise AppError(
                "ROLE_REVOKED",
                "Active role is no longer authorized.",
                status_code=403,
            )
        return principal

    return _dep


# Convenience: admin gate with the DB re-check (admin is privileged).
require_admin_db = require_active_role_db("admin")
# Annotated dependency: inject the admin Principal into a handler (and enforce the gate).
AdminDep = Annotated[Principal, Depends(require_admin_db)]


async def require_admin_or_cron(request: Request, session: SessionDep) -> Principal | None:
    """Gate for idempotent scheduled-job endpoints: allow EITHER an authenticated admin
    (the SQLAdmin / human path) OR a system-cron caller presenting a valid ``X-Cron-Secret``
    header. The header secret is compared in constant time and only accepted when
    ``settings.cron_secret`` is configured (non-empty), so an unset secret never authorizes.
    Returns the admin Principal when present, else None (cron caller has no user identity).
    """
    import hmac

    from app.core.config import get_settings

    secret = get_settings().cron_secret
    provided = request.headers.get("X-Cron-Secret")
    if secret and provided and hmac.compare_digest(provided, secret):
        return None  # authenticated as cron; no user principal
    # Fall back to the standard admin gate (raises 401/403 if not an admin).
    return await require_admin_db(await current_principal(request), session)


# Annotated dependency for cron-target endpoints (admin OR valid X-Cron-Secret).
AdminOrCronDep = Annotated["Principal | None", Depends(require_admin_or_cron)]


async def require_kyc_verified(principal: PrincipalDep, session: SessionDep) -> Principal:
    res = await session.execute(
        select(KycVerification.status).where(KycVerification.user_id == principal.user_id)
    )
    status = res.scalar_one_or_none()
    if str(status) != "verified":
        raise AppError("KYC_REQUIRED", "Identity verification required.", status_code=403)
    return principal


# Annotated dependency: inject a KYC-verified principal (used by money endpoints).
KycVerifiedDep = Annotated[Principal, Depends(require_kyc_verified)]
