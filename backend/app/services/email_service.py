"""Email outbox drainer (Phase 12).

Sends ``email_outbox`` rows OUTSIDE any money transaction — the counterpart to the
transactional write in ``notification_service.notify``. Cron-able (Phase 13): pulls a
batch of ``pending`` rows ``FOR UPDATE SKIP LOCKED`` so concurrent drainers never
double-send, calls the configured provider seam, and marks each ``sent`` (idempotent —
already-sent rows are never reselected) or bumps ``attempts``/``last_error`` and retires
to ``failed`` after ``max_attempts``. Console provider locally (logs, never raises);
Resend live on the VPS.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.models import EmailOutbox
from app.services.integrations import email as email_provider


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def dispatch_pending(
    session: AsyncSession, *, limit: int = 50, max_attempts: int = 5
) -> dict:
    """Send up to ``limit`` pending emails. Returns {sent, failed, retried}."""
    rows = (
        (
            await session.execute(
                select(EmailOutbox)
                .where(EmailOutbox.status == "pending", EmailOutbox.attempts < max_attempts)
                .order_by(EmailOutbox.created_at)
                .limit(min(limit, 200))
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    sent = failed = retried = 0
    for row in rows:
        try:
            await email_provider.send_email(to=row.to_email, subject=row.subject, text=row.body)
        except Exception as exc:  # noqa: BLE001 — provider error: retry, never crash the drain
            row.attempts += 1
            row.last_error = str(exc)[:500]
            if row.attempts >= max_attempts:
                row.status = "failed"
                failed += 1
            else:
                retried += 1
            continue
        row.status = "sent"
        row.sent_at = _utcnow()
        row.attempts += 1
        sent += 1

    if sent or failed:
        await write_audit(
            session,
            action="email.dispatch",
            entity_type="email_outbox",
            entity_id="batch",
            after={"sent": sent, "failed": failed, "retried": retried},
        )
    return {"sent": sent, "failed": failed, "retried": retried}
