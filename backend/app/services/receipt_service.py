"""A numbered PDF receipt for one wallet movement (owner brief, 2026-10-20): every row of the
wallet ledger (a deposit, a withdrawal's debit, its refund when it was not sent, a return...)
can be downloaded as a receipt, by its owner only. The number is the movement's own
(``RCT-`` and ten characters of its id), so the same movement always gives the same receipt.
Laid out like the account statement."""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import io
import uuid

from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Transaction, Withdrawal
from app.models.identity import User
from app.services.certificate_service import (
    _CX,
    _GOLD,
    _GREEN,
    _GREEN_D,
    _H,
    _INK,
    _MUTED,
    _PANEL,
    _W,
    _clip,
    _divider,
    _draw_brand,
    _fit_centred,
    _wrap,
)
from app.services.certificate_service import _spaced_centred as _spaced_centred_raw
from app.services.installment_pdf import _RED, _page_frame
from app.services.statement_service import STATUS_LABELS, TYPE_LABELS, english


@dataclasses.dataclass(frozen=True)
class Receipt:
    number: str
    at: dt.datetime
    holder: str
    email: str
    type_label: str
    description: str
    status: str
    amount: decimal.Decimal
    request: str | None  # e.g. the withdrawal's WD- number
    destination: str | None
    transfer_reference: str | None
    issued_at: dt.datetime


def receipt_number(transaction_id: uuid.UUID) -> str:
    return "RCT-" + transaction_id.hex[:10].upper()


async def build_receipt(
    session: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> Receipt:
    tx = await session.get(Transaction, transaction_id)
    if tx is None or tx.user_id != user_id:  # another member's movement does not exist here
        raise AppError("NOT_FOUND", "Movement not found.", status_code=404)
    user = await session.get(User, user_id)
    kind = getattr(tx.type, "value", tx.type)
    wd = None
    if kind == "withdrawal" and tx.reference_id:
        wd = (
            await session.execute(select(Withdrawal).where(Withdrawal.id == tx.reference_id))
        ).scalar_one_or_none()
    return Receipt(
        number=receipt_number(tx.id),
        at=tx.created_at,
        holder=(english(user.full_name) if user else None) or (user.email if user else ""),
        email=user.email if user else "",
        type_label=TYPE_LABELS.get(kind, str(kind).replace("_", " ").capitalize()),
        description=english(tx.description) or "-",
        status=STATUS_LABELS.get(tx.status, str(tx.status).capitalize()),
        amount=decimal.Decimal(tx.amount).quantize(decimal.Decimal("0.01")),
        request=wd.reference if wd else None,
        destination=english(wd.destination_label) if wd else None,
        transfer_reference=(
            wd.transfer_reference if wd and wd.status == "completed" and tx.amount < 0 else None
        ),
        issued_at=dt.datetime.now(dt.UTC),
    )


def filename(r: Receipt) -> str:
    return f"capimax-receipt-{r.number}.pdf"


def _spaced_centred(c: canvas.Canvas, *args) -> None:
    c.saveState()
    _spaced_centred_raw(c, *args)
    c.restoreState()


def _when(t: dt.datetime) -> str:
    return f"{t:%d %b %Y, %H:%M} UTC"


def render_pdf(r: Receipt) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_W, _H), pageCompression=0)
    c.setTitle(f"Capimax PropShare — Receipt {r.number}")
    _page_frame(c)
    _draw_brand(c, _CX)
    _divider(c, _CX, 712, 150)
    _spaced_centred(c, _CX, 676, "Times-Bold", 27, "Receipt", 1.0, _GREEN_D)
    c.setFillColor(_MUTED)
    c.setFont("Times-Italic", 11.5)
    c.drawCentredString(_CX, 658, r.number)
    _fit_centred(c, _CX, 630, "Times-Bold", 15, r.holder, 440, _GREEN)
    c.setFillColor(_INK)
    c.setFont("Times-Roman", 10.5)
    c.drawCentredString(_CX, 613, r.email)

    # the amount, large
    sign = "+" if r.amount >= 0 else "-"
    c.setFillColor(_GREEN if r.amount >= 0 else _RED)
    c.setFont("Times-Bold", 30)
    c.drawCentredString(_CX, 560, f"{sign}{abs(r.amount):,.2f} USD")
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(
        _CX, 544, "MONEY INTO THE WALLET" if r.amount >= 0 else "MONEY OUT OF THE WALLET"
    )

    rows = [
        ("Receipt number", r.number),
        ("Date", _when(r.at)),
        ("Movement", r.type_label),
        ("Description", r.description),
        ("Status", r.status),
    ]
    if r.request:
        rows.append(("Withdrawal request", r.request))
    if r.destination:
        rows.append(("Paid to", r.destination))
    if r.transfer_reference:
        rows.append(("Transfer reference", r.transfer_reference))
    px, pw = 76.0, _W - 152.0
    row_h = 30.0
    top = 510.0
    ph = row_h * len(rows) + 16
    c.setFillColor(_PANEL)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(0.8)
    c.roundRect(px, top - ph, pw, ph, 6, stroke=1, fill=1)
    y = top - 26
    for label, value in rows:
        c.setFillColor(_MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(px + 20, y + 2, label.upper())
        c.setFillColor(_INK)
        c.setFont("Times-Roman", 11)
        c.drawRightString(px + pw - 20, y, _clip(value, "Times-Roman", 11, pw - 190))
        y -= row_h

    c.setFillColor(_MUTED)
    c.setFont("Times-Roman", 8.5)
    note = (
        "Issued from the Capimax PropShare wallet ledger for this one movement. Times are UTC. "
        "This receipt is informational and is not a tax document."
    )
    fy = 96
    for ln in _wrap(note, "Times-Roman", 8.5, 400):
        c.drawCentredString(_CX, fy, ln)
        fy -= 11
    c.setFillColor(_GOLD)
    c.setFont("Helvetica", 8)
    c.drawCentredString(
        _CX, 62, f"{r.number}   •   issued {_when(r.issued_at)}   •   capimaxpropshare.com"
    )
    c.showPage()
    c.save()
    return buf.getvalue()
