"""Server-side consent for signed-in users (plan rev 3).

A user must accept the CURRENT policy version before the first message; a Privacy Policy
change bumps ``ASSISTANT_POLICY_VERSION`` and re-prompts. Visitors are acknowledged in the
browser only (there is no account to attach a row to).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AssistantConsent


def current_version() -> str:
    return get_settings().assistant_policy_version


async def has_consent(session: AsyncSession, user_id: uuid.UUID) -> bool:
    row = await session.scalar(
        select(AssistantConsent.accepted_at).where(
            AssistantConsent.user_id == user_id,
            AssistantConsent.policy_version == current_version(),
        )
    )
    return row is not None


async def require_consent(session: AsyncSession, user_id: uuid.UUID) -> None:
    if not await has_consent(session, user_id):
        raise AppError(
            "CONSENT_REQUIRED",
            "Please accept the assistant privacy notice first.",
            status_code=428,
            details={"policy_version": current_version()},
        )


async def record(
    session: AsyncSession, *, user_id: uuid.UUID, policy_version: str, ip: str | None
) -> AssistantConsent:
    if policy_version != current_version():
        raise AppError(
            "POLICY_VERSION_MISMATCH",
            "The privacy notice has changed; please review the current version.",
            status_code=409,
            details={"policy_version": current_version()},
        )
    existing = await session.get(AssistantConsent, (user_id, policy_version))
    if existing is not None:
        return existing
    row = AssistantConsent(user_id=user_id, policy_version=policy_version, ip=ip)
    session.add(row)
    await write_audit(
        session,
        action="assistant.consent_recorded",
        entity_type="user",
        entity_id=str(user_id),
        actor_id=user_id,
        after={"policy_version": policy_version},
        ip=ip,
    )
    await session.flush()
    return row
