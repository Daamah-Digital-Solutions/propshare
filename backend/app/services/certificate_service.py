"""Investment certificate generation (Phase: storage/certificates).

Generates a REAL one-page PDF certificate from the caller's CURRENT net holding in a
property (read from the append-only ``ownership_ledger`` — never fabricated). The PDF is
built with a tiny dependency-free writer (no reportlab) so the artifact is deterministic
and testable. Wording is factual (units recorded in the CapiMax ledger) — it does not
over-claim legal/SPV status.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import OwnershipLedger, Property
from app.models.identity import User


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_pdf(lines: list[str]) -> bytes:
    """Minimal, valid single-page PDF (Helvetica) showing ``lines`` as text.

    Text is written uncompressed in the content stream, so the real values appear
    literally in the bytes (verifiable in tests)."""
    content_ops = ["BT", "/F1 12 Tf", "72 760 Td", "18 TL"]
    for ln in lines:
        content_ops.append(f"({_esc(ln)}) Tj")
        content_ops.append("T*")
    content_ops.append("ET")
    content = "\n".join(content_ops).encode("latin-1", "replace")

    objs: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = b"%PDF-1.4\n"
    offsets: list[int] = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size "
        + str(len(objs) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF"
    )
    return out


async def _net_units(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    res = await session.execute(
        select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
            OwnershipLedger.user_id == user_id,
            OwnershipLedger.property_id == property_id,
        )
    )
    return int(res.scalar_one() or 0)


async def build_for_holding(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> tuple[str, bytes]:
    """Return (filename, pdf_bytes) for the caller's net holding; 404 if they hold none."""
    units = await _net_units(session, user_id, property_id)
    if units <= 0:
        raise AppError("NO_HOLDING", "You do not hold any units in this property.", status_code=404)
    prop = await session.get(Property, property_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)
    user = await session.get(User, user_id)
    holder = (user.full_name if user and user.full_name else (user.email if user else "")) or "—"
    unit_price = decimal.Decimal(str(prop.unit_price or 0)).quantize(decimal.Decimal("0.01"))
    as_of = (now or dt.datetime.now(dt.UTC)).date().isoformat()

    lines = [
        "CapiMax PropShare",
        "Certificate of Fractional Ownership",
        "",
        f"Holder: {holder}",
        f"Property: {prop.title}",
        f"Units held: {units}",
        f"Recorded unit price: ${unit_price}",
        f"As of: {as_of}",
        "",
        "This certificate reflects fractional units recorded in the CapiMax",
        "ownership ledger as of the date above. It is generated from live data",
        "and is not a transferable security or a substitute for the offering",
        "documents and SPV agreements governing this property.",
    ]
    slug = prop.slug or str(prop.id)
    return f"certificate-{slug}.pdf", render_pdf(lines)
