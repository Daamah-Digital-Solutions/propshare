"""Wallet preparation tools: a deposit, a withdrawal or an account statement, prepared inside
the chat (owner's principle: the assistant prepares everything, the user presses the last
button).

Nothing here moves money. ``prepare_deposit`` and ``prepare_withdrawal`` check the same rules
as the wallet endpoints (verification, live rails, balance, a payout destination, instant
eligibility and its fee) and the server turns the result into a card whose link opens the
wallet with the form filled in, stopping at the user's own Deposit / Withdraw click.
``prepare_statement`` validates the period and summarises it; its card downloads the file
through the normal statement endpoint (rate-limited and audited there).
"""

from __future__ import annotations

import datetime as dt
import decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.errors import AppError
from app.services import (
    connect_service,
    payment_service,
    payout_methods_service,
    platform_accounts_service,
    statement_service,
    wallet_service,
    withdrawal_service,
)
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.account import mask_tail
from app.services.assistant.tools.base import ToolOutput, ToolSpec, register

_CENTS = decimal.Decimal("0.01")
_KYC_NOTES = {
    "submitted": "Your identity verification is still being reviewed; this works once it is "
    "approved.",
    "rejected": "Your identity verification was not approved; submit it again first.",
}


def kyc_note(status: str) -> str | None:
    """The wallet endpoints need an approved verification (KycVerifiedDep)."""
    if status == "verified":
        return None
    return _KYC_NOTES.get(status, "Complete identity verification first.")


def _now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def _amount(value: float) -> decimal.Decimal:
    return decimal.Decimal(str(value)).quantize(_CENTS)


# --------------------------------------------------------------------------- #
# prepare_deposit
# --------------------------------------------------------------------------- #
DEPOSIT_LABELS = {"card": "Card", "crypto": "Crypto", "bank": "Bank transfer"}
_DEPOSIT_STEPS = {
    "card": "The wallet opens with the amount filled in; pressing Deposit opens the secure card "
    "checkout, and the wallet is credited as soon as the payment succeeds.",
    "crypto": "The wallet opens with the amount filled in; pressing Deposit opens the crypto "
    "payment page, and the wallet is credited once the network confirms the payment.",
    "bank": "The wallet opens with our receiving bank account shown; transfer the amount from "
    "your bank, then press Record transfer. The team credits the wallet when it arrives.",
}


class DepositPrepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(gt=0, le=1_000_000_000, description="Amount to add, in USD")
    method: Literal["card", "crypto", "bank"] | None = Field(
        default=None, description="card, crypto or bank (bank transfer); empty = the first live one"
    )


class DepositPrepOut(ToolOutput):
    amount: str
    currency: str
    method: str
    method_label: str
    live_methods: list[str]
    ready: bool  # nothing blocks the Deposit button
    notes: list[str]
    next_step: str
    as_of: str


async def _live_deposit_methods(session) -> list[str]:
    """Live rails in the order a deposit defaults to them: card, bank transfer, crypto."""
    bank = bool(await platform_accounts_service.list_active(session))
    return [
        m
        for m, on in (
            ("card", payment_service.provider_configured("card")),
            ("bank", bank),
            ("crypto", payment_service.provider_configured("crypto")),
        )
        if on
    ]


async def _prepare_deposit(session, ctx: AgentContext, args) -> dict:
    a: DepositPrepIn = args
    live = await _live_deposit_methods(session)
    method = a.method or (live[0] if live else "bank")
    notes: list[str] = []  # every note here blocks the Deposit button
    if method not in live:
        others = ", ".join(DEPOSIT_LABELS[m].lower() for m in live)
        notes.append(
            f"{DEPOSIT_LABELS[method]} deposits are not available yet"
            + (f"; you can use {others} now." if others else ".")
        )
    if kyc := kyc_note(ctx.kyc_status):
        notes.append(kyc)
    return {
        "amount": f"{_amount(a.amount):.2f}",
        "currency": get_settings().wallet_currency,
        "method": method,
        "method_label": DEPOSIT_LABELS[method],
        "live_methods": live,
        "ready": not notes,
        "notes": notes,
        "next_step": _DEPOSIT_STEPS[method],
        "as_of": _now(),
    }


register(
    ToolSpec(
        "prepare_deposit",
        "Prepare adding funds to the signed-in user's wallet: checks the method is live and the "
        "user may deposit. The user then sees a deposit card whose button opens the wallet with "
        "the amount and method filled in, stopping at their own Deposit click. Nothing is charged.",
        DepositPrepIn,
        DepositPrepOut,
        "prepare_only",
        _prepare_deposit,
    )
)


# --------------------------------------------------------------------------- #
# prepare_withdrawal
# --------------------------------------------------------------------------- #
_INSTANT_REASONS = {
    "DISABLED": "Instant payouts are switched off right now",
    "BANK_NOT_AUTOMATIC": "Instant payouts need automatic bank withdrawals, which are not on yet",
    "CONNECT_NOT_READY": "Instant payouts need a linked bank account first",
    "NO_ELIGIBLE_CARD": "Your linked account has no debit card that supports instant payouts",
}


class WithdrawalPrepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(gt=0, le=1_000_000_000, description="Amount to take out, in USD")
    method: Literal["bank", "crypto"] | None = Field(
        default=None, description="bank or crypto; empty = bank"
    )
    speed: Literal["standard", "instant"] | None = Field(
        default=None,
        description="instant = to a debit card in minutes, for a fee; empty = standard",
    )


class WithdrawalPrepOut(ToolOutput):
    amount: str
    currency: str
    method: str
    speed: str
    fee: str
    net_amount: str  # what reaches the user
    available_balance: str
    settlement: str  # automatic | reviewed (by the team)
    destination: str | None  # masked
    timing: str
    ready: bool  # nothing blocks the Withdraw button
    notes: list[str]
    as_of: str


async def _destination(
    session, ctx: AgentContext, method: str, manual: bool, blocking: list[str]
) -> str | None:
    """Where the money would go, masked — the same pick the endpoint makes (the default saved
    account, else the first; automatic bank payouts go to the Stripe-linked account)."""
    uid = ctx.user_id
    if method == "bank" and not manual:
        acct = await connect_service.get_account(session, uid)
        if acct is None or not acct.payouts_enabled:
            blocking.append(
                "Link your bank account once in the wallet (Withdraw, Link bank account)."
            )
            return None
        return "Your linked bank account"
    if method == "bank":
        banks = await payout_methods_service.list_bank_accounts(session, uid)
        bank = next((b for b in banks if b.is_default), banks[0] if banks else None)
        if bank is None:
            blocking.append("Add a bank account in the wallet (Payment Methods) first.")
            return None
        return f"{bank.bank_name} {mask_tail(bank.iban or bank.account_number) or ''}".strip()
    wallets = await payout_methods_service.list_crypto_wallets(session, uid)
    w = next((x for x in wallets if x.is_default), wallets[0] if wallets else None)
    if w is None:
        blocking.append("Add a crypto wallet in the wallet (Payment Methods) first.")
        return None
    return f"{w.network} {mask_tail(w.address) or ''}".strip()


async def _prepare_withdrawal(session, ctx: AgentContext, args) -> dict:
    a: WithdrawalPrepIn = args
    assert ctx.user_id is not None  # prepare_only: guard.authorize refuses visitors
    method = a.method or "bank"
    amount = _amount(a.amount)
    blocking: list[str] = []  # stop the Withdraw button
    info: list[str] = []  # worth saying, blocks nothing
    wallet = await wallet_service.get_wallet(session, ctx.user_id)
    if amount > wallet.balance:
        blocking.append(f"That is more than your available balance of {wallet.balance:.2f}.")
    if kyc := kyc_note(ctx.kyc_status):
        blocking.append(kyc)
    manual = await withdrawal_service.is_manual_for(session, method)

    speed, fee = "standard", decimal.Decimal("0.00")
    if a.speed == "instant":
        # Every reason instant cannot run is answered here, like the endpoint does before the
        # hold; the order falls back to the free standard speed and the note says why.
        why = None
        if manual or method != "bank":
            why = "Instant payouts are only for automatic bank withdrawals"
        else:
            ready = await withdrawal_service.instant_readiness(session, ctx.user_id)
            if not ready["available"]:
                why = _INSTANT_REASONS.get(ready["reason"], "Instant is not available right now")
            elif amount > decimal.Decimal(ready["max_amount"]):
                why = f"Instant payouts are capped at {ready['max_amount']} per request"
            else:
                instant_fee = withdrawal_service.instant_fee_for(
                    amount, decimal.Decimal(ready["fee_pct"])
                )
                if instant_fee >= amount:
                    why = "The amount is too small for an instant payout"
                else:
                    speed, fee = "instant", instant_fee
        if why:
            info.append(f"{why}, so this is prepared at the standard speed (no fee).")

    destination = await _destination(session, ctx, method, manual, blocking)
    if manual:
        settlement = "reviewed"
        timing = "Paid by our team after a check, usually in 1-2 business days."
    elif speed == "instant":
        settlement, timing = "automatic", "Sent at once; usually arrives within 30 minutes."
    else:
        settlement = "automatic"
        timing = "Sent at once; banks usually post it within 1-2 business days."
        limit = await withdrawal_service._auto_limit(session)
        if amount > limit:
            timing = f"Above {limit:.2f}, our team reviews it first; then 1-2 business days."
    return {
        "amount": f"{amount:.2f}",
        "currency": get_settings().wallet_currency,
        "method": method,
        "speed": speed,
        "fee": f"{fee:.2f}",
        "net_amount": f"{(amount - fee):.2f}",
        "available_balance": f"{wallet.balance:.2f}",
        "settlement": settlement,
        "destination": destination,
        "timing": timing,
        "ready": not blocking,
        "notes": blocking + info,
        "as_of": _now(),
    }


register(
    ToolSpec(
        "prepare_withdrawal",
        "Prepare a withdrawal from the signed-in user's wallet: checks the balance, the payout "
        "destination, and for instant speed the eligibility, limit and fee (net amount shown). "
        "The user then sees a withdrawal card whose button opens the wallet with everything "
        "filled in, stopping at their own Withdraw click. Nothing is sent.",
        WithdrawalPrepIn,
        WithdrawalPrepOut,
        "prepare_only",
        _prepare_withdrawal,
    )
)


# --------------------------------------------------------------------------- #
# prepare_statement
# --------------------------------------------------------------------------- #
_DATE = r"^\d{4}-\d{2}-\d{2}$"


class StatementPrepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = Field(pattern=_DATE, description="First day, YYYY-MM-DD (UTC)")
    end: str = Field(pattern=_DATE, description="Last day, YYYY-MM-DD (UTC), not in the future")
    format: Literal["pdf", "xlsx"] | None = Field(default=None, description="pdf (default) or xlsx")


class StatementPrepOut(ToolOutput):
    start: str
    end: str
    format: str
    movements: int
    opening_balance: str
    closing_balance: str
    money_in: str
    money_out: str
    currency: str
    note: str


def _date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise AppError("BAD_PERIOD", f"{value} is not a real date.", status_code=422) from exc


async def _prepare_statement(session, ctx: AgentContext, args) -> dict:
    a: StatementPrepIn = args
    assert ctx.user_id is not None  # prepare_only: guard.authorize refuses visitors
    stmt = await statement_service.build_statement(
        session, ctx.user_id, _date(a.start), _date(a.end)
    )
    return {
        "start": stmt.start.isoformat(),
        "end": stmt.end.isoformat(),
        "format": a.format or "pdf",
        "movements": len(stmt.rows),
        "opening_balance": f"{stmt.opening:.2f}",
        "closing_balance": f"{stmt.closing:.2f}",
        "money_in": f"{stmt.money_in:.2f}",
        "money_out": f"{stmt.money_out:.2f}",
        "currency": stmt.currency,
        "note": "Both days are included (UTC). The card downloads the PDF or Excel file directly.",
    }


register(
    ToolSpec(
        "prepare_statement",
        "Prepare the signed-in user's account statement for a period (up to three years): "
        "number of movements, opening and closing balance, money in and out. The user then "
        "sees a statement card that downloads the PDF or Excel file straight away.",
        StatementPrepIn,
        StatementPrepOut,
        "prepare_only",
        _prepare_statement,
    )
)
