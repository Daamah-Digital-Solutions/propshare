"""A payment that arrives late never buys at a price the property no longer has (0034).

A hold lasts 30 minutes; a hosted checkout can still be paid for a day. Before unit prices
could change that was harmless: a late payment simply took the units back if they were free.
With recorded prices it would be a free option: open a checkout, do not pay, and pay the old
session only if the price went up overnight (and, on a plan, lock yesterday's price for the
whole schedule). So:

  * paid while the hold is still valid: honoured at the price it was made at, even if the
    price changed meanwhile (the units were held for that buyer at that price);
  * paid after the hold ran out, price unchanged: honoured if the units are still free
    (as before);
  * paid after the hold ran out, price changed: refunded to the wallet, the units stay on
    sale at today's price, and the buyer is told why. Whether the sweep has already released
    the hold or not makes no difference.
"""

from __future__ import annotations

import decimal
import uuid

import pytest

from app.services import installment_service, investment_service, price_service
from app.tests.test_investment_db import (
    _assert_balance_invariant,
    _assert_unit_invariant,
    _configure_stripe,
    _invest,
    _payment_id_for,
    _post_stripe,
    _seed_property,
    _stripe_event,
    _uid,
    _verified_user,
)
from app.tests.test_purchase_methods_db import _card_rail, _plan, _stripe_webhook

D = decimal.Decimal


async def _reprice(asession, pid: str, price: str) -> None:
    await price_service.record_price(asession, property_id=uuid.UUID(pid), price=price)
    await asession.commit()


def _lapse(db, table: str, row_id: str) -> None:
    db(
        f"UPDATE {table} SET reservation_expires_at = now() - interval '1 hour' WHERE id=:i",
        i=row_id,
    )


def _offering(db, pid: str) -> tuple:
    return db(
        "SELECT available_units, total_value, unit_price, funded_amount "
        "FROM properties WHERE id=:i",
        i=pid,
    )[0]


@pytest.mark.asyncio
async def test_a_purchase_paid_after_its_hold_and_a_price_change_is_refunded(
    client, db, asession, monkeypatch
):
    _configure_stripe(monkeypatch)
    token = await _verified_user(client, db, "late.price@i.com")
    uid = _uid(db, "late.price@i.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    inv_id = (await _invest(client, token, pid, 1000, "card")).json()["investment_id"]
    pay_id = _payment_id_for(db, inv_id)

    # the hold runs out unpaid, the sweep releases it, and the next day the price is 110
    _lapse(db, "investments", inv_id)
    assert await investment_service.expire_reservations(asession) == 1
    await asession.commit()
    await _reprice(asession, pid, "110")
    assert _offering(db, pid) == (100, D("11000.00"), D("110.00"), D("0.00"))

    # the old checkout is paid now: not 10 units at 100, the money goes to the wallet
    r = await _post_stripe(client, _stripe_event(pay_id, cents=102500, event_id="evt_price_1"))
    assert r.json()["result"] == "refunded"
    assert db("SELECT status, failure_reason FROM investments WHERE id=:i", i=inv_id)[0] == (
        "expired",
        "price_changed_refunded",
    )
    assert db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0] == D("1025.00")
    assert db("SELECT count(*) FROM ownership_ledger WHERE user_id=:u", u=uid)[0][0] == 0
    assert _offering(db, pid) == (100, D("11000.00"), D("110.00"), D("0.00"))
    note = db("SELECT message FROM notifications WHERE user_id=:u ORDER BY created_at", u=uid)
    assert "unit price of Marina Bay changed before your payment confirmed" in note[-1][0]
    _assert_balance_invariant(db, uid)
    _assert_unit_invariant(db, pid)
    # the same event again changes nothing
    again = await _post_stripe(client, _stripe_event(pay_id, cents=102500, event_id="evt_price_1"))
    assert again.status_code == 200
    assert db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0] == D("1025.00")


@pytest.mark.asyncio
async def test_the_sweep_not_having_run_yet_makes_no_difference(client, db, asession, monkeypatch):
    _configure_stripe(monkeypatch)
    token = await _verified_user(client, db, "unswept@i.com")
    uid = _uid(db, "unswept@i.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    inv_id = (await _invest(client, token, pid, 1000, "card")).json()["investment_id"]
    pay_id = _payment_id_for(db, inv_id)

    # the hold has run out but the sweep has not released it; the price changes
    _lapse(db, "investments", inv_id)
    await _reprice(asession, pid, "110")
    # 90 units repriced; the 10 still held keep what they were priced at
    assert _offering(db, pid)[:2] == (90, D("10900.00"))

    r = await _post_stripe(client, _stripe_event(pay_id, cents=102500, event_id="evt_price_2"))
    assert r.json()["result"] == "refunded"
    assert db("SELECT status, failure_reason FROM investments WHERE id=:i", i=inv_id)[0] == (
        "expired",
        "price_changed_refunded",
    )
    # its units are on sale again, at today's price
    assert _offering(db, pid) == (100, D("11000.00"), D("110.00"), D("0.00"))
    assert db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0] == D("1025.00")
    _assert_unit_invariant(db, pid)


@pytest.mark.asyncio
async def test_a_purchase_paid_within_its_hold_keeps_the_price_it_was_made_at(
    client, db, asession, monkeypatch
):
    _configure_stripe(monkeypatch)
    token = await _verified_user(client, db, "in.time@i.com")
    uid = _uid(db, "in.time@i.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    inv_id = (await _invest(client, token, pid, 1000, "card")).json()["investment_id"]
    pay_id = _payment_id_for(db, inv_id)

    await _reprice(asession, pid, "110")  # during the 30 minutes the units are held
    r = await _post_stripe(client, _stripe_event(pay_id, cents=102500, event_id="evt_price_3"))
    assert r.json()["result"] == "confirmed"
    assert db("SELECT units, unit_price FROM ownership_ledger WHERE user_id=:u", u=uid)[0] == (
        10,
        D("100.00"),
    )
    # 10 sold at 100, 90 for sale at 110
    assert _offering(db, pid) == (90, D("10900.00"), D("110.00"), D("1000.00"))
    _assert_unit_invariant(db, pid)


@pytest.mark.asyncio
async def test_a_late_purchase_is_still_honoured_while_the_price_is_the_same(
    client, db, asession, monkeypatch
):
    _configure_stripe(monkeypatch)
    token = await _verified_user(client, db, "same.price@i.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    inv_id = (await _invest(client, token, pid, 1000, "card")).json()["investment_id"]
    pay_id = _payment_id_for(db, inv_id)
    _lapse(db, "investments", inv_id)
    await investment_service.expire_reservations(asession)
    await asession.commit()
    # the price went up and came back: it is the price this purchase was made at
    await _reprice(asession, pid, "110")
    await _reprice(asession, pid, "100")
    r = await _post_stripe(client, _stripe_event(pay_id, cents=102500, event_id="evt_price_4"))
    assert r.json()["result"] == "reconciled_confirmed"
    assert _offering(db, pid) == (90, D("10000.00"), D("100.00"), D("1000.00"))


@pytest.mark.asyncio
async def test_a_plan_paid_late_does_not_lock_yesterdays_price(client, db, asession, monkeypatch):
    _card_rail(monkeypatch)
    token = await _verified_user(client, db, "late.plan.price@i.com")
    uid = _uid(db, "late.plan.price@i.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    db("UPDATE properties SET model='installment' WHERE id=:p", p=pid)

    # swept, then repriced, then the old checkout is paid
    plan = (await _plan(client, token, pid, method="card")).json()  # 12 units at 100
    cents = int(D(plan["payments"][0]["total_amount"]) * 100)
    _lapse(db, "installment_plans", plan["id"])
    assert await installment_service.expire_pending_plans(asession) == 1
    await asession.commit()
    await _reprice(asession, pid, "110")
    r = await _stripe_webhook(client, plan["payment_id"], cents=cents)
    assert r.status_code == 200, r.text
    assert db(
        "SELECT status, failure_reason, vested_units FROM installment_plans WHERE id=:p",
        p=plan["id"],
    )[0] == ("expired", "price_changed_refunded", 0)
    assert db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0] == D(cents) / 100
    assert _offering(db, pid) == (100, D("11000.00"), D("110.00"), D("0.00"))
    note = db("SELECT message FROM notifications WHERE user_id=:u ORDER BY created_at", u=uid)
    assert "changed before your down payment confirmed" in note[-1][0]

    # not swept yet: the same answer, and the held units go back on sale at today's price
    plan2 = (await _plan(client, token, pid, method="card", amount=1100)).json()  # 10 at 110
    cents2 = int(D(plan2["payments"][0]["total_amount"]) * 100)
    _lapse(db, "installment_plans", plan2["id"])
    await _reprice(asession, pid, "121")
    r = await _stripe_webhook(client, plan2["payment_id"], cents=cents2)
    assert r.status_code == 200, r.text
    assert db("SELECT status, failure_reason FROM installment_plans WHERE id=:p", p=plan2["id"])[
        0
    ] == ("expired", "price_changed_refunded")
    assert _offering(db, pid) == (100, D("12100.00"), D("121.00"), D("0.00"))
    assert db("SELECT count(*) FROM ownership_ledger WHERE user_id=:u", u=uid)[0][0] == 0
    _assert_unit_invariant(db, pid)

    # paid within its hold: the plan starts at the price it locked, whatever happens to the price
    plan3 = (await _plan(client, token, pid, method="card", amount=1210)).json()  # 10 at 121
    cents3 = int(D(plan3["payments"][0]["total_amount"]) * 100)
    await _reprice(asession, pid, "125")
    r = await _stripe_webhook(client, plan3["payment_id"], cents=cents3)
    assert r.status_code == 200, r.text
    assert db("SELECT status, unit_price FROM installment_plans WHERE id=:p", p=plan3["id"])[0] == (
        "active",
        D("121.00"),
    )
