"""Cards (client, 2026-11-19): not issued yet; the member can join the waitlist.

GET  /api/v1/cards/waitlist   whether the caller is on the waitlist, and for which card
POST /api/v1/cards/waitlist   join it, or change the card chosen ({"card_type": ...})
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import PrincipalDep, SessionDep
from app.services import card_waitlist_service

router = APIRouter(prefix="/api/v1/cards", tags=["cards"])


class CardWaitlistOut(BaseModel):
    joined: bool
    card_type: str | None
    joined_at: dt.datetime | None


class CardWaitlistIn(BaseModel):
    card_type: str


@router.get("/waitlist", response_model=CardWaitlistOut)
async def my_waitlist(session: SessionDep, principal: PrincipalDep) -> CardWaitlistOut:
    entry = await card_waitlist_service.get_entry(session, principal.user_id)
    return CardWaitlistOut(**card_waitlist_service.entry_dict(entry))


@router.post("/waitlist", response_model=CardWaitlistOut)
async def join_waitlist(
    body: CardWaitlistIn, session: SessionDep, principal: PrincipalDep
) -> CardWaitlistOut:
    entry = await card_waitlist_service.join(session, principal.user_id, body.card_type)
    return CardWaitlistOut(**card_waitlist_service.entry_dict(entry))
