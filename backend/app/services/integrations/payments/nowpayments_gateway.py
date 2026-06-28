"""NOWPayments rail (crypto) — D4.

Hosted invoice checkout; NOWPayments auto-converts and settles to our outcome
currency, so we credit the USD-equivalent it settles (original asset/amount kept
in raw_payload). The wallet is credited ONLY by a verified IPN callback.

IPN signature (per NOWPayments docs): sort the JSON payload by keys, compact-encode
it, HMAC-SHA512 with the IPN secret, and compare to the ``x-nowpayments-sig``
header. This mirrors their PHP reference (ksort + json_encode + hash_hmac sha512).
"""

from __future__ import annotations

import decimal
import hashlib
import hmac
import json
import uuid

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.integrations.payments import (
    CheckoutResult,
    ParsedPayoutEvent,
    ParsedWebhook,
    PayoutResult,
)

# NOWPayments payment_status values we care about.
_SUCCESS = {"finished"}
_FAILED = {"failed", "expired", "refunded"}


def is_configured() -> bool:
    return get_settings().nowpayments_configured


def payout_configured() -> bool:
    return get_settings().nowpayments_payout_configured


async def create_checkout(
    *,
    payment_id: uuid.UUID,
    amount: decimal.Decimal,
    currency: str,
    success_url: str,
    cancel_url: str,
    ipn_url: str,
) -> CheckoutResult:
    if not is_configured():
        raise AppError("PAYMENTS_NOT_CONFIGURED", "NOWPayments is not configured.", status_code=503)
    settings = get_settings()
    body = {
        "price_amount": float(amount),
        "price_currency": currency.lower(),
        "order_id": str(payment_id),
        "ipn_callback_url": ipn_url,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{settings.nowpayments_base_url}/invoice",
            json=body,
            headers={"x-api-key": settings.nowpayments_api_key},
        )
    if resp.status_code >= 400:
        raise AppError(
            "PAYMENT_PROVIDER_ERROR",
            f"NOWPayments error ({resp.status_code}).",
            status_code=502,
            details={"body": resp.text[:300]},
        )
    inv = resp.json()
    return CheckoutResult(
        provider_payment_id=str(inv["id"]),
        checkout_url=str(inv["invoice_url"]),
        status="pending",
    )


async def _jwt(settings) -> str:
    """Exchange account email+password for a bearer JWT (required for payouts)."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{settings.nowpayments_base_url}/auth",
            json={"email": settings.nowpayments_email, "password": settings.nowpayments_password},
        )
    if resp.status_code >= 400:
        raise AppError("PAYOUT_PROVIDER_ERROR", "NOWPayments auth failed.", status_code=502)
    return str(resp.json()["token"])


async def create_payout(
    *,
    withdrawal_id: uuid.UUID,
    address: str,
    amount: decimal.Decimal,
    currency: str,
    idempotency_key: str,
) -> PayoutResult:
    """Submit a crypto payout to a user-supplied address (JWT-authed). Settlement is
    confirmed by the payout IPN; our withdrawal id is echoed for idempotent matching."""
    if not payout_configured():
        raise AppError(
            "PAYOUTS_NOT_CONFIGURED", "NOWPayments payouts are not configured.", status_code=503
        )
    settings = get_settings()
    token = await _jwt(settings)
    body = {
        "ipn_callback_url": "",
        "withdrawals": [
            {
                "address": address,
                "currency": currency.lower(),
                "amount": float(amount),
                "unique_external_id": str(withdrawal_id),
            }
        ],
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{settings.nowpayments_base_url}/payout",
            json=body,
            headers={"Authorization": f"Bearer {token}", "x-api-key": settings.nowpayments_api_key},
        )
    if resp.status_code >= 400:
        raise AppError(
            "PAYOUT_PROVIDER_ERROR",
            f"NOWPayments payout error ({resp.status_code}).",
            status_code=502,
            details={"body": resp.text[:300]},
        )
    data = resp.json()
    return PayoutResult(
        provider_payout_id=str(data.get("id") or data.get("batch_id")), status="processing"
    )


_PAYOUT_DONE = {"finished", "sent"}
_PAYOUT_FAIL = {"failed", "rejected", "expired"}


async def get_payout_status(provider_payout_id: str) -> str:
    """Re-query a payout's state for the reconciliation sweep:
    'settled' | 'failed' | 'pending'."""
    settings = get_settings()
    try:
        token = await _jwt(settings)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{settings.nowpayments_base_url}/payout/{provider_payout_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
    except AppError:
        return "pending"
    if resp.status_code >= 400:
        return "pending"
    ps = str(resp.json().get("status", ""))
    return "settled" if ps in _PAYOUT_DONE else "failed" if ps in _PAYOUT_FAIL else "pending"


def verify_payout_ipn(raw_body: bytes, signature: str | None) -> ParsedPayoutEvent:
    """Verify + parse a NOWPayments payout IPN (HMAC-SHA512, same scheme as deposits)."""
    secret = get_settings().nowpayments_ipn_secret
    if not secret:
        raise AppError("PAYOUTS_NOT_CONFIGURED", "NOWPayments IPN not configured.", status_code=503)
    try:
        expected = compute_signature(secret, raw_body)
    except (ValueError, UnicodeDecodeError):
        raise AppError("BAD_PAYLOAD", "IPN body is not valid JSON.", status_code=400) from None
    if not signature or not hmac.compare_digest(expected.lower(), signature.lower()):
        raise AppError(
            "WEBHOOK_SIGNATURE_INVALID", "Invalid NOWPayments signature.", status_code=401
        )
    data = json.loads(raw_body.decode("utf-8"))
    ps = str(data.get("status", ""))
    status = "settled" if ps in _PAYOUT_DONE else "failed" if ps in _PAYOUT_FAIL else "ignored"
    pid = str(data.get("id")) if data.get("id") is not None else None
    return ParsedPayoutEvent(
        event_id=f"{pid}:{ps}",
        kind="payout",
        status=status,
        provider_payout_id=pid,
        withdrawal_id=(
            str(data.get("unique_external_id")) if data.get("unique_external_id") else None
        ),
        account_id=None,
        raw=data,
    )


def compute_signature(secret: str, raw_body: bytes) -> str:
    """HMAC-SHA512 of the key-sorted, compact JSON (matches NOWPayments)."""
    parsed = json.loads(raw_body.decode("utf-8"))
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha512).hexdigest()


def verify_and_parse(raw_body: bytes, signature: str | None) -> ParsedWebhook:
    secret = get_settings().nowpayments_ipn_secret
    if not secret:
        raise AppError(
            "PAYMENTS_NOT_CONFIGURED", "NOWPayments IPN not configured.", status_code=503
        )
    try:
        expected = compute_signature(secret, raw_body)
    except (ValueError, UnicodeDecodeError):
        raise AppError("BAD_PAYLOAD", "IPN body is not valid JSON.", status_code=400) from None
    if not signature or not hmac.compare_digest(expected.lower(), signature.lower()):
        raise AppError(
            "WEBHOOK_SIGNATURE_INVALID", "Invalid NOWPayments signature.", status_code=401
        )

    data = json.loads(raw_body.decode("utf-8"))
    ps = str(data.get("payment_status", ""))
    provider_payment_id = (
        str(data.get("payment_id")) if data.get("payment_id") is not None else None
    )
    if ps in _SUCCESS:
        status = "succeeded"
    elif ps in _FAILED:
        status = "failed"
    elif ps == "partially_paid":
        status = "ignored"  # under-payment — do not credit; surfaced for manual review
    else:
        status = "pending"
    captured = None
    if status == "succeeded" and data.get("price_amount") is not None:
        captured = decimal.Decimal(str(data["price_amount"]))
    return ParsedWebhook(
        # one logical event per (payment, status) transition -> idempotent dedupe
        event_id=f"{provider_payment_id}:{ps}",
        provider_payment_id=provider_payment_id,
        order_id=str(data.get("order_id")) if data.get("order_id") else None,
        status=status,
        captured_amount=captured,
        type=ps,
        raw=data,
    )
