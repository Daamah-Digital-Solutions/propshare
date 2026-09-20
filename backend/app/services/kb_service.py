"""Approved knowledge base for the assistant (plan §7).

Only ``approved`` articles reach the model. ``render_bundle`` turns them into ONE deterministic
text block for the system prompt: same rows in, same bytes out, so the provider's prompt cache
keeps hitting until an article is actually approved or retired.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import KbArticle

MAX_BUNDLE_CHARS = 60_000  # ~15k tokens; a bigger KB must be split by audience (Phase 2)


async def approved_articles(session: AsyncSession) -> list[KbArticle]:
    stmt = (
        select(KbArticle)
        .where(KbArticle.status == "approved")
        .order_by(KbArticle.priority, KbArticle.slug, KbArticle.lang, KbArticle.version)
    )
    return list((await session.execute(stmt)).scalars().all())


def render_articles(rows: list[KbArticle]) -> str:
    parts = [
        f"## [{r.lang}] {r.title.strip()}  (kb:{r.slug} v{r.version})\n{r.body_md.strip()}"
        for r in rows
    ]
    text = "\n\n".join(parts)
    if len(text) > MAX_BUNDLE_CHARS:
        raise AppError(
            "KB_TOO_LARGE",
            f"The approved knowledge base is {len(text)} characters; the limit is "
            f"{MAX_BUNDLE_CHARS}. Retire or merge articles.",
            status_code=503,
        )
    return text or "(no approved articles yet)"


async def render_bundle(session: AsyncSession) -> str:
    return render_articles(await approved_articles(session))


async def upsert_draft(
    session: AsyncSession,
    *,
    slug: str,
    lang: str,
    title: str,
    body_md: str,
    category: str | None = None,
    audience: str = "all",
    priority: int = 100,
    source_ref: str | None = None,
) -> KbArticle:
    """A new DRAFT version of (slug, lang). Approval is a separate, audited step."""
    latest = await session.scalar(
        select(KbArticle.version)
        .where(KbArticle.slug == slug, KbArticle.lang == lang)
        .order_by(KbArticle.version.desc())
        .limit(1)
    )
    row = KbArticle(
        slug=slug,
        lang=lang,
        title=title,
        body_md=body_md,
        category=category,
        audience=audience,
        priority=priority,
        source_ref=source_ref,
        status="draft",
        version=(latest or 0) + 1,
    )
    session.add(row)
    await session.flush()
    return row


async def approve(
    session: AsyncSession, *, article_id: uuid.UUID, actor_id: uuid.UUID
) -> KbArticle:
    """Approve one version and retire any other approved version of the same (slug, lang)."""
    row = await session.get(KbArticle, article_id)
    if row is None:
        raise AppError("NOT_FOUND", "Article not found.", status_code=404)
    others = (
        await session.execute(
            select(KbArticle).where(
                KbArticle.slug == row.slug,
                KbArticle.lang == row.lang,
                KbArticle.status == "approved",
                KbArticle.id != row.id,
            )
        )
    ).scalars()
    now = dt.datetime.now(dt.UTC)
    for other in others:
        other.status = "retired"
        other.updated_at = now
    row.status = "approved"
    row.approved_by = actor_id
    row.approved_at = now
    row.updated_at = now
    await write_audit(
        session,
        action="kb.approved",
        entity_type="kb_article",
        entity_id=str(row.id),
        actor_id=actor_id,
        after={"slug": row.slug, "lang": row.lang, "version": row.version},
    )
    await session.flush()
    return row


async def retire(session: AsyncSession, *, article_id: uuid.UUID, actor_id: uuid.UUID) -> KbArticle:
    row = await session.get(KbArticle, article_id)
    if row is None:
        raise AppError("NOT_FOUND", "Article not found.", status_code=404)
    row.status = "retired"
    row.updated_at = dt.datetime.now(dt.UTC)
    await write_audit(
        session,
        action="kb.retired",
        entity_type="kb_article",
        entity_id=str(row.id),
        actor_id=actor_id,
        after={"slug": row.slug, "lang": row.lang, "version": row.version},
    )
    await session.flush()
    return row
