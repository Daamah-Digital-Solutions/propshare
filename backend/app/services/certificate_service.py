"""Investment certificate generation (Group 2 — storage/certificates).

Generates a REAL, professionally branded one-page PDF certificate from the caller's CURRENT
net holding in a property (read from the append-only ``ownership_ledger`` — never fabricated).

The PDF is drawn with a tiny dependency-free writer (no reportlab) so the artifact is
deterministic and testable: vector graphics (branded border, header band, gold rule, seal)
plus text, all in an UNCOMPRESSED content stream so the real values appear literally in the
bytes. Wording stays factual (units recorded in the CapiMax ledger) and does not over-claim
legal/SPV status. ``build_all_zip`` bundles every held-property certificate into one .zip.
"""

from __future__ import annotations

import datetime as dt
import decimal
import io
import uuid
import zipfile

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import OwnershipLedger, Property
from app.models.identity import User

# Brand palette as PDF colour operands ("r g b").
_GREEN = "0.098 0.525 0.325"
_GOLD = "0.961 0.624 0.039"
_INK = "0.133 0.165 0.149"
_MUTED = "0.42 0.43 0.41"
_WHITE = "1 1 1"


def _esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _n(v: float) -> str:
    """Compact number formatting for PDF operands (no trailing zeros noise)."""
    return f"{v:.2f}".rstrip("0").rstrip(".")


class _Canvas:
    """Accumulates PDF content-stream operators for a single page (origin bottom-left)."""

    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(self, x: float, y: float, size: float, font: str, color: str, s: str) -> None:
        self.ops += [
            "BT",
            f"/{font} {_n(size)} Tf",
            f"{color} rg",
            f"{_n(x)} {_n(y)} Td",
            f"({_esc(s)}) Tj",
            "ET",
        ]

    def fill_rect(self, x: float, y: float, w: float, h: float, color: str) -> None:
        self.ops += [f"{color} rg", f"{_n(x)} {_n(y)} {_n(w)} {_n(h)} re", "f"]

    def stroke_rect(self, x: float, y: float, w: float, h: float, color: str, lw: float) -> None:
        self.ops += [f"{color} RG", f"{_n(lw)} w", f"{_n(x)} {_n(y)} {_n(w)} {_n(h)} re", "S"]

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str, lw: float) -> None:
        self.ops += [
            f"{color} RG",
            f"{_n(lw)} w",
            f"{_n(x1)} {_n(y1)} m",
            f"{_n(x2)} {_n(y2)} l",
            "S",
        ]

    def circle(self, cx: float, cy: float, r: float, color: str, lw: float) -> None:
        k = 0.5523 * r
        self.ops += [
            f"{color} RG",
            f"{_n(lw)} w",
            f"{_n(cx + r)} {_n(cy)} m",
            f"{_n(cx + r)} {_n(cy + k)} {_n(cx + k)} {_n(cy + r)} {_n(cx)} {_n(cy + r)} c",
            f"{_n(cx - k)} {_n(cy + r)} {_n(cx - r)} {_n(cy + k)} {_n(cx - r)} {_n(cy)} c",
            f"{_n(cx - r)} {_n(cy - k)} {_n(cx - k)} {_n(cy - r)} {_n(cx)} {_n(cy - r)} c",
            f"{_n(cx + k)} {_n(cy - r)} {_n(cx + r)} {_n(cy - k)} {_n(cx + r)} {_n(cy)} c",
            "S",
        ]

    def bytes(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1", "replace")


def render_certificate_pdf(
    *,
    holder: str,
    property_title: str,
    location: str,
    units: int,
    ownership: str,
    value: str,
    spv: str,
    jurisdiction: str,
    cert_ref: str,
    issued: str,
) -> bytes:
    """Draw the branded CapiMax PropShare certificate. A4 (595x842), Helvetica + Bold."""
    c = _Canvas()
    # Frame: green outer border + thin gold inner border.
    c.fill_rect(34, 743, 527, 65, _GREEN)  # header band
    c.stroke_rect(26, 26, 543, 790, _GREEN, 2.5)  # outer border
    c.stroke_rect(33, 33, 529, 776, _GOLD, 0.8)  # inner border
    c.line(34, 740, 561, 740, _GOLD, 1.5)  # gold rule under the band

    # Header (on the green band).
    c.text(54, 772, 20, "F2", _WHITE, "CapiMax PropShare")
    c.text(55, 754, 10.5, "F1", _WHITE, "Certificate of Fractional Ownership")

    # Attestation.
    c.text(56, 706, 11, "F1", _INK, "This certifies that")
    c.text(56, 685, 15, "F2", _GREEN, holder)
    c.text(
        56, 661, 11, "F1", _INK,
        f"is the registered holder of {units} fractional ownership unit(s) in the",
    )
    c.text(56, 645, 11, "F1", _INK,
           "property below, as recorded in the CapiMax PropShare ownership ledger.")

    # Fact table (label / value), each row with a faint separator.
    rows = [
        ("Property", property_title),
        ("Location", location),
        ("Units held", str(units)),
        ("Ownership stake", ownership),
        ("Recorded value", value),
        ("Issuing SPV", spv),
        ("Jurisdiction", jurisdiction),
        ("Certificate reference", cert_ref),
        ("Issued", issued),
    ]
    y = 604
    for label, val in rows:
        c.text(70, y, 10, "F2", _MUTED, label.upper())
        c.text(240, y, 11, "F1", _INK, val)
        c.line(70, y - 9, 525, y - 9, "0.9 0.9 0.88", 0.4)
        y -= 29

    # Seal (concentric circles + monogram).
    c.circle(470, 250, 46, _GREEN, 2)
    c.circle(470, 250, 38, _GOLD, 0.8)
    c.text(451, 254, 15, "F2", _GREEN, "CMX")
    c.text(440, 236, 7, "F1", _MUTED, "OWNERSHIP")

    # Signature block.
    c.line(70, 205, 250, 205, _INK, 0.8)
    c.text(70, 212, 10, "F2", _INK, "CapiMax PropShare")
    c.text(70, 192, 8.5, "F1", _MUTED, "Authorized on behalf of the platform")

    # Footer — honest legal framing (no over-claim).
    footer = [
        "This certificate reflects fractional units recorded in the CapiMax PropShare ownership"
        " ledger as of",
        "the issue date. It is generated from live data and is not a transferable security or a"
        " substitute for the",
        "offering documents and SPV agreements governing this property.",
    ]
    fy = 128
    for ln in footer:
        c.text(56, fy, 8.5, "F1", _MUTED, ln)
        fy -= 12
    c.text(56, 62, 8, "F1", _MUTED, f"{cert_ref}   -   capimaxpropshare.com")

    return _pdf_bytes(c.bytes())


def _pdf_bytes(content: bytes) -> bytes:
    """Assemble a valid single-page PDF with Helvetica (F1) + Helvetica-Bold (F2)."""
    objs: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
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


async def _held_property_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    res = await session.execute(
        select(OwnershipLedger.property_id)
        .where(OwnershipLedger.user_id == user_id)
        .group_by(OwnershipLedger.property_id)
        .having(func.coalesce(func.sum(OwnershipLedger.units), 0) > 0)
    )
    return [r[0] for r in res.all()]


async def build_for_holding(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> tuple[str, bytes]:
    """Return (filename, pdf_bytes) for the caller's net holding; 404 if they hold none.

    All values are REAL: units from the ledger; ownership %, value, SPV reference and
    jurisdiction derived from the property record; the certificate reference is a stable,
    deterministic id (property + holder), never random."""
    units = await _net_units(session, user_id, property_id)
    if units <= 0:
        raise AppError("NO_HOLDING", "You do not hold any units in this property.", status_code=404)
    prop = await session.get(Property, property_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)
    user = await session.get(User, user_id)
    holder = (user.full_name if user and user.full_name else (user.email if user else "")) or "-"

    unit_price = decimal.Decimal(str(prop.unit_price or 0))
    value = (unit_price * units).quantize(decimal.Decimal("0.01"))
    total_units = int(prop.total_units or 0)
    ownership = (
        f"{(decimal.Decimal(units) / total_units * 100).quantize(decimal.Decimal('0.01'))}%"
        if total_units > 0
        else "-"
    )
    jurisdiction = prop.country or getattr(prop, "city", None) or prop.location or "-"
    cert_ref = ("CMX-" + str(property_id)[:4] + str(user_id)[:4]).upper()
    issued = (now or dt.datetime.now(dt.UTC)).strftime("%b %d, %Y")

    pdf = render_certificate_pdf(
        holder=holder,
        property_title=prop.title,
        location=prop.location or "-",
        units=units,
        ownership=ownership,
        value=f"${value:,.2f}",
        spv=f"{prop.title} SPV",
        jurisdiction=jurisdiction,
        cert_ref=cert_ref,
        issued=issued,
    )
    slug = prop.slug or str(prop.id)
    return f"certificate-{slug}.pdf", pdf


async def build_all_zip(
    session: AsyncSession, *, user_id: uuid.UUID, now: dt.datetime | None = None
) -> tuple[str, bytes]:
    """Bundle a certificate for EVERY property the caller currently holds into one .zip.
    404 if they hold no units anywhere."""
    pids = await _held_property_ids(session, user_id)
    if not pids:
        raise AppError("NO_HOLDING", "You do not hold units in any property.", status_code=404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pid in pids:
            fname, pdf = await build_for_holding(
                session, user_id=user_id, property_id=pid, now=now
            )
            zf.writestr(fname, pdf)
    return "capimax-certificates.zip", buf.getvalue()
