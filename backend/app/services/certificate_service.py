"""Investment certificate generation (Group 2 — storage/certificates).

Generates a REAL, elegantly branded one-page PDF certificate from the caller's CURRENT net
holding in a property (read from the append-only ``ownership_ledger`` — never fabricated).

Rendered with reportlab (classic certificate styling: ornate green/gold border with corner
flourishes, serif typography, cream ground, a faint monogram watermark, and a gold-gradient
seal with a ribbon). The content stream is left uncompressed so the real values appear
literally in the bytes (verifiable in tests). ``build_all_zip`` bundles every held-property
certificate into a single .zip.
"""

from __future__ import annotations

import datetime as dt
import decimal
import io
import math
import pathlib
import uuid
import zipfile

from reportlab.lib.colors import Color, HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import OwnershipLedger, Property
from app.models.identity import User

_W, _H = 595.0, 842.0  # A4 points
_CX = _W / 2

_GREEN_D = HexColor("#0F6E4E")
_GREEN = HexColor("#198653")
_GOLD = HexColor("#B0852E")
_GOLD_L = HexColor("#E4C979")
_INK = HexColor("#23302A")
_MUTED = HexColor("#6B726C")
_CREAM = HexColor("#FCFBF5")
_PANEL = HexColor("#F3F8F4")

# Official logo asset (transparent PNG). Embedded in the certificate header when available;
# rendering falls back to the vector emblem + wordmark if it (or Pillow) is missing.
_LOGO_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "capimax-logo.png"


def _spaced_centred(
    c: canvas.Canvas, cx: float, y: float, font: str, size: float, text: str,
    spacing: float, color: HexColor,
) -> None:
    """Centred text with letter-spacing (Canvas has no setCharSpace — use a text object)."""
    w = stringWidth(text, font, size) + spacing * max(0, len(text) - 1)
    t = c.beginText(cx - w / 2, y)
    t.setFont(font, size)
    t.setFillColor(color)
    t.setCharSpace(spacing)
    t.textLine(text)
    c.drawText(t)


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    """Greedy word-wrap so a line never exceeds ``max_width`` at the given font/size."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if stringWidth(trial, font, size) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit_centred(
    c: canvas.Canvas, cx: float, y: float, font: str, base_size: float, text: str,
    max_width: float, color: HexColor,
) -> None:
    """Draw centred text, shrinking the font just enough that a long value never overflows."""
    size = base_size
    while size > 8 and stringWidth(text, font, size) > max_width:
        size -= 0.5
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawCentredString(cx, y, text)


def _clip(text: str, font: str, size: float, max_width: float) -> str:
    """Truncate with an ellipsis so a value fits inside its column."""
    if stringWidth(text, font, size) <= max_width:
        return text
    while text and stringWidth(text + "…", font, size) > max_width:
        text = text[:-1]
    return text + "…"


def _corner(c: canvas.Canvas, x: float, y: float, sx: int, sy: int) -> None:
    """A small gold bracket + diamond flourish tucked into a frame corner."""
    c.saveState()
    c.setStrokeColor(_GOLD)
    c.setLineWidth(1.2)
    c.line(x + sx * 10, y + sy * 10, x + sx * 34, y + sy * 10)
    c.line(x + sx * 10, y + sy * 10, x + sx * 10, y + sy * 34)
    c.setFillColor(_GOLD)
    ex, ey, d = x + sx * 10, y + sy * 10, 3.2
    p = c.beginPath()
    p.moveTo(ex, ey + d)
    p.lineTo(ex + d, ey)
    p.lineTo(ex, ey - d)
    p.lineTo(ex - d, ey)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def _divider(c: canvas.Canvas, cx: float, y: float, half: float) -> None:
    c.saveState()
    c.setStrokeColor(_GOLD)
    c.setLineWidth(0.8)
    c.line(cx - half, y, cx - 7, y)
    c.line(cx + 7, y, cx + half, y)
    c.setFillColor(_GOLD)
    d = 3.4
    p = c.beginPath()
    p.moveTo(cx, y + d)
    p.lineTo(cx + d, y)
    p.lineTo(cx, y - d)
    p.lineTo(cx - d, y)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def _emblem(c: canvas.Canvas, cx: float, cy: float, r: float) -> None:
    c.saveState()
    c.setFillColor(_GREEN)
    c.circle(cx, cy, r, stroke=0, fill=1)
    c.setStrokeColor(_GOLD_L)
    c.setLineWidth(1.2)
    c.circle(cx, cy, r - 3, stroke=1, fill=0)
    c.setFillColor(_CREAM)
    c.setFont("Times-Bold", 22)
    c.drawCentredString(cx, cy - 8, "C")
    c.restoreState()


def _seal(c: canvas.Canvas, cx: float, cy: float, r: float) -> None:
    """A gold-gradient wax-style seal with a rosette, monogram and ribbon tails."""
    c.saveState()
    # Ribbon tails first (so the disc overlaps them).
    top, bot = cy - r + 6, cy - r - 24
    c.setFillColor(_GOLD)
    for sgn in (-1, 1):
        bx, tx = cx + sgn * 11, cx + sgn * 22
        p = c.beginPath()
        p.moveTo(bx - 8, top)
        p.lineTo(bx + 8, top)
        p.lineTo(tx + 8, bot)
        p.lineTo(tx, bot + 8)
        p.lineTo(tx - 8, bot)
        p.close()
        c.drawPath(p, stroke=0, fill=1)

    # Gold radial-gradient face (clipped to the disc).
    c.saveState()
    disc = c.beginPath()
    disc.circle(cx, cy, r)
    c.clipPath(disc, stroke=0, fill=0)
    c.radialGradient(cx, cy + r * 0.35, r * 1.5, (_GOLD_L, _GOLD), (0.0, 1.0))
    c.restoreState()

    # Rosette ticks around the rim.
    c.setStrokeColor(_GOLD)
    c.setLineWidth(0.5)
    n = 64
    for i in range(n):
        a = 2 * math.pi * i / n
        c.line(
            cx + math.cos(a) * (r - 2), cy + math.sin(a) * (r - 2),
            cx + math.cos(a) * (r - 9), cy + math.sin(a) * (r - 9),
        )
    c.setStrokeColor(_GREEN_D)
    c.setLineWidth(1.6)
    c.circle(cx, cy, r, stroke=1, fill=0)

    # Inner cream medallion + rings + text.
    c.setFillColor(_CREAM)
    c.circle(cx, cy, r - 13, stroke=0, fill=1)
    c.setStrokeColor(_GREEN_D)
    c.setLineWidth(1.1)
    c.circle(cx, cy, r - 13, stroke=1, fill=0)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(0.5)
    c.circle(cx, cy, r - 17, stroke=1, fill=0)
    c.setFillColor(_GREEN_D)
    c.setFont("Times-Bold", 26)
    c.drawCentredString(cx, cy - 3, "C")
    c.setFont("Helvetica-Bold", 5.5)
    c.setFillColor(_GREEN)
    c.drawCentredString(cx, cy + 17, "OWNERSHIP")
    c.drawCentredString(cx, cy - 24, "CERTIFIED")
    c.restoreState()


def _draw_brand(c: canvas.Canvas, cx: float) -> None:
    """Centre the official CapiMax PropShare logo in the header. Falls back to the vector
    emblem + wordmark if the logo asset — or its image backend (Pillow) — is unavailable, so a
    certificate ALWAYS renders (never 500s on a missing dependency)."""
    try:
        from reportlab.lib.utils import ImageReader

        img = ImageReader(str(_LOGO_PATH))
        iw, ih = img.getSize()
        target_w = 210.0
        target_h = target_w * ih / iw
        top = 792.0  # just inside the top border
        c.drawImage(
            img,
            cx - target_w / 2,
            top - target_h,
            width=target_w,
            height=target_h,
            mask="auto",
            preserveAspectRatio=True,
        )
    except Exception:  # asset missing / no Pillow -> elegant vector fallback
        _emblem(c, cx, 760, 24)
        _spaced_centred(c, cx, 724, "Times-Bold", 15, "CAPIMAX PROPSHARE", 3.2, _GREEN_D)


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
    """Draw the branded CapiMax PropShare certificate (A4, classic styling)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_W, _H), pageCompression=0)
    c.setTitle("CapiMax PropShare — Certificate of Ownership")

    # Ground + faint monogram watermark.
    c.setFillColor(_CREAM)
    c.rect(0, 0, _W, _H, stroke=0, fill=1)
    c.saveState()
    c.setFillColor(Color(0.06, 0.43, 0.30, alpha=0.045))
    c.setFont("Times-Bold", 380)
    c.drawCentredString(_CX, 250, "C")
    c.restoreState()

    # Ornamental triple border + corner flourishes.
    c.setStrokeColor(_GREEN_D)
    c.setLineWidth(3.5)
    c.roundRect(30, 30, _W - 60, _H - 60, 9, stroke=1, fill=0)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(1.0)
    c.rect(40, 40, _W - 80, _H - 80, stroke=1, fill=0)
    c.setStrokeColor(_GREEN)
    c.setLineWidth(0.6)
    c.rect(44, 44, _W - 88, _H - 88, stroke=1, fill=0)
    _corner(c, 44, _H - 44, 1, -1)
    _corner(c, _W - 44, _H - 44, -1, -1)
    _corner(c, 44, 44, 1, 1)
    _corner(c, _W - 44, 44, -1, 1)

    # Header: official logo (with a vector emblem + wordmark fallback), then divider.
    _draw_brand(c, _CX)
    _divider(c, _CX, 712, 150)

    # Title + subtitle.
    _spaced_centred(c, _CX, 668, "Times-Bold", 31, "Certificate of Ownership", 1.2, _GREEN_D)
    c.setFillColor(_MUTED)
    c.setFont("Times-Italic", 12)
    c.drawCentredString(_CX, 648, "Fractional Real-Estate Ownership")

    # Attestation.
    c.setFillColor(_INK)
    c.setFont("Times-Roman", 12)
    c.drawCentredString(_CX, 612, "This is to certify that")
    _fit_centred(c, _CX, 584, "Times-Bold", 22, holder, 400, _GREEN_D)
    c.setStrokeColor(_GOLD_L)
    c.setLineWidth(0.8)
    c.line(_CX - 150, 576, _CX + 150, 576)
    c.setFillColor(_INK)
    c.setFont("Times-Roman", 12)
    holds_line = f"is the registered holder of {units} fractional ownership units in"
    c.drawCentredString(_CX, 552, holds_line)
    _fit_centred(c, _CX, 530, "Times-Bold", 14, property_title, 430, _GREEN)
    c.setFillColor(_INK)
    c.setFont("Times-Roman", 12)
    c.drawCentredString(_CX, 510, "as recorded in the CapiMax PropShare ownership ledger.")

    # Fact panel (2 columns x 4 rows).
    px, py, pw, ph = 82, 292, _W - 164, 170
    c.setFillColor(_PANEL)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(0.8)
    c.roundRect(px, py, pw, ph, 6, stroke=1, fill=1)
    fields = [
        ("LOCATION", location),
        ("RECORDED VALUE", value),
        ("UNITS HELD", str(units)),
        ("OWNERSHIP STAKE", ownership),
        ("ISSUING SPV", spv),
        ("JURISDICTION", jurisdiction),
        ("CERTIFICATE REFERENCE", cert_ref),
        ("ISSUED", issued),
    ]
    for i, (label, val) in enumerate(fields):
        col, row = i % 2, i // 2
        x = px + 30 + col * (pw / 2 - 12)
        y = py + ph - 30 - row * 38
        c.setFillColor(_MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(x, y, label)
        c.setFillColor(_INK)
        c.setFont("Times-Roman", 12.5)
        c.drawString(x, y - 16, _clip(str(val), "Times-Roman", 12.5, pw / 2 - 44))

    # Seal (bottom-right) + signature (bottom-left) share a band well above the footer.
    _seal(c, 458, 232, 48)
    c.setStrokeColor(_INK)
    c.setLineWidth(0.8)
    c.line(92, 210, 250, 210)
    c.setFillColor(_GREEN_D)
    c.setFont("Times-Italic", 12)
    c.drawString(98, 216, "CapiMax PropShare")
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(92, 196, "Authorized on behalf of the platform")

    # Footer — honest legal framing, word-wrapped so it never spills past the frame.
    c.setFillColor(_MUTED)
    c.setFont("Times-Roman", 8.5)
    footer_text = (
        "This certificate reflects the fractional units recorded in the CapiMax PropShare "
        "ownership ledger as of the issue date. It is generated from live data and is not a "
        "transferable security or a substitute for the offering documents and SPV agreements "
        "governing this property."
    )
    # NB: viewers render base-14 Times with a WIDER metric-compatible substitute (~1.4x) than
    # stringWidth() assumes, so keep the wrap width well under the ~500pt safe area.
    fy = 128
    for ln in _wrap(footer_text, "Times-Roman", 8.5, 290):
        c.drawCentredString(_CX, fy, ln)
        fy -= 12.5
    c.setFillColor(_GOLD)
    c.setFont("Helvetica", 8)
    c.drawCentredString(_CX, 74, f"{cert_ref}   •   capimaxpropshare.com")

    c.showPage()
    c.save()
    return buf.getvalue()


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


async def build_property_bundle_zip(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> tuple[str, bytes]:
    """ONE .zip for a SINGLE property: the caller's live ownership certificate (when they hold
    units) PLUS every document published for the property — SPV papers, agreements, valuation
    and financial reports, legal docs, insurance certificates, audit reports, etc. — each filed
    under a folder named for its category. 404 only if there is genuinely nothing to include."""
    from app.services import document_service  # lazy: avoids any import cycle

    prop = await session.get(Property, property_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)

    buf = io.BytesIO()
    added = 0
    used: set[str] = set()

    def _put(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
        nonlocal added
        candidate, i = name, 2
        while candidate in used:  # never overwrite a same-named file inside the zip
            stem, dot, ext = name.rpartition(".")
            candidate = f"{stem}-{i}{dot}{ext}" if dot else f"{name}-{i}"
            i += 1
        used.add(candidate)
        zf.writestr(candidate, data)
        added += 1

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) the caller's live ownership certificate (skip silently if they hold nothing)
        try:
            fname, pdf = await build_for_holding(
                session, user_id=user_id, property_id=property_id, now=now
            )
            _put(zf, f"Certificate/{fname}", pdf)
        except AppError:
            pass
        # 2) every published document for the property, grouped into category folders
        try:
            docs = await document_service.list_property_documents(session, str(property_id))
        except AppError:
            docs = []  # property not public yet -> just the certificate
        for d in docs:
            try:
                _doc, data, _ct = await document_service.get_for_download(session, d.id)
            except AppError:
                continue  # a missing/forbidden file is skipped, never fatal
            folder = (d.type or "other").strip().replace("/", "-") or "other"
            base = d.file_url.rsplit("/", 1)[-1]
            _put(zf, f"{folder}/{base}", data)

    if added == 0:
        raise AppError(
            "NO_DOCUMENTS",
            "No certificate or documents are available for this property yet.",
            status_code=404,
        )
    slug = prop.slug or str(prop.id)
    return f"{slug}-documents.zip", buf.getvalue()
