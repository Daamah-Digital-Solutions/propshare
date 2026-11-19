"""Certificates issued the moment units change hands (client letter, 2026-11-18: "KYC first,
then the purchase, then the certificate is issued automatically and appears under
Certificates").

Every movement of units is a row of the ownership ledger (a purchase, an installment that
vests, a market purchase or sale, a liquidity-provider deal, a transfer, a gift, a family or
estate move). The session notes each (holder, property) whose ledger moved; just before the
transaction commits, ``issue_pending`` issues the holder's current certificate for each one that
still holds units (superseding the one that stated the old number), so the certificate exists
when the purchase completes, not only when the Certificates tab is opened. An installment plan
whose status changes (completed, cancelled) is noted too: its holder's certificate turns from
provisional to final even when the last payment vests no new unit.

Best effort by design: a certificate that cannot be issued (a database hiccup, a listing gone)
never undoes the purchase; it is then issued, as before, when the holder opens Certificates.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import OwnershipLedger
from app.models.installments import InstallmentPlan

log = logging.getLogger("capimax.certificates")

KEY = "certificate_holdings"


@event.listens_for(Session, "after_flush")
def _note_ledger_rows(session: Session, _ctx) -> None:
    for obj in session.new:
        if isinstance(obj, OwnershipLedger) and obj.user_id and obj.property_id:
            session.info.setdefault(KEY, set()).add((obj.user_id, obj.property_id))
    for obj in session.dirty:
        if isinstance(obj, InstallmentPlan) and inspect(obj).attrs.status.history.has_changes():
            session.info.setdefault(KEY, set()).add((obj.investor_id, obj.property_id))


async def issue_pending(session: AsyncSession) -> int:
    """Issue the current certificate of every holding whose units moved in this transaction.
    Returns how many holdings were brought up to date."""
    from app.services import certificate_service  # the service imports models only

    done = 0
    await session.flush()  # rows still pending are noted too
    while True:
        pending: set[tuple[uuid.UUID, uuid.UUID]] = session.info.pop(KEY, set())
        if not pending:
            return done
        for user_id, property_id in sorted(pending, key=lambda k: (str(k[0]), str(k[1]))):
            try:
                async with session.begin_nested():
                    if await certificate_service._net_units(session, user_id, property_id) > 0:
                        await certificate_service.current_certificate(
                            session, user_id=user_id, property_id=property_id
                        )
                        done += 1
            except Exception:  # noqa: BLE001 — never undo the purchase over its certificate
                log.exception(
                    "certificate not issued at once (holder=%s, property=%s)", user_id, property_id
                )
