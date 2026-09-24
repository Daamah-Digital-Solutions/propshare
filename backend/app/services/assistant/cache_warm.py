"""Keep the provider's prompt cache warm so the first message after a quiet spell is fast.

Measured locally (2026-09-23, gpt-5.6-luna): the ~11k-token prefix (system prompt + KB +
tool schemas) took 31 s to first token when the cache was cold and 2.7 s when it was warm.
The provider drops a cached prefix after ~30 minutes without use, and any deploy that
changes the prompt, the KB or a tool starts cold. So every ``assistant_cache_warm_minutes``
(default 20, 0 = off) one tiny request with the exact same prefix is sent.

Only one process warms per interval even with several gunicorn workers: each worker's loop
first *claims* the slot with a conditional upsert on ``platform_settings``; the loser skips.
A warm-up that hits a warm cache costs about 11k cached tokens (a fraction of a cent).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.services import settings_service
from app.services.assistant import agent, guard
from app.services.assistant.tools import llm_tools
from app.services.llm import registry
from app.services.llm.types import Completed, Failed, LLMRequest, UserMessage

log = logging.getLogger("capimax.assistant.cache")

CLAIM_KEY = "assistant_cache_warmed_at"
CHECK_EVERY_SECONDS = 60


async def _claim(session: AsyncSession, now: dt.datetime, every: dt.timedelta) -> bool:
    """True for exactly one caller per interval (ISO timestamps compare as text)."""
    row = await session.execute(
        text(
            "INSERT INTO platform_settings (key, value) VALUES (:k, :now) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value "
            "WHERE platform_settings.value < :cutoff RETURNING key"
        ),
        {"k": CLAIM_KEY, "now": now.isoformat(), "cutoff": (now - every).isoformat()},
    )
    return row.first() is not None


async def warm_once(
    session: AsyncSession, *, llm_factory=registry.get_client, now: dt.datetime | None = None
) -> str:
    """One warm-up if it is due. Returns what happened (for logs and tests)."""
    minutes = int(await settings_service.get_setting(session, "assistant_cache_warm_minutes"))
    settings = await agent.load_settings(session)
    if minutes <= 0 or not settings.enabled or not settings.model:
        return "off"
    if not get_settings().assistant_configured:
        return "not_configured"
    now = now or dt.datetime.now(dt.UTC)
    if not await _claim(session, now, dt.timedelta(minutes=minutes)):
        return "not_due"
    await session.commit()  # the claim is visible to the other workers before the slow call

    req = LLMRequest(
        # byte-identical prefix to a real turn: same instructions, tools and effort
        instructions=await agent.build_prompt(session, settings),
        tools=llm_tools(exclude=set(settings.disabled_tools)),
        items=(UserMessage("Reply with the single word OK."),),
        model=settings.model,
        effort=settings.effort,
        max_output_tokens=16,
        cache_key=agent.CACHE_KEY,
        user_key=guard.safety_identifier("cache-warmup"),
    )
    try:
        async for ev in llm_factory(settings.provider).stream(req):
            if isinstance(ev, Completed):
                return f"warmed:cached={ev.usage.cached_input_tokens}"
            if isinstance(ev, Failed):
                return f"failed:{ev.code}"
    except Exception as exc:  # a warm-up must never take the app down
        log.warning("assistant cache warm-up error: %s", exc)
        return "failed:exception"
    return "failed:no_terminal_event"


async def run_forever() -> None:
    """Background loop started with the app; cheap checks every minute, work only when due."""
    while True:
        try:
            async with get_sessionmaker()() as session:
                outcome = await warm_once(session)
                await session.commit()
            if outcome.startswith(("warmed", "failed")):
                log.info("assistant cache warm-up: %s", outcome)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("assistant cache warm-up loop error: %s", exc)
        await asyncio.sleep(CHECK_EVERY_SECONDS)
