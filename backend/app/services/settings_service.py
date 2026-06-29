"""Platform settings (Phase 5) — admin-configurable values, never hardcoded.

Fees are READ from ``platform_settings`` so the owner can change rates without a
code deploy (an admin editor arrives in Phase 13). The fee RATES live here as the
single source of truth:

  * ``platform_fee_pct``   — one-time, charged to the buyer AT PURCHASE.
  * ``management_fee_pct`` — annual, deducted from distributions in Phase 6
                             (disclosed at purchase; no money moves now).

Defaults match the frontend's disclosed fee note so display == what is charged.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.investments import PlatformSetting

# Phase 13 validation specs. Keys not listed accept any value (free-form settings).
#   pct      -> numeric 0..100
#   pct_open -> numeric >= 0 OR empty string (price bounds; "" == open/no bound)
#   int      -> integer >= 0
#   bool_locked_false -> only "false" (hard-locked; cannot be enabled)
_SETTING_SPECS: dict[str, str] = {
    "platform_fee_pct": "pct",
    "management_fee_pct": "pct",
    "secondary_resale_fee_pct": "pct",
    "liquidity_discount_pct": "pct",
    "liquidity_fee_pct": "pct",
    "lp_exit_price_band_pct": "pct",
    "family_reinvest_discount_pct": "pct",
    "family_transfer_fee_pct": "pct",
    "gift_fee_pct": "pct",
    "broker_commission_pct": "pct",
    "reinvest_discount_pct": "pct",
    "secondary_price_min_pct": "pct_open",
    "secondary_price_max_pct": "pct_open",
    "secondary_lockup_days": "int",
    "lp_exit_request_ttl_minutes": "int",
    "withdrawal_auto_approve_limit": "int",
    "lp_passive_enabled": "bool_locked_false",
}


def validate_setting(key: str, value: str) -> None:
    """Reject a malformed/out-of-range platform setting (Phase 13). Raises AppError(422)
    so a bad value never reaches the store (no more silent fallback). Unknown keys pass.
    ``lp_passive_enabled`` is HARD-LOCKED to ``false`` — PASSIVE economics are undecided."""
    spec = _SETTING_SPECS.get(key)
    if spec is None:
        return
    raw = (value or "").strip()

    def _bad(msg: str) -> NoReturn:
        raise AppError("INVALID_SETTING", f"{key}: {msg}", status_code=422)

    if spec == "bool_locked_false":
        if raw.lower() in ("true", "1", "yes", "on"):
            _bad("PASSIVE is hard-locked; it cannot be enabled until its economics are set.")
        if raw.lower() not in ("false", "0", "no", "off", ""):
            _bad("must be a boolean (false).")
        return
    if spec == "pct_open" and raw == "":
        return  # empty price bound == open
    try:
        num = Decimal(raw)
    except (ArithmeticError, ValueError):
        _bad("must be a number.")
    if num < 0:
        _bad("must be >= 0.")
    if spec == "pct" and num > 100:
        _bad("must be between 0 and 100.")
    if spec == "int" and num != num.to_integral_value():
        _bad("must be a whole number.")


DEFAULTS: dict[str, str] = {
    "platform_fee_pct": "2.5",
    "management_fee_pct": "1.0",
    # Withdrawals at/under this auto-process; above it go to admin review (Phase 7).
    "withdrawal_auto_approve_limit": "5000",
    # Secondary market (Phase 8). Resale fee is buyer-side on top; lock-up in days
    # from the seller's earliest acquisition; price bounds as a % of unit_price
    # (empty = open / no bound). These MUST mirror the 0009 seeds because the test
    # fixture truncates platform_settings.
    "secondary_resale_fee_pct": "1.0",
    "secondary_lockup_days": "0",
    "secondary_price_min_pct": "",
    "secondary_price_max_pct": "",
    # Liquidity provider (Phase 9). One source of truth for the LP-exit fee + discount;
    # PASSIVE pool is hard-locked OFF until its economics are real.
    "liquidity_discount_pct": "3.0",
    "liquidity_fee_pct": "2.0",
    "lp_exit_request_ttl_minutes": "1440",
    "lp_exit_price_band_pct": "10",
    "lp_passive_enabled": "false",
    # Family (Phase 10). Discount is family-scoped only (D5 holds elsewhere); the
    # transfer fee default 0 makes the UI's "$0 family transfer" a real configurable source.
    "family_reinvest_discount_pct": "7.5",
    "family_transfer_fee_pct": "0",
    # Inter-vivos gifting (Group 5). Default 0 — a gift isn't a sale (mirrors the family
    # transfer fee); charged to the giver at execution when > 0.
    "gift_fee_pct": "0",
    # Investor reinvest discount (Phase 14) — a real, server-applied subsidy (2nd narrow
    # D5 exception). Standard invest stays no-discount.
    "reinvest_discount_pct": "5.0",
    # Broker commissions (Phase 11). Percent of the PLATFORM REVENUE attributable to a
    # referred client (purchase platform fee + rental mgmt fee), NEVER of the investment
    # amount. Admin-editable live; each accrual snapshots the rate so history is immutable.
    "broker_commission_pct": "10.0",
}


async def get_family_settings(session: AsyncSession) -> dict[str, Decimal]:
    """Family-scoped knobs: reinvest discount + member-transfer fee (percent)."""

    def _dec(raw: str, fallback: str) -> Decimal:
        try:
            return Decimal(raw)
        except (ArithmeticError, ValueError):
            return Decimal(fallback)

    return {
        "reinvest_discount_pct": _dec(
            await get_setting(session, "family_reinvest_discount_pct"), "7.5"
        ),
        "transfer_fee_pct": _dec(await get_setting(session, "family_transfer_fee_pct"), "0"),
    }


async def get_broker_commission_pct(session: AsyncSession) -> Decimal:
    """Broker commission rate (percent of platform revenue from a referred client).
    Single source of truth for the accrual calc + every display surface — no literals."""
    try:
        return Decimal(await get_setting(session, "broker_commission_pct"))
    except (ArithmeticError, ValueError):
        return Decimal("10.0")


async def get_reinvest_discount_pct(session: AsyncSession) -> Decimal:
    """Investor reinvest discount rate (percent). Server-authoritative; the reinvest path
    applies it as an effective unit price — the client never computes the final price."""
    try:
        return Decimal(await get_setting(session, "reinvest_discount_pct"))
    except (ArithmeticError, ValueError):
        return Decimal("5.0")


async def get_gift_fee_pct(session: AsyncSession) -> Decimal:
    """Inter-vivos gift fee rate (percent of gifted value). Server-authoritative;
    default 0 — a gift isn't a sale."""
    try:
        return Decimal(await get_setting(session, "gift_fee_pct"))
    except (ArithmeticError, ValueError):
        return Decimal("0")


async def get_management_fee_pct(session: AsyncSession) -> Decimal:
    """Platform management-fee rate, stamped onto LP/secondary-acquired ownership rows
    at acquisition (the rate those owners consent to)."""
    return Decimal(await get_setting(session, "management_fee_pct"))


async def get_liquidity_settings(session: AsyncSession) -> dict[str, Decimal | int | bool]:
    """Live LP-exit knobs (server-authoritative pricing inputs)."""

    def _dec(raw: str, fallback: str) -> Decimal:
        try:
            return Decimal(raw)
        except (ArithmeticError, ValueError):
            return Decimal(fallback)

    discount = _dec(await get_setting(session, "liquidity_discount_pct"), "3.0")
    fee = _dec(await get_setting(session, "liquidity_fee_pct"), "2.0")
    ttl = _dec(await get_setting(session, "lp_exit_request_ttl_minutes"), "1440")
    band = _dec(await get_setting(session, "lp_exit_price_band_pct"), "10")
    passive_raw = (await get_setting(session, "lp_passive_enabled")).strip().lower()
    return {
        "discount_pct": discount,
        "fee_pct": fee,
        "ttl_minutes": int(ttl),
        "band_pct": band,
        "passive_enabled": passive_raw in ("true", "1", "yes", "on"),
    }


async def get_secondary_settings(session: AsyncSession) -> dict[str, Decimal | int | None]:
    """Live secondary-market knobs. Price bounds are ``None`` when open (unset)."""

    def _pct_or_none(raw: str) -> Decimal | None:
        raw = (raw or "").strip()
        if raw == "":
            return None
        try:
            return Decimal(raw)
        except (ArithmeticError, ValueError):
            return None

    fee_raw = await get_setting(session, "secondary_resale_fee_pct")
    lockup_raw = await get_setting(session, "secondary_lockup_days")
    try:
        resale_fee_pct = Decimal(fee_raw)
    except (ArithmeticError, ValueError):
        resale_fee_pct = Decimal("1.0")
    try:
        lockup_days = int(Decimal(lockup_raw))
    except (ArithmeticError, ValueError):
        lockup_days = 0
    return {
        "resale_fee_pct": resale_fee_pct,
        "lockup_days": lockup_days,
        "price_min_pct": _pct_or_none(await get_setting(session, "secondary_price_min_pct")),
        "price_max_pct": _pct_or_none(await get_setting(session, "secondary_price_max_pct")),
    }


async def get_setting(session: AsyncSession, key: str) -> str:
    value = await session.scalar(select(PlatformSetting.value).where(PlatformSetting.key == key))
    if value is None:
        return DEFAULTS.get(key, "0")
    return value


async def get_fee_rates(session: AsyncSession) -> dict[str, Decimal]:
    """Return the live fee rates as percentages (e.g. Decimal('2.5'))."""
    platform = await get_setting(session, "platform_fee_pct")
    management = await get_setting(session, "management_fee_pct")
    return {
        "platform_fee_pct": Decimal(platform),
        "management_fee_pct": Decimal(management),
    }
