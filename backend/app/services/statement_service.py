"""Account statements: every wallet movement of one user over a period they choose, as a
branded PDF or an Excel workbook.

Balances are anchored to the wallet balance the user sees today and walked back through the
signed ledger (``transactions.amount``):

    closing balance = wallet balance now - SUM(amount) of rows after the period
    opening balance = closing balance    - SUM(amount) of rows inside the period

and every row carries the running balance. With the wallet invariant ``balance ==
SUM(ledger)`` (checked nightly by reconciliation) this equals summing the ledger from the
start; if an account ever broke the invariant (a balance set by hand), the statement still
ends on the real balance instead of printing an impossible negative one.

Periods are whole UTC days, both ends inclusive. Holdings are the units the user owned at the
end of the period (``ownership_ledger``).

Statements are in English only (owner's decision, 2026-09-24). The PDF is set in the standard
Latin fonts, so free text written in another script — an Arabic name, property title or
admin note — is replaced by an English equivalent (the email, the slug, the movement's type)
instead of being printed as empty boxes; see ``english``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import unicodedata
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import OwnershipLedger, Property, Transaction, User, Wallet

MAX_DAYS = 3 * 366  # a longer statement is split into several downloads
MAX_ROWS = 5000
EARLIEST = dt.date(2020, 1, 1)
_ZERO = decimal.Decimal("0.00")

TYPE_LABELS = {
    "deposit": "Deposit",
    "investment": "Investment",
    "withdrawal": "Withdrawal",
    "return": "Return / distribution",
    "fee": "Fee",
    "referral_commission": "Referral commission",
    "secondary_sale": "Secondary-market sale",
    "lp_deposit": "Liquidity pool",
    "lp_yield": "Liquidity pool yield",
    "family_allocation": "Family allocation",
    "gift": "Gift",
}
STATUS_LABELS = {"completed": "Completed", "pending": "In progress", "reversed": "Reversed"}


@dataclasses.dataclass(frozen=True)
class StatementRow:
    at: dt.datetime
    type: str
    type_label: str
    description: str
    status: str
    amount: decimal.Decimal  # signed: money in > 0, money out < 0
    balance: decimal.Decimal  # running balance after this row
    reference: str


@dataclasses.dataclass(frozen=True)
class TypeTotal:
    label: str
    money_in: decimal.Decimal
    money_out: decimal.Decimal  # positive number


@dataclasses.dataclass(frozen=True)
class Holding:
    property_title: str
    units: int


@dataclasses.dataclass(frozen=True)
class Statement:
    ref: str
    holder: str
    email: str
    currency: str
    start: dt.date
    end: dt.date
    generated_at: dt.datetime
    opening: decimal.Decimal
    closing: decimal.Decimal
    money_in: decimal.Decimal
    money_out: decimal.Decimal  # positive number
    rows: list[StatementRow]
    totals: list[TypeTotal]
    holdings: list[Holding]


def english(text: str | None) -> str | None:
    """``text`` if the statement fonts can print it, else None (the caller falls back).

    Symbols the fonts lack (an emoji, an arrow) are simply dropped; a lost letter or digit
    (Arabic or any other script) means the text cannot be shown faithfully, so None."""
    if not text:
        return None
    kept: list[str] = []
    lost = False
    for ch in unicodedata.normalize("NFKC", text):
        try:
            ch.encode("cp1252")  # WinAnsi: what the PDF's standard fonts can draw
            kept.append(ch)
        except UnicodeEncodeError:
            lost = lost or ch.isalnum()
    out = " ".join("".join(kept).split())
    return None if lost or not out else out


def _humanize(slug: str | None) -> str | None:
    return english(slug.replace("-", " ").title()) if slug else None


def validate_period(start: dt.date, end: dt.date, today: dt.date | None = None) -> None:
    today = today or dt.datetime.now(dt.UTC).date()
    if start > end:
        raise AppError(
            "BAD_PERIOD", "The start date must be on or before the end date.", status_code=422
        )
    if end > today:
        raise AppError("BAD_PERIOD", "The end date cannot be in the future.", status_code=422)
    if start < EARLIEST:
        raise AppError(
            "BAD_PERIOD", f"Statements start from {EARLIEST.isoformat()}.", status_code=422
        )
    if (end - start).days + 1 > MAX_DAYS:
        raise AppError(
            "PERIOD_TOO_LONG",
            "A statement can cover up to three years. Please choose a shorter period.",
            status_code=422,
        )


def _day_start(d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time.min, tzinfo=dt.UTC)


def _money(v: decimal.Decimal | None) -> decimal.Decimal:
    return (v or _ZERO).quantize(decimal.Decimal("0.01"))


def statement_ref(user_id: uuid.UUID, start: dt.date, end: dt.date) -> str:
    return f"STM-{str(user_id)[:4].upper()}-{start:%Y%m%d}-{end:%Y%m%d}"


async def build_statement(
    session: AsyncSession, user_id: uuid.UUID, start: dt.date, end: dt.date
) -> Statement:
    validate_period(start, end)
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("NOT_FOUND", "User not found.", status_code=404)
    lo, hi = _day_start(start), _day_start(end + dt.timedelta(days=1))

    balance_now = _money(
        await session.scalar(select(Wallet.balance).where(Wallet.user_id == user_id))
    )
    after_period = _money(
        await session.scalar(
            select(func.sum(Transaction.amount)).where(
                Transaction.user_id == user_id, Transaction.created_at >= hi
            )
        )
    )
    count = await session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.created_at >= lo,
            Transaction.created_at < hi,
        )
    )
    if count and count > MAX_ROWS:
        raise AppError(
            "PERIOD_TOO_LONG",
            f"This period has more than {MAX_ROWS} movements. Please choose a shorter period.",
            status_code=422,
        )
    txs = (
        (
            await session.execute(
                select(Transaction).where(
                    Transaction.user_id == user_id,
                    Transaction.created_at >= lo,
                    Transaction.created_at < hi,
                )
                # rows booked together (a purchase and its fee) list the principal first
                .order_by(Transaction.created_at, Transaction.type == "fee", Transaction.id)
            )
        )
        .scalars()
        .all()
    )

    in_period = sum((_money(tx.amount) for tx in txs), start=_ZERO)
    opening = balance_now - after_period - in_period
    rows: list[StatementRow] = []
    running = opening
    by_type: dict[str, list[decimal.Decimal]] = {}
    money_in = money_out = _ZERO
    for tx in txs:
        amount = _money(tx.amount)
        running += amount
        kind = str(tx.type)
        label = TYPE_LABELS.get(kind, kind.replace("_", " ").capitalize())
        note = (tx.description or "").strip()
        rows.append(
            StatementRow(
                at=tx.created_at,
                type=kind,
                type_label=label,
                description=(english(note) or label) if note else "",
                status=STATUS_LABELS.get(tx.status, tx.status.capitalize()),
                amount=amount,
                balance=running,
                reference=str(tx.reference_id or tx.id)[:8].upper(),
            )
        )
        bucket = by_type.setdefault(label, [_ZERO, _ZERO])
        if amount >= 0:
            bucket[0] += amount
            money_in += amount
        else:
            bucket[1] -= amount
            money_out -= amount

    held = (
        await session.execute(
            select(Property.id, Property.title, Property.slug, func.sum(OwnershipLedger.units))
            .join(Property, Property.id == OwnershipLedger.property_id)
            .where(OwnershipLedger.user_id == user_id, OwnershipLedger.created_at < hi)
            .group_by(Property.id, Property.title, Property.slug)
            .having(func.sum(OwnershipLedger.units) > 0)
        )
    ).all()
    holdings = sorted(
        (
            Holding(
                english(title) or _humanize(slug) or f"Property {str(pid)[:8].upper()}",
                int(units),
            )
            for pid, title, slug, units in held
        ),
        key=lambda h: h.property_title.lower(),
    )

    return Statement(
        ref=statement_ref(user_id, start, end),
        holder=english(user.full_name) or user.email,
        email=user.email,
        currency=get_settings().wallet_currency,
        start=start,
        end=end,
        generated_at=dt.datetime.now(dt.UTC),
        opening=opening,
        closing=running,
        money_in=money_in,
        money_out=money_out,
        rows=rows,
        totals=[TypeTotal(k, v[0], v[1]) for k, v in sorted(by_type.items())],
        holdings=holdings,
    )


def filename(stmt: Statement, fmt: str) -> str:
    return f"capimax-statement-{stmt.start.isoformat()}-to-{stmt.end.isoformat()}.{fmt}"
