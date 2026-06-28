"""Redis client (used for locks/idempotency/queues in later phases).

Phase 0 only needs a health ping. Like the DB layer, this is defensive: a
missing client or unreachable server reports "down" instead of crashing.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings

_client: Any | None = None


def get_redis() -> Any:
    global _client
    if _client is None:
        from redis.asyncio import Redis  # imported lazily so app import never fails

        _client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def ping_redis() -> bool:
    """Return True iff Redis responds to PING. Never raises."""
    try:
        client = get_redis()
        return bool(await client.ping())
    except Exception:
        return False


async def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None
