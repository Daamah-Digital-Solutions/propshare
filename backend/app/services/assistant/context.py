"""Who is talking to the assistant, resolved once per turn from the real database.

The context is the ONLY source of identity for tools: no tool accepts a user id as an
argument, every "my" tool reads ``ctx.user_id``. A visitor (not signed in) has no user id
and can only use informational tools.

It also carries the page the user has open (``page``), so "this property" needs no
question back. The browser reports the path; only a route of ours survives (the deep-link
allow-list), and a property page is resolved to its public title from the database.
"""

from __future__ import annotations

import dataclasses
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KycVerification, Property
from app.models.identity import User
from app.services import auth_service, property_service


@dataclasses.dataclass(frozen=True)
class CurrentPage:
    """A page of ours the user has open: a deep-link route id, its canonical path (only the
    ``tab`` query parameter kept) and, for a property or developer page, the slug. ``title``
    is the property's public title, when it is live."""

    route_id: str
    path: str
    slug: str | None = None
    title: str | None = None


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
    page: CurrentPage | None = None

    @property
    def is_visitor(self) -> bool:
        return self.user_id is None

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


_TITLE_JUNK_RE = re.compile(r"[\x00-\x1f\x7f<>\"`]+")


async def resolve_page(session: AsyncSession, raw: str | None) -> CurrentPage | None:
    """The page the browser reported, if it is one of ours; anything else is dropped."""
    from app.services.assistant import guard  # guard imports this module; keep it one-way

    route = guard.page_route(raw)
    if route is None:
        return None
    route_id, path, slug = route
    title = None
    if route_id == "property" and slug:
        title = await session.scalar(
            select(Property.title).where(
                Property.slug == slug, Property.status.in_(property_service.PUBLIC_STATUSES)
            )
        )
        if title:  # a title is owner-written text: one plain line, no markup, capped
            title = " ".join(_TITLE_JUNK_RE.sub(" ", title).split())[:80] or None
    return CurrentPage(route_id=route_id, path=path, slug=slug, title=title)


async def load_context(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    visitor_key: str | None = None,
    lang: str = "en",
    conversation_id: uuid.UUID | None = None,
    page: str | None = None,
) -> AgentContext:
    """Build the context from the database (never from the token alone: a revoked role must
    stop working within the token's lifetime)."""
    current = await resolve_page(session, page)
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
            page=current,
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
        page=current,
    )
