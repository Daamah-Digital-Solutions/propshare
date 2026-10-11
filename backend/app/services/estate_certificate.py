"""The beneficiary's certificate: one branded A4 page stating that an account holder designated
a person (heir, beneficiary, authorized person or legal representative), with that person's
details as recorded and where a claim is made.

Client (2026-10-07): the person who comes to claim after the holder's death "has nothing to
show"; with this they bring "the certificate with my name and details, and a copy of my ID".

It belongs to the same family as the ownership certificate (``certificate_service``): same
frame, logo, palette and seal. It is a record of a designation, not of ownership, and says so:
the holder may change the register afterwards, so the certificate carries the record's version
and the footer states that the register at the time of a claim prevails.

Set in the PDF's standard Latin fonts, like the ownership certificate and the statements: the
caller passes text that is already printable (``statement_service.english``).
"""

from __future__ import annotations

import io

import segno
from reportlab.lib.colors import Color, HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.services import certificate_service as base

_W, _H, _CX = base._W, base._H, base._CX
_FRAME = 44.0  # the inner border: nothing is drawn outside it


def _plain_spacing(c: canvas.Canvas) -> None:
    """Letter-spacing set for a spaced title stays in the PDF text state and widens every
    later line beyond what ``stringWidth`` reports: put it back to none."""
    t = c.beginText(0, 0)
    t.setCharSpace(0)
    c.drawText(t)


def _fit_left(
    c: canvas.Canvas,
    x: float,
    y: float,
    font: str,
    size: float,
    text: str,
    max_width: float,
    color: HexColor,
) -> None:
    """A left-aligned value that shrinks before it wraps, and wraps onto a second line before
    it is ever cut: a long address or list stays whole."""
    while size > 8 and stringWidth(text, font, size) > max_width:
        size -= 0.5
    c.setFillColor(color)
    c.setFont(font, size)
    if stringWidth(text, font, size) <= max_width:
        c.drawString(x, y, text)
        return
    first, rest = _two_lines(text, font, size, max_width)
    c.drawString(x, y + 3, first)
    c.drawString(x, y - 6.5, base._clip(rest, font, size, max_width))


def _two_lines(text: str, font: str, size: float, max_width: float) -> tuple[str, str]:
    """``text`` cut after the last word that fits on a first line of ``max_width``; a single
    long word (an email address) is cut where the line ends."""
    words = text.split()
    first = ""
    for i, word in enumerate(words):
        trial = f"{first} {word}".strip()
        if stringWidth(trial, font, size) > max_width:
            if first:
                return first, " ".join(words[i:])
            break
        first = trial
    cut = len(text)
    while cut > 1 and stringWidth(text[:cut], font, size) > max_width:
        cut -= 1
    return text[:cut], text[cut:].strip()


def _qr(c: canvas.Canvas, x: float, y: float, side: float, url: str) -> None:
    """The claim page as a QR code, drawn as vector squares (no image, no extra library)."""
    matrix = segno.make(url, error="m").matrix
    n = len(matrix)
    cell = side / n
    c.saveState()
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(x - 4, y - 4, side + 8, side + 8, stroke=0, fill=1)
    c.setFillColor(base._INK)
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


def render(
    *,
    beneficiary: str,
    holder: str,
    role: str,
    designation: str,
    relationship: str,
    id_type: str,
    id_number: str,
    allocation: str,
    coverage: str,
    condition: str,
    email: str,
    certificate_no: str,
    issued: str,
    version: int,
    claim_url: str,
) -> bytes:
    """Draw the certificate. ``designation`` is the sentence part after the holder's name
    ("as heir to 40% of the holder's assets on Capimax PropShare,")."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_W, _H), pageCompression=0)
    c.setTitle("Capimax PropShare — Certificate of Designation")

    # Ground, watermark, frame: the ownership certificate's own.
    c.setFillColor(base._CREAM)
    c.rect(0, 0, _W, _H, stroke=0, fill=1)
    c.saveState()
    c.setFillColor(Color(0.06, 0.43, 0.30, alpha=0.045))
    c.setFont("Times-Bold", 380)
    c.drawCentredString(_CX, 250, "C")
    c.restoreState()
    c.setStrokeColor(base._GREEN_D)
    c.setLineWidth(3.5)
    c.roundRect(30, 30, _W - 60, _H - 60, 9, stroke=1, fill=0)
    c.setStrokeColor(base._GOLD)
    c.setLineWidth(1.0)
    c.rect(40, 40, _W - 80, _H - 80, stroke=1, fill=0)
    c.setStrokeColor(base._GREEN)
    c.setLineWidth(0.6)
    c.rect(_FRAME, _FRAME, _W - 2 * _FRAME, _H - 2 * _FRAME, stroke=1, fill=0)
    base._corner(c, _FRAME, _H - _FRAME, 1, -1)
    base._corner(c, _W - _FRAME, _H - _FRAME, -1, -1)
    base._corner(c, _FRAME, _FRAME, 1, 1)
    base._corner(c, _W - _FRAME, _FRAME, -1, 1)

    base._draw_brand(c, _CX)
    _plain_spacing(c)
    base._divider(c, _CX, 712, 150)

    base._spaced_centred(
        c, _CX, 670, "Times-Bold", 30, "Certificate of Designation", 1.2, base._GREEN_D
    )
    _plain_spacing(c)
    c.setFillColor(base._MUTED)
    c.setFont("Times-Italic", 12)
    c.drawCentredString(_CX, 650, f"{role}  -  Capimax PropShare Beneficiary Register")

    # The statement.
    c.setFillColor(base._INK)
    c.setFont("Times-Roman", 12)
    c.drawCentredString(_CX, 616, "This is to certify that")
    base._fit_centred(c, _CX, 588, "Times-Bold", 22, beneficiary, 420, base._GREEN_D)
    c.setStrokeColor(base._GOLD_L)
    c.setLineWidth(0.8)
    c.line(_CX - 150, 580, _CX + 150, 580)
    c.setFillColor(base._INK)
    c.setFont("Times-Roman", 12)
    c.drawCentredString(_CX, 558, "has been designated by the account holder")
    base._fit_centred(c, _CX, 537, "Times-Bold", 14, holder, 430, base._GREEN)
    base._fit_centred(c, _CX, 517, "Times-Roman", 12, designation, 440, base._INK)
    c.setFillColor(base._INK)
    c.setFont("Times-Roman", 12)
    c.drawCentredString(_CX, 501, "as recorded in the Capimax PropShare beneficiary register.")

    # The person's details as recorded (2 columns x 5 rows).
    px, pw = 82.0, _W - 164.0
    rows, pitch = 5, 32.0
    ph = rows * pitch + 18
    py = 484 - ph
    c.setFillColor(base._PANEL)
    c.setStrokeColor(base._GOLD)
    c.setLineWidth(0.8)
    c.roundRect(px, py, pw, ph, 6, stroke=1, fill=1)
    fields = [
        ("RELATIONSHIP TO THE HOLDER", relationship),
        ("DESIGNATED AS", role),
        ("IDENTITY DOCUMENT", id_type),
        ("DOCUMENT NUMBER", id_number),
        ("ALLOCATION", allocation),
        ("COVERAGE RECORDED", coverage),
        ("TRANSFER CONDITION", condition),
        ("EMAIL ON RECORD", email),
        ("CERTIFICATE NUMBER", certificate_no),
        ("ISSUED", f"{issued}  -  Version {version}"),
    ]
    col_w = pw / 2 - 12
    for i, (label, value) in enumerate(fields):
        col, row = i % 2, i // 2
        x = px + 26 + col * col_w
        y = py + ph - 24 - row * pitch
        c.setFillColor(base._MUTED)
        c.setFont("Helvetica", 7)
        c.drawString(x, y, label)
        _fit_left(c, x, y - 14, "Times-Roman", 12, value or "-", col_w - 30, base._INK)

    # How a claim is made, with the page as a QR code.
    by, bh = py - 10 - 82, 82.0
    c.setFillColor(HexColor("#FFFDF6"))
    c.setStrokeColor(base._GOLD_L)
    c.setLineWidth(0.8)
    c.roundRect(px, by, pw, bh, 6, stroke=1, fill=1)
    qr_side = 58.0
    _qr(c, px + pw - qr_side - 16, by + (bh - qr_side) / 2, qr_side, claim_url)
    c.setFillColor(base._GREEN_D)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(px + 18, by + bh - 18, "HOW A CLAIM IS MADE")
    how = (
        "The person named above presents this certificate together with their own identity "
        "document at capimaxpropshare.com/estate-claim. After verification, the assets "
        "allocated to them are transferred to their own Capimax PropShare account. The "
        "holder's account, password and records are never handed over."
    )
    c.setFillColor(base._INK)
    c.setFont("Times-Roman", 9.5)
    ty = by + bh - 32
    for line in base._wrap(how, "Times-Roman", 9.5, pw - qr_side - 58):
        c.drawString(px + 18, ty, line)
        ty -= 11.5

    # Signature (left) and seal (right).
    c.setStrokeColor(base._INK)
    c.setLineWidth(0.8)
    c.line(92, 152, 250, 152)
    c.setFillColor(base._GREEN_D)
    c.setFont("Times-Italic", 12)
    c.drawString(98, 158, "Capimax PropShare")
    c.setFillColor(base._MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(92, 139, "Issued from the platform's beneficiary register")
    base._seal(c, 458, 152, 48, upper="DESIGNATION", lower="RECORDED")

    # What this certificate is, and is not.
    c.setFillColor(base._MUTED)
    c.setFont("Times-Roman", 8)
    footer = (
        "This certificate records a designation made by the account holder in the Capimax "
        "PropShare beneficiary register, as it stood on the issue date. The holder may change "
        "or withdraw it at any time: the register at the time of a claim prevails. It is not "
        "a will, not a transferable instrument and not evidence of ownership. Any transfer is "
        "made only after Capimax PropShare has verified a claim, and is subject to the "
        "platform's terms and to applicable law."
    )
    fy = 122.0
    for line in base._wrap(footer, "Times-Roman", 8, 305):
        c.drawString(92, fy, line)
        fy -= 10
    c.setFillColor(base._GOLD)
    c.setFont("Helvetica", 8)
    c.drawCentredString(_CX, 56, f"{certificate_no}   -   capimaxpropshare.com/estate-claim")
    link_w = stringWidth(
        f"{certificate_no}   -   capimaxpropshare.com/estate-claim", "Helvetica", 8
    )
    c.linkURL(claim_url, (_CX - link_w / 2, 52, _CX + link_w / 2, 64), relative=0)

    c.showPage()
    c.save()
    return buf.getvalue()
