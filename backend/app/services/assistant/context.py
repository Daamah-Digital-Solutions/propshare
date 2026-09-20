"""Who is talking to the assistant, resolved once per turn from the real database.

The context is the ONLY source of identity for tools: no tool accepts a user id as an
argument, every "my" tool reads ``ctx.user_id``. A visitor (not signed in) has no user id
and can only use informational tools.
"""

from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KycVerification
from app.models.identity import User
from app.services import auth_service


@dataclasses.dataclass(frozen=True)
class AgentContext:
    user_id: uuid.UUID | None  # None => visitor
    visitor_key: str | None
    roles: tuple[str, ...]
    active_role: str | None
    kyc_status: str
    email_verified: bool
    full_name: str | None
    lang: str = "en"
    conversation_id: uuid.UUID | None = None

    @property
    def is_visitor(self) -> bool:
        return self.user_id is None

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


async def load_context(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    visitor_key: str | None = None,
    lang: str = "en",
    conversation_id: uuid.UUID | None = None,
) -> AgentContext:
    """Build the context from the database (never from the token alone: a revoked role must
    stop working within the token's lifetime)."""
    if user_id is None:
        return AgentContext(
            user_id=None,
            visitor_key=visitor_key,
            roles=(),
            active_role=None,
            kyc_status="none",
            email_verified=False,
            full_name=None,
            lang=lang,
            conversation_id=conversation_id,
        )
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError("unknown user")
    roles = tuple(await auth_service.get_roles(session, user.id))
    kyc = await session.scalar(
        select(KycVerification.status).where(KycVerification.user_id == user.id)
    )
    return AgentContext(
        user_id=user.id,
        visitor_key=None,
        roles=roles,
        active_role=str(user.active_role) if user.active_role is not None else None,
        kyc_status=str(kyc or "pending"),
        email_verified=bool(user.email_verified),
        full_name=user.full_name,
        lang=lang,
        conversation_id=conversation_id,
    )
