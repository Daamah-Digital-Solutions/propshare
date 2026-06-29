"""Inter-vivos gifting routes (Group 5) — owner-scoped scheduled gifts.

- GET  /api/v1/gifts                 the caller's own scheduled/executed gifts (real statuses).
- POST /api/v1/gifts                 schedule a gift (Idempotency-Key) — reserves units /
  escrows cash so "executes automatically on the date" is truthful.
- POST /api/v1/gifts/{id}/cancel     cancel a scheduled gift (releases reservation / refunds).

Schedule/cancel are KYC-gated + Idempotency-Key (they reserve units / move money).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.api.deps import KycVerifiedDep, PrincipalDep, SessionDep
from app.core.errors import AppError
from app.schemas.gifts import GiftOut, GiftScheduleIn
from app.services import gift_service

router = APIRouter(prefix="/api/v1/gifts", tags=["gifting"])


def _idem(request: Request) -> str:
    key = request.headers.get("Idempotency-Key")
    if not key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED", "An Idempotency-Key header is required.", status_code=400
        )
    return key


@router.get("", response_model=list[GiftOut])
async def list_gifts(session: SessionDep, principal: PrincipalDep):
    rows = await gift_service.list_gifts(session, principal.user_id)
    return [GiftOut(**gift_service.serialize(g)) for g in rows]


@router.post("", response_model=GiftOut, status_code=201)
async def schedule_gift(
    body: GiftScheduleIn, request: Request, session: SessionDep, principal: KycVerifiedDep
):
    result = await gift_service.schedule_gift(
        session,
        giver_id=principal.user_id,
        data=body.model_dump(),
        idempotency_key=_idem(request),
    )
    return GiftOut(**result)


@router.post("/{gift_id}/cancel", response_model=GiftOut)
async def cancel_gift(gift_id: uuid.UUID, session: SessionDep, principal: KycVerifiedDep):
    result = await gift_service.cancel_gift(session, giver_id=principal.user_id, gift_id=gift_id)
    return GiftOut(**result)
