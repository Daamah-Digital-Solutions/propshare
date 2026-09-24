"""Stripe rail (cards / Apple Pay / Google Pay) — D2.

Payments use Stripe Checkout Sessions (hosted), so the SPA only redirects. Saving a card
uses Stripe's Payment Element in the SPA on a SetupIntent: card data goes from Stripe's form
to Stripe and never reaches us. The wallet is credited ONLY by the signature-verified webhook
(``checkout.session.completed``), never on the browser redirect. Signature
verification is the standard Stripe ``Stripe-Signature`` HMAC-SHA256 scheme,
implemented directly (no SDK dependency).
"""

from __future__ import annotations

import decimal
import hashlib
import hmac
import json
import logging
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

_API = "https://api.stripe.com/v1/checkout/sessions"
_API_BASE = "https://api.stripe.com/v1"
logger = logging.getLogger(__name__)


def _refused(resp: httpx.Response, code: str, what: str) -> AppError:
    """Stripe said no. Log its own reason: with a restricted key a 403 names the permission to
    add, which is otherwise invisible from our side."""
    try:
        err = resp.json().get("error") or {}
    except ValueError:
        err = {}
    logger.warning(
        "Stripe refused %s: %s %s",
        what,
        resp.status_code,
        str(err.get("message") or resp.text)[:300],
    )
    return AppError(
        code,
        f"Stripe error ({resp.status_code}).",
        status_code=502,
        details={"body": resp.text[:300], "code": err.get("code"), "param": err.get("param")},
    )


def is_unknown_customer(exc: AppError) -> bool:
    """A refusal because the customer id does not exist for this key (keys were switched)."""
    details = exc.details or {}
    return details.get("code") == "resource_missing" and details.get("param") == "customer"


def is_configured() -> bool:
    # Customer-facing readiness: in production this requires LIVE keys (see
    # Settings.stripe_customer_ready) so a real customer never lands on a test-card checkout.
    return get_settings().stripe_customer_ready


def connect_configured() -> bool:
    return get_settings().stripe_connect_configured


async def create_checkout(
    *,
    payment_id: uuid.UUID,
    amount: decimal.Decimal,
    currency: str,
    success_url: str,
    cancel_url: str,
    idempotency_key: str | None,
    product_name: str = "Capimax wallet deposit",
    customer_id: str | None = None,
) -> CheckoutResult:
    """Hosted Checkout for one payment. With the investor's Stripe customer, Checkout lists the
    cards they saved in the wallet so they can pay with one."""
    if not is_configured():
        raise AppError("PAYMENTS_NOT_CONFIGURED", "Stripe is not configured.", status_code=503)
    settings = get_settings()
    minor = int((amount * 100).to_integral_value(rounding=decimal.ROUND_HALF_UP))
    data = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(payment_id),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": currency.lower(),
        "line_items[0][price_data][unit_amount]": str(minor),
        "line_items[0][price_data][product_data][name]": product_name,
        "metadata[payment_id]": str(payment_id),
        "payment_intent_data[metadata][payment_id]": str(payment_id),
    }
    if customer_id:
        data["customer"] = customer_id
    headers = {}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            _API, data=data, headers=headers, auth=(settings.stripe_secret_key, "")
        )
        if customer_id and _unknown_customer(resp):
            # A customer from another Stripe mode or account (keys were switched): take the
            # payment without the saved cards rather than refusing it. A new idempotency key,
            # because Stripe binds a key to the parameters it was first used with.
            data.pop("customer")
            if idempotency_key:
                headers["Idempotency-Key"] = f"{idempotency_key}-no-customer"
            resp = await client.post(
                _API, data=data, headers=headers, auth=(settings.stripe_secret_key, "")
            )
    if resp.status_code >= 400:
        raise _refused(resp, "PAYMENT_PROVIDER_ERROR", "a checkout")
    session = resp.json()
    return CheckoutResult(
        provider_payment_id=str(session["id"]),
        checkout_url=str(session["url"]),
        status="pending",
    )


def _unknown_customer(resp: httpx.Response) -> bool:
    """Stripe's answer when the customer id does not exist for this key."""
    if resp.status_code != 400:
        return False
    try:
        err = resp.json().get("error") or {}
    except ValueError:
        return False
    return err.get("code") == "resource_missing" and err.get("param") == "customer"


def verify_and_parse(raw_body: bytes, signature: str | None) -> ParsedWebhook:
    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise AppError("PAYMENTS_NOT_CONFIGURED", "Stripe webhook not configured.", status_code=503)
    if not _verify(secret, raw_body, signature or ""):
        raise AppError("WEBHOOK_SIGNATURE_INVALID", "Invalid Stripe signature.", status_code=401)

    event = json.loads(raw_body.decode("utf-8"))
    etype = str(event.get("type", ""))
    obj = (event.get("data") or {}).get("object") or {}
    event_id = str(event.get("id"))

    if etype == "checkout.session.completed":
        paid = obj.get("payment_status") == "paid"
        captured = None
        if obj.get("amount_total") is not None:
            captured = decimal.Decimal(int(obj["amount_total"])) / decimal.Decimal(100)
        return ParsedWebhook(
            event_id=event_id,
            provider_payment_id=str(obj.get("id")) if obj.get("id") else None,
            order_id=obj.get("client_reference_id")
            or (obj.get("metadata") or {}).get("payment_id"),
            status="succeeded" if paid else "pending",
            captured_amount=captured,
            type=etype,
            raw=event,
        )
    if etype in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        return ParsedWebhook(
            event_id=event_id,
            provider_payment_id=str(obj.get("id")) if obj.get("id") else None,
            order_id=obj.get("client_reference_id")
            or (obj.get("metadata") or {}).get("payment_id"),
            status="failed",
            captured_amount=None,
            type=etype,
            raw=event,
        )
    return ParsedWebhook(event_id, None, None, "ignored", None, etype, event)


# --- Saved payment methods (Group 3, PCI-safe tokenization) ---------------- #
# Raw card data NEVER touches our server: the card is collected client-side via the
# SetupIntent (Stripe.js/Elements) and we only ever store TOKENS + safe display metadata
# that Stripe returns (brand/last4/exp). All calls are gated on is_configured() => 503.
async def create_customer(*, email: str) -> str:
    if not is_configured():
        raise AppError("PAYMENTS_NOT_CONFIGURED", "Stripe is not configured.", status_code=503)
    cust = await _post("customers", {"email": email})
    return str(cust["id"])


async def create_setup_intent(*, customer_id: str) -> dict:
    """A SetupIntent lets the SPA tokenize a card for future use (no charge). on_session: a saved
    card is only ever used by the investor at checkout, never charged in their absence, so Stripe
    does not ask them to authorise future charges."""
    if not is_configured():
        raise AppError("PAYMENTS_NOT_CONFIGURED", "Stripe is not configured.", status_code=503)
    si = await _post(
        "setup_intents",
        {"customer": customer_id, "usage": "on_session", "payment_method_types[]": "card"},
    )
    return {"id": str(si["id"]), "client_secret": str(si["client_secret"])}


async def retrieve_setup_intent(setup_intent_id: str) -> dict:
    """Stripe's own record of a card setup the browser says it finished: whose customer it
    belongs to, whether it succeeded and which payment method it produced. The server trusts
    this, never a payment-method id sent by the browser."""
    if not is_configured():
        raise AppError("PAYMENTS_NOT_CONFIGURED", "Stripe is not configured.", status_code=503)
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_API_BASE}/setup_intents/{setup_intent_id}",
            auth=(settings.stripe_secret_key, ""),
        )
    if resp.status_code >= 400:
        raise _refused(resp, "PAYMENT_PROVIDER_ERROR", "reading a card setup")
    si = resp.json()

    def _id(value):  # expandable fields arrive as an id or as the object
        return value.get("id") if isinstance(value, dict) else value

    return {
        "id": str(si.get("id")),
        "status": str(si.get("status")),
        "customer": _id(si.get("customer")),
        "payment_method": _id(si.get("payment_method")),
    }


async def retrieve_payment_method(payment_method_id: str) -> dict:
    """Server-side metadata fetch — we trust Stripe for brand/last4/exp, never the client."""
    if not is_configured():
        raise AppError("PAYMENTS_NOT_CONFIGURED", "Stripe is not configured.", status_code=503)
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_API_BASE}/payment_methods/{payment_method_id}",
            auth=(settings.stripe_secret_key, ""),
        )
    if resp.status_code >= 400:
        raise _refused(resp, "PAYMENT_PROVIDER_ERROR", "reading a card")
    pm = resp.json()
    card = pm.get("card") or {}
    billing = pm.get("billing_details") or {}
    return {
        "id": str(pm.get("id")),
        "type": str(pm.get("type") or "card"),
        "brand": card.get("brand"),
        "last4": card.get("last4"),
        "exp_month": card.get("exp_month"),
        "exp_year": card.get("exp_year"),
        "billing_name": billing.get("name"),
        "billing_email": billing.get("email"),
        "allow_redisplay": pm.get("allow_redisplay"),
    }


async def offer_again_at_checkout(
    payment_method_id: str, *, name: str | None = None, email: str | None = None
) -> None:
    """Let hosted Checkout show a card the investor chose to save. Checkout only lists saved
    cards marked allow_redisplay=always (a card saved through a SetupIntent is 'unspecified'),
    and it prefills them only with a billing name and email, which the card form does not ask
    for; missing ones are filled from the account."""
    data = {"allow_redisplay": "always"}
    if name:
        data["billing_details[name]"] = name
    if email:
        data["billing_details[email]"] = email
    await _post(f"payment_methods/{payment_method_id}", data)


async def detach_payment_method(payment_method_id: str) -> None:
    if not is_configured():
        raise AppError("PAYMENTS_NOT_CONFIGURED", "Stripe is not configured.", status_code=503)
    await _post(f"payment_methods/{payment_method_id}/detach", {})


# --- Stripe Connect onboarding (Phase 7, bank withdrawals) ----------------- #
async def _post(path: str, data: dict, *, idempotency_key: str | None = None) -> dict:
    settings = get_settings()
    headers = {}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{_API_BASE}/{path}", data=data, headers=headers, auth=(settings.stripe_secret_key, "")
        )
    if resp.status_code >= 400:
        raise _refused(resp, "PAYOUT_PROVIDER_ERROR", f"POST {path.split('/')[0]}")
    return resp.json()


async def create_connected_account(email: str) -> str:
    if not connect_configured():
        raise AppError(
            "PAYOUTS_NOT_CONFIGURED", "Stripe Connect is not configured.", status_code=503
        )
    acct = await _post("accounts", {"type": "express", "email": email})
    return str(acct["id"])


async def create_account_link(account_id: str, *, refresh_url: str, return_url: str) -> str:
    if not connect_configured():
        raise AppError(
            "PAYOUTS_NOT_CONFIGURED", "Stripe Connect is not configured.", status_code=503
        )
    link = await _post(
        "account_links",
        {
            "account": account_id,
            "refresh_url": refresh_url,
            "return_url": return_url,
            "type": "account_onboarding",
        },
    )
    return str(link["url"])


async def get_account_status(account_id: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_API_BASE}/accounts/{account_id}", auth=(settings.stripe_secret_key, "")
        )
    if resp.status_code >= 400:
        raise AppError(
            "PAYOUT_PROVIDER_ERROR", f"Stripe error ({resp.status_code}).", status_code=502
        )
    acct = resp.json()
    return {
        "payouts_enabled": bool(acct.get("payouts_enabled")),
        "details_submitted": bool(acct.get("details_submitted")),
    }


async def create_payout(
    *,
    withdrawal_id: uuid.UUID,
    account_id: str,
    amount: decimal.Decimal,
    currency: str,
    idempotency_key: str,
) -> PayoutResult:
    """Transfer funds to the investor's connected account (their bank payout follows).
    The Idempotency-Key (= withdrawal id) guarantees a retried submit never sends twice.
    """
    if not connect_configured():
        raise AppError(
            "PAYOUTS_NOT_CONFIGURED", "Stripe Connect is not configured.", status_code=503
        )
    minor = int((amount * 100).to_integral_value(rounding=decimal.ROUND_HALF_UP))
    transfer = await _post(
        "transfers",
        {
            "amount": str(minor),
            "currency": currency.lower(),
            "destination": account_id,
            "metadata[withdrawal_id]": str(withdrawal_id),
        },
        idempotency_key=idempotency_key,
    )
    return PayoutResult(provider_payout_id=str(transfer["id"]), status="processing")


async def get_payout_status(provider_payout_id: str) -> str:
    """Re-query a transfer's state for the reconciliation sweep:
    'settled' | 'failed' | 'pending'."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_API_BASE}/transfers/{provider_payout_id}", auth=(settings.stripe_secret_key, "")
        )
    if resp.status_code >= 400:
        return "pending"
    t = resp.json()
    if t.get("reversed") or t.get("amount_reversed"):
        return "failed"
    return "settled"


# Payout settlement statuses we map to terminal outcomes.
_PAYOUT_SETTLED = {"payout.paid", "transfer.paid"}
_PAYOUT_FAILED = {"payout.failed", "transfer.failed"}
_PAYOUT_RETURNED = {"payout.returned", "charge.refunded"}


def parse_payout_event(raw_body: bytes, signature: str | None) -> ParsedPayoutEvent:
    """Verify + parse a Stripe payout/Connect webhook (money-OUT settlement)."""
    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise AppError("PAYOUTS_NOT_CONFIGURED", "Stripe webhook not configured.", status_code=503)
    if not _verify(secret, raw_body, signature or ""):
        raise AppError("WEBHOOK_SIGNATURE_INVALID", "Invalid Stripe signature.", status_code=401)
    event = json.loads(raw_body.decode("utf-8"))
    etype = str(event.get("type", ""))
    obj = (event.get("data") or {}).get("object") or {}
    event_id = str(event.get("id"))
    meta = obj.get("metadata") or {}
    if etype == "account.updated":
        return ParsedPayoutEvent(
            event_id=event_id,
            kind="account",
            status="updated",
            provider_payout_id=None,
            withdrawal_id=None,
            account_id=str(obj.get("id")) if obj.get("id") else None,
            raw=event,
        )
    if etype in _PAYOUT_SETTLED or etype in _PAYOUT_FAILED or etype in _PAYOUT_RETURNED:
        status = (
            "settled"
            if etype in _PAYOUT_SETTLED
            else "failed" if etype in _PAYOUT_FAILED else "returned"
        )
        return ParsedPayoutEvent(
            event_id=event_id,
            kind="payout",
            status=status,
            provider_payout_id=str(obj.get("id")) if obj.get("id") else None,
            withdrawal_id=meta.get("withdrawal_id"),
            account_id=None,
            raw=event,
        )
    return ParsedPayoutEvent(event_id, "ignored", "ignored", None, None, None, event)


def _verify(secret: str, raw_body: bytes, header: str) -> bool:
    # Header form: "t=<ts>,v1=<sig>[,v1=<sig2>]". Sign "<ts>.<raw>" with HMAC-SHA256.
    if not header:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    timestamp = parts.get("t")
    if not timestamp:
        return False
    v1s = [p.split("=", 1)[1] for p in header.split(",") if p.startswith("v1=")]
    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, v) for v in v1s)
