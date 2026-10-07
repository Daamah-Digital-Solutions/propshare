"""Crypto payments (NOWPayments): what arrives is credited, whatever way it arrives.

Client, 2026-10-06: he chose BNB on the payment page and sent 13 USDT to the same address.
NOWPayments recovered it as a second payment marked "partially paid" (1.5 cents under 13 USD);
its notification was refused (a number in it, see test_payments_gateway) and, had it passed, it
was ignored: the money sat at NOWPayments and nothing reached his wallet or told him.

What each test protects:
  * a deposit sent in another coin, or short, is credited at what arrived, said to the member,
    once per NOWPayments payment (sent again, or set to Finished by hand: nothing more), and
    the invoice paid as asked afterwards is a second deposit;
  * an under-payment in the coin asked for is worth its share of the price;
  * money NOWPayments does not value is not guessed: no credit, one staff case, the member told;
  * a purchase is never completed with less than its price: the units go back on sale, the
    money goes to the wallet, and paying the invoice properly afterwards still buys;
  * an under-payment recorded before this (and left for a person) is settled when sent again;
  * the member picks the coin on the platform: the coins are the account's own, the invoice is
    made for the coin chosen, and the wallet lists what is still on its way.
"""

# ruff: noqa: E501
from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest

from app.core.config import get_settings
from app.services.integrations.payments import CheckoutResult
from app.services.integrations.payments import nowpayments_gateway as nowp
from app.tests.test_purchase_methods_db import (
    _available,
    _balance,
    _h,
    _investor,
    _owned,
    _plan,
    _property,
    _told,
)

IPN_URL = "/api/v1/payments/webhooks/nowpayments"


def _crypto_rail(monkeypatch, answers: dict | None = None) -> list[dict]:
    """NOWPayments on, without the network; returns the invoices asked for. ``answers``: what
    its API says when asked (path -> body); anything else is a 404. The paths asked are kept
    under ``answers["asked"]``."""
    made: list[dict] = []
    answers = answers if answers is not None else {}
    answers.setdefault("asked", [])

    async def fake_checkout(**kwargs):
        made.append(kwargs)
        invoice = str(5_000_000_000 + len(made))
        return CheckoutResult(
            provider_payment_id=invoice,
            checkout_url=f"https://nowpayments.test/payment/?iid={invoice}",
            status="pending",
        )

    async def fake_get(path: str):
        answers["asked"].append(path)
        return (200, answers[path]) if path in answers else (404, None)

    monkeypatch.setattr(nowp, "is_configured", lambda: True)
    monkeypatch.setattr(nowp, "create_checkout", fake_checkout)
    monkeypatch.setattr(nowp, "_get", fake_get)
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    return made


async def _send(client, body: bytes):
    return await client.post(
        IPN_URL,
        content=body,
        headers={
            "x-nowpayments-sig": nowp.compute_signature("ipn_t", body),
            "content-type": "application/json",
        },
    )


async def _ipn(client, **fields):
    return await _send(client, json.dumps(fields).encode())


async def _deposit(client, token, amount, coin="usdtbsc") -> str:
    r = await client.post(
        "/api/v1/wallet/deposit",
        json={"amount": amount, "method": "crypto", "pay_currency": coin},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["payment_id"]


def _payment(db, pid: str):
    row = db("SELECT status, amount_captured, raw_payload FROM payments WHERE id=:p", p=pid)[0]
    return row[0], (float(row[1]) if row[1] is not None else None), row[2] or {}


# --- a deposit that did not arrive as its invoice asked ---------------------------------------
@pytest.mark.asyncio
async def test_a_deposit_sent_in_another_coin_is_credited_at_what_arrived(client, db, monkeypatch):
    made = _crypto_rail(monkeypatch)
    token, uid = await _investor(client, db, "wrong.coin@cp.io")
    pid = await _deposit(client, token, 13, coin="BNBBSC")
    assert made[0]["pay_currency"] == "BNBBSC"
    assert _payment(db, pid)[2]["pay_currency"] == "bnbbsc"

    # the page asked for BNB: NOWPayments reports that payment, waiting
    r = await _ipn(
        client,
        payment_id=6160305429,
        payment_status="waiting",
        order_id=pid,
        price_amount=13,
        pay_amount=0.01669618,
        actually_paid=0,
        pay_currency="bnbbsc",
    )
    assert r.json() == {"status": "ignored", "result": "pending"} and _balance(db, uid) == 0

    # 13 USDT arrived on that address instead: recovered as a payment of its own, written the
    # way NOWPayments writes it (the fee is the number the old check refused)
    recovered = (
        '{"payment_id":4870885867,"parent_payment_id":6160305429,"invoice_id":null,'
        '"payment_status":"partially_paid","price_amount":13,"price_currency":"usd",'
        '"pay_amount":13,"actually_paid":13,"actually_paid_at_fiat":12.98513924,'
        f'"pay_currency":"usdtbsc","order_id":"{pid}","outcome_amount":0.01633459,'
        '"outcome_currency":"bnbbsc","fee":{"currency":"bnbbsc","depositFee":0.000083,'
        '"withdrawalFee":0,"serviceFee":0.000249}}'
    ).encode()
    r = await _send(client, recovered)
    assert r.status_code == 200 and r.json() == {
        "status": "processed",
        "result": "credited_received",
    }
    assert _balance(db, uid) == 12.99
    status, captured, raw = _payment(db, pid)
    assert (status, captured) == ("succeeded", 12.99)
    kept = raw["nowpayments"]
    assert kept["4870885867"] == {
        "status": "partially_paid",
        "coin": "usdtbsc",
        "asked": "13",
        "received": "13",
        "parent": "6160305429",
        "credited": "12.99",
    }
    assert kept["6160305429"]["status"] == "waiting" and "credited" not in kept["6160305429"]
    told = _told(db, uid, "Deposit received")
    assert len(told) == 1 and "arrived as 12.99 USD, not the 13.00 USD of the deposit" in told[0]
    assert "12.99 USD was credited to your wallet" in told[0]
    moves = db("SELECT amount, type, payment_method FROM transactions WHERE user_id=:u", u=uid)
    assert [(float(a), kind, how) for a, kind, how in moves] == [(12.99, "deposit", "crypto")]

    # sent again from the dashboard, then set to Finished there by hand: nothing more
    assert (await _send(client, recovered)).json() == {"status": "duplicate"}
    finished = recovered.replace(b'"partially_paid"', b'"finished"')
    assert (await _send(client, finished)).json() == {"status": "already_processed"}
    assert (await _send(client, finished)).json() == {"status": "duplicate"}
    assert _balance(db, uid) == 12.99

    # the member then also pays the BNB the page asked for: a second deposit, at its price
    r = await _ipn(
        client,
        payment_id=6160305429,
        payment_status="finished",
        order_id=pid,
        price_amount=13,
        pay_amount=0.01669618,
        actually_paid=0.01669618,
        pay_currency="bnbbsc",
    )
    assert r.json() == {"status": "processed", "result": "credited_received"}
    assert _balance(db, uid) == 25.99 and _payment(db, pid)[1] == 25.99
    assert "Another crypto payment arrived" in _told(db, uid, "Deposit received")[1]
    # and that payment expiring or failing later changes nothing
    r = await _ipn(client, payment_id=6160305429, payment_status="expired", order_id=pid)
    assert r.json() == {"status": "already_processed"} and _payment(db, pid)[0] == "succeeded"


@pytest.mark.asyncio
async def test_an_under_payment_is_worth_its_share_and_the_rest_counts_when_it_comes(
    client, db, monkeypatch
):
    _crypto_rail(monkeypatch)
    token, uid = await _investor(client, db, "short@cp.io")
    pid = await _deposit(client, token, 100, coin="btc")
    # asked 0.002 BTC for 100 USD, 0.0015 arrived: three quarters of the price
    r = await _ipn(
        client,
        payment_id=7001,
        payment_status="partially_paid",
        order_id=pid,
        price_amount=100,
        pay_amount=0.002,
        actually_paid=0.0015,
        pay_currency="btc",
    )
    assert r.json()["result"] == "credited_received" and _balance(db, uid) == 75.0
    # the rest is sent to the same address: NOWPayments adds it as its own payment and says
    # what it is worth (no rate was quoted for it)
    r = await _ipn(
        client,
        payment_id=7002,
        parent_payment_id=7001,
        payment_status="finished",
        order_id=pid,
        price_amount=100,
        pay_amount=0.0005,
        actually_paid=0.0005,
        actually_paid_at_fiat=25.4,
        pay_currency="btc",
    )
    assert r.json()["result"] == "credited_received" and _balance(db, uid) == 100.4
    assert _payment(db, pid)[:2] == ("succeeded", 100.4)
    told = _told(db, uid, "Deposit received")
    assert len(told) == 2
    assert any("arrived as 75.00 USD, not the 100.00 USD of the deposit" in m for m in told)
    # what comes after the deposit was credited is said as a further payment
    assert any(
        "Another crypto payment arrived" in m and "25.40 USD more was credited" in m for m in told
    )


@pytest.mark.asyncio
async def test_money_that_is_not_valued_is_not_guessed(client, db, monkeypatch):
    answers: dict = {}
    _crypto_rail(monkeypatch, answers)
    token, uid = await _investor(client, db, "unvalued@cp.io")
    pid = await _deposit(client, token, 50)
    # an extra deposit in another coin, with no valuation: its "asked" is whatever arrived, so
    # the share-of-the-price rule would credit the whole invoice for any amount
    extra = dict(
        payment_id=8002,
        parent_payment_id=8001,
        payment_status="partially_paid",
        order_id=pid,
        price_amount=50,
        price_currency="usd",
        pay_amount=3,
        actually_paid=3,
        actually_paid_at_fiat=0,
        pay_currency="doge",
    )
    r = await _ipn(client, **extra)
    assert r.json() == {"status": "processed", "result": "needs_review"}
    # NOWPayments was asked its rate for the coin, and gave none
    assert answers["asked"] == ["/estimate?amount=50&currency_from=usd&currency_to=doge"]
    assert _balance(db, uid) == 0 and _payment(db, pid)[0] == "pending"
    cases = db("SELECT subject, priority, context FROM support_tickets WHERE kind='ops_case'")
    assert len(cases) == 1 and cases[0][1] == "high"
    assert "received but not valued" in cases[0][0]
    assert cases[0][2]["case_key"] == f"provider_payment:{pid}"
    assert len(_told(db, uid, "Crypto payment received")) == 1
    # told again by NOWPayments: still one case, one message, no credit
    assert (await _ipn(client, **extra)).json() == {"status": "already_processed"}
    done = {**extra, "payment_status": "finished"}
    assert (await _ipn(client, **done)).json() == {"status": "already_processed"}
    assert db("SELECT count(*) FROM support_tickets WHERE kind='ops_case'")[0][0] == 1
    assert len(_told(db, uid, "Crypto payment received")) == 1 and _balance(db, uid) == 0

    # NOWPayments can say what it is worth after all (50 USD buys 245.9 DOGE: 3 arrived), and
    # staff press "IPN" on it: credited once, and the case answers itself so nobody credits it
    # again by hand
    answers["/estimate?amount=50&currency_from=usd&currency_to=doge"] = {"estimated_amount": 245.9}
    r = await _ipn(client, **extra)
    assert r.json() == {"status": "processed", "result": "credited_received"}
    assert _balance(db, uid) == 0.61
    status, captured, raw = _payment(db, pid)
    assert (status, captured) == ("succeeded", 0.61)
    assert raw["nowpayments"]["8002"]["credited"] == "0.61"
    assert raw["nowpayments"]["8002"]["valued_by"] == "rate"
    assert "review" not in raw["nowpayments"]["8002"]
    case = db("SELECT id, status, resolved_at FROM support_tickets WHERE kind='ops_case'")[0]
    assert case[1] == "resolved" and case[2] is not None
    note = db(
        "SELECT author_type, internal, body FROM support_ticket_messages WHERE ticket_id=:t",
        t=case[0],
    )
    assert len(note) == 1 and note[0][:2] == ("system", True)
    assert "0.61 USD was credited to the member's wallet" in note[0][2]
    for again in (extra, done):
        assert (await _ipn(client, **again)).json() == {"status": "duplicate"}
    assert _balance(db, uid) == 0.61


@pytest.mark.asyncio
async def test_a_notification_without_a_value_is_valued_by_asking_nowpayments(
    client, db, monkeypatch
):
    """NOWPayments' own example of a repeated deposit carries ``actually_paid_at_fiat: 0``, and
    its record of a payment carries no value either (seen on the server, 2026-10-06). The money
    is real: its rate for the coin tells what the amount that arrived is worth."""
    usdt = "/estimate?amount=60&currency_from=usd&currency_to=usdtbsc"
    answers: dict = {
        # 60 USD buys 60.05 USDT today, and 0.024 ETH
        usdt: {"estimated_amount": "60.05"},
        "/estimate?amount=60&currency_from=usd&currency_to=eth": {"estimated_amount": 0.024},
        # read only for a notification that leaves out its coin and currency
        "/payment/8104": {"payment_id": 8104, "price_currency": "usd", "pay_currency": "usdtbsc"},
    }
    _crypto_rail(monkeypatch, answers)
    token, uid = await _investor(client, db, "asked@cp.io")
    pid = await _deposit(client, token, 60)
    extra = dict(
        parent_payment_id=8101,
        payment_status="finished",
        order_id=pid,
        price_amount=60,
        price_currency="usd",
        actually_paid_at_fiat=0,
    )
    r = await _ipn(
        client, payment_id=8102, pay_amount=20, actually_paid=20, pay_currency="usdtbsc", **extra
    )
    assert r.json()["result"] == "credited_received" and _balance(db, uid) == 19.98
    r = await _ipn(
        client, payment_id=8103, pay_amount=0.01, actually_paid=0.01, pay_currency="ETH", **extra
    )
    assert r.json()["result"] == "credited_received" and _balance(db, uid) == 44.98  # + 25.00
    # the rate was asked, the record was not: it has nothing to add
    assert answers["asked"] == [usdt, "/estimate?amount=60&currency_from=usd&currency_to=eth"]
    kept = _payment(db, pid)[2]["nowpayments"]
    assert (kept["8102"]["credited"], kept["8102"]["valued_by"]) == ("19.98", "rate")
    assert (kept["8103"]["credited"], kept["8103"]["valued_by"]) == ("25.00", "rate")

    # a notification without its coin and currency: the record says them, then the rate
    bare = {k: v for k, v in extra.items() if k != "price_currency"}
    r = await _ipn(client, payment_id=8104, pay_amount=7, actually_paid=7, **bare)
    assert r.json()["result"] == "credited_received" and _balance(db, uid) == 51.97  # + 6.99
    assert answers["asked"][-2:] == ["/payment/8104", usdt]

    # a coin NOWPayments gives no rate for: a person
    r = await _ipn(
        client, payment_id=8105, pay_amount=7, actually_paid=7, pay_currency="odd", **extra
    )
    assert r.json() == {"status": "processed", "result": "needs_review"}
    assert _balance(db, uid) == 51.97
    # a notification that says its value asks NOWPayments nothing
    before = len(answers["asked"])
    r = await _ipn(
        client,
        payment_id=8106,
        pay_amount=5,
        actually_paid=5,
        pay_currency="usdtbsc",
        **{**extra, "actually_paid_at_fiat": 4.99},
    )
    assert r.json()["result"] == "credited_received" and len(answers["asked"]) == before
    assert "valued_by" not in _payment(db, pid)[2]["nowpayments"]["8106"]


@pytest.mark.asyncio
async def test_an_extra_deposit_that_fails_leaves_the_invoice_open(client, db, monkeypatch):
    _crypto_rail(monkeypatch)
    token, uid = await _investor(client, db, "extra.failed@cp.io")
    prop = _property(db, model="ready-income")
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": prop, "amount": 1000, "method": "crypto", "pay_currency": "usdtbsc"},
        headers=_h(token),
    )
    inv = r.json()["investment_id"]
    pid, due = db("SELECT id, amount FROM payments WHERE related_investment_id=:i", i=inv)[0]
    pid, due = str(pid), float(due)
    # a stray transfer NOWPayments could not process: the purchase keeps its units
    r = await _ipn(
        client, payment_id=3202, parent_payment_id=3201, payment_status="failed", order_id=pid
    )
    assert r.json() == {"status": "ignored", "result": "extra_failed"}
    assert _payment(db, pid)[0] == "pending" and _available(db, prop) == 90
    # and the invoice paid as asked still buys them
    r = await _ipn(
        client, payment_id=3201, payment_status="finished", order_id=pid, price_amount=due
    )
    assert r.json()["status"] == "processed" and _owned(db, uid, prop) == 10
    # while the invoice's own payment failing does release them
    other = await client.post(
        "/api/v1/investments",
        json={"property_id": prop, "amount": 1000, "method": "crypto", "pay_currency": "usdtbsc"},
        headers=_h(token),
    )
    second = db(
        "SELECT id FROM payments WHERE related_investment_id=:i", i=other.json()["investment_id"]
    )[0][0]
    assert _available(db, prop) == 80
    r = await _ipn(client, payment_id=3301, payment_status="expired", order_id=str(second))
    assert r.json() == {"status": "processed", "result": "failed"} and _available(db, prop) == 90


@pytest.mark.asyncio
async def test_an_under_payment_recorded_earlier_is_settled_when_sent_again(
    client, db, monkeypatch
):
    """Before 2026-10 an under-payment was recorded and left for a person. Staff press "IPN" on
    it in the NOWPayments dashboard: the same notification comes again and is settled now."""
    _crypto_rail(monkeypatch)
    token, uid = await _investor(client, db, "resent@cp.io")
    pid = await _deposit(client, token, 40)
    db(
        "INSERT INTO payment_events (provider, event_id, payment_id, type)"
        " VALUES ('nowpayments', '9001:partially_paid', :p, 'partially_paid')",
        p=pid,
    )
    fields = dict(
        payment_id=9001,
        payment_status="partially_paid",
        order_id=pid,
        price_amount=40,
        pay_amount=40,
        actually_paid=30,
        pay_currency="usdtbsc",
    )
    assert (await _ipn(client, **fields)).json()["result"] == "credited_received"
    assert (await _ipn(client, **fields)).json() == {"status": "duplicate"}
    assert _balance(db, uid) == 30.0
    assert db("SELECT count(*) FROM payment_events WHERE event_id='9001:partially_paid'")[0][0] == 1
    # a "finished" recorded before is still never applied twice
    done = await _deposit(client, token, 20)
    paid = dict(payment_id=9002, payment_status="finished", order_id=done, price_amount=20)
    assert (await _ipn(client, **paid)).json()["result"] == "credited"
    assert (await _ipn(client, **paid)).json() == {"status": "duplicate"}
    assert _balance(db, uid) == 50.0
    # the invoice simply paid is kept like any other outcome
    assert _payment(db, done)[2]["nowpayments"]["9002"] == {
        "status": "finished",
        "coin": None,
        "asked": None,
        "received": None,
        "parent": None,
        "credited": "20.00",
    }

    # An under-payment recorded back then whose deposit was settled since (it was set to
    # Finished by hand and credited in full, before each payment's outcome was kept): sent
    # again, it must not be credited a second time. Neither is one on a row that was closed.
    settled = await _deposit(client, token, 60)
    closed = await _deposit(client, token, 70)
    for payment, np_id, status in ((settled, 9003, "succeeded"), (closed, 9004, "failed")):
        db("UPDATE payments SET status=:s WHERE id=:p", s=status, p=payment)
        db(
            "INSERT INTO payment_events (provider, event_id, payment_id, type)"
            " VALUES ('nowpayments', :e, :p, 'partially_paid')",
            e=f"{np_id}:partially_paid",
            p=payment,
        )
        again = dict(fields, payment_id=np_id, order_id=payment, price_amount=60, pay_amount=60)
        assert (await _ipn(client, **again)).json() == {"status": "duplicate"}
    assert _balance(db, uid) == 50.0
    # a notification seen before for a payment that is not ours is dropped quietly
    db(
        "INSERT INTO payment_events (provider, event_id, type)"
        " VALUES ('nowpayments', '9005:partially_paid', 'partially_paid')"
    )
    stray = dict(fields, payment_id=9005, order_id=str(uuid.uuid4()))
    assert (await _ipn(client, **stray)).json() == {"status": "duplicate"}


# --- a purchase is never completed with less than its price -------------------------------------
@pytest.mark.asyncio
async def test_a_short_payment_for_a_purchase_goes_to_the_wallet(client, db, monkeypatch):
    made = _crypto_rail(monkeypatch)
    token, uid = await _investor(client, db, "short.buy@cp.io")
    prop = _property(db, model="ready-income")
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": prop, "amount": 1000, "method": "crypto", "pay_currency": "usdttrc20"},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    inv = r.json()["investment_id"]
    assert made[0]["pay_currency"] == "usdttrc20" and _available(db, prop) == 90
    pid, due = db("SELECT id, amount FROM payments WHERE related_investment_id=:i", i=inv)[0]
    pid, due = str(pid), float(due)

    r = await _ipn(
        client,
        payment_id=3001,
        payment_status="partially_paid",
        order_id=pid,
        price_amount=due,
        pay_amount=due,
        actually_paid=due / 2,
        pay_currency="usdttrc20",
    )
    half = round(due / 2, 2)
    assert r.json() == {"status": "processed", "result": "credited_received"}
    assert _balance(db, uid) == half and _owned(db, uid, prop) == 0
    assert _available(db, prop) == 100  # the units are back on sale
    assert db("SELECT status, failure_reason FROM investments WHERE id=:i", i=inv)[0] == (
        "cancelled",
        "payment_short_credited",
    )
    assert _payment(db, pid)[:2] == ("failed", half)
    told = _told(db, uid, "Crypto payment credited to your wallet")
    assert (
        len(told) == 1 and "The purchase was not completed and its units were released" in told[0]
    )
    assert f"arrived as {half:.2f} USD, not the {due:.2f} USD due" in told[0]

    # paying the invoice properly afterwards (another coin picked on the same page) still buys
    r = await _ipn(
        client, payment_id=3002, payment_status="finished", order_id=pid, price_amount=due
    )
    assert r.json() == {"status": "processed", "result": "reconciled_confirmed"}
    assert _owned(db, uid, prop) == 10 and _available(db, prop) == 90
    assert _balance(db, uid) == half  # what came first stays in the wallet
    assert _payment(db, pid)[:2] == ("succeeded", round(due + half, 2))


@pytest.mark.asyncio
async def test_a_short_down_payment_does_not_start_the_plan(client, db, monkeypatch):
    made = _crypto_rail(monkeypatch)
    token, uid = await _investor(client, db, "short.plan@cp.io")
    prop = _property(db)
    r = await client.post(
        "/api/v1/installments",
        json={
            "property_id": prop,
            "amount": 1200,
            "duration_months": 12,
            "method": "crypto",
            "pay_currency": "usdtbsc",
        },
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    plan = r.json()["id"]
    assert made[0]["pay_currency"] == "usdtbsc" and _available(db, prop) == 88
    pid, due = db("SELECT id, amount FROM payments WHERE related_plan_id=:i", i=plan)[0]
    r = await _ipn(
        client,
        payment_id=3101,
        parent_payment_id=3100,
        payment_status="partially_paid",
        order_id=str(pid),
        price_amount=float(due),
        pay_amount=10,
        actually_paid=10,
        actually_paid_at_fiat=9.99,
        pay_currency="usdterc20",
    )
    assert r.json()["result"] == "credited_received" and _balance(db, uid) == 9.99
    assert _available(db, prop) == 100
    assert db("SELECT status, failure_reason FROM installment_plans WHERE id=:i", i=plan)[0] == (
        "cancelled",
        "payment_short_credited",
    )
    assert (
        "The installment plan was not completed"
        in _told(db, uid, "Crypto payment credited to your wallet")[0]
    )
    # a wallet plan is untouched by any of this
    assert (await _plan(client, token, prop, method="card")).status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("tolerance", [False, True])
async def test_the_down_payment_that_started_all_this(client, db, monkeypatch, tolerance):
    """The client's own payment, as the server showed it on 2026-10-06: a 13 USD down payment
    whose invoice he opened for BNB and paid with 13 USDT. The recovered deposit's "confirmed"
    notification passed, its "partially paid" one was refused twice, and when it was sent again
    the plan's hold had long run out. Valued at NOWPayments' rate (13 USD buys 13.00982534
    USDT) it is worth 12.99.

    That day nothing short completed a purchase: the plan did not start and 12.99 reached his
    wallet (``tolerance`` off). Since 2026-10-07 a payment a hair short pays for the purchase:
    the same notification starts his plan, late, its unit still being free."""
    rate = "/estimate?amount=13&currency_from=usd&currency_to=usdtbsc"
    answers: dict = {rate: {"currency_from": "usd", "estimated_amount": "13.00982534"}}
    _crypto_rail(monkeypatch, answers)
    if not tolerance:
        db("INSERT INTO platform_settings (key, value) VALUES ('crypto_short_tolerance_max', '0')")
    token, uid = await _investor(client, db, f"first.case.{int(tolerance)}@cp.io")
    prop = _property(db)
    db("UPDATE properties SET unit_price=50, minimum_investment=50 WHERE id=:p", p=prop)
    # one unit of 50 over 12 months: 25% down + 4% fee = 13.00; no coin, as before the release
    r = await _plan(client, token, prop, method="crypto", amount=50)
    assert r.status_code == 201, r.text
    plan = r.json()["id"]
    pid, due = db("SELECT id, amount FROM payments WHERE related_plan_id=:i", i=plan)[0]
    pid = str(pid)
    assert float(due) == 13.0 and _available(db, prop) == 99

    child = dict(
        payment_id=4870885867,
        parent_payment_id=6160305429,
        invoice_id=4730828777,
        order_id=pid,
        price_amount=13,
        price_currency="usd",
        pay_amount=13,
        actually_paid=13,
        actually_paid_at_fiat=0,
        pay_currency="usdtbsc",
        outcome_amount=0.01633459,
        outcome_currency="bnbbsc",
    )
    waiting = dict(payment_id=6160305429, order_id=pid, price_amount=13, pay_currency="bnbbsc")
    assert (await _ipn(client, payment_status="waiting", **waiting)).json()["status"] == "ignored"
    r = await _ipn(client, payment_status="confirmed", **child)
    assert r.json() == {"status": "ignored", "result": "pending"} and _balance(db, uid) == 0

    # half an hour later the hold runs out: the plan is released, the payment still pending
    db("UPDATE installment_plans SET reservation_expires_at = now() - interval '1 minute'")
    monkeypatch.setattr(get_settings(), "cron_secret", "cron-t", raising=False)
    r = await client.post(
        "/api/v1/investments/maintenance/expire-reservations", headers={"X-Cron-Secret": "cron-t"}
    )
    assert r.json()["expired_plans"] == 1 and _available(db, prop) == 100

    # the notification that was refused, sent again: the fee is the number that broke the check
    body = json.dumps(
        {
            **child,
            "payment_status": "partially_paid",
            "fee": {"currency": "bnbbsc", "depositFee": 0.000083, "serviceFee": 0.000249},
        }
    ).encode()
    assert b"8.3e-05" in body  # Python's spelling: accepted as the same value
    r = await _send(client, body)
    assert r.status_code == 200 and answers["asked"] == [rate]
    status, captured, raw = _payment(db, pid)
    assert raw["nowpayments"]["4870885867"]["credited"] == "12.99"
    assert raw["nowpayments"]["4870885867"]["valued_by"] == "rate"
    plan_status = db("SELECT status FROM installment_plans WHERE id=:i", i=plan)[0][0]
    wallet_note = _told(db, uid, "Crypto payment credited to your wallet")
    if tolerance:
        # a cent short of 13.00: it pays for the plan, which starts late on its free unit
        assert r.json() == {"status": "processed", "result": "reconciled_started"}
        assert (status, captured, plan_status) == ("succeeded", 12.99, "active")
        assert _balance(db, uid) == 0 and _available(db, prop) == 99 and not wallet_note
        noted = db(
            "SELECT after FROM audit_log WHERE action='payment.webhook.received_as_paid'"
            " AND entity_id=:p",
            p=pid,
        )
        assert len(noted) == 1 and noted[0][0]["short_by"] == "0.01"
        assert (noted[0][0]["due"], noted[0][0]["arrived"]) == ("13.00", "12.99")
    else:
        assert r.json() == {"status": "processed", "result": "credited_received"}
        assert (status, captured, plan_status) == ("failed", 12.99, "expired")
        assert _balance(db, uid) == 12.99 and _available(db, prop) == 100
        assert len(wallet_note) == 1
        assert "arrived as 12.99 USD, not the 13.00 USD due" in wallet_note[0]
        assert "12.99 USD is in your wallet" in wallet_note[0]
    # pressed again, and the BNB payment he never sent expiring a week later: nothing more
    balance = _balance(db, uid)
    assert (await _send(client, body)).json() == {"status": "duplicate"}
    r = await _ipn(client, payment_status="expired", **waiting)
    assert r.json() == {"status": "already_processed"} and _balance(db, uid) == balance


@pytest.mark.asyncio
async def test_a_purchase_a_hair_short_is_completed_and_no_further(client, db, monkeypatch):
    """2026-10-07, on the owner's go-ahead: a payment a hair short of the amount due still
    completes the purchase, the platform bearing the difference: within 0.5% of the amount and
    1 USD at most. One cent beyond that it goes to the wallet as before. Worth more than the
    amount due (another coin at a better rate), it buys and the rest goes to the wallet."""
    _crypto_rail(monkeypatch)
    token, uid = await _investor(client, db, "hair@cp.io")
    prop = _property(db, model="ready-income", units=1000)
    monkeypatch.setattr(get_settings(), "cron_secret", "cron-t", raising=False)

    async def buy(amount: int) -> tuple[str, float]:
        r = await client.post(
            "/api/v1/investments",
            json={"property_id": prop, "amount": amount, "method": "crypto", "pay_currency": "eth"},
            headers=_h(token),
        )
        assert r.status_code == 200, r.text
        row = db(
            "SELECT id, amount FROM payments WHERE related_investment_id=:i",
            i=r.json()["investment_id"],
        )[0]
        return str(row[0]), float(row[1])

    async def short(pid: str, due: float, by: float, np_id: int):
        # an under-payment in the coin asked for: its share of the price
        return await _ipn(
            client,
            payment_id=np_id,
            payment_status="partially_paid",
            order_id=pid,
            price_amount=due,
            pay_amount=due,
            actually_paid=round(due - by, 2),
            pay_currency="usdtbsc",
        )

    # 1,000 + 2.5% fee = 1,025.00 due: half a percent would be 5.12, so the 1 USD cap decides
    pid, due = await buy(1000)
    assert due == 1025.0
    r = await short(pid, due, 1.01, 5001)
    assert r.json() == {"status": "processed", "result": "credited_received"}
    assert _balance(db, uid) == 1023.99 and _owned(db, uid, prop) == 0
    assert _payment(db, pid)[:2] == ("failed", 1023.99)

    pid, due = await buy(1000)
    r = await short(pid, due, 1.00, 5002)
    assert r.json() == {"status": "processed", "result": "confirmed"}
    assert _owned(db, uid, prop) == 10 and _balance(db, uid) == 1023.99  # nothing more credited
    assert _payment(db, pid)[:2] == ("succeeded", 1024.0)
    noted = db(
        "SELECT after FROM audit_log WHERE action='payment.webhook.received_as_paid'"
        " AND entity_id=:p",
        p=pid,
    )[0][0]
    assert (noted["short_by"], noted["credited_extra"], noted["outcome"]) == (
        "1.00",
        "0.00",
        "confirmed",
    )
    # sent again: nothing more
    assert (await short(pid, due, 1.00, 5002)).json() == {"status": "duplicate"}

    # 100 + 2.5% = 102.50 due: half a percent is 0.51 (the cap is not reached)
    pid, due = await buy(100)
    assert due == 102.5
    r = await short(pid, due, 0.52, 5003)
    assert r.json()["result"] == "credited_received" and _owned(db, uid, prop) == 10
    wallet = _balance(db, uid)
    pid, due = await buy(100)
    assert (await short(pid, due, 0.51, 5004)).json()["result"] == "confirmed"
    assert _owned(db, uid, prop) == 11 and _balance(db, uid) == wallet

    # another coin, worth more than the amount due: it buys, the difference is his
    pid, due = await buy(100)
    r = await _ipn(
        client,
        payment_id=5006,
        parent_payment_id=5005,
        payment_status="partially_paid",
        order_id=pid,
        price_amount=due,
        pay_amount=106,
        actually_paid=106,
        actually_paid_at_fiat=105.71,
        pay_currency="usdterc20",
    )
    assert r.json() == {"status": "processed", "result": "confirmed"}
    assert _owned(db, uid, prop) == 12 and _balance(db, uid) == round(wallet + 3.21, 2)
    assert _payment(db, pid)[:2] == ("succeeded", 105.71)
    told = _told(db, uid, "Crypto payment above the amount due")
    assert len(told) == 1 and "The difference, 3.21 USD, was credited to your wallet" in told[0]
    wallet = _balance(db, uid)

    # a hair short, but paid after the hold ran out and the units went to someone else: what
    # arrived is refunded, not the amount that was due
    pid, due = await buy(100)
    db("UPDATE investments SET reservation_expires_at = now() - interval '1 minute'")
    r = await client.post(
        "/api/v1/investments/maintenance/expire-reservations", headers={"X-Cron-Secret": "cron-t"}
    )
    assert r.status_code == 200
    db("UPDATE properties SET available_units = 0, status = 'funded' WHERE id=:p", p=prop)
    r = await short(pid, due, 0.30, 5007)
    assert r.json() == {"status": "processed", "result": "refunded"}
    assert _balance(db, uid) == round(wallet + 102.20, 2) and _owned(db, uid, prop) == 12

    # the tolerance switched off: a cent short goes to the wallet
    db("UPDATE properties SET available_units = 500, status = 'active' WHERE id=:p", p=prop)
    db("INSERT INTO platform_settings (key, value) VALUES ('crypto_short_tolerance_pct', '0')")
    wallet = _balance(db, uid)
    pid, due = await buy(100)
    r = await short(pid, due, 0.01, 5008)
    assert r.json()["result"] == "credited_received"
    assert _balance(db, uid) == round(wallet + 102.49, 2) and _owned(db, uid, prop) == 12
    # ... while a payment that covers the amount in full still buys
    pid, due = await buy(100)
    r = await _ipn(
        client,
        payment_id=5010,
        parent_payment_id=5009,
        payment_status="finished",
        order_id=pid,
        price_amount=due,
        actually_paid=103,
        actually_paid_at_fiat=102.5,
        pay_currency="usdterc20",
    )
    assert r.json()["result"] == "confirmed" and _owned(db, uid, prop) == 13


@pytest.mark.asyncio
async def test_a_purchase_valued_only_when_sent_again_is_completed_then(client, db, monkeypatch):
    """A purchase paid in another coin that NOWPayments could not value at first waits for a
    person. Valued when its notification is sent again, and worth the amount due, it buys, and
    the case answers itself saying so (not that the money went to the wallet: it did not)."""
    answers: dict = {}
    _crypto_rail(monkeypatch, answers)
    token, uid = await _investor(client, db, "later@cp.io")
    prop = _property(db, model="ready-income", units=1000)
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": prop, "amount": 100, "method": "crypto", "pay_currency": "eth"},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    pid = str(
        db("SELECT id FROM payments WHERE related_investment_id=:i", i=r.json()["investment_id"])[
            0
        ][0]
    )
    extra = dict(
        payment_id=9002,
        parent_payment_id=9001,
        payment_status="partially_paid",
        order_id=pid,
        price_amount=102.5,
        price_currency="usd",
        pay_amount=505,
        actually_paid=505,
        actually_paid_at_fiat=0,
        pay_currency="doge",
    )
    r = await _ipn(client, **extra)
    assert r.json() == {"status": "processed", "result": "needs_review"}
    assert _owned(db, uid, prop) == 0 and _balance(db, uid) == 0
    assert _payment(db, pid)[0] == "pending"

    # 102.50 USD buys 504.1 DOGE now and 505 arrived: worth 102.68, 18 cents above the amount due
    answers["/estimate?amount=102.5&currency_from=usd&currency_to=doge"] = {
        "estimated_amount": 504.1
    }
    r = await _ipn(client, **extra)
    assert r.json() == {"status": "processed", "result": "confirmed"}
    assert _owned(db, uid, prop) == 1 and _balance(db, uid) == 0.18
    status, captured, raw = _payment(db, pid)
    assert (status, captured) == ("succeeded", 102.68)
    kept = raw["nowpayments"]["9002"]
    assert (kept["credited"], kept["valued_by"]) == ("102.68", "rate") and "review" not in kept
    assert len(_told(db, uid, "Crypto payment above the amount due")) == 1
    case = db("SELECT id, status FROM support_tickets WHERE kind='ops_case'")
    assert len(case) == 1 and case[0][1] == "resolved"
    note = db("SELECT body FROM support_ticket_messages WHERE ticket_id=:t", t=case[0][0])
    assert len(note) == 1
    assert "(102.68 USD) and paid for the purchase. Nothing more to do." in note[0][0]
    # sent once more: nothing more
    assert (await _ipn(client, **extra)).json() == {"status": "duplicate"}
    assert _owned(db, uid, prop) == 1 and _balance(db, uid) == 0.18


@pytest.mark.asyncio
async def test_the_tolerance_stays_a_hair_whatever_is_typed(client, db, monkeypatch):
    """A typo in the admin panel must not let a purchase complete far short: neither value can
    be set above its ceiling (2 percent, 20 USD), and a value that got into the store another
    way is held to it. A value nobody can read turns the tolerance off, not on."""
    from decimal import Decimal

    from app.core.db import session_scope
    from app.core.errors import AppError
    from app.services import settings_service as s

    for key, good, bad in (
        ("crypto_short_tolerance_pct", ("0", "0.5", "2"), ("2.01", "50", "-1", "half", "NaN")),
        (
            "crypto_short_tolerance_max",
            ("0", "1.00", "20"),
            ("20.01", "100", "-1", "one", "Infinity"),
        ),
    ):
        for value in good:
            s.validate_setting(key, value)
        for value in bad:
            with pytest.raises(AppError) as refused:
                s.validate_setting(key, value)
            assert refused.value.code == "INVALID_SETTING"

    async def tolerance(due: str) -> Decimal:
        async with session_scope() as session:
            return await s.crypto_short_tolerance(session, Decimal(due))

    # as shipped: half a percent, 1 USD at most, in whole cents rounded down
    assert await tolerance("13.00") == Decimal("0.06")
    assert await tolerance("102.50") == Decimal("0.51")
    assert await tolerance("1025.00") == Decimal("1.00")
    assert await tolerance("0") == 0
    # written past the ceiling behind the panel's back: held to 2 percent and 20 USD
    db(
        "INSERT INTO platform_settings (key, value) VALUES"
        " ('crypto_short_tolerance_pct', '100'), ('crypto_short_tolerance_max', '100000')"
    )
    assert await tolerance("500.00") == Decimal("10.00")
    assert await tolerance("50000.00") == Decimal("20.00")
    # unreadable: off
    for unreadable in ("lots", "NaN", "Infinity", ""):
        db(
            "UPDATE platform_settings SET value=:v WHERE key='crypto_short_tolerance_max'",
            v=unreadable,
        )
        assert await tolerance("500.00") == 0


# --- the coin is chosen on the platform ----------------------------------------------------------
@pytest.mark.asyncio
async def test_the_coins_offered_are_the_accounts_own(client, db, monkeypatch):
    monkeypatch.setattr(nowp, "is_configured", lambda: True)
    monkeypatch.setattr(nowp, "_coins", None)
    asked: list[str] = []

    async def fake_get(path: str):
        asked.append(path)
        if path == "/merchant/coins":
            return 200, {
                "selectedCurrencies": [
                    "DOGE",
                    "BTC",
                    "USDTTRC20",
                    "XRP",
                    "GONE",
                    "BNBBSC",
                    "USDTBSC",
                    "FDUSDBSC",
                ]
            }
        return 200, {
            "currencies": [
                # the account marks neither of these two, and knows nothing of USDTBSC
                {"code": "BNBBSC", "name": "BNB (Binance Smart Chain)", "ticker": "bnb"},
                {"code": "FDUSDBSC", "name": "First Digital USD", "is_stable": True},
                {
                    "code": "BTC",
                    "name": "Bitcoin",
                    "ticker": "btc",
                    "network": "btc",
                    "is_popular": True,
                },
                {
                    "code": "USDTTRC20",
                    "name": "Tether USD (Tron)",
                    "ticker": "usdt",
                    "network": "trx",
                    "is_stable": True,
                },
                {
                    "code": "XRP",
                    "name": "Ripple",
                    "ticker": "xrp",
                    "network": "xrp",
                    "extra_id_exists": True,
                },
                {"code": "GONE", "name": "Gone", "available_for_payment": False},
                {"code": "ETH", "name": "Ethereum", "is_popular": True},
            ]
        }

    monkeypatch.setattr(nowp, "_get", fake_get)
    assert (await client.get("/api/v1/payments/crypto/coins")).status_code == 401
    token, _uid = await _investor(client, db, "coins@cp.io")
    hdr = {"Authorization": f"Bearer {token}"}
    body = (await client.get("/api/v1/payments/crypto/coins", headers=hdr)).json()
    # The coins members use most come first and are listed up front whatever the account
    # marks (it holds hundreds); then stablecoins, the popular ones, the rest by name. A coin
    # switched off for payments or not switched on in the account is not offered.
    assert [c["code"] for c in body["items"]] == [
        "usdttrc20",
        "usdtbsc",
        "btc",
        "bnbbsc",
        "fdusdbsc",
        "doge",
        "xrp",
    ]
    assert body["total"] == 7
    assert body["items"][0] == {
        "code": "usdttrc20",
        "ticker": "USDT",
        "name": "Tether USD (Tron)",
        "network": "TRX",
        "stable": True,
        "popular": True,
        "memo": False,
    }
    # one the account's list says nothing about is still offered, by its code
    assert body["items"][1] == {
        "code": "usdtbsc",
        "ticker": "USDTBSC",
        "name": "USDTBSC",
        "network": None,
        "stable": False,
        "popular": True,
        "memo": False,
    }
    assert body["items"][3]["popular"] is True and body["items"][4]["popular"] is False
    assert body["items"][5]["name"] == "DOGE" and body["items"][6]["memo"] is True
    # remembered: a second page view asks NOWPayments nothing
    await client.get("/api/v1/payments/crypto/coins", headers=hdr)
    assert asked == ["/merchant/coins", "/full-currencies"]


def test_the_assistant_explains_crypto_the_way_it_works_now():
    """Its knowledge base and tools said the coin is picked on NOWPayments' page, and nothing
    about a transfer that arrives short or in another coin."""
    from app.services.assistant.tools import platform, wallet
    from app.tests.test_assistant_eval_tools_db import _load

    seed = _load("seed_kb")
    for rows, chosen_here, short, hair, least in (
        (
            seed.ARTICLES,
            "choose the coin and its network on PropShare",
            "arrives short",
            "short by a hair only (a rounding or network-fee difference) still completes it",
            "Every coin has a smallest payment, which moves with its network's fees",
        ),
        (
            seed.ARTICLES_AR,
            "تختار العملة وشبكتها على PropShare",
            "يصل ناقصًا",
            "أما النقص الطفيف جدًا (فرق تقريب أو رسوم شبكة) فلا يمنع إتمامها",
            "ولكل عملة حد أدنى للدفعة يتغيّر مع رسوم شبكتها",
        ),
    ):
        bodies = {slug: body for slug, *_rest, body in rows}
        assert chosen_here in bodies["getting-started"]
        assert chosen_here in bodies["wallet-deposits-withdrawals"]
        assert short in bodies["wallet-deposits-withdrawals"]
        # 2026-10-07: a purchase a hair short still completes, and a coin's smallest payment is
        # said under it (as sentences: the article's lines wrap)
        said = " ".join(bodies["wallet-deposits-withdrawals"].split())
        assert hair in said and least in said
        assert all("on NOWPayments' page)" not in body for body in bodies.values())
        assert all("من صفحة NOWPayments)" not in body for body in bodies.values())
    assert "choose there the coin and network" in wallet._DEPOSIT_STEPS["crypto"]
    assert "smallest payment that coin takes right now" in wallet._DEPOSIT_STEPS["crypto"]
    note = platform._purchase_methods()["note"]
    assert "picks the coin and its network on PropShare" in note
    assert "short by a hair only still completes it" in note


@pytest.mark.asyncio
async def test_the_smallest_payment_of_a_coin_is_told_before_paying(client, db, monkeypatch):
    """USDT on Tron asked for 12 USD on 2026-10-06 while members tried 3 and 4: the minimum is
    shown under the coin chosen, not learnt from a refusal."""
    monkeypatch.setattr(nowp, "is_configured", lambda: True)
    monkeypatch.setattr(nowp, "_coins", None)
    monkeypatch.setattr(nowp, "_minimums", {})
    asked: list[str] = []

    async def fake_get(path: str):
        asked.append(path)
        if path == "/merchant/coins":
            return 200, {"selectedCurrencies": ["USDTTRC20", "BTC"]}
        if path == "/full-currencies":
            return 200, {"currencies": [{"code": "BTC", "name": "Bitcoin"}]}
        if path == "/min-amount?currency_from=usdttrc20&fiat_equivalent=usd":
            return 200, {"min_amount": 12.01, "fiat_equivalent": 11.997}
        return 404, None

    monkeypatch.setattr(nowp, "_get", fake_get)
    url = "/api/v1/payments/crypto/minimum"
    assert (await client.get(url, params={"coin": "usdttrc20"})).status_code == 401
    token, _uid = await _investor(client, db, "minimum@cp.io")
    hdr = {"Authorization": f"Bearer {token}"}
    r = await client.get(url, params={"coin": "USDTTRC20"}, headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json() == {"coin": "usdttrc20", "minimum": "12.00", "currency": "USD"}
    # a coin NOWPayments gives no minimum for: said as unknown, the payment is made anyway
    r = await client.get(url, params={"coin": "btc"}, headers=hdr)
    assert r.json() == {"coin": "btc", "minimum": None, "currency": "USD"}
    # a coin the account does not take, and something that is no coin code
    r = await client.get(url, params={"coin": "doge"}, headers=hdr)
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNKNOWN_COIN"
    assert (await client.get(url, params={"coin": "us dt"}, headers=hdr)).status_code == 422
    # remembered: asking again asks NOWPayments nothing
    before = len(asked)
    await client.get(url, params={"coin": "usdttrc20"}, headers=hdr)
    assert len(asked) == before


@pytest.mark.asyncio
async def test_a_coins_smallest_payment_cannot_be_asked_without_end(client, db, monkeypatch):
    """Each question the cache cannot answer reaches NOWPayments, which refuses whoever asks it
    a few times in a row (seen on 2026-10-06): one caller walking the whole coin list must not
    make members' invoices fail. Over the limit the answer is 429 and the site shows no line."""
    from app.core.ratelimit import limiter

    monkeypatch.setattr(nowp, "is_configured", lambda: True)
    monkeypatch.setattr(nowp, "_coins", None)
    monkeypatch.setattr(nowp, "_minimums", {})
    asked: list[str] = []

    async def fake_get(path: str):
        asked.append(path)
        if path == "/merchant/coins":
            return 200, {"selectedCurrencies": ["USDTTRC20"]}
        if path == "/full-currencies":
            return 200, {"currencies": [{"code": "USDTTRC20", "name": "Tether USD (Tron)"}]}
        return 200, {"min_amount": 12, "fiat_equivalent": 12.0}

    monkeypatch.setattr(nowp, "_get", fake_get)
    token, _uid = await _investor(client, db, "walker@cp.io")
    limiter.enabled = True
    try:
        codes = [
            (
                await client.get(
                    "/api/v1/payments/crypto/minimum?coin=usdttrc20", headers=_h(token)
                )
            ).status_code
            for _ in range(32)  # the limit is 30 a minute
        ]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert codes[:30] == [200] * 30 and codes[30:] == [429] * 2
    # and the same coin asked again is answered from memory: NOWPayments heard it once
    assert len([p for p in asked if p.startswith("/min-amount")]) == 1


@pytest.mark.asyncio
async def test_the_wallet_lists_the_crypto_payments_still_on_their_way(client, db, monkeypatch):
    _crypto_rail(monkeypatch)
    token, uid = await _investor(client, db, "open@cp.io")
    other_token, _other = await _investor(client, db, "open.other@cp.io")
    hdr = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/payments/crypto/open")).status_code == 401

    fresh = await _deposit(client, token, 25, coin="usdtbsc")
    old = await _deposit(client, token, 30, coin="btc")
    seen = await _deposit(client, token, 35, coin="eth")
    paid = await _deposit(client, token, 40, coin="ltc")
    unopened = await _deposit(client, token, 50, coin="trx")
    opened = await _deposit(client, token, 55, coin="sol")
    await _deposit(client, other_token, 45)
    now = dt.datetime.now(dt.UTC)
    two_days, two_hours = now - dt.timedelta(days=2), now - dt.timedelta(hours=2)
    db("UPDATE payments SET created_at=:t WHERE id = ANY(:ids)", t=two_days, ids=[old, seen])
    db(
        "UPDATE payments SET created_at=:t WHERE id = ANY(:ids)",
        t=two_hours,
        ids=[unopened, opened],
    )
    # funds for the old ETH one were seen on the network; the LTC one is paid
    await _ipn(
        client, payment_id=4001, payment_status="confirming", order_id=seen, pay_currency="eth"
    )
    await _ipn(client, payment_id=4002, payment_status="finished", order_id=paid, price_amount=40)
    # two hours old: one whose payment page was opened (NOWPayments made a payment and gave an
    # address), one nobody ever opened, so nothing can be on its way for it
    await _ipn(
        client, payment_id=4003, payment_status="waiting", order_id=opened, pay_currency="sol"
    )

    rows = (await client.get("/api/v1/payments/crypto/open", headers=hdr)).json()
    assert [(r["id"], r["coin"], r["stage"], r["amount"]) for r in rows] == [
        (fresh, "usdtbsc", "awaiting_transfer", "25.00"),
        (opened, "sol", "awaiting_transfer", "55.00"),
        (seen, "eth", "confirming", "35.00"),
    ]
    assert unopened not in [r["id"] for r in rows]
    assert rows[0]["purpose"] == "deposit" and rows[0]["title"] is None
    assert rows[0]["checkout_url"].startswith("https://nowpayments.test/payment/?iid=")
    assert _balance(db, uid) == 40.0
    assert str(uuid.UUID(rows[0]["id"])) == fresh
