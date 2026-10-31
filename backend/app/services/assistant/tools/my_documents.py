"""The signed-in user's own documents, handed over inside the chat.

Client (2026-10-01 meeting): asked for "the certificate of property X" or "my installment
schedule as a PDF", the assistant sent people to a page and said it could not make the file.
These tools find the right holding or plan and the server turns the result into a document
card whose buttons download the files straight away, through the platform's own owner-only
endpoints (the same files the dashboard gives):

  * ``get_my_certificates``         the ownership certificate of each property held (PDF), all
    of them in one ZIP, the share of the property, its number and the page its QR code opens;
  * ``get_my_installment_schedules`` each installment plan's schedule (PDF and Excel) with what
    is paid, what is left and the next payment.

Nothing is generated here: the card only points at the endpoints, which check ownership again.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Property
from app.services import (
    certificate_service,
    installment_service,
    secondary_service,
    verification_partners,
)
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.base import ToolOutput, ToolSpec, register

MAX_ITEMS = 5


def _now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def _matching(query: str | None, rows: list[dict], *, what: str) -> list[dict]:
    """The rows the user means: all of them without a query; else an exact id or slug, else
    every row whose title has all the query's words. Nothing matching is an error naming what
    they do have."""
    if not rows:
        raise AppError("NOTHING_HELD", f"You have no {what} yet.", status_code=404)
    if not query or not query.strip():
        return rows
    q = query.strip().lower()
    exact = [r for r in rows if q in (str(r["id"]).lower(), (r.get("slug") or "").lower())]
    if exact:
        return exact
    words = [w for w in re.split(r"[^\w]+", q) if w]
    hits = [r for r in rows if words and all(w in (r.get("title") or "").lower() for w in words)]
    if hits:
        return hits
    titles = ", ".join(sorted({str(r.get("title")) for r in rows}))
    raise AppError(
        "NOT_FOUND", f"No {what} matches '{query}'. You have: {titles}.", status_code=404
    )


class MyDocumentsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property: str | None = Field(
        default=None,
        max_length=160,
        description="The property's name, slug or id; empty = all of the user's",
    )


# --------------------------------------------------------------------------- #
# get_my_certificates
# --------------------------------------------------------------------------- #
class CertificateItem(ToolOutput):
    property_id: str
    property_title: str | None
    property_slug: str | None
    units: int
    ownership_pct: str  # the share of the whole property, e.g. "0.04762%"
    certificate_number: str  # printed on the PDF
    verification_code: str  # printed beside the QR code
    verify_path: str  # the certificate's verification page (what its QR code opens)
    issued_at: str


class CertificatesOut(ToolOutput):
    items: list[CertificateItem]
    holdings: int  # how many properties the user holds in all
    verify_path: str  # where anyone enters a verification code (the Verification Center)
    note: str
    as_of: str


async def _get_my_certificates(session, ctx: AgentContext, args) -> dict:
    a: MyDocumentsIn = args
    assert ctx.user_id is not None  # read_own: guard.authorize refuses visitors
    holdings = await secondary_service.my_holdings(session, ctx.user_id)
    ids = [uuid.UUID(h["property_id"]) for h in holdings]
    props = {
        p.id: p
        for p in (await session.execute(select(Property).where(Property.id.in_(ids or [None]))))
        .scalars()
        .all()
    }
    rows = []
    for h in holdings:
        prop = props.get(uuid.UUID(h["property_id"]))
        rows.append(
            {
                "id": h["property_id"],
                "slug": prop.slug if prop else None,
                "title": h["title"],
                "units": h["units"],
                "total_units": int(prop.total_units or 0) if prop else 0,
            }
        )
    picked = _matching(a.property, rows, what="holding")
    items = []
    for r in picked[:MAX_ITEMS]:
        # the certificate stating the units now (issued when they changed), in a short
        # transaction of its own: the chat's session stays open until the reply ends, and the
        # certificate's locks must not be held that long (its public page waits on them)
        async with AsyncSession(session.bind, expire_on_commit=False) as own, own.begin():
            cert = await certificate_service.current_certificate(
                own, user_id=ctx.user_id, property_id=uuid.UUID(r["id"])
            )
        items.append(
            {
                "property_id": r["id"],
                "property_title": r["title"],
                "property_slug": r["slug"],
                "units": cert.units,
                "ownership_pct": cert.ownership,
                "certificate_number": cert.number,
                "verification_code": cert.verification_code,
                "verify_path": certificate_service.verify_path(cert.verification_code),
                "issued_at": cert.issued_at.date().isoformat(),
            }
        )
    return {
        "items": items,
        "holdings": len(rows),
        "verify_path": verification_partners.CERTIFICATES.url,
        "note": (
            "The card below downloads each certificate (PDF) and, with more than one holding, "
            "all of them in one ZIP. Each certificate carries a QR code that opens its own "
            "verification page on Capimax PropShare (verify_path): anyone holding the paper "
            "scans it to see that it is authentic and current. Without a camera, the "
            "verification_code is entered on the Verification Center. A certificate states the "
            "units held when it was issued; when they change, the next one states the new count "
            "and the old one shows as superseded."
        ),
        "as_of": _now(),
    }


register(
    ToolSpec(
        "get_my_certificates",
        "The signed-in user's ownership certificates: for one property (by name) or all they "
        "hold, with the units, the share of the property and the certificate number. The user "
        "gets a card that downloads the PDF certificate(s) right away, so use this whenever "
        "they ask for a certificate instead of sending them to a page.",
        MyDocumentsIn,
        CertificatesOut,
        "read_own",
        _get_my_certificates,
    )
)


# --------------------------------------------------------------------------- #
# get_my_installment_schedules
# --------------------------------------------------------------------------- #
class SchedulePlan(ToolOutput):
    plan_id: str
    property_title: str | None
    property_slug: str | None
    status: str
    units_total: int
    vested_units: int
    duration_months: int
    total_amount: str  # every payment of the plan with its fee
    paid_amount: str
    remaining_amount: str
    payments_left: int
    next_due_date: str | None
    next_due_amount: str | None


class SchedulesOut(ToolOutput):
    items: list[SchedulePlan]
    plans: int  # how many plans the user has in all
    note: str
    as_of: str


def _money(value: decimal.Decimal) -> str:
    return f"{value.quantize(decimal.Decimal('0.01')):f}"


async def _get_my_installment_schedules(session, ctx: AgentContext, args) -> dict:
    a: MyDocumentsIn = args
    assert ctx.user_id is not None
    plans = await installment_service.list_plans(session, ctx.user_id)
    # a plan that is running comes before one that is finished or was never started
    order = {"active": 0, "completed": 1}
    plans.sort(key=lambda p: order.get(str(p["status"]), 2))
    rows = [
        {**p, "id": str(p["id"]), "slug": p.get("property_slug"), "title": p.get("property_title")}
        for p in plans
    ]
    picked = _matching(a.property, rows, what="installment plan")
    items = []
    for p in picked[:MAX_ITEMS]:
        pays = p["payments"]
        total = sum((decimal.Decimal(str(x["total_amount"])) for x in pays), decimal.Decimal(0))
        paid = sum(
            (decimal.Decimal(str(x["total_amount"])) for x in pays if x["status"] == "paid"),
            decimal.Decimal(0),
        )
        unpaid = sorted((x for x in pays if x["status"] != "paid"), key=lambda x: x["due_date"])
        items.append(
            {
                "plan_id": p["id"],
                "property_title": p.get("property_title"),
                "property_slug": p.get("property_slug"),
                "status": str(p["status"]),
                "units_total": p["units_total"],
                "vested_units": p["vested_units"],
                "duration_months": p["duration_months"],
                "total_amount": _money(total),
                "paid_amount": _money(paid),
                "remaining_amount": _money(total - paid),
                "payments_left": len(unpaid),
                "next_due_date": unpaid[0]["due_date"].isoformat() if unpaid else None,
                "next_due_amount": str(unpaid[0]["total_amount"]) if unpaid else None,
            }
        )
    return {
        "items": items,
        "plans": len(rows),
        "note": (
            "The card below downloads each plan's full schedule as a PDF or an Excel file "
            "(every payment with its due date, fee and status). Summarise the plan in a "
            "sentence or two; do not retype the whole schedule. To pay the next installment "
            "now, use prepare_installment_payment."
        ),
        "as_of": _now(),
    }


register(
    ToolSpec(
        "get_my_installment_schedules",
        "The signed-in user's installment schedules: for one property (by name) or all their "
        "plans, with what is paid, what is left and the next payment. The user gets a card "
        "that downloads each schedule as PDF or Excel right away, so use this whenever they "
        "ask for their schedule or a copy of it instead of sending them to a page.",
        MyDocumentsIn,
        SchedulesOut,
        "read_own",
        _get_my_installment_schedules,
    )
)
