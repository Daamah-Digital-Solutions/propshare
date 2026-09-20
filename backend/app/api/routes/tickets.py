"""Support tickets (plan §4): the LLM-free form, the owner's ticket list/detail and replies.

Works with the assistant switched off: it is the fallback the safe-mode message points to.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.api.deps import PrincipalDep, SessionDep, current_principal
from app.core.ratelimit import TICKET_LIMIT, limiter
from app.models import SupportTicket, SupportTicketMessage
from app.schemas.assistant import (
    CsatIn,
    TicketCreateIn,
    TicketMessageIn,
    TicketMessageOut,
    TicketOut,
)
from app.services import ticket_service

router = APIRouter(prefix="/api/v1/support", tags=["support"])


def _out(t: SupportTicket, msgs: list[SupportTicketMessage] | None = None) -> TicketOut:
    return TicketOut(
        id=t.id,
        ticket_no=t.ticket_no,
        category=t.category,
        priority=t.priority,
        status=t.status,
        subject=t.subject,
        source=t.source,
        created_at=t.created_at,
        updated_at=t.updated_at,
        resolved_at=t.resolved_at,
        csat=t.csat,
        messages=[
            TicketMessageOut(
                id=m.id, author_type=m.author_type, body=m.body, created_at=m.created_at
            )
            for m in (msgs or [])
        ],
    )


@router.post("/tickets", response_model=TicketOut, status_code=201)
@limiter.limit(TICKET_LIMIT)
async def create_ticket(body: TicketCreateIn, request: Request, session: SessionDep):
    user_id = (
        (await current_principal(request)).user_id if request.headers.get("Authorization") else None
    )
    ticket = await ticket_service.create_from_form(
        session,
        user_id=user_id,
        contact_email=str(body.contact_email) if body.contact_email else None,
        category=body.category,
        subject=body.subject,
        body=body.body,
        priority=body.priority,
    )
    msgs = await ticket_service.list_messages(session, ticket_id=ticket.id, include_internal=False)
    return _out(ticket, msgs)


@router.get("/tickets", response_model=list[TicketOut])
async def my_tickets(principal: PrincipalDep, session: SessionDep):
    rows = await ticket_service.list_my_tickets(session, user_id=principal.user_id)
    return [_out(t) for t in rows]


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
async def my_ticket(ticket_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    ticket = await ticket_service.get_my_ticket(
        session, user_id=principal.user_id, ticket_id=ticket_id
    )
    msgs = await ticket_service.list_messages(session, ticket_id=ticket.id, include_internal=False)
    return _out(ticket, msgs)


@router.post("/tickets/{ticket_id}/csat", response_model=TicketOut)
async def rate(ticket_id: uuid.UUID, body: CsatIn, principal: PrincipalDep, session: SessionDep):
    """CSAT (client doc §28): the owner rates a resolved or closed ticket 1..5."""
    ticket = await ticket_service.rate_ticket(
        session, user_id=principal.user_id, ticket_id=ticket_id, score=body.score
    )
    msgs = await ticket_service.list_messages(session, ticket_id=ticket.id, include_internal=False)
    return _out(ticket, msgs)


@router.post("/tickets/{ticket_id}/messages", response_model=TicketOut)
async def reply(
    ticket_id: uuid.UUID, body: TicketMessageIn, principal: PrincipalDep, session: SessionDep
):
    await ticket_service.user_reply(
        session, user_id=principal.user_id, ticket_id=ticket_id, body=body.body
    )
    ticket = await ticket_service.get_my_ticket(
        session, user_id=principal.user_id, ticket_id=ticket_id
    )
    msgs = await ticket_service.list_messages(session, ticket_id=ticket.id, include_internal=False)
    return _out(ticket, msgs)
