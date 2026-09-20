"""Scheduled upkeep (plan §3/§10): retention purge and key rotation re-encryption.

Both are idempotent and safe to re-run; they are exposed as admin-or-cron endpoints.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core import crypto
from app.models import AssistantConversation, AssistantMessage

ENCRYPTED_FIELDS = ("text", "content", "tool_calls", "cards")


async def purge_expired(session: AsyncSession, *, retention_days: int) -> int:
    """Delete conversations whose last activity is older than the retention window.
    Messages and proposals cascade; tickets keep their (structured) summary and lose only
    the transcript link target."""
    if retention_days <= 0:
        return 0
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=retention_days)
    last = func.coalesce(AssistantConversation.last_message_at, AssistantConversation.created_at)
    result = await session.execute(delete(AssistantConversation).where(last < cutoff))
    return int(result.rowcount or 0)


async def reencrypt(session: AsyncSession, *, batch: int = 500) -> dict[str, int]:
    """Re-save every message not yet encrypted with the ACTIVE key. Reading decrypts with
    the old key (still in the key file), writing encrypts with the active one; the old key
    can be retired once ``remaining`` is 0."""
    active = crypto.active_key_id()
    rows = (
        (
            await session.execute(
                select(AssistantMessage)
                .where(
                    (AssistantMessage.enc_key_id.is_(None))
                    | (AssistantMessage.enc_key_id != active)
                )
                .limit(batch)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        for field in ENCRYPTED_FIELDS:
            getattr(row, field)  # load (decrypt) so the value is present
            flag_modified(row, field)  # force a re-write even though the value is unchanged
        row.enc_key_id = active
    await session.flush()
    remaining = await session.scalar(
        select(func.count())
        .select_from(AssistantMessage)
        .where((AssistantMessage.enc_key_id.is_(None)) | (AssistantMessage.enc_key_id != active))
    )
    return {"reencrypted": len(rows), "remaining": int(remaining or 0), "active_key": active}
