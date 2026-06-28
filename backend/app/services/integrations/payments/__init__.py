"""Payment provider adapters (Phase 4) behind one shape.

Each gateway exposes:
  * ``is_configured() -> bool``
  * ``create_checkout(...) -> CheckoutResult`` (hosted checkout to redirect to)
  * ``verify_and_parse(raw_body, signature) -> ParsedWebhook`` (signature-verified;
    raises AppError 401 on a bad/forged signature)

The webhook is the ONLY trusted source of a balance change — see payment_service.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckoutResult:
    provider_payment_id: str
    checkout_url: str
    status: str  # 'pending'


@dataclass(frozen=True)
class ParsedWebhook:
    event_id: str  # stable per-delivery key for idempotent dedupe
    provider_payment_id: str | None
    order_id: str | None  # our payments.id, echoed back by the provider
    status: str  # 'succeeded' | 'failed' | 'pending' | 'ignored'
    captured_amount: decimal.Decimal | None  # USD-equivalent the provider settled
    type: str
    raw: dict


@dataclass(frozen=True)
class PayoutResult:
    provider_payout_id: str
    status: str  # 'processing'


@dataclass(frozen=True)
class ParsedPayoutEvent:
    """A settlement (or Connect-account) webhook for a money-OUT payout."""

    event_id: str  # stable per-delivery key for idempotent dedupe
    kind: str  # 'payout' | 'account' | 'ignored'
    status: str  # payout: 'settled'|'failed'|'returned'|'ignored'; account: 'updated'
    provider_payout_id: str | None  # echoes withdrawals.provider_payout_id
    withdrawal_id: str | None  # our withdrawals.id, echoed in metadata
    account_id: str | None  # Connect account id (for 'account' events)
    raw: dict
