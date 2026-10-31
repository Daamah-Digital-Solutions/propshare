"""Investment certificate generation (Group 2 — storage/certificates).

Generates a REAL, elegantly branded one-page PDF certificate from the caller's CURRENT net
holding in a property (read from the append-only ``ownership_ledger`` — never fabricated).

Every certificate issued is kept (``investment_certificates``, client 2026-10-28, as on Capimax
BRX): it has a unique number and a secret verification code, and its QR code opens
``/verify/{code}`` on PropShare, where anyone holding the paper can confirm it is authentic and
current. A certificate states the holder's units at the time it was issued; when they change,
the next certificate states the new count and the old one is shown as superseded, so a paper
that no longer matches the ledger never reads as valid. See ``current_certificate``.

Rendered with reportlab (classic certificate styling: ornate green/gold border with corner
flourishes, serif typography, cream ground, a faint monogram watermark, and a gold-gradient
seal with a ribbon). The content stream is left uncompressed so the real values appear
literally in the bytes (verifiable in tests). ``build_all_zip`` bundles every held-property
certificate into a single .zip.
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import hmac
import io
import math
import pathlib
import secrets
import uuid
import zipfile

import segno
from reportlab.lib.colors import Color, HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import InvestmentCertificate, OwnershipLedger, Property
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
# The certificate title's letter-spacing, in points. PDF keeps it for the text drawn after it.
_TRACKING = 1.2

# Official logo asset (transparent PNG). Embedded in the certificate header when available;
# rendering falls back to the vector emblem + wordmark if it (or Pillow) is missing.
_LOGO_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "capimax-logo.png"


def _spaced_centred(
    c: canvas.Canvas,
    cx: float,
    y: float,
    font: str,
    size: float,
    text: str,
    spacing: float,
    color: HexColor,
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
    c: canvas.Canvas,
    cx: float,
    y: float,
    font: str,
    base_size: float,
    text: str,
    max_width: float,
    color: HexColor,
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


def _seal(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    r: float,
    *,
    upper: str = "OWNERSHIP",
    lower: str = "CERTIFIED",
) -> None:
    """A gold-gradient wax-style seal with a rosette, monogram and ribbon tails. ``upper``
    and ``lower`` are the two words around the monogram (the beneficiary certificate has
    its own)."""
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
            cx + math.cos(a) * (r - 2),
            cy + math.sin(a) * (r - 2),
            cx + math.cos(a) * (r - 9),
            cy + math.sin(a) * (r - 9),
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
    c.drawCentredString(cx, cy + 17, upper)
    c.drawCentredString(cx, cy - 24, lower)
    c.restoreState()


def draw_qr(c: canvas.Canvas, x: float, y: float, side: float, url: str) -> None:
    """``url`` as a QR code, drawn as vector squares on a white pad (no image, no extra
    library): sharp at any zoom and when printed. Used by the beneficiary certificate too."""
    matrix = segno.make(url, error="m").matrix
    n = len(matrix)
    cell = side / n
    c.saveState()
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(x - 4, y - 4, side + 8, side + 8, stroke=0, fill=1)
    c.setFillColor(_INK)
    for row_no, row in enumerate(matrix):
        for col_no, dark in enumerate(row):
            if dark:
                # a hair of overlap so no viewer shows seams between the squares
                c.rect(
                    x + col_no * cell,
                    y + side - (row_no + 1) * cell,
                    cell + 0.2,
                    cell + 0.2,
                    stroke=0,
                    fill=1,
                )
    c.restoreState()


def _draw_brand(c: canvas.Canvas, cx: float) -> None:
    """Centre the official Capimax PropShare logo in the header. Falls back to the vector
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
    verification_code: str,
    verify_url: str,
) -> bytes:
    """Draw the branded Capimax PropShare certificate (A4, classic styling). ``cert_ref`` is
    the certificate's number; its QR code opens ``verify_url``, where ``verification_code`` is
    checked."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_W, _H), pageCompression=0)
    c.setTitle("Capimax PropShare — Certificate of Ownership")

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
    _spaced_centred(c, _CX, 668, "Times-Bold", 31, "Certificate of Ownership", _TRACKING, _GREEN_D)
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
    ledger_line = "as recorded in the Capimax PropShare ownership ledger."
    if ownership == "-":  # a listing without a unit count has no share to state
        c.drawCentredString(_CX, 510, ledger_line)
    else:
        # how much of the property the units are (client, 2026-10-01): OWNERSHIP STAKE below
        c.drawCentredString(_CX, 511, f"representing {ownership} of the property,")
        c.drawCentredString(_CX, 494, ledger_line)

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
        ("CERTIFICATE NUMBER", cert_ref),
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

    # Signature (bottom-left), the QR code (centre) and the seal (bottom-right) share a band
    # well above the footer. The QR opens the certificate's verification page (client,
    # 2026-10-28, as on Capimax BRX).
    qr_side = 70.0
    qr_x, qr_y = _CX - qr_side / 2 + 8, 196.0
    draw_qr(c, qr_x, qr_y, qr_side, verify_url)
    c.linkURL(verify_url, (qr_x, qr_y, qr_x + qr_side, qr_y + qr_side), relative=0)
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 6.8)
    c.drawCentredString(qr_x + qr_side / 2, qr_y - 13, "SCAN TO VERIFY")
    _seal(c, 458, 232, 48)
    c.setStrokeColor(_INK)
    c.setLineWidth(0.8)
    c.line(92, 210, 250, 210)
    c.setFillColor(_GREEN_D)
    c.setFont("Times-Italic", 12)
    c.drawString(98, 216, "Capimax PropShare")
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(92, 196, "Authorized on behalf of the platform")

    # Footer — honest legal framing, word-wrapped so it never spills past the frame.
    c.setFillColor(_MUTED)
    c.setFont("Times-Roman", 8.5)
    footer_text = (
        "This certificate reflects the fractional units recorded in the Capimax PropShare "
        "ownership ledger on its issue date; scan its QR code to confirm it is authentic and "
        "still current. It is not a transferable security or a substitute for the offering "
        "documents and SPV agreements governing this property."
    )
    # NB: the title's letter-spacing stays in the PDF text state, so every later line is drawn
    # wider than stringWidth() says (~1.3x at this size): keep the wrap width well under the
    # ~500pt safe area.
    fy = 128
    for ln in _wrap(footer_text, "Times-Roman", 8.5, 270):
        c.drawCentredString(_CX, fy, ln)
        fy -= 12.5

    # The number, then where it is verified: the code and the page, written out for a printed
    # copy (and a link in the file). The title's letter-spacing (NB above) widens a line by its
    # length, so each line is placed by its drawn width to sit centred.
    def _centred_tracked(text: str, y: float, color: HexColor, size: float) -> tuple[float, float]:
        drawn = stringWidth(text, "Helvetica", size) + _TRACKING * (len(text) - 1)
        left = _CX - drawn / 2
        c.setFillColor(color)
        c.setFont("Helvetica", size)
        c.drawString(left, y, text)
        return left, drawn

    _centred_tracked(f"{cert_ref}   •   Verification code {verification_code}", 74, _GOLD, 7.2)
    shown = verify_url.split("://", 1)[-1]
    left, drawn = _centred_tracked(f"Verify at {shown}", 61, _GREEN_D, 7.2)
    c.linkURL(verify_url, (left, 57, left + drawn, 69), relative=0)

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


def ownership_pct(units: int, total_units: int) -> str:
    """A holder's share of the property as a percentage, precise enough that a small holding
    never reads 0.00%: two decimals from 1% up, else four significant figures (1 unit of
    42,000 is 0.002381%). "-" when the property has no unit count."""
    if total_units <= 0 or units <= 0:
        return "-"
    pct = decimal.Decimal(units) / decimal.Decimal(total_units) * 100
    step = decimal.Decimal("0.01") if pct >= 1 else decimal.Decimal(1).scaleb(pct.adjusted() - 3)
    return f"{format(pct.quantize(step).normalize(), 'f')}%"


# Certificate numbers: no 0/O or 1/I, so a number reads back over the phone.
_NUMBER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def verify_path(code: str) -> str:
    """The certificate's public verification page, on the site."""
    return f"/verify/{code}"


def verify_url(code: str) -> str:
    return get_settings().app_base_url.rstrip("/") + verify_path(code)


def _holder_name(user: User | None) -> str:
    """The name the certificate states. It is public (the verification page), so an account
    without a name is never named by its email address."""
    return ((user.full_name or "").strip() if user else "") or "Capimax PropShare investor"


def _holder_ref(user_id: uuid.UUID) -> str:
    """The holder's account, shown on the verification page without revealing it."""
    return "****" + user_id.hex[-6:].upper()


def _signature(c: InvestmentCertificate) -> str:
    """A keyed digest of what the certificate states: printed on the verification page, it
    changes if any value is altered, and cannot be made up without the platform's key."""
    payload = "|".join(
        str(v)
        for v in (
            c.number,
            c.verification_code,
            c.holder_name,
            c.holder_ref,
            c.property_id,
            c.property_title,
            c.units,
            c.ownership,
            c.unit_price,
            c.value,
            c.issued_at.isoformat(),
        )
    )
    key = ("investment-certificate|" + get_settings().jwt_secret).encode()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


async def _new_number(session: AsyncSession, year: int) -> str:
    for _ in range(5):
        number = f"PSC-{year}-" + "".join(secrets.choice(_NUMBER_ALPHABET) for _ in range(8))
        taken = await session.scalar(
            select(InvestmentCertificate.id).where(InvestmentCertificate.number == number)
        )
        if taken is None:
            return number
    raise AppError("NUMBER_UNAVAILABLE", "Please try again.", status_code=503)


async def _lock_holding(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> None:
    """One issuer at a time per holder and property (two downloads at once must not both
    issue): a transaction-scoped advisory lock."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"certificate:{user_id}:{property_id}")))
    )


async def _valid_certificate(
    session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID
) -> InvestmentCertificate | None:
    return (
        await session.execute(
            select(InvestmentCertificate)
            .where(
                InvestmentCertificate.user_id == user_id,
                InvestmentCertificate.property_id == property_id,
                InvestmentCertificate.status == "valid",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()


def _supersede(cert: InvestmentCertificate, now: dt.datetime, by: uuid.UUID | None = None) -> None:
    cert.status = "superseded"
    cert.superseded_at = now
    cert.superseded_by = by


async def issued_number(
    session: AsyncSession, *, user_id: uuid.UUID, property_id: uuid.UUID, units: int
) -> str | None:
    """The number of the valid certificate that still states ``units``, or None; issues
    nothing and locks nothing, for read-only answers (the holdings list)."""
    return await session.scalar(
        select(InvestmentCertificate.number).where(
            InvestmentCertificate.user_id == user_id,
            InvestmentCertificate.property_id == property_id,
            InvestmentCertificate.status == "valid",
            InvestmentCertificate.units == units,
        )
    )


async def current_certificate(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> InvestmentCertificate:
    """The holder's valid certificate for their CURRENT units in the property: the one already
    issued while it still states them, else a new one (the old one superseded by it).
    NO_HOLDING when they hold none."""
    now = now or dt.datetime.now(dt.UTC)
    await _lock_holding(session, user_id, property_id)
    units = await _net_units(session, user_id, property_id)
    current = await _valid_certificate(session, user_id, property_id)
    user = await session.get(User, user_id)
    holder = _holder_name(user)
    if units <= 0:
        # Nothing to certify. A certificate they had keeps its row as it is: its verification
        # page compares it with the ledger and shows it superseded (``verify``).
        raise AppError("NO_HOLDING", "You do not hold any units in this property.", status_code=404)
    if current is not None and current.units == units and current.holder_name == holder:
        return current
    prop = await session.get(Property, property_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)
    if current is not None:  # the old one goes first: one valid certificate at a time
        _supersede(current, now)
        await session.flush()
    unit_price = decimal.Decimal(str(prop.unit_price or 0)).quantize(decimal.Decimal("0.01"))
    cert = InvestmentCertificate(
        id=uuid.uuid4(),
        number=await _new_number(session, now.year),
        verification_code=secrets.token_urlsafe(16),
        user_id=user_id,
        property_id=property_id,
        status="valid",
        holder_name=holder,
        holder_ref=_holder_ref(user_id),
        property_title=prop.title,
        location=prop.location or None,
        # the listing's registered SPV; never a name made up from the title
        spv_name=(prop.spv_name or "").strip() or None,
        jurisdiction=prop.country or getattr(prop, "city", None) or prop.location or None,
        units=units,
        total_units=int(prop.total_units or 0) or None,
        ownership=ownership_pct(units, int(prop.total_units or 0)),
        unit_price=unit_price,
        value=(unit_price * units).quantize(decimal.Decimal("0.01")),
        signature="",
        issued_at=now,
    )
    cert.signature = _signature(cert)
    session.add(cert)
    await session.flush()
    # every earlier certificate of this holding left without a successor (superseded when it
    # was checked, or when the units ran out) now points at this one
    await session.execute(
        update(InvestmentCertificate)
        .where(
            InvestmentCertificate.user_id == user_id,
            InvestmentCertificate.property_id == property_id,
            InvestmentCertificate.status == "superseded",
            InvestmentCertificate.superseded_by.is_(None),
            InvestmentCertificate.id != cert.id,
        )
        .values(superseded_by=cert.id)
    )
    await write_audit(
        session,
        action="certificate.issued",
        entity_type="investment_certificate",
        entity_id=str(cert.id),
        actor_id=user_id,
        after={
            "number": cert.number,
            "property_id": str(property_id),
            "units": units,
            "supersedes": current.number if current is not None else None,
        },
    )
    return cert


async def certificates_for(
    session: AsyncSession, user_id: uuid.UUID, *, now: dt.datetime | None = None
) -> list[InvestmentCertificate]:
    """The holder's current certificate for every property they hold units in (issued now
    where needed), in property-title order."""
    # one lock per holding, always taken in the same order (two lists at once never deadlock)
    certs = [
        await current_certificate(session, user_id=user_id, property_id=pid, now=now)
        for pid in sorted(await _held_property_ids(session, user_id))
    ]
    return sorted(certs, key=lambda c: c.property_title.lower())


def certificate_dict(c: InvestmentCertificate) -> dict:
    """What the holder sees of their own certificate."""
    return {
        "id": c.id,
        "property_id": c.property_id,
        "number": c.number,
        "verification_code": c.verification_code,
        "verify_path": verify_path(c.verification_code),
        "verify_url": verify_url(c.verification_code),
        "units": c.units,
        "ownership": c.ownership,
        "spv_name": c.spv_name,
        "location": c.location,
        "status": c.status,
        "issued_at": c.issued_at,
    }


async def verify(session: AsyncSession, code: str, *, now: dt.datetime | None = None) -> dict:
    """What the public verification page shows for a certificate's code (no account needed).
    A valid certificate whose units no longer match the ledger is superseded here and then,
    so a paper the holder has outgrown never reads as valid. NOT_FOUND for an unknown code."""
    now = now or dt.datetime.now(dt.UTC)
    code = (code or "").strip()
    cert = None
    if 10 <= len(code) <= 64:
        cert = (
            await session.execute(
                select(InvestmentCertificate)
                .where(InvestmentCertificate.verification_code == code)
                .with_for_update()
            )
        ).scalar_one_or_none()
    if cert is None:
        raise AppError(
            "CERTIFICATE_NOT_FOUND",
            "No certificate matches this verification code.",
            status_code=404,
        )
    if cert.status == "valid":
        units = await _net_units(session, cert.user_id, cert.property_id)
        if units != cert.units:
            _supersede(cert, now)
            await write_audit(
                session,
                action="certificate.superseded",
                entity_type="investment_certificate",
                entity_id=str(cert.id),
                after={"number": cert.number, "reason": "units changed", "units_now": units},
            )
    cert.verification_count = (cert.verification_count or 0) + 1
    cert.last_verified_at = now
    return {
        "number": cert.number,
        "status": cert.status,
        "issued_at": cert.issued_at,
        "superseded_at": cert.superseded_at,
        "revoked_at": cert.revoked_at,
        "revocation_reason": cert.revocation_reason,
        "holder_name": cert.holder_name,
        "holder_ref": cert.holder_ref,
        "property_title": cert.property_title,
        "location": cert.location,
        "spv_name": cert.spv_name,
        "jurisdiction": cert.jurisdiction,
        "units": cert.units,
        "ownership": cert.ownership,
        "unit_price": str(cert.unit_price),
        "value": str(cert.value),
        "verification_code": cert.verification_code,
        "signature": cert.signature,
        "issuer": "Capimax PropShare",
        "verified_at": now,
    }


async def revoke(
    session: AsyncSession,
    *,
    certificate_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reason: str,
    now: dt.datetime | None = None,
) -> InvestmentCertificate:
    """The platform withdraws a certificate: its page shows it revoked, with the reason. The
    holding is untouched; the holder's next download is a new certificate."""
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise AppError("REASON_REQUIRED", "Say why the certificate is revoked.", status_code=422)
    cert = (
        await session.execute(
            select(InvestmentCertificate)
            .where(InvestmentCertificate.id == certificate_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if cert is None:
        raise AppError("NOT_FOUND", "Certificate not found.", status_code=404)
    if cert.status == "revoked":
        return cert
    before = cert.status
    cert.status = "revoked"
    cert.revoked_at = now or dt.datetime.now(dt.UTC)
    cert.revoked_by = actor_id
    cert.revocation_reason = reason[:300]
    await write_audit(
        session,
        action="certificate.revoked",
        entity_type="investment_certificate",
        entity_id=str(cert.id),
        actor_id=actor_id,
        before={"status": before},
        after={"status": "revoked", "reason": cert.revocation_reason},
    )
    return cert


def render_for(cert: InvestmentCertificate) -> bytes:
    """The PDF of a stored certificate: exactly what it stated when issued."""
    return render_certificate_pdf(
        holder=cert.holder_name,
        property_title=cert.property_title,
        location=cert.location or "-",
        units=cert.units,
        ownership=cert.ownership,
        value=f"${cert.value:,.2f}",
        spv=cert.spv_name or "-",
        jurisdiction=cert.jurisdiction or "-",
        cert_ref=cert.number,
        issued=cert.issued_at.strftime("%b %d, %Y"),
        verification_code=cert.verification_code,
        verify_url=verify_url(cert.verification_code),
    )


async def build_for_holding(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> tuple[str, bytes]:
    """Return (filename, pdf_bytes) for the caller's net holding; 404 if they hold none.

    All values are REAL: units from the ledger; ownership %, value, SPV reference and
    jurisdiction from the property record, as stored on the certificate when it was issued
    (``current_certificate``)."""
    cert = await current_certificate(session, user_id=user_id, property_id=property_id, now=now)
    prop = await session.get(Property, property_id)
    slug = (prop.slug if prop else None) or str(property_id)
    return f"certificate-{slug}.pdf", render_for(cert)


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
            fname, pdf = await build_for_holding(session, user_id=user_id, property_id=pid, now=now)
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
