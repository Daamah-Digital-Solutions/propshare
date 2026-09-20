"""Document search for the assistant (Batch D, client doc §3/§18).

``index_pending`` (cron) extracts text from PROPERTY documents that have none yet — PDFs
through pypdf, plain text as is; anything else is recorded as unsupported so it is never
retried every hour. ``search`` returns short passages around the query words from the
public documents of one property, so the model can quote the document instead of guessing.

Only property documents are indexed; user-scoped documents (KYC files, role applications)
are excluded by construction. Scanned PDFs yield no text and are marked ``empty``: the
assistant then says the document exists but cannot be searched.
"""

from __future__ import annotations

import io
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentText, Property
from app.services import property_service
from app.services.integrations import storage

log = logging.getLogger(__name__)

MAX_CHARS = 400_000  # per document; beyond this the text is cut (contracts are long, fine)
SNIPPET = 220  # chars either side of a hit
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


def extract_text(data: bytes, file_url: str) -> tuple[str, int, str]:
    """(text, pages, status) for one file. Never raises: failures become a status."""
    lower = file_url.lower()
    if lower.endswith((".txt", ".md")):
        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            return "", 0, "failed"
        return _clean(text), 1, "indexed" if text.strip() else "empty"
    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            parts = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:  # noqa: BLE001 — one bad page must not lose the rest
                    parts.append("")
            text = _clean("\n".join(parts))
            return text, len(reader.pages), "indexed" if text.strip() else "empty"
        except Exception as exc:  # noqa: BLE001
            log.warning("pdf extraction failed for %s: %s", file_url, exc)
            return "", 0, "failed"
    return "", 0, "unsupported"


def _clean(text: str) -> str:
    text = _WS.sub(" ", text.replace("\x00", ""))
    text = _NL.sub("\n\n", text)
    return text.strip()[:MAX_CHARS]


async def index_document(session: AsyncSession, doc: Document) -> DocumentText:
    try:
        data = storage.load(doc.file_url)
    except storage.StorageNotFound:
        row = DocumentText(
            document_id=doc.id,
            property_id=doc.property_id,
            status="failed",
            error="file missing",
        )
        await session.merge(row)
        return row
    text, pages, status = extract_text(data, doc.file_url)
    row = DocumentText(
        document_id=doc.id,
        property_id=doc.property_id,
        status=status,
        pages=pages,
        chars=len(text),
        body=text,
        error=None,
    )
    await session.merge(row)
    return row


async def index_pending(session: AsyncSession, *, limit: int = 50) -> dict[str, int]:
    """Index property documents that have no text row yet (cron; idempotent)."""
    indexed = set(r[0] for r in (await session.execute(select(DocumentText.document_id))).all())
    docs = (
        (
            await session.execute(
                select(Document)
                .where(Document.property_id.is_not(None), Document.user_id.is_(None))
                .order_by(Document.created_at)
            )
        )
        .scalars()
        .all()
    )
    todo = [d for d in docs if d.id not in indexed][:limit]
    counts: dict[str, int] = {"indexed": 0, "empty": 0, "unsupported": 0, "failed": 0}
    for doc in todo:
        row = await index_document(session, doc)
        counts[row.status] = counts.get(row.status, 0) + 1
    await session.flush()
    counts["remaining"] = max(len(docs) - len(indexed) - len(todo), 0)
    return counts


async def reindex_document(session: AsyncSession, doc_id: uuid.UUID) -> DocumentText | None:
    """After an admin replaces a file (document_service.replace_document_file)."""
    doc = await session.get(Document, doc_id)
    if doc is None or doc.property_id is None:
        return None
    return await index_document(session, doc)


def _terms(query: str) -> list[str]:
    words = [w for w in re.split(r"[^\w؀-ۿ%.-]+", query.lower()) if len(w) >= 3]
    return words[:8]


def _snippets(body: str, terms: list[str], *, max_hits: int) -> list[str]:
    lower = body.lower()
    out: list[str] = []
    seen: list[tuple[int, int]] = []
    for term in terms:
        start = 0
        while len(out) < max_hits:
            i = lower.find(term, start)
            if i < 0:
                break
            a, b = max(0, i - SNIPPET), min(len(body), i + len(term) + SNIPPET)
            if any(a < e and b > s for s, e in seen):
                start = i + len(term)
                continue
            seen.append((a, b))
            piece = body[a:b].strip()
            out.append(("…" if a > 0 else "") + piece + ("…" if b < len(body) else ""))
            start = i + len(term)
    return out


async def search(
    session: AsyncSession,
    *,
    property_id_or_slug: str,
    query: str,
    max_hits: int = 4,
    preview_token: str | None = None,
) -> dict:
    """Passages from the PUBLIC documents of one property that contain the query words."""
    prop: Property = await property_service.get_public_detail(
        session, property_id_or_slug, preview_token=preview_token
    )
    rows = (
        await session.execute(
            select(Document, DocumentText)
            .join(DocumentText, DocumentText.document_id == Document.id, isouter=True)
            .where(Document.property_id == prop.id, Document.user_id.is_(None))
            .order_by(Document.created_at.desc())
        )
    ).all()
    terms = _terms(query)
    hits = []
    unsearchable = []
    for doc, text in rows:
        if text is None or text.status != "indexed":
            unsearchable.append(
                {
                    "title": doc.title,
                    "type": str(doc.type),
                    "reason": (text.status if text else "not indexed yet"),
                }
            )
            continue
        snippets = _snippets(text.body, terms, max_hits=max_hits) if terms else []
        if snippets:
            hits.append(
                {
                    "title": doc.title,
                    "type": str(doc.type),
                    "pages": text.pages,
                    "passages": snippets[:max_hits],
                }
            )
    return {
        "property_title": prop.title,
        "slug": prop.slug,
        "documents_total": len(rows),
        "hits": hits[:6],
        "unsearchable": unsearchable[:10],
    }
