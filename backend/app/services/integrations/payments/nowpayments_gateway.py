"""NOWPayments rail (crypto) — D4.

Hosted invoice checkout; NOWPayments auto-converts and settles to our outcome
currency, so we credit the USD-equivalent it settles (original asset/amount kept
in raw_payload). The wallet is credited ONLY by a verified IPN callback.

IPN signature (per NOWPayments docs): sort the JSON payload by keys, compact-encode
it, HMAC-SHA512 with the IPN secret, and compare to the ``x-nowpayments-sig``
header (``signatures`` below: the numbers must stay as they were sent).

The member picks the coin on the platform (``list_coins``: the coins switched on in the
NOWPayments account) and the invoice is made for that coin, so the payment page asks for one
coin on one network and never shows a list of its own.
"""

from __future__ import annotations

import decimal
import hashlib
import hmac
import json
import logging
import time
import uuid
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.integrations.payments import (
    CheckoutResult,
    ParsedPayoutEvent,
    ParsedWebhook,
    PayoutResult,
)

logger = logging.getLogger(__name__)

# NOWPayments payment_status values we care about.
_FAILED = {"failed", "expired", "refunded"}
_CENT = decimal.Decimal("0.01")
# The coins members pay with most: listed first and up front, whatever marks the account's
# own list carries (it holds hundreds of coins).
FEATURED = (
    "usdttrc20",
    "usdtbsc",
    "usdterc20",
    "usdc",
    "usdcsol",
    "btc",
    "eth",
    "bnbbsc",
    "trx",
    "sol",
)
# How long the account's coin list and a coin's smallest payment are remembered (seconds). The
# list changes when staff switch a coin on or off; a minimum moves with network fees.
COINS_TTL = 900.0
MINIMUM_TTL = 300.0
_coins: tuple[float, list[dict]] | None = None
_minimums: dict[str, tuple[float, decimal.Decimal | None]] = {}


def is_configured() -> bool:
    return get_settings().nowpayments_configured


def payout_configured() -> bool:
    return get_settings().nowpayments_payout_configured


async def _get(path: str) -> tuple[int, object]:
    """GET on the NOWPayments API with the account's key: (status, parsed body or None)."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{settings.nowpayments_base_url}{path}",
            headers={"x-api-key": settings.nowpayments_api_key},
        )
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, None


def _coin(code: str, details: dict | None) -> dict:
    """One coin as the picker shows it. NOWPayments names a token with its network in the
    name ("Tether USD (Tron)"); the code is what an invoice is made for."""
    info = details or {}
    return {
        "code": code,
        "ticker": str(info.get("ticker") or code).upper(),
        "name": str(info.get("name") or code.upper()),
        "network": str(info.get("network") or "").upper() or None,
        "stable": bool(info.get("is_stable")),
        "popular": bool(info.get("is_popular")) or code in FEATURED,
        # a payment in this coin needs a memo / tag as well as the address
        "memo": bool(info.get("extra_id_exists")),
    }


def _coin_order(coin: dict) -> tuple:
    featured = FEATURED.index(coin["code"]) if coin["code"] in FEATURED else len(FEATURED)
    return (featured, not coin["stable"], not coin["popular"], coin["name"].lower(), coin["code"])


async def list_coins() -> list[dict]:
    """The coins a member can pay with: the ones switched on in the NOWPayments account
    (Settings -> Payments). The most used come first (``FEATURED``), then stablecoins, then
    the popular ones, then the rest by name. Remembered for ``COINS_TTL``; a failure answers
    with the last list when there is one."""
    global _coins
    if not is_configured():
        raise AppError("PAYMENTS_NOT_CONFIGURED", "NOWPayments is not configured.", status_code=503)
    now = time.monotonic()
    if _coins is not None and now - _coins[0] < COINS_TTL:
        return _coins[1]
    try:
        status, body = await _get("/merchant/coins")
        selected = (body or {}) if isinstance(body, dict) else {}
        codes = selected.get("selectedCurrencies") or selected.get("currencies") or []
        if status != 200 or not isinstance(codes, list):
            raise AppError(
                "PAYMENT_PROVIDER_ERROR",
                f"NOWPayments did not give its coins ({status}).",
                status_code=502,
            )
        _status, full = await _get("/full-currencies")
    except httpx.HTTPError as exc:
        if _coins is not None:
            return _coins[1]
        raise AppError(
            "PAYMENT_PROVIDER_ERROR", "NOWPayments cannot be reached.", status_code=502
        ) from exc
    listed = full.get("currencies") if isinstance(full, dict) else None
    known = {
        str(item["code"]).lower(): item
        for item in listed or []
        if isinstance(item, dict) and item.get("code")
    }
    coins = []
    for raw in codes:
        code = str(raw).lower()
        details = known.get(code)
        if details is not None and details.get("available_for_payment") is False:
            continue
        coins.append(_coin(code, details))
    coins.sort(key=_coin_order)
    _coins = (now, coins)
    return coins


async def minimum_usd(coin: str) -> decimal.Decimal | None:
    """The smallest payment NOWPayments takes in ``coin`` right now, in USD; None when it does
    not say (the invoice is then made anyway and NOWPayments has the last word)."""
    code = coin.lower()
    now = time.monotonic()
    cached = _minimums.get(code)
    if cached is not None and now - cached[0] < MINIMUM_TTL:
        return cached[1]
    value = None
    path = f"/min-amount?currency_from={code}&fiat_equivalent=usd"
    try:
        # towards the account's own outcome currency; else the coin kept as it is
        for query in (path, f"{path}&currency_to={code}"):
            status, body = await _get(query)
            usd = body.get("fiat_equivalent") if status == 200 and isinstance(body, dict) else None
            if isinstance(usd, int | float) and usd > 0:
                value = decimal.Decimal(str(usd)).quantize(_CENT, rounding=decimal.ROUND_UP)
                break
    except httpx.HTTPError:
        return None  # not remembered: asked again next time
    _minimums[code] = (now, value)
    return value


async def create_checkout(
    *,
    payment_id: uuid.UUID,
    amount: decimal.Decimal,
    currency: str,
    success_url: str,
    cancel_url: str,
    ipn_url: str,
    pay_currency: str | None = None,
) -> CheckoutResult:
    """A hosted invoice for ``amount``. With ``pay_currency`` (a code of ``list_coins``) it is
    an invoice for that one coin: its page asks for nothing but the transfer."""
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
    if pay_currency:
        coin = pay_currency.lower()
        if coin not in {c["code"] for c in await list_coins()}:
            raise AppError(
                "UNKNOWN_COIN",
                "This coin is not accepted. Choose one from the list.",
                status_code=422,
            )
        floor = await minimum_usd(coin)
        if floor is not None and amount < floor:
            raise AppError(
                "CRYPTO_AMOUNT_TOO_SMALL",
                f"The smallest payment in {coin.upper()} is about {floor} {currency.upper()} "
                "right now. Choose another coin or a larger amount.",
                status_code=422,
                details={"coin": coin, "minimum": str(floor)},
            )
        body["pay_currency"] = coin
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{settings.nowpayments_base_url}/invoice",
            json=body,
            headers={"x-api-key": settings.nowpayments_api_key},
        )
    if resp.status_code >= 400:
        said = resp.text.lower()
        if pay_currency and resp.status_code == 400 and ("minimal" in said or "too small" in said):
            # under the coin's minimum after all (it moved since it was asked)
            raise AppError(
                "CRYPTO_AMOUNT_TOO_SMALL",
                f"This amount is under the smallest payment in {body['pay_currency'].upper()} "
                "right now. Choose another coin or a larger amount.",
                status_code=422,
                details={"coin": body["pay_currency"]},
            )
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
        accepted = _signature_ok(secret, raw_body, signature)
    except (ValueError, UnicodeDecodeError):
        raise AppError("BAD_PAYLOAD", "IPN body is not valid JSON.", status_code=400) from None
    if not accepted:
        raise _refused("payout", raw_body)
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


def _dec(value: object) -> decimal.Decimal | None:
    try:
        return decimal.Decimal(str(value)) if value not in (None, "") else None
    except (decimal.InvalidOperation, ValueError):
        return None


def is_extra(data: dict) -> bool:
    """A deposit NOWPayments attached to an earlier payment of the same invoice: a second
    transfer to its address, or one it recovered from another coin or network (its dashboard
    labels them "Re-deposit" and "Wrong Asset")."""
    return data.get("parent_payment_id") not in (None, "", 0, "0")


def received_value(data: dict) -> decimal.Decimal | None:
    """What a payment that is not simply its invoice paid is worth, in the invoice's currency.

    An under-payment in the coin asked for is worth its share of the price, at the rate the
    payer was quoted. An extra deposit has no quoted rate (what it "asked" is whatever
    arrived), so only NOWPayments' own valuation of it counts. None when neither can be told:
    a person decides then."""
    price = _dec(data.get("price_amount"))
    fiat = _dec(data.get("actually_paid_at_fiat"))
    asked, paid = _dec(data.get("pay_amount")), _dec(data.get("actually_paid"))
    value = None
    if is_extra(data):
        value = fiat
    elif price is not None and asked and paid and asked > 0 and paid > 0:
        value = min(price, price * paid / asked)
    elif fiat is not None:
        value = fiat if price is None else min(price, fiat)
    if value is None:
        return None
    value = value.quantize(_CENT, rounding=decimal.ROUND_HALF_UP)
    return value if value > 0 else None


async def fetch_payment(payment_id: str) -> dict | None:
    """One payment as NOWPayments has it now (the API key is enough); None when it cannot be
    read."""
    try:
        status, body = await _get(f"/payment/{quote(str(payment_id), safe='')}")
    except httpx.HTTPError:
        return None
    return body if status == 200 and isinstance(body, dict) else None


async def value_now(data: dict) -> tuple[decimal.Decimal, str] | None:
    """What received money is worth when its notification does not say: (value, how).

    First NOWPayments' own record of the payment, read again ("record": a notification can
    leave before the fiat value is worked out). Then its rate for the coin right now ("rate"):
    how much of the coin the invoice's price buys today, and so what the amount that arrived
    is worth. None when neither tells: a person decides."""
    payment_id = data.get("payment_id")
    record = await fetch_payment(str(payment_id)) if payment_id is not None else None
    if record is not None:
        ours, theirs = data.get("order_id"), record.get("order_id")
        if str(record.get("payment_id")) != str(payment_id) or (
            ours and theirs and str(ours) != str(theirs)
        ):
            record = None  # not the payment that was asked for: not believed
    if record is not None:
        if is_extra(data) and not is_extra(record):
            # an extra deposit stays one, whatever the record leaves out: what it "asked" is
            # whatever arrived, so its share of the price says nothing
            record = {**record, "parent_payment_id": data["parent_payment_id"]}
        value = received_value(record)
        if value is not None:
            return value, "record"

    def known(key: str) -> object:
        mine = data.get(key)
        return mine if mine not in (None, "") else (record or {}).get(key)

    price, paid = _dec(known("price_amount")), _dec(known("actually_paid"))
    coin, fiat = known("pay_currency"), known("price_currency")
    if not (price and paid and coin and fiat) or price <= 0 or paid <= 0:
        return None
    path = (
        f"/estimate?amount={price}&currency_from={quote(str(fiat).lower(), safe='')}"
        f"&currency_to={quote(str(coin).lower(), safe='')}"
    )
    try:
        status, body = await _get(path)
    except httpx.HTTPError:
        return None
    asked = _dec(body.get("estimated_amount")) if status == 200 and isinstance(body, dict) else None
    if not asked or asked <= 0:
        return None
    value = price * paid / asked
    if not is_extra(data):
        value = min(price, value)
    value = value.quantize(_CENT, rounding=decimal.ROUND_HALF_UP)
    return (value, "rate") if value > 0 else None


class _Literal:
    """A JSON number kept as the text it arrived in."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def _js_number(text: str) -> str:
    """A JSON number the way JavaScript writes its value (what ``JSON.stringify`` gives):
    0.000083 whether it arrived as 0.000083 or 8.3e-05, 1e-7 for 1e-07, 13 for 13.0."""
    whole = text.lstrip("-")
    if whole.isdigit() and len(whole) <= 15:
        return str(int(text))
    try:
        number = float(text)
    except ValueError:
        return text
    if number != number or number in (float("inf"), float("-inf")):
        return text
    if number == 0:
        return "0"
    # the shortest digits that give the number back (Python and JavaScript agree on these);
    # only where the point goes and when an exponent is used differ
    _negative, digits, exponent = decimal.Decimal(repr(abs(number))).as_tuple()
    point = len(digits) + exponent  # digits before the decimal point
    shown = "".join(map(str, digits)).rstrip("0") or "0"
    if len(shown) <= point <= 21:
        out = shown + "0" * (point - len(shown))
    elif 0 < point <= 21:
        out = f"{shown[:point]}.{shown[point:]}"
    elif -6 < point <= 0:
        out = "0." + "0" * (-point) + shown
    else:
        power = point - 1
        mantissa = shown[0] + (f".{shown[1:]}" if len(shown) > 1 else "")
        out = f"{mantissa}e{'+' if power >= 0 else '-'}{abs(power)}"
    return f"-{out}" if number < 0 else out


def _signed_text(value: object, *, lists_as_objects: bool = False, javascript: bool = False) -> str:
    """``value`` the way NOWPayments' ``JSON.stringify(sortObject(params))`` writes it: keys
    sorted at every level, nothing between tokens, text not escaped to ASCII, and every number
    spelled as it was sent (or, with ``javascript``, as JavaScript spells its value)."""
    again = {"lists_as_objects": lists_as_objects, "javascript": javascript}
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                f"{json.dumps(key, ensure_ascii=False)}:{_signed_text(value[key], **again)}"
                for key in sorted(value)
            )
            + "}"
        )
    if isinstance(value, list):
        items = [_signed_text(item, **again) for item in value]
        if lists_as_objects:  # their sortObject turns a list into {"0": …, "1": …}
            return "{" + ",".join(f'"{i}":{item}' for i, item in enumerate(items)) + "}"
        return "[" + ",".join(items) + "]"
    if isinstance(value, _Literal):
        return _js_number(value.text) if javascript else value.text
    return json.dumps(value, ensure_ascii=False)


def _sign(secret: str, text: str) -> str:
    return hmac.new(secret.encode(), text.encode(), hashlib.sha512).hexdigest()


def signatures(secret: str, raw_body: bytes) -> list[str]:
    """Every signature a genuine notification of this body can carry.

    NOWPayments signs the JavaScript text of the key-sorted payload. Python spells some
    numbers differently (0.000083 becomes 8.3e-05, 1e-7 becomes 1e-07), so re-serialising the
    parsed body refused every notification that carried a small fee, which is what a paid
    BNB, BTC or ETH payment carries (found 2026-10-06). The numbers are therefore kept as
    they were sent, and also tried as JavaScript spells their values (should the body ever be
    written by something else than what signed it). A list is tried both as a list and as
    their documented sortObject would write it, and the old Python spelling stays accepted."""
    body = raw_body.decode("utf-8")
    kept = json.loads(body, parse_float=_Literal, parse_int=_Literal)
    legacy = json.dumps(json.loads(body), sort_keys=True, separators=(",", ":"))
    texts = [
        _signed_text(kept),
        _signed_text(kept, lists_as_objects=True),
        _signed_text(kept, javascript=True),
        _signed_text(kept, javascript=True, lists_as_objects=True),
        legacy,
    ]
    return [_sign(secret, text) for text in dict.fromkeys(texts)]


def compute_signature(secret: str, raw_body: bytes) -> str:
    """HMAC-SHA512 of the key-sorted, compact payload, as NOWPayments signs it."""
    return signatures(secret, raw_body)[0]


def _signature_ok(secret: str, raw_body: bytes, signature: str | None) -> bool:
    """Raises ValueError / UnicodeDecodeError when the body is not JSON."""
    given = (signature or "").strip().lower()
    return bool(given) and any(
        hmac.compare_digest(expected, given) for expected in signatures(secret, raw_body)
    )


def _refused(kind: str, raw_body: bytes) -> AppError:
    """A notification whose signature is none we accept. What it carried goes to the server
    log (it holds no secret), so a refusal can be looked into afterwards: in 2026-10 a genuine
    one was refused each time it was sent and nothing on the server said what it carried."""
    logger.warning(
        "NOWPayments %s notification refused, its signature does not match: %r",
        kind,
        raw_body[:2000].decode("utf-8", "replace"),
    )
    return AppError("WEBHOOK_SIGNATURE_INVALID", "Invalid NOWPayments signature.", status_code=401)


def verify_and_parse(raw_body: bytes, signature: str | None) -> ParsedWebhook:
    secret = get_settings().nowpayments_ipn_secret
    if not secret:
        raise AppError(
            "PAYMENTS_NOT_CONFIGURED", "NOWPayments IPN not configured.", status_code=503
        )
    try:
        accepted = _signature_ok(secret, raw_body, signature)
    except (ValueError, UnicodeDecodeError):
        raise AppError("BAD_PAYLOAD", "IPN body is not valid JSON.", status_code=400) from None
    if not accepted:
        raise _refused("payment", raw_body)

    data = json.loads(raw_body.decode("utf-8"))
    ps = str(data.get("payment_status", ""))
    provider_payment_id = (
        str(data.get("payment_id")) if data.get("payment_id") is not None else None
    )
    captured = None
    if ps in _FAILED:
        status = "failed"
    elif ps == "finished" and not is_extra(data):
        status = "succeeded"  # the invoice, paid in the coin and amount it asked for
        if data.get("price_amount") is not None:
            captured = decimal.Decimal(str(data["price_amount"]))
    elif ps in ("finished", "partially_paid"):
        status = "received"  # money that is not the invoice simply paid
        captured = received_value(data)
    else:
        status = "pending"
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
