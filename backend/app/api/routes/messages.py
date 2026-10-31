"""Inbox: messages the platform team sends from the admin panel (client, 2026-10-28).

  GET  /api/v1/messages            the caller's messages and how many are unread
  GET  /api/v1/messages/{id}       one of the caller's messages (marks it read)
  POST /api/v1/messages/read-all   mark every message read

Every signed-in role has an inbox; nobody reads anyone else's messages. See message_service.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import PrincipalDep, SessionDep
from app.core.errors import AppError
from app.schemas.messages import InboxMessageOut, InboxOut, ReadAllOut
from app.services import message_service

router = APIRouter(prefix="/api/v1", tags=["messages"])


@router.get("/messages", response_model=InboxOut)
async def my_messages(session: SessionDep, principal: PrincipalDep):
    return InboxOut(**await message_service.inbox(session, principal.user_id))


@router.post("/messages/read-all", response_model=ReadAllOut)
async def read_all(session: SessionDep, principal: PrincipalDep):
    return ReadAllOut(marked=await message_service.read_all(session, principal.user_id))


@router.get("/messages/{message_id}", response_model=InboxMessageOut)
async def one_message(message_id: str, session: SessionDep, principal: PrincipalDep):
    try:
        mid = uuid.UUID(message_id)
    except ValueError as exc:
        raise AppError("MESSAGE_NOT_FOUND", "Message not found.", status_code=404) from exc
    return InboxMessageOut(**await message_service.open_message(session, principal.user_id, mid))
