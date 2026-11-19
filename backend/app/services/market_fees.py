"""Trading and liquidity fees (client, 2026-11-18, the Capimax market fees letter, PropShare).

All rates are of the value of the units sold (the deal):

  deal                                   seller   buyer   platform   liquidity provider
  ordinary secondary-market sale          0.5%     1.5%     2%         —
  a provider buys through the LP market   1.5%     0%       1%         0.5% (of the seller fee)
  a provider resells those units          0%       1.5%     1%         0.5% (of the buyer fee)

The rates are Platform Settings (``secondary_seller_fee_pct``, ``secondary_resale_fee_pct``
for the buyer, ``liquidity_fee_pct`` for the seller in the LP market, ``lp_fee_share_pct``).
There is no platform wallet: a fee is a ``fee`` row on the payer's wallet, the provider's share
an ``lp_fee_share`` credit on its own; what the platform keeps is the fees less the share.

This module only computes; the services move the money.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass

_CENT = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)
_ZERO = decimal.Decimal("0.00")


def q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENT, rounding=decimal.ROUND_HALF_UP)


def pct_of(amount: decimal.Decimal, pct: decimal.Decimal) -> decimal.Decimal:
    if amount <= 0 or pct <= 0:
        return _ZERO
    return q(amount * pct / _HUNDRED)


@dataclass(frozen=True)
class SecondaryFees:
    """One secondary-market trade."""

    gross: decimal.Decimal  # what the buyer pays for the units (the deal)
    buyer_fee: decimal.Decimal  # on top, from the buyer
    seller_fee: decimal.Decimal  # out of the seller's proceeds (ordinary units only)
    lp_units: int  # units a provider resells that it bought through the LP market
    lp_fee_share: decimal.Decimal  # the provider-seller's share of the buyer fee on those
    total_charged: decimal.Decimal  # the buyer pays gross + buyer_fee
    seller_net: decimal.Decimal  # the seller receives gross - seller_fee + lp_fee_share
    platform: decimal.Decimal  # buyer_fee + seller_fee - lp_fee_share


def secondary_fees(
    *,
    gross: decimal.Decimal,
    units: int,
    lp_units: int,
    buyer_pct: decimal.Decimal,
    seller_pct: decimal.Decimal,
    share_pct: decimal.Decimal,
) -> SecondaryFees:
    """The fees of a trade of ``units`` for ``gross``, of which ``lp_units`` are a provider's
    LP-market units (sold under the provider's rules: no seller fee, a share of the buyer's)."""
    gross = q(gross)
    lp_units = max(0, min(lp_units, units))
    lp_gross = q(gross * lp_units / units) if units else _ZERO
    ordinary_gross = gross - lp_gross
    buyer_fee = pct_of(gross, buyer_pct)
    seller_fee = pct_of(ordinary_gross, seller_pct)
    # the share comes out of the buyer fee on those units, never more than it
    share = min(pct_of(lp_gross, share_pct), pct_of(lp_gross, buyer_pct))
    return SecondaryFees(
        gross=gross,
        buyer_fee=buyer_fee,
        seller_fee=seller_fee,
        lp_units=lp_units,
        lp_fee_share=share,
        total_charged=q(gross + buyer_fee),
        seller_net=q(gross - seller_fee + share),
        platform=q(buyer_fee + seller_fee - share),
    )


@dataclass(frozen=True)
class LiquidityFees:
    """A provider buying through the LP market."""

    deal: decimal.Decimal  # what the provider pays (no purchase fee)
    seller_fee: decimal.Decimal  # the liquidity fee, out of the seller's proceeds
    lp_fee_share: decimal.Decimal  # the provider's share of it, credited to the provider
    seller_net: decimal.Decimal
    platform: decimal.Decimal


def liquidity_fees(
    *, deal: decimal.Decimal, fee_pct: decimal.Decimal, share_pct: decimal.Decimal
) -> LiquidityFees:
    deal = q(deal)
    seller_fee = pct_of(deal, fee_pct)
    share = min(pct_of(deal, share_pct), seller_fee)
    return LiquidityFees(
        deal=deal,
        seller_fee=seller_fee,
        lp_fee_share=share,
        seller_net=q(deal - seller_fee),
        platform=q(seller_fee - share),
    )
