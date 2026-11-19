"""The card waitlist (client, 2026-11-19: the cards section reads "Coming soon · Join the
Waitlist"; a click lets the member ask for the card they want).

One row per member; joining again changes the card chosen. The member is told in the app that
they are on the list. Staff read the list in the admin panel (Card waitlist).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models.cards import CardWaitlistEntry
from app.services import notification_service

# the cards the sections show: the investor's three, and one per role dashboard
CARD_TYPES: dict[str, str] = {
    "personal": "Personal card",
    "family": "Family card",
    "team": "Team card",
    "developer": "Developer card",
    "owner": "Property owner card",
    "broker": "Broker card",
    "liquidity": "Liquidity provider card",
}


def entry_dict(entry: CardWaitlistEntry | None) -> dict:
    if entry is None:
        return {"joined": False, "card_type": None, "joined_at": None}
    return {"joined": True, "card_type": entry.card_type, "joined_at": entry.created_at}


async def get_entry(session: AsyncSession, user_id: uuid.UUID) -> CardWaitlistEntry | None:
    return await session.scalar(
        select(CardWaitlistEntry).where(CardWaitlistEntry.user_id == user_id)
    )


async def join(session: AsyncSession, user_id: uuid.UUID, card_type: str) -> CardWaitlistEntry:
    if card_type not in CARD_TYPES:
        raise AppError("VALIDATION_ERROR", "Choose a card.", status_code=422)
    entry = await get_entry(session, user_id)
    before = entry.card_type if entry is not None else None
    if entry is None:
        entry = CardWaitlistEntry(user_id=user_id, card_type=card_type)
        session.add(entry)
    elif entry.card_type != card_type:
        entry.card_type = card_type
        entry.updated_at = dt.datetime.now(dt.UTC)
    else:
        return entry
    await session.flush()
    await session.refresh(entry)
    await write_audit(
        session,
        action="card_waitlist.joined" if before is None else "card_waitlist.changed",
        entity_type="card_waitlist",
        entity_id=str(entry.id),
        actor_id=user_id,
        before={"card_type": before} if before else None,
        after={"card_type": card_type},
    )
    await notification_service.notify(
        session,
        user_id=user_id,
        type="card_waitlist",
        title="You're on the card waitlist",
        message="Your request is recorded. We will tell you as soon as cards can be requested.",
    )
    return entry
