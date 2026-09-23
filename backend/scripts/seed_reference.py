"""Load the company reference library (app/knowledge/reference) into ``kb_articles``.

Each document is split into heading-sized chunks (see ``app.services.reference_library``) and
stored with ``audience='reference'``: searchable by the assistant's ``search_reference`` tool,
never part of the prompt's knowledge-base block.

Like seed_kb.py, a run writes DRAFTS (a new version only when a chunk's text changed) and
approval is a separate, audited act: the admin panel (Knowledge Base -> Approve) or
``--approve-as <admin email>``. With ``--approve-as``, chunks that no longer exist in the
source files (a document was shortened) are retired, so stale passages stop being served.

Usage:
    python scripts/seed_reference.py                      # drafts only
    python scripts/seed_reference.py --approve-as admin@example.com
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.db import session_scope
from app.models import KbArticle
from app.services import auth_service, kb_service, reference_library


async def _seed(approve_as: str | None) -> int:
    chunks = reference_library.load_chunks()
    created = retired = 0
    async with session_scope() as session:
        actor = None
        if approve_as:
            user = await auth_service.get_user_by_email(session, approve_as)
            if user is None or "admin" not in await auth_service.get_roles(session, user.id):
                print(f"refusing: {approve_as} is not an admin", file=sys.stderr)
                return 2
            actor = user.id
        for chunk in chunks:
            latest = await session.scalar(
                select(KbArticle)
                .where(KbArticle.slug == chunk.slug, KbArticle.lang == chunk.lang)
                .order_by(KbArticle.version.desc())
                .limit(1)
            )
            if (
                latest is not None
                and latest.body_md == chunk.body
                and latest.title == chunk.title
                and latest.status != "retired"
            ):
                row = latest
            else:
                row = await kb_service.upsert_draft(
                    session,
                    slug=chunk.slug,
                    lang=chunk.lang,
                    title=chunk.title,
                    body_md=chunk.body,
                    category="reference",
                    audience=reference_library.REFERENCE_AUDIENCE,
                    priority=500,
                    source_ref=chunk.source_ref,
                )
                created += 1
            if actor is not None and row.status == "draft":
                await kb_service.approve(session, article_id=row.id, actor_id=actor)
        if actor is not None:
            live = {(c.slug, c.lang) for c in chunks}
            stale = (
                await session.execute(
                    select(KbArticle).where(
                        KbArticle.audience == reference_library.REFERENCE_AUDIENCE,
                        KbArticle.status.in_(("approved", "draft")),
                    )
                )
            ).scalars()
            for row in list(stale):
                if (row.slug, row.lang) not in live:
                    await kb_service.retire(session, article_id=row.id, actor_id=actor)
                    retired += 1
    print(
        f"seed_reference: {created} new draft version(s), {retired} stale retired; "
        f"{len(chunks)} passages from {len(reference_library.SOURCES)} documents"
    )
    return 0


def main(argv: list[str]) -> int:
    approve_as = None
    if "--approve-as" in argv:
        approve_as = argv[argv.index("--approve-as") + 1]
    return asyncio.run(_seed(approve_as))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
