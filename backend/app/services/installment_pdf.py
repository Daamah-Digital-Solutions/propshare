"""Branded installment-schedule PDF (Task 6).

A REAL, elegantly branded PDF of an investor's installment plan — the official CapiMax
PropShare design (green/gold classic frame, the platform logo in the header, a serif hand),
matching the certificate's visual language. It carries the full plan details the client asked
for: the property under installment, the plan summary (contract value, down payment, duration,
fee, totals paid/remaining, next due, status) and the complete payment schedule (per-payment
base / fee / total / due date / status), paginated across pages when a plan has many months.

All brand primitives (logo header, frame corners, dividers, palette, text helpers) are reused
verbatim from ``certificate_service`` so there is a single source of design truth.
"""

from __future__ import annotations

import io

from reportlab.lib.colors import Color, HexColor
from reportlab.pdfgen import canvas

from app.services.certificate_service import (
    _CREAM,
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
    _corner,
    _divider,
    _draw_brand,
    _fit_centred,
    _spaced_centred,
    _wrap,
)

_RED = HexColor("#B23A2E")  # overdue

_BOTTOM = 108.0  # rows stop here; a further row spills to a new page
_ROW_H = 16.0

# Table column geometry (A4, inner frame ~56..539). BASE/FEE/TOTAL are right-aligned money
# columns; STATUS is right-aligned at the far edge with a wide gap so "SCHEDULED" never collides
# with the total.
_C_PAY = 62.0  # "Payment" label, left-aligned
_C_DUE = 176.0  # due date, left-aligned
_C_BASE = 320.0  # base amount, right-aligned
_C_FEE = 382.0  # fee, right-aligned
_C_TOTAL = 450.0  # total, right-aligned
_C_STATUS = 536.0  # status, right-aligned


def _page_frame(c: canvas.Canvas) -> None:
    """Cream ground, faint monogram watermark, green/gold double border + corner flourishes."""
    c.setFillColor(_CREAM)
    c.rect(0, 0, _W, _H, stroke=0, fill=1)
    c.saveState()
    c.setFillColor(Color(0.06, 0.43, 0.30, alpha=0.04))
    c.setFont("Times-Bold", 340)
    c.drawCentredString(_CX, 250, "C")
    c.restoreState()
    c.setStrokeColor(_GREEN_D)
    c.setLineWidth(3.0)
    c.roundRect(30, 30, _W - 60, _H - 60, 9, stroke=1, fill=0)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(1.0)
    c.rect(40, 40, _W - 80, _H - 80, stroke=1, fill=0)
    _corner(c, 44, _H - 44, 1, -1)
    _corner(c, _W - 44, _H - 44, -1, -1)
    _corner(c, 44, 44, 1, 1)
    _corner(c, _W - 44, 44, -1, 1)


def _footer(c: canvas.Canvas, plan_ref: str) -> None:
    c.setFillColor(_MUTED)
    c.setFont("Times-Roman", 8.5)
    note = (
        "This schedule reflects the installment plan recorded in the CapiMax PropShare ledger as "
        "of the issue date. It is generated from live data. Ownership vests progressively with "
        "each paid installment; rental income begins at handover (final payment)."
    )
    fy = 96
    for ln in _wrap(note, "Times-Roman", 8.5, 300):
        c.drawCentredString(_CX, fy, ln)
        fy -= 12
    c.setFillColor(_GOLD)
    c.setFont("Helvetica", 8)
    c.drawCentredString(_CX, 62, f"{plan_ref}   •   capimaxpropshare.com")


def _status_color(status: str) -> HexColor:
    s = status.lower()
    if s == "paid":
        return _GREEN
    if s == "overdue":
        return _RED
    return _MUTED


def _table_header(c: canvas.Canvas, y: float) -> float:
    c.setFillColor(_MUTED)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(_C_PAY, y, "PAYMENT")
    c.drawString(_C_DUE, y, "DUE DATE")
    c.drawRightString(_C_BASE, y, "BASE")
    c.drawRightString(_C_FEE, y, "FEE")
    c.drawRightString(_C_TOTAL, y, "TOTAL")
    c.drawRightString(_C_STATUS, y, "STATUS")
    c.setStrokeColor(_GOLD)
    c.setLineWidth(0.8)
    c.line(_C_PAY, y - 6, _C_STATUS, y - 6)
    return y - 20


def _table_row(c: canvas.Canvas, y: float, row: dict, zebra: bool) -> None:
    if zebra:
        c.setFillColor(_PANEL)
        c.rect(_C_PAY - 6, y - 5, _C_STATUS - _C_PAY + 12, _ROW_H, stroke=0, fill=1)
    c.setFillColor(_INK)
    c.setFont("Times-Roman", 9)
    c.drawString(_C_PAY, y, _clip(str(row["label"]), "Times-Roman", 9, _C_DUE - _C_PAY - 8))
    c.setFillColor(_MUTED)
    c.drawString(_C_DUE, y, str(row["due"]))
    c.setFillColor(_INK)
    c.drawRightString(_C_BASE, y, str(row["base"]))
    c.drawRightString(_C_FEE, y, str(row["fee"]))
    c.setFont("Times-Bold", 9)
    c.drawRightString(_C_TOTAL, y, str(row["total"]))
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(_status_color(str(row["status"])))
    c.drawRightString(_C_STATUS, y, str(row["status"]).upper())


def render_schedule_pdf(
    *,
    holder: str,
    property_title: str,
    location: str,
    spv: str,
    status: str,
    units_total: int,
    vested_units: int,
    unit_price: str,
    down_payment_pct: int,
    duration_months: int,
    fee_rate: str,
    contract_value: str,
    total_fees: str,
    grand_total: str,
    total_paid: str,
    remaining_balance: str,
    next_due: str,
    plan_ref: str,
    issued: str,
    rows: list[dict],
) -> bytes:
    """Render the branded installment-schedule PDF and return its bytes.

    Every value is passed in already computed/formatted by the service (server-authoritative);
    this function only lays out the page. Content stream is left uncompressed so the real
    figures appear literally in the bytes (verifiable in tests)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_W, _H), pageCompression=0)
    c.setTitle("CapiMax PropShare — Installment Schedule")

    _page_frame(c)

    # Header — official logo (vector fallback), divider, title, subtitle.
    _draw_brand(c, _CX)
    _divider(c, _CX, 712, 150)
    _spaced_centred(c, _CX, 676, "Times-Bold", 27, "Installment Schedule", 1.0, _GREEN_D)
    c.setFillColor(_MUTED)
    c.setFont("Times-Italic", 11.5)
    c.drawCentredString(_CX, 658, "Progressive-Ownership Payment Plan")

    # Property + holder line.
    _fit_centred(c, _CX, 628, "Times-Bold", 16, property_title, 440, _GREEN)
    c.setFillColor(_INK)
    c.setFont("Times-Roman", 11)
    loc = " • ".join([p for p in (location, spv) if p and p != "-"])
    if loc:
        c.drawCentredString(_CX, 610, loc)
    c.setFillColor(_MUTED)
    c.setFont("Times-Italic", 10.5)
    c.drawCentredString(_CX, 594, f"Plan holder: {holder}")

    # Summary panel — 3 columns x 4 rows of plan facts.
    px, pw = 56.0, _W - 112.0
    ph = 150.0
    py = 424.0
    c.setFillColor(_PANEL)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(0.8)
    c.roundRect(px, py, pw, ph, 6, stroke=1, fill=1)
    fields = [
        ("UNITS", f"{vested_units} / {units_total} vested"),
        ("UNIT PRICE", unit_price),
        ("CONTRACT VALUE", contract_value),
        ("DOWN PAYMENT", f"{down_payment_pct}%"),
        ("DURATION", f"{duration_months} months"),
        ("INSTALLMENT FEE", f"{fee_rate}% / payment"),
        ("TOTAL FEES", total_fees),
        ("GRAND TOTAL", grand_total),
        ("PAID TO DATE", total_paid),
        ("REMAINING", remaining_balance),
        ("NEXT PAYMENT", next_due),
        ("STATUS", "Completed — handover" if status == "completed" else "Active"),
    ]
    col_w = pw / 3
    for i, (label, val) in enumerate(fields):
        col, rrow = i % 3, i // 3
        x = px + 18 + col * col_w
        y = py + ph - 26 - rrow * 32
        c.setFillColor(_MUTED)
        c.setFont("Helvetica", 6.8)
        c.drawString(x, y, label)
        c.setFillColor(_GREEN_D if label in ("GRAND TOTAL", "REMAINING") else _INK)
        c.setFont("Times-Bold" if label in ("GRAND TOTAL", "REMAINING") else "Times-Roman", 10.5)
        c.drawString(x, y - 15, _clip(str(val), "Times-Roman", 10.5, col_w - 24))

    # Payment schedule table (paginates when a long plan overruns the page).
    y = py - 26
    c.setFillColor(_GREEN_D)
    c.setFont("Times-Bold", 12)
    c.drawString(_C_PAY, y, "Payment Schedule")
    y -= 22
    y = _table_header(c, y)
    for i, row in enumerate(rows):
        if y < _BOTTOM:
            _footer(c, plan_ref)
            c.showPage()
            _page_frame(c)
            _spaced_centred(
                c, _CX, 780, "Times-Bold", 15, "Payment Schedule (continued)", 1.0, _GREEN_D
            )
            y = _table_header(c, 748)
        _table_row(c, y, row, zebra=(i % 2 == 1))
        y -= _ROW_H

    c.setFillColor(_MUTED)
    c.setFont("Times-Italic", 8.5)
    c.drawString(_C_PAY, y - 4, f"Issued {issued}")

    _footer(c, plan_ref)
    c.showPage()
    c.save()
    return buf.getvalue()
