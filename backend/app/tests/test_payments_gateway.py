"""Phase 4 — DB-free unit tests for the payment-provider signature verification
and decision mapping (the automation core that needs no DB/network)."""

from __future__ import annotations

import decimal
import hashlib
import hmac
import json
import time
import types
import uuid

import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.integrations.payments import nowpayments_gateway as nowp
from app.services.integrations.payments import stripe_gateway as stripe


def _stripe_header(secret: str, body: bytes, ts: str = "1700000000") -> str:
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_stripe_verifies_and_maps_paid_session(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_1",
                "client_reference_id": "11111111-1111-1111-1111-111111111111",
                "payment_status": "paid",
                "amount_total": 5000,
                "currency": "usd",
            }
        },
    }
    body = json.dumps(event).encode()
    out = stripe.verify_and_parse(body, _stripe_header("whsec_t", body))
    assert out.status == "succeeded"
    assert out.captured_amount == 50  # 5000 cents -> $50
    assert out.order_id == "11111111-1111-1111-1111-111111111111"
    assert out.event_id == "evt_1"


def test_stripe_rejects_forged_signature(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    body = b'{"id":"evt_2","type":"checkout.session.completed","data":{"object":{}}}'
    with pytest.raises(AppError) as exc:
        stripe.verify_and_parse(body, "t=1700000000,v1=deadbeef")
    assert exc.value.code == "WEBHOOK_SIGNATURE_INVALID"
    assert exc.value.status_code == 401


# --- Stripe Connect (money out) ---------------------------------------------- #
def test_each_stripe_endpoint_is_verified_with_its_own_secret(monkeypatch) -> None:
    """Stripe gives the deposits endpoint and the Connect endpoint different secrets."""
    s = get_settings()
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    monkeypatch.setattr(s, "stripe_connect_webhook_secret", "whsec_connect", raising=False)
    event = {
        "id": "evt_c1",
        "type": "account.updated",
        "account": "acct_1",
        "data": {"object": {"id": "acct_1"}},
    }
    body = json.dumps(event).encode()
    out = stripe.parse_payout_event(body, _stripe_header("whsec_connect", body))
    assert (out.kind, out.account_id) == ("account", "acct_1")
    # the deposits endpoint does not take the Connect endpoint's signature
    with pytest.raises(AppError) as exc:
        stripe.verify_and_parse(body, _stripe_header("whsec_connect", body))
    assert exc.value.code == "WEBHOOK_SIGNATURE_INVALID"
    with pytest.raises(AppError) as exc:
        stripe.parse_payout_event(body, _stripe_header("whsec_other", body))
    assert exc.value.status_code == 401


def test_connect_endpoint_takes_the_single_cli_secret(monkeypatch) -> None:
    """`stripe listen` signs everything it forwards with one secret (local development)."""
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_cli", raising=False)
    body = json.dumps(
        {"id": "evt_c2", "type": "account.updated", "data": {"object": {"id": "acct_2"}}}
    ).encode()
    assert stripe.parse_payout_event(body, _stripe_header("whsec_cli", body)).kind == "account"


def test_connect_endpoint_without_any_secret_is_unavailable() -> None:
    body = b'{"id":"evt_c3","type":"account.updated","data":{"object":{}}}'
    with pytest.raises(AppError) as exc:
        stripe.parse_payout_event(body, _stripe_header("whsec_x", body))
    assert exc.value.status_code == 503


def test_payout_events_name_the_connected_account(monkeypatch) -> None:
    monkeypatch.setattr(
        get_settings(), "stripe_connect_webhook_secret", "whsec_connect", raising=False
    )
    event = {
        "id": "evt_p1",
        "type": "payout.failed",
        "account": "acct_9",
        "data": {"object": {"id": "po_1", "metadata": {"withdrawal_id": "w1"}}},
    }
    body = json.dumps(event).encode()
    out = stripe.parse_payout_event(body, _stripe_header("whsec_connect", body))
    assert (out.kind, out.status, out.provider_payout_id) == ("payout", "failed", "po_1")
    assert (out.withdrawal_id, out.account_id) == ("w1", "acct_9")


def test_events_stripe_no_longer_sends_are_not_payout_outcomes(monkeypatch) -> None:
    """transfer.paid / transfer.failed were retired and payout.returned never existed."""
    monkeypatch.setattr(
        get_settings(), "stripe_connect_webhook_secret", "whsec_connect", raising=False
    )
    for etype in ("transfer.paid", "transfer.failed", "payout.returned", "charge.refunded"):
        body = json.dumps({"id": etype, "type": etype, "data": {"object": {"id": "x"}}}).encode()
        out = stripe.parse_payout_event(body, _stripe_header("whsec_connect", body))
        assert out.kind == "ignored", etype


@pytest.mark.asyncio
async def test_a_transfer_is_final_once_stripe_accepts_it(monkeypatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test_x", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    sent: dict = {}

    async def fake_post(path, data, **kw):
        sent.update(path=path, data=data, **kw)
        return {"id": "tr_123"}

    monkeypatch.setattr(stripe, "_post", fake_post)
    out = await stripe.create_payout(
        withdrawal_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        account_id="acct_1",
        amount=decimal.Decimal("12.34"),
        currency="USD",
        idempotency_key="k1",
    )
    assert (out.provider_payout_id, out.status) == ("tr_123", "settled")
    assert (sent["path"], sent["idempotency_key"]) == ("transfers", "k1")
    assert (sent["data"]["amount"], sent["data"]["destination"]) == ("1234", "acct_1")


def test_nowpayments_signature_is_sorted_hmac_sha512() -> None:
    secret = "ipn_secret"
    body = b'{"payment_status":"finished","order_id":"x","payment_id":99}'
    expected = hmac.new(
        secret.encode(),
        json.dumps(json.loads(body), sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha512,
    ).hexdigest()
    assert nowp.compute_signature(secret, body) == expected


def test_nowpayments_verifies_finished_and_maps_amount(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    payload = {
        "payment_id": 555,
        "order_id": "22222222-2222-2222-2222-222222222222",
        "payment_status": "finished",
        "price_amount": 75.0,
        "price_currency": "usd",
    }
    body = json.dumps(payload).encode()
    sig = nowp.compute_signature("ipn_t", body)
    out = nowp.verify_and_parse(body, sig)
    assert out.status == "succeeded"
    assert out.captured_amount == 75
    assert out.order_id == "22222222-2222-2222-2222-222222222222"
    assert out.event_id == "555:finished"


def test_nowpayments_rejects_bad_signature(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    body = b'{"payment_id":1,"payment_status":"finished"}'
    with pytest.raises(AppError) as exc:
        nowp.verify_and_parse(body, "wrong")
    assert exc.value.code == "WEBHOOK_SIGNATURE_INVALID"
    with pytest.raises(AppError) as exc:
        nowp.verify_and_parse(body, None)
    assert exc.value.code == "WEBHOOK_SIGNATURE_INVALID"


def _hmac512(secret: str, text: str) -> str:
    return hmac.new(secret.encode(), text.encode(), hashlib.sha512).hexdigest()


def test_nowpayments_accepts_a_small_number_as_javascript_writes_it(monkeypatch) -> None:
    """Regression (prod, 2026-10-06): the notification of a deposit recovered from another coin
    carried a network fee of 0.000083 BNB and was refused with 401. NOWPayments signs
    JSON.stringify of the key-sorted payload; Python re-serialised that fee as 8.3e-05, so no
    notification with a small fee (a paid BNB, BTC or ETH payment) could ever settle."""
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    body = (
        b'{"payment_id":4870885867,"parent_payment_id":6160305429,'
        b'"payment_status":"partially_paid","price_amount":13,"pay_amount":13,'
        b'"actually_paid":13,"actually_paid_at_fiat":12.98513924,"pay_currency":"usdtbsc",'
        b'"order_id":"cf5910cb-5a46-4489-b1dc-f0dffe6da8da","outcome_amount":0.01633459,'
        b'"fee":{"currency":"bnbbsc","depositFee":0.000083,"withdrawalFee":0,'
        b'"serviceFee":0.000249},"tiny":1e-7}'
    )
    # what JSON.stringify(sortObject(params)) gives for that payload
    signed = (
        '{"actually_paid":13,"actually_paid_at_fiat":12.98513924,'
        '"fee":{"currency":"bnbbsc","depositFee":0.000083,"serviceFee":0.000249,'
        '"withdrawalFee":0},"order_id":"cf5910cb-5a46-4489-b1dc-f0dffe6da8da",'
        '"outcome_amount":0.01633459,"parent_payment_id":6160305429,"pay_amount":13,'
        '"pay_currency":"usdtbsc","payment_id":4870885867,"payment_status":"partially_paid",'
        '"price_amount":13,"tiny":1e-7}'
    )
    out = nowp.verify_and_parse(body, _hmac512("ipn_t", signed))
    assert out.type == "partially_paid" and out.provider_payment_id == "4870885867"
    assert nowp.compute_signature("ipn_t", body) == _hmac512("ipn_t", signed)
    # the same signature in capitals, and Python's own spelling of the numbers, still pass
    nowp.verify_and_parse(body, _hmac512("ipn_t", signed).upper())
    python_text = json.dumps(json.loads(body), sort_keys=True, separators=(",", ":"))
    assert "8.3e-05" in python_text and "1e-07" in python_text
    nowp.verify_and_parse(body, _hmac512("ipn_t", python_text))
    # a signature over anything else is still refused
    with pytest.raises(AppError):
        nowp.verify_and_parse(body, _hmac512("ipn_t", signed.replace("12.98513924", "13")))
    with pytest.raises(AppError):
        nowp.verify_and_parse(body, _hmac512("other-secret", signed))


def test_nowpayments_accepts_a_body_another_language_wrote(monkeypatch) -> None:
    """The signature is JavaScript's text of the VALUES. Should the body ever be written by
    something that spells numbers its own way (8.3e-05, 13.0, 1E-7), the values are the same
    and the notification is genuine: it must not be refused for its spelling."""
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    body = (
        b'{"payment_id": 4870885867, "payment_status": "partially_paid", "price_amount": 13.0,'
        b' "actually_paid": 13.00, "outcome_amount": 1.633459E-2,'
        b' "fee": {"depositFee": 8.3e-05, "serviceFee": 2.49e-4, "withdrawalFee": 0.0},'
        b' "tiny": 1E-7, "big": 1.5e+21, "whole": 250000.0}'
    )
    signed = (
        '{"actually_paid":13,"big":1.5e+21,"fee":{"depositFee":0.000083,"serviceFee":0.000249,'
        '"withdrawalFee":0},"outcome_amount":0.01633459,"payment_id":4870885867,'
        '"payment_status":"partially_paid","price_amount":13,"tiny":1e-7,"whole":250000}'
    )
    assert nowp.verify_and_parse(body, _hmac512("ipn_t", signed)).type == "partially_paid"
    with pytest.raises(AppError):  # other values are another payload
        nowp.verify_and_parse(body, _hmac512("ipn_t", signed.replace("0.000083", "0.00083")))
    for sent, javascript in [
        ("0.000083", "0.000083"),
        ("8.3e-05", "0.000083"),
        ("0.000001", "0.000001"),
        ("1e-07", "1e-7"),
        ("1.5E-7", "1.5e-7"),
        ("13.0", "13"),
        ("13", "13"),
        ("-0", "0"),
        ("-2.50", "-2.5"),
        ("0.1", "0.1"),
        ("100.5", "100.5"),
        ("123456.789", "123456.789"),
        ("4870885867", "4870885867"),
        ("1e20", "100000000000000000000"),
        ("1e21", "1e+21"),
        ("12345678901234567890", "12345678901234567000"),
    ]:
        assert nowp._js_number(sent) == javascript, sent


def test_a_refused_nowpayments_notification_is_logged(monkeypatch, caplog) -> None:
    """In 2026-10 a genuine notification was refused for days and nothing on the server said
    what it carried. A refusal now leaves its body in the log (no secret is in it)."""
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    body = (
        b'{"payment_id":4870885867,"payment_status":"partially_paid","fee":{"depositFee":0.000083}}'
    )
    with caplog.at_level("WARNING"), pytest.raises(AppError) as exc:
        nowp.verify_and_parse(body, "0" * 128)
    assert exc.value.status_code == 401
    assert "payment notification refused" in caplog.text
    assert "4870885867" in caplog.text and "0.000083" in caplog.text
    assert "ipn_t" not in caplog.text
    with caplog.at_level("WARNING"), pytest.raises(AppError):
        nowp.verify_payout_ipn(b'{"id":"77","status":"FINISHED"}', "0" * 128)
    assert "payout notification refused" in caplog.text
    # an accepted one leaves nothing
    caplog.clear()
    with caplog.at_level("WARNING"):
        nowp.verify_and_parse(body, nowp.compute_signature("ipn_t", body))
    assert "refused" not in caplog.text


def test_nowpayments_accepts_a_list_either_way_and_text_as_sent(monkeypatch) -> None:
    """Their documented sortObject rewrites a list as {"0": …, "1": …}; JSON.stringify leaves
    non-ASCII text and slashes as they are."""
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    body = (
        '{"payment_status":"waiting","payment_id":7,"payment_extra_ids":[20,3],'
        '"order_description":"شقة/1"}'
    ).encode()
    as_list = (
        '{"order_description":"شقة/1","payment_extra_ids":[20,3],"payment_id":7,'
        '"payment_status":"waiting"}'
    )
    as_object = as_list.replace("[20,3]", '{"0":20,"1":3}')
    for text in (as_list, as_object):
        assert nowp.verify_and_parse(body, _hmac512("ipn_t", text)).status == "pending"
    with pytest.raises(AppError) as exc:
        nowp.verify_and_parse(b"not json", "x")
    assert exc.value.code == "BAD_PAYLOAD"


def test_nowpayments_status_mapping(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    for ps, expected in [
        ("finished", "succeeded"),
        ("failed", "failed"),
        ("expired", "failed"),
        ("partially_paid", "received"),
        ("confirming", "pending"),
    ]:
        body = json.dumps({"payment_id": 1, "payment_status": ps}).encode()
        out = nowp.verify_and_parse(body, nowp.compute_signature("ipn_t", body))
        assert out.status == expected, ps
    # a deposit added to an invoice is never "the invoice paid", even when marked finished
    body = json.dumps(
        {"payment_id": 2, "parent_payment_id": 1, "payment_status": "finished", "price_amount": 50}
    ).encode()
    out = nowp.verify_and_parse(body, nowp.compute_signature("ipn_t", body))
    assert (out.status, out.captured_amount) == ("received", None)


def test_nowpayments_values_what_arrived() -> None:
    """An under-payment in the coin asked for: its share of the price, at the rate quoted. An
    extra deposit (it has a parent): only NOWPayments' own valuation, because what it "asked"
    is whatever arrived, so a share would always be the whole price."""
    value = nowp.received_value
    asked = {"price_amount": 100, "pay_amount": 0.002, "actually_paid": 0.0015}
    assert value(asked) == decimal.Decimal("75.00")
    assert value({**asked, "actually_paid": 0.004}) == decimal.Decimal("100.00")  # never more
    assert value({**asked, "actually_paid": 0}) is None
    assert value({"price_amount": 13, "actually_paid_at_fiat": 12.98513924}) == decimal.Decimal(
        "12.99"
    )
    extra = {
        "parent_payment_id": 6160305429,
        "price_amount": 13,
        "pay_amount": 13,
        "actually_paid": 13,
    }
    assert value(extra) is None
    assert value({**extra, "actually_paid_at_fiat": 12.98513924}) == decimal.Decimal("12.99")
    assert value({**extra, "actually_paid_at_fiat": 20.5}) == decimal.Decimal("20.50")
    assert value({**extra, "actually_paid_at_fiat": 0.001}) is None  # rounds to nothing
    assert not nowp.is_extra({"parent_payment_id": None}) and nowp.is_extra(extra)


@pytest.mark.asyncio
async def test_nowpayments_is_asked_what_unvalued_money_is_worth(monkeypatch, caplog) -> None:
    """A notification that carries no fiat value: NOWPayments' rate for the coin tells what the
    amount that arrived is worth. Its record of a payment carries no value (seen on the server,
    2026-10-06), so it is read only for what a notification leaves out. Asked too often it
    answers 429: it is asked again. Nothing it cannot be asked is guessed."""
    answers: dict = {}
    asked: list[str] = []

    async def fake_get(path: str):
        asked.append(path)
        answer = answers.get(path)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, list):  # answers in turn, the last one from then on
            return answer.pop(0) if len(answer) > 1 else answer[0]
        return (200, answer) if path in answers else (404, None)

    monkeypatch.setattr(nowp, "_get", fake_get)
    monkeypatch.setattr(nowp, "RETRY_PAUSES", (0, 0))
    rate = "/estimate?amount=13&currency_from=usd&currency_to=usdtbsc"
    extra = {
        "payment_id": 4870885867,
        "parent_payment_id": 6160305429,
        "order_id": "order-1",
        "price_amount": 13,
        "price_currency": "USD",
        "pay_amount": 13,
        "actually_paid": 13,
        "actually_paid_at_fiat": 0,
        "pay_currency": "USDTBSC",
    }
    with caplog.at_level("WARNING"):
        assert await nowp.value_now(extra) is None
    # the record is not read: the notification has all a rate needs
    assert asked == [rate]
    # why it could not be valued is in the server log: what each step answered
    assert "payment 4870885867 could not be valued" in caplog.text
    assert "its notification says fiat 0" in caplog.text
    assert f"its rate {rate} (HTTP 404) answers" in caplog.text

    # what the server was answered on 2026-10-06: 13 USD buys 13.00982534 USDT, 13 arrived
    answers[rate] = {"currency_from": "usd", "amount_from": 13, "estimated_amount": "13.00982534"}
    assert await nowp.value_now(extra) == (decimal.Decimal("12.99"), "rate")
    # an extra deposit is worth what arrived even above the invoice, an under-payment never
    # more than its price
    assert await nowp.value_now({**extra, "actually_paid": 40}) == (
        decimal.Decimal("39.97"),
        "rate",
    )
    under = {k: v for k, v in extra.items() if k not in ("parent_payment_id", "pay_amount")}
    assert await nowp.value_now({**under, "actually_paid": 40}) == (
        decimal.Decimal("13.00"),
        "rate",
    )

    # refused for being asked too often, twice, then answered: asked again, valued
    asked.clear()
    answers[rate] = [(429, None), (429, None), (200, {"estimated_amount": "13.00982534"})]
    assert await nowp.value_now(extra) == (decimal.Decimal("12.99"), "rate")
    assert asked == [rate, rate, rate]
    # still refused after the pauses: no value, and the log says so
    answers[rate] = [(429, None)]
    caplog.clear()
    with caplog.at_level("WARNING"):
        assert await nowp.value_now(extra) is None
    assert "(HTTP 429)" in caplog.text
    # an answer that is no rate, and NOWPayments out of reach: no value, asked once
    for bad in ({"estimated_amount": 0}, {"message": "no"}, nowp.httpx.ConnectError("down")):
        answers[rate] = bad
        asked.clear()
        assert await nowp.value_now(extra) is None
        assert asked == [rate]

    # a notification that leaves out its coin and currency: the record is read for them
    bare = {k: v for k, v in extra.items() if k not in ("price_currency", "pay_currency")}
    record = {
        "payment_id": 4870885867,
        "order_id": "order-1",
        "price_amount": 13,
        "price_currency": "usd",
        "pay_amount": 13,
        "actually_paid": 13,
        "pay_currency": "usdtbsc",
    }
    answers["/payment/4870885867"] = record
    answers[rate] = {"estimated_amount": "13.00982534"}
    asked.clear()
    assert await nowp.value_now(bare) == (decimal.Decimal("12.99"), "rate")
    assert asked == ["/payment/4870885867", rate]
    # a record that values the payment itself is believed, and the payment stays an extra
    # deposit when the record names no parent (13 of the 13 it "asked" is not the whole price)
    answers["/payment/4870885867"] = {**record, "actually_paid_at_fiat": 12.98513924}
    assert await nowp.value_now(bare) == (decimal.Decimal("12.99"), "record")
    # a record of another payment or another order is not believed
    for wrong in ({"payment_id": 1}, {"order_id": "order-2"}):
        answers["/payment/4870885867"] = {**record, "actually_paid_at_fiat": 50, **wrong}
        assert await nowp.value_now(bare) is None
    assert await nowp.value_now({"payment_id": None, "price_amount": 13}) is None


class _FakeNowHTTP:
    """Stands in for httpx.AsyncClient on the invoice call: records what was asked."""

    def __init__(self, sent: list[dict]):
        self.sent = sent

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.sent.append({"url": url, "json": json, "headers": headers})
        status, said = 200, ""
        if json["price_amount"] == 1.5:  # NOWPayments' own refusal of an amount under a minimum
            status = 400
            said = '{"code":"AMOUNT_MINIMAL_ERROR","message":"amountTo is too small"}'
        if json["price_amount"] == 7.0:
            status, said = 500, "boom"
        return types.SimpleNamespace(
            status_code=status,
            text=said,
            json=lambda: {"id": "4455", "invoice_url": "https://nowpayments.io/payment/?iid=4455"},
        )


@pytest.mark.asyncio
async def test_nowpayments_invoice_is_made_for_the_coin_chosen(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "nowpayments_api_key", "key_t", raising=False)
    monkeypatch.setattr(settings, "nowpayments_ipn_secret", "ipn_t", raising=False)
    monkeypatch.setattr(nowp, "_coins", None)
    monkeypatch.setattr(nowp, "_minimums", {})
    asked: list[str] = []

    async def fake_get(path: str):
        asked.append(path)
        if path == "/merchant/coins":
            return 200, {"selectedCurrencies": ["USDTBSC", "BTC"]}
        if path == "/full-currencies":
            return 200, {"currencies": [{"code": "USDTBSC", "name": "Tether USD (BSC)"}]}
        if path.startswith("/min-amount?currency_from=btc") and "currency_to" not in path:
            return 400, {"message": "currency_to is required"}
        if path.startswith("/min-amount?currency_from=btc"):
            return 200, {"min_amount": 0.0002, "fiat_equivalent": 18.431}
        return 200, {"min_amount": 1.2, "fiat_equivalent": 1.2}

    sent: list[dict] = []
    monkeypatch.setattr(nowp, "_get", fake_get)
    monkeypatch.setattr(nowp.httpx, "AsyncClient", _FakeNowHTTP(sent))
    common = dict(
        payment_id=uuid.uuid4(),
        currency="USD",
        success_url="https://app.t/ok",
        cancel_url="https://app.t/no",
        ipn_url="https://api.t/ipn",
    )
    out = await nowp.create_checkout(amount=decimal.Decimal("13"), pay_currency="USDTBSC", **common)
    assert out.checkout_url.endswith("iid=4455")
    assert sent[0]["json"]["pay_currency"] == "usdtbsc" and sent[0]["json"]["price_amount"] == 13.0
    # no coin given (an older page): an invoice with the choice left to NOWPayments' page
    await nowp.create_checkout(amount=decimal.Decimal("13"), **common)
    assert "pay_currency" not in sent[1]["json"]
    # a coin the account does not take, and an amount under the coin's minimum, are refused
    # before any invoice is made
    with pytest.raises(AppError) as exc:
        await nowp.create_checkout(amount=decimal.Decimal("13"), pay_currency="doge", **common)
    assert exc.value.code == "UNKNOWN_COIN"
    with pytest.raises(AppError) as exc:
        await nowp.create_checkout(amount=decimal.Decimal("13"), pay_currency="btc", **common)
    assert exc.value.code == "CRYPTO_AMOUNT_TOO_SMALL"
    assert exc.value.details == {"coin": "btc", "minimum": "18.44"}  # rounded up to the cent
    assert "about 18.44 USD" in exc.value.message and len(sent) == 2
    # the minimum is remembered for a while, the coin list too
    before = len(asked)
    await nowp.create_checkout(amount=decimal.Decimal("20"), pay_currency="btc", **common)
    assert len(asked) == before and len(sent) == 3
    # the minimum moved since it was asked and NOWPayments refuses the amount itself: said the
    # same way, so the member changes the coin or the amount; any other refusal is its error
    with pytest.raises(AppError) as exc:
        await nowp.create_checkout(amount=decimal.Decimal("1.5"), pay_currency="usdtbsc", **common)
    assert exc.value.code == "CRYPTO_AMOUNT_TOO_SMALL" and exc.value.status_code == 422
    assert exc.value.details == {"coin": "usdtbsc"} and "USDTBSC" in exc.value.message
    with pytest.raises(AppError) as exc:
        await nowp.create_checkout(amount=decimal.Decimal("7"), pay_currency="usdtbsc", **common)
    assert exc.value.code == "PAYMENT_PROVIDER_ERROR" and exc.value.status_code == 502


@pytest.mark.asyncio
async def test_nowpayments_asked_too_often_is_asked_again(monkeypatch) -> None:
    """Seen on the server, 2026-10-06: the third of three requests in a row was answered 429.
    A member's coin list, a coin's minimum and the invoice itself must not fail for that, and
    a list that came without the coins' details must not be kept as if it were whole."""
    settings = get_settings()
    monkeypatch.setattr(settings, "nowpayments_api_key", "key_t", raising=False)
    monkeypatch.setattr(settings, "nowpayments_ipn_secret", "ipn_t", raising=False)
    monkeypatch.setattr(nowp, "_coins", None)
    monkeypatch.setattr(nowp, "_minimums", {})
    monkeypatch.setattr(nowp, "RETRY_PAUSES", (0, 0))
    busy = (429, None)
    turns = {
        "/merchant/coins": [busy, (200, {"selectedCurrencies": ["XRP", "USDTBSC"]})],
        "/full-currencies": [busy],
        "/min-amount?currency_from=usdtbsc&fiat_equivalent=usd": [
            busy,
            (200, {"fiat_equivalent": 1.2}),
        ],
        "/min-amount?currency_from=xrp&fiat_equivalent=usd": [busy],
        "/min-amount?currency_from=xrp&fiat_equivalent=usd&currency_to=xrp": [busy],
    }
    asked: list[str] = []

    async def fake_get(path: str):
        asked.append(path)
        answers = turns[path]
        return answers.pop(0) if len(answers) > 1 else answers[0]

    monkeypatch.setattr(nowp, "_get", fake_get)

    # the list comes on the second asking; its details never do: a stopgap (codes for names,
    # no memo marks) a member can still pay with, kept for a minute only
    coins = await nowp.list_coins()
    assert [(c["code"], c["name"], c["memo"]) for c in coins] == [
        ("usdtbsc", "USDTBSC", False),
        ("xrp", "XRP", False),
    ]
    assert asked.count("/merchant/coins") == 2 and asked.count("/full-currencies") == 3
    left = nowp.COINS_TTL - (time.monotonic() - nowp._coins[0])
    assert left <= nowp.COINS_STOPGAP_TTL + 1
    # the minute over and the details back: the whole list, memo mark and all
    monkeypatch.setattr(nowp, "_coins", (time.monotonic() - nowp.COINS_TTL - 1, coins))
    turns["/full-currencies"] = [
        (200, {"currencies": [{"code": "XRP", "name": "Ripple", "extra_id_exists": True}]})
    ]
    whole = await nowp.list_coins()
    assert (whole[1]["name"], whole[1]["memo"]) == ("Ripple", True)
    assert nowp.COINS_TTL - (time.monotonic() - nowp._coins[0]) > nowp.COINS_STOPGAP_TTL + 1
    # NOWPayments then refusing altogether, or giving no details again, leaves that list
    monkeypatch.setattr(nowp, "_coins", (time.monotonic() - nowp.COINS_TTL - 1, whole))
    turns["/full-currencies"] = [busy]
    assert (await nowp.list_coins())[1]["name"] == "Ripple"
    monkeypatch.setattr(nowp, "_coins", (time.monotonic() - nowp.COINS_TTL - 1, whole))
    turns["/merchant/coins"] = [busy]
    assert (await nowp.list_coins())[1]["name"] == "Ripple"

    # a coin's minimum: refused once, then told; never told is not remembered as "no minimum"
    assert await nowp.minimum_usd("usdtbsc") == decimal.Decimal("1.20")
    assert await nowp.minimum_usd("xrp") is None and "xrp" not in nowp._minimums

    # the invoice: refused once for the same reason, made on the second asking
    sent: list[dict] = []

    class _Busy:
        def __call__(self, *a, **kw):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            sent.append(json)
            return types.SimpleNamespace(
                status_code=429 if len(sent) == 1 else 200,
                text="",
                json=lambda: {"id": "77", "invoice_url": "https://nowpayments.io/payment/?iid=77"},
            )

    monkeypatch.setattr(nowp.httpx, "AsyncClient", _Busy())
    out = await nowp.create_checkout(
        payment_id=uuid.uuid4(),
        amount=decimal.Decimal("13"),
        currency="USD",
        success_url="https://app.t/ok",
        cancel_url="https://app.t/no",
        ipn_url="https://api.t/ipn",
        pay_currency="usdtbsc",
    )
    assert out.provider_payment_id == "77" and len(sent) == 2


class _FakeStripeHTTP:
    """Stands in for httpx.AsyncClient: answers checkout creation from a queue."""

    def __init__(self, answers, calls):
        self.answers, self.calls = answers, calls

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data=None, headers=None, auth=None):
        import httpx

        self.calls.append({"data": dict(data or {}), "headers": dict(headers or {})})
        status, body = self.answers.pop(0)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))


@pytest.mark.asyncio
async def test_checkout_with_a_customer_from_another_mode_still_takes_the_payment(monkeypatch):
    """Keys switched (test -> live, or another account): the stored customer is unknown. The
    payment must still go through, without saved cards, rather than be refused."""
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test_x", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    calls: list = []
    missing = {"error": {"code": "resource_missing", "param": "customer", "message": "No such"}}
    fake = _FakeStripeHTTP([(400, missing), (200, {"id": "cs_1", "url": "https://c"})], calls)
    monkeypatch.setattr(stripe.httpx, "AsyncClient", fake)
    out = await stripe.create_checkout(
        payment_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        amount=decimal.Decimal("10"),
        currency="USD",
        success_url="https://s",
        cancel_url="https://c",
        idempotency_key="dep-1",
        customer_id="cus_old",
    )
    assert out.provider_payment_id == "cs_1"
    assert calls[0]["data"]["customer"] == "cus_old"
    assert "customer" not in calls[1]["data"]
    assert calls[1]["headers"]["Idempotency-Key"] == "dep-1-no-customer"


@pytest.mark.asyncio
async def test_checkout_other_errors_are_not_retried(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test_x", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    calls: list = []
    denied = {"error": {"type": "invalid_request_error", "message": "permission"}}
    monkeypatch.setattr(stripe.httpx, "AsyncClient", _FakeStripeHTTP([(403, denied)], calls))
    with pytest.raises(AppError):
        await stripe.create_checkout(
            payment_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
            amount=decimal.Decimal("10"),
            currency="USD",
            success_url="https://s",
            cancel_url="https://c",
            idempotency_key=None,
            customer_id="cus_1",
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_stripe_refusal_is_logged_with_its_reason(monkeypatch, caplog):
    """With a restricted key a 403 names the missing permission: it must reach the server log."""
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "rk_live_x", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    denied = {
        "error": {
            "type": "invalid_request_error",
            "message": "The provided key does not have the required permissions: customer_write",
        }
    }
    monkeypatch.setattr(stripe.httpx, "AsyncClient", _FakeStripeHTTP([(403, denied)], []))
    with caplog.at_level("WARNING"), pytest.raises(AppError) as exc:
        await stripe.create_customer(email="a@b.c")
    assert "customer_write" in caplog.text
    assert exc.value.status_code == 502 and not stripe.is_unknown_customer(exc.value)


def test_unknown_customer_is_recognised_from_the_refusal() -> None:
    err = AppError(
        "X",
        "Stripe error (400).",
        status_code=502,
        details={"code": "resource_missing", "param": "customer"},
    )
    assert stripe.is_unknown_customer(err)
    other = AppError("X", "e", status_code=502, details={"code": "resource_missing", "param": "pm"})
    assert not stripe.is_unknown_customer(other)


# --- Delayed payment methods + the direct session lookup ---------------------- #
def _session_event(etype: str, *, payment_status: str, event_id: str = "evt_a") -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": etype,
            "data": {
                "object": {
                    "id": "cs_async",
                    "client_reference_id": "22222222-2222-2222-2222-222222222222",
                    "payment_status": payment_status,
                    "amount_total": 1234,
                    "currency": "usd",
                }
            },
        }
    ).encode()


def test_stripe_completed_unpaid_stays_pending_until_async_success(monkeypatch) -> None:
    """A bank-debit checkout completes unpaid, then async_payment_succeeded carries the money."""
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    body = _session_event("checkout.session.completed", payment_status="unpaid")
    out = stripe.verify_and_parse(body, _stripe_header("whsec_t", body))
    assert out.status == "pending" and out.captured_amount is None

    body = _session_event(
        "checkout.session.async_payment_succeeded", payment_status="paid", event_id="evt_b"
    )
    out = stripe.verify_and_parse(body, _stripe_header("whsec_t", body))
    assert out.status == "succeeded"
    assert out.captured_amount == decimal.Decimal("12.34")
    assert out.order_id == "22222222-2222-2222-2222-222222222222"
    assert out.event_id == "evt_b"


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient: one canned GET answer, records the URL."""

    calls: list[str] = []
    answer: _FakeResponse = _FakeResponse(200, {})

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        _FakeClient.calls.append(url)
        return _FakeClient.answer


@pytest.mark.asyncio
async def test_stripe_session_lookup_maps_like_the_webhook(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "stripe_secret_key", "sk_test_x", raising=False)
    monkeypatch.setattr(stripe.httpx, "AsyncClient", _FakeClient)
    session = {
        "id": "cs_look",
        "client_reference_id": "33333333-3333-3333-3333-333333333333",
        "payment_status": "paid",
        "status": "complete",
        "amount_total": 5000,
    }
    _FakeClient.answer = _FakeResponse(200, session)
    out = await stripe.get_checkout_status("cs_look")
    assert _FakeClient.calls[-1].endswith("/checkout/sessions/cs_look")
    assert out.status == "succeeded" and out.captured_amount == 50
    assert out.order_id == "33333333-3333-3333-3333-333333333333"
    assert out.event_id == "sync:cs_look:succeeded"

    _FakeClient.answer = _FakeResponse(
        200, {**session, "payment_status": "unpaid", "status": "open"}
    )
    out = await stripe.get_checkout_status("cs_look")
    assert out.status == "pending" and out.event_id == "sync:cs_look:pending"

    _FakeClient.answer = _FakeResponse(
        200, {**session, "payment_status": "unpaid", "status": "expired"}
    )
    out = await stripe.get_checkout_status("cs_look")
    assert out.status == "failed"

    _FakeClient.answer = _FakeResponse(404, {"error": {"message": "No such checkout session"}})
    with pytest.raises(AppError) as exc:
        await stripe.get_checkout_status("cs_look")
    assert exc.value.code == "PAYMENT_PROVIDER_ERROR"


@pytest.mark.asyncio
async def test_stripe_session_lookup_needs_a_key_of_either_mode(monkeypatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "", raising=False)
    assert stripe.lookup_configured() is False
    with pytest.raises(AppError) as exc:
        await stripe.get_checkout_status("cs_x")
    assert exc.value.status_code == 503
    # a TEST key can look up a test-mode payment even where the customer rail is hidden
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test_x", raising=False)
    monkeypatch.setattr(s, "environment", "production", raising=False)
    assert stripe.lookup_configured() is True
