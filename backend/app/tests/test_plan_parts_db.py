"""Part of a running installment plan changes hands (0042; client, 2026-11-08).

"An investor on an installment plan can sell or send part of it (one unit, two, any number);
the rest stays theirs. Selling 3 units of 10, the buyer takes 30% of everything: of what was
paid (that is what he pays the seller, plus or minus the price change), and of every payment
still to come, as a plan of his own with the same number of payments on the same dates. The
seller keeps 7 units and every installment drops to 70%. The last installment takes the
rounding, so the two plans add up to the original exactly. On the secondary market (the buyer
can take part of a listing too), to a liquidity provider, and to another person. At least one
unit. Overdue installments are paid first. Selling the whole plan stays as it is."

What each test protects:
  * the arithmetic: every payment is shared out and the two parts add up EXACTLY to the
    original (paid, still to pay, fees, units), the last payment of each kind taking the
    rounding; units vest no faster than the payment vests;
  * the secondary market: a buyer takes part of a listed plan and sees, before buying, the
    units, the cash now and the schedule at the new amounts; a second buyer takes another part;
    a buyer resells part of what he bought; every plan adds up to the original, money and units
    are conserved, both sides are told, the buyer has the plan and its document in his name;
  * the liquidity provider takes part of a plan (in two fills) and pays the discounted value
    less the installments taken over;
  * a transfer gives part (or all) of a plan to a verified member, who carries on paying;
  * what refuses: overdue installments, more units than are free or for sale, fewer than one,
    a later date or an unverified recipient for a transfer;
  * the new holders' installments are charged to them and vest to them.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.models import InstallmentPayment, InstallmentPlan
from app.services import installment_service
from app.tests.test_liquidity_db import _lp_user
from app.tests.test_offplan_exit_db import (
    D,
    _balance,
    _buy_position,
    _code,
    _h,
    _held,
    _investor,
    _plan,
    _property,
    _reconciles,
    _reprice,
)


# --- arrange ------------------------------------------------------------------------------- #
async def _list(client, token: str, plan_id: str, price, units: int | None = None):
    body: dict = {"plan_id": plan_id, "price_per_unit": price}
    if units is not None:
        body["units"] = units
    return await client.post("/api/v1/secondary/listings", json=body, headers=_h(token))


def _rows(db, plan_id: str) -> list[tuple]:
    """A plan's payments: (seq, base, fee, total, vest, status)."""
    return [
        tuple(r)
        for r in db(
            "SELECT seq, base_amount, fee_amount, total_amount, vest_units, status "
            "FROM installment_payments WHERE plan_id=:p ORDER BY seq",
            p=plan_id,
        )
    ]


def _plan_row(db, plan_id: str) -> tuple:
    return tuple(
        db(
            "SELECT investor_id, units_total, vested_units, status, parent_plan_id "
            "FROM installment_plans WHERE id=:p",
            p=plan_id,
        )[0]
    )


def _all_plans_add_up(db, original: list[tuple], units_total: int, pid: str) -> None:
    """Every plan of the property, together, is the original plan: per payment, the base, the
    fee, the total and the units; and the units of all the plans are the original units."""
    sums = {
        r[0]: (r[1], r[2], r[3], int(r[4]))
        for r in db(
            "SELECT p.seq, SUM(p.base_amount), SUM(p.fee_amount), SUM(p.total_amount), "
            "SUM(p.vest_units) FROM installment_payments p "
            "JOIN installment_plans pl ON pl.id = p.plan_id "
            "WHERE pl.property_id=:pid GROUP BY p.seq ORDER BY p.seq",
            pid=pid,
        )
    }
    assert sums == {r[0]: (r[1], r[2], r[3], int(r[4])) for r in original}
    total = db("SELECT SUM(units_total) FROM installment_plans WHERE property_id=:pid", pid=pid)[0][
        0
    ]
    assert int(total) == units_total


# --- the arithmetic ------------------------------------------------------------------------ #
def _synthetic(units: int, paid: int) -> tuple[InstallmentPlan, list[InstallmentPayment]]:
    """A plan with awkward amounts, so every share has to be rounded."""
    plan = InstallmentPlan(id=uuid.uuid4(), units_total=units, unit_price=D("142.86"))
    bases = [D("333.33")] + [D("111.11")] * 5 + [D("111.12")]
    fees = [D("13.33")] + [D("4.44")] * 5 + [D("4.45")]
    vests = [2, 0, 1, 1, 0, 1, units - 5]
    today = dt.date(2026, 11, 8)
    payments = [
        InstallmentPayment(
            seq=i,
            kind="downpayment" if i == 0 else ("final" if i == 6 else "installment"),
            due_date=today if i == 0 else dt.date(2026, 11 + i, 8) if i < 2 else today,
            base_amount=b,
            fee_amount=f,
            total_amount=b + f,
            vest_units=v,
            status="paid" if i < paid else "scheduled",
        )
        for i, (b, f, v) in enumerate(zip(bases, fees, vests, strict=True))
    ]
    return plan, payments


@pytest.mark.parametrize(
    "units,total,paid", [(3, 7, 2), (1, 7, 1), (6, 7, 3), (2, 9, 0), (5, 9, 6)]
)
def test_the_two_parts_add_up_to_the_original_exactly(units, total, paid):
    plan, payments = _synthetic(total, paid)
    rows = installment_service.split_figures(plan, payments, units)
    share = D(units) / D(total)
    q = installment_service._q
    for part, orig in zip(rows, payments, strict=True):
        # never more than the payment, never below nothing
        for name in ("base_amount", "fee_amount", "total_amount"):
            assert D(0) <= getattr(part, name) <= getattr(orig, name)
        assert part.total_amount == part.base_amount + part.fee_amount
        assert 0 <= part.vest_units <= orig.vest_units
    # the part of what was paid, and of what is still to pay, is the exact share of each
    for group in ("paid", "unpaid"):
        mine = [r for r in rows if (r.status == "paid") == (group == "paid")]
        orig = [p for p in payments if (p.status == "paid") == (group == "paid")]
        for name in ("base_amount", "fee_amount"):
            assert sum((getattr(r, name) for r in mine), D(0)) == q(
                sum((getattr(p, name) for p in orig), D(0)) * share
            )
        # every payment but the last of its kind is the plain share; the last takes the rest
        for r, p in zip(mine[:-1], orig[:-1], strict=True):
            assert r.base_amount == q(p.base_amount * share)
    assert sum(r.vest_units for r in rows) == units


def test_the_whole_plan_is_the_plan_itself():
    plan, payments = _synthetic(7, 2)
    rows = installment_service.split_figures(plan, payments, 7)
    assert [(r.base_amount, r.fee_amount, r.vest_units) for r in rows] == [
        (p.base_amount, p.fee_amount, p.vest_units) for p in payments
    ]


# --- the secondary market ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_part_of_a_plan_is_sold_bought_again_and_resold(client, db, asession):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "pp.seller@x.io", funds=2000)
    b1_tok, b1 = await _investor(client, db, "pp.b1@x.io", funds=1000)
    b2_tok, b2 = await _investor(client, db, "pp.b2@x.io", funds=1000)
    b3_tok, b3 = await _investor(client, db, "pp.b3@x.io", funds=1000)
    plan = await _plan(client, seller_tok, pid, amount=1000)  # 10 units: $300 down, 5 x $140
    original = _rows(db, plan["id"])
    await _reprice(asession, pid, "110")

    listing = (await _list(client, seller_tok, plan["id"], 110)).json()
    lid = listing["listing_id"]
    assert (listing["units_for_sale"], listing["units_remaining"]) == (10, 10)

    # before buying: 3 units, what he pays now, and the schedule he carries on at 30%
    quote = await client.get(
        f"/api/v1/secondary/listings/{lid}/quote", params={"units": 3}, headers=_h(b1_tok)
    )
    assert quote.status_code == 200, quote.text
    qt = quote.json()
    assert (qt["units"], qt["plan_units"], qt["whole"]) == (3, 10, False)
    # 3 x 110 = 330, less the 210 (30% of 700) he takes over: 120, + the 1% resale fee
    assert (qt["value"], qt["paid_principal"], qt["remaining_principal"]) == (
        "330.00",
        "90.00",
        "210.00",
    )
    assert (qt["cash"], qt["resale_fee"], qt["total_now"]) == ("120.00", "1.20", "121.20")
    assert [
        (s["seq"], s["base_amount"], s["fee_amount"], s["total_amount"]) for s in qt["schedule"]
    ] == [(n, "42.00", "1.68", "43.68") for n in range(1, 6)]
    # the dates are the plan's
    assert [s["due_date"] for s in qt["schedule"]] == [
        str(r[0])
        for r in db(
            "SELECT due_date FROM installment_payments WHERE plan_id=:p AND seq>0 ORDER BY seq",
            p=plan["id"],
        )
    ]

    bought = await _buy_position(client, b1_tok, lid, 3, "120.00")
    assert bought.status_code == 200, bought.text
    trade = bought.json()
    child1 = str(trade["plan_id"])
    assert child1 != plan["id"] and trade["units"] == 3 and trade["gross"] == "120.00"
    assert _balance(db, b1) == D("878.80") and _balance(db, seller) == D("1688.00") + D("120.00")
    # the seller keeps 7 units and every installment is 70%; the buyer's plan is the other 30%
    assert [r[1] for r in _rows(db, plan["id"])] == [D("210.00")] + [D("98.00")] * 5
    assert [r[1] for r in _rows(db, child1)] == [D("90.00")] + [D("42.00")] * 5
    assert [r[5] for r in _rows(db, child1)] == ["paid"] + ["scheduled"] * 5
    s_row, c_row = _plan_row(db, plan["id"]), _plan_row(db, child1)
    assert (str(s_row[0]), s_row[1], s_row[3]) == (seller, 7, "active")
    assert (str(c_row[0]), c_row[1], c_row[3], str(c_row[4])) == (b1, 3, "active", plan["id"])
    # the units vested so far are shared the same way and moved in the ledger
    assert _held(db, seller, pid) == s_row[2] and _held(db, b1, pid) == c_row[2]
    assert s_row[2] + c_row[2] == 3
    # the listing goes on with the 7 units left
    assert db("SELECT status, units_remaining FROM secondary_listings WHERE id=:i", i=lid)[0] == (
        "active",
        7,
    )
    _all_plans_add_up(db, original, 10, pid)
    await _reconciles(asession)

    # the buyer sees his own plan, its schedule, and the document in his name
    theirs = (await client.get("/api/v1/installments", headers=_h(b1_tok))).json()
    assert [p["id"] for p in theirs] == [child1]
    assert theirs[0]["parent_plan_id"] == plan["id"] and theirs[0]["acquired_at"] is not None
    assert (theirs[0]["position"]["entry_price"], theirs[0]["position"]["gain"]) == (
        "110.00",
        "0.00",
    )
    pdf = await client.get(f"/api/v1/installments/{child1}/schedule.pdf", headers=_h(b1_tok))
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert (
        await client.get(f"/api/v1/installments/{child1}/schedule.pdf", headers=_h(seller_tok))
    ).status_code == 404
    notes = {
        (str(r[0]), r[1])
        for r in db("SELECT user_id, title FROM notifications WHERE type='secondary'")
    }
    assert (seller, "Part of your installment plan sold") in notes
    assert (b1, "Installment position bought") in notes

    # a second buyer takes 2 of the 7 still listed: 2/7 of the seller's plan now
    q2 = (
        await client.get(
            f"/api/v1/secondary/listings/{lid}/quote", params={"units": 2}, headers=_h(b2_tok)
        )
    ).json()
    assert (q2["remaining_principal"], q2["cash"]) == ("140.00", "80.00")
    second = await _buy_position(client, b2_tok, lid, 2, "80.00")
    assert second.status_code == 200, second.text
    child2 = str(second.json()["plan_id"])
    assert _plan_row(db, plan["id"])[1] == 5 and _plan_row(db, child2)[1] == 2
    assert [r[1] for r in _rows(db, plan["id"])] == [D("150.00")] + [D("70.00")] * 5
    _all_plans_add_up(db, original, 10, pid)

    # the first buyer resells 1 of his 3 units (1/3 of his plan) at 120
    resale = await _list(client, b1_tok, child1, 120, units=1)
    assert resale.status_code == 200, resale.text
    assert resale.json()["position"]["cash"] == "50.00"  # 120 less a third of his 210
    third = await _buy_position(client, b3_tok, resale.json()["listing_id"], 1, "50.00")
    assert third.status_code == 200, third.text
    child3 = str(third.json()["plan_id"])
    assert str(_plan_row(db, child3)[4]) == child1
    assert _plan_row(db, child1)[1] == 2 and _plan_row(db, child3)[1] == 1
    assert (
        db("SELECT status FROM secondary_listings WHERE id=:i", i=resale.json()["listing_id"])[0][0]
        == "sold"
    )
    _all_plans_add_up(db, original, 10, pid)
    await _reconciles(asession)

    # the seller can still sell the rest whole, as before: the plan itself changes hands
    rest = await _buy_position(client, b2_tok, lid, 5, None)
    assert rest.status_code == 422 or rest.status_code == 409  # the cash must be confirmed
    q5 = (
        await client.get(
            f"/api/v1/secondary/listings/{lid}/quote", params={"units": 5}, headers=_h(b2_tok)
        )
    ).json()
    assert q5["whole"] is True
    whole = await _buy_position(client, b2_tok, lid, 5, q5["cash"])
    assert whole.status_code == 200, whole.text
    assert str(whole.json()["plan_id"]) == plan["id"]
    assert str(_plan_row(db, plan["id"])[0]) == b2
    _all_plans_add_up(db, original, 10, pid)
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_the_new_holders_installments_are_charged_to_them(client, db, asession):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "pc.seller@x.io", funds=2000)
    buyer_tok, buyer = await _investor(client, db, "pc.buyer@x.io", funds=1000)
    plan = await _plan(client, seller_tok, pid, amount=1000)
    original = _rows(db, plan["id"])
    lid = (await _list(client, seller_tok, plan["id"], 100)).json()["listing_id"]
    child = str((await _buy_position(client, buyer_tok, lid, 3, "90.00")).json()["plan_id"])

    # every installment falls due and the daily run charges each holder his own share
    db("UPDATE installment_payments SET due_date = current_date WHERE seq > 0")
    s_before, b_before = _balance(db, seller), _balance(db, buyer)
    await installment_service.run_due(asession)
    await asession.commit()
    assert s_before - _balance(db, seller) == 5 * D("101.92")  # 98 + 3.92, five times
    assert b_before - _balance(db, buyer) == 5 * D("43.68")  # 42 + 1.68, five times
    # both plans are complete and every unit vested to its holder
    assert _plan_row(db, plan["id"])[1:4] == (7, 7, "completed")
    assert _plan_row(db, child)[1:4] == (3, 3, "completed")
    assert (_held(db, seller, pid), _held(db, buyer, pid)) == (7, 3)
    _all_plans_add_up(db, original, 10, pid)
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_a_part_refuses_what_it_must(client, db, asession):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "pr.seller@x.io", funds=2000)
    buyer_tok, _buyer = await _investor(client, db, "pr.buyer@x.io", funds=1000)
    plan = await _plan(client, seller_tok, pid, amount=1000)

    # fewer than one, more than the plan has
    assert (await _list(client, seller_tok, plan["id"], 100, units=0)).status_code == 422
    over = await _list(client, seller_tok, plan["id"], 100, units=11)
    assert over.status_code == 422 and _code(over) == "INVALID_UNITS"

    listing = (await _list(client, seller_tok, plan["id"], 100, units=4)).json()
    lid = listing["listing_id"]
    assert (listing["units_for_sale"], listing["position"]["units"]) == (4, 4)
    # more than is for sale
    more = await _buy_position(client, buyer_tok, lid, 5, "1.00")
    assert more.status_code == 409 and _code(more) == "INSUFFICIENT_UNITS"
    # a stale amount is never charged
    stale = await _buy_position(client, buyer_tok, lid, 2, "1.00")
    assert stale.status_code == 409 and _code(stale) == "POSITION_CHANGED"

    # an installment is overdue: no part changes hands until it is paid
    db(
        "UPDATE installment_payments SET due_date = current_date - 1 WHERE plan_id=:p AND seq=1",
        p=plan["id"],
    )
    late = await _buy_position(client, buyer_tok, lid, 2, "60.00")
    assert late.status_code == 409 and _code(late) == "PLAN_OVERDUE"
    quoted = await client.get(
        f"/api/v1/secondary/listings/{lid}/quote", params={"units": 2}, headers=_h(buyer_tok)
    )
    assert _code(quoted) == "PLAN_OVERDUE"
    await client.post(f"/api/v1/secondary/listings/{lid}/cancel", headers=_h(seller_tok))
    part = await _list(client, seller_tok, plan["id"], 100, units=3)
    assert part.status_code == 409 and _code(part) == "PLAN_OVERDUE"
    assert "overdue" in part.json()["error"]["message"]
    # selling the whole plan stays as it was
    assert (await _list(client, seller_tok, plan["id"], 100)).status_code == 200
    # nothing moved through any of that
    assert db("SELECT count(*) FROM installment_plans")[0][0] == 1
    assert db("SELECT count(*) FROM secondary_trades")[0][0] == 0
    assert _plan_row(db, plan["id"])[1] == 10 and str(_plan_row(db, plan["id"])[0]) == seller
    await _reconciles(asession)


# --- the liquidity provider ---------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_liquidity_provider_takes_part_of_a_plan(client, db, asession):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "pl.seller@x.io", funds=2000)
    lp_tok = await _lp_user(client, db, "pl.lp@x.io")
    lp = str(db("SELECT id FROM users WHERE email='pl.lp@x.io'")[0][0])
    db(
        "INSERT INTO transactions (user_id, type, amount, status) "
        "VALUES (:u,'deposit',1000,'completed')",
        u=lp,
    )
    db("UPDATE wallets SET balance=1000 WHERE user_id=:u", u=lp)
    plan = await _plan(client, seller_tok, pid, amount=1000)
    original = _rows(db, plan["id"])

    # 4 of the 10 units: 400 at the 3% discount = 388, less the 280 they carry: 108 now;
    # the 2% fee comes off the seller's 108
    made = await client.post(
        "/api/v1/liquidity/exit-requests",
        json={"plan_id": plan["id"], "units": 4},
        headers=_h(seller_tok, idem=True),
    )
    assert made.status_code == 200, made.text
    req = made.json()
    assert (req["plan_id"], req["units"]) == (plan["id"], 4)
    pos = req["position"]
    assert (pos["lp_value"], pos["remaining_principal"], pos["cash"]) == (
        "388.00",
        "280.00",
        "108.00",
    )
    assert (pos["liquidity_fee"], pos["seller_net"]) == ("2.16", "105.84")
    # the 4 units are offered: the rest of the plan can be listed, not more
    over = await _list(client, seller_tok, plan["id"], 100)
    assert over.status_code == 409 and _code(over) == "PLAN_UNITS_COMMITTED"
    # the provider sees them in the book, and what 2 of them come to
    book = (await client.get("/api/v1/liquidity/exit-requests", headers=_h(lp_tok))).json()
    assert book["items"][0]["position"]["cash"] == "108.00"
    rid = req["request_id"]
    q2 = (
        await client.get(
            f"/api/v1/liquidity/exit-requests/{rid}/quote", params={"units": 2}, headers=_h(lp_tok)
        )
    ).json()
    assert (q2["cash"], q2["whole"]) == ("54.00", False)
    assert [s["base_amount"] for s in q2["schedule"]] == ["28.00"] * 5

    funded = await client.post(
        f"/api/v1/liquidity/exit-requests/{rid}/fund",
        json={"units": 2, "expected_cash": "54.00"},
        headers=_h(lp_tok, idem=True),
    )
    assert funded.status_code == 200, funded.text
    lp_plan = str(funded.json()["plan_id"])
    assert _plan_row(db, lp_plan)[1] == 2 and str(_plan_row(db, lp_plan)[0]) == lp
    assert _balance(db, lp) == D("946.00")
    assert _balance(db, seller) == D("1688.00") + D("54.00") - D("1.08")
    # the second half: 2 of the 8 units the seller has now
    q_rest = (
        await client.get(
            f"/api/v1/liquidity/exit-requests/{rid}/quote", params={"units": 2}, headers=_h(lp_tok)
        )
    ).json()
    assert q_rest["cash"] == "54.00"
    again = await client.post(
        f"/api/v1/liquidity/exit-requests/{rid}/fund",
        json={"units": 2, "expected_cash": "54.00"},
        headers=_h(lp_tok, idem=True),
    )
    assert again.status_code == 200, again.text
    assert db("SELECT status FROM lp_exit_requests WHERE id=:i", i=rid)[0][0] == "filled"
    assert _plan_row(db, plan["id"])[1] == 6
    assert db("SELECT count(*) FROM installment_plans WHERE investor_id=:u", u=lp)[0][0] == 2
    _all_plans_add_up(db, original, 10, pid)
    await _reconciles(asession)
    notes = {r[0] for r in db("SELECT title FROM notifications WHERE type='liquidity'")}
    assert notes == {"Instant exit funded", "Liquidity deployed"}

    # overdue: the seller cannot offer more until it is paid
    db(
        "UPDATE installment_payments SET due_date = current_date - 1 WHERE plan_id=:p AND seq=1",
        p=plan["id"],
    )
    late = await client.post(
        "/api/v1/liquidity/exit-requests",
        json={"plan_id": plan["id"], "units": 1},
        headers=_h(seller_tok, idem=True),
    )
    assert late.status_code == 409 and _code(late) == "PLAN_OVERDUE"


# --- a transfer to another person ---------------------------------------------------------- #
async def _send(client, token: str, plan_id: str, units: int, to: str, **extra):
    body = {"asset": "plan", "plan_id": plan_id, "units": units, "recipient_email": to, **extra}
    return await client.post("/api/v1/transfers", json=body, headers=_h(token, idem=True))


@pytest.mark.asyncio
async def test_part_of_a_plan_is_sent_to_another_person(client, db, asession):
    pid = _property(db)
    db(
        "INSERT INTO platform_settings (key, value) VALUES ('transfer_fee_pct', '1') "
        "ON CONFLICT (key) DO UPDATE SET value='1'"
    )
    sender_tok, sender = await _investor(client, db, "pt.sender@x.io", funds=2000)
    _rtok, recipient = await _investor(client, db, "pt.recipient@x.io")
    db("UPDATE users SET email_verified=true WHERE id IN (:a,:b)", a=sender, b=recipient)
    _ntok, _new = await _investor(client, db, "pt.unverified@x.io", kyc=False)
    plan = await _plan(client, sender_tok, pid, amount=1000)
    original = _rows(db, plan["id"])

    # the review: 2 units worth 200, carrying 140 still to pay: 60 given, the 1% fee on that
    quote = await client.post(
        "/api/v1/transfers/quote",
        json={
            "asset": "plan",
            "plan_id": plan["id"],
            "units": 2,
            "recipient_email": "pt.recipient@x.io",
        },
        headers=_h(sender_tok),
    )
    assert quote.status_code == 200, quote.text
    qt = quote.json()
    assert (qt["amount"], qt["fee"], qt["charged"]) == ("60.00", "0.60", "0.60")
    assert qt["plan"]["remaining_principal"] == "140.00"
    assert [s["base_amount"] for s in qt["plan"]["schedule"]] == ["28.00"] * 5

    # refused: a later date, an unverified recipient, more units than the plan has
    later = await _send(
        client,
        sender_tok,
        plan["id"],
        2,
        "pt.recipient@x.io",
        deliver_on=(dt.date.today() + dt.timedelta(days=3)).isoformat(),
    )
    assert _code(later) == "PLAN_TRANSFER_TODAY"
    assert _code(await _send(client, sender_tok, plan["id"], 2, "pt.unverified@x.io")) == (
        "RECIPIENT_NOT_READY"
    )
    assert _code(await _send(client, sender_tok, plan["id"], 11, "pt.recipient@x.io")) == (
        "INSUFFICIENT_UNITS"
    )

    sent = await _send(client, sender_tok, plan["id"], 2, "pt.recipient@x.io")
    assert sent.status_code in (200, 201), sent.text
    assert sent.json()["status"] == "delivered"
    new_plan = str(db("SELECT new_plan_id FROM transfers")[0][0])
    assert str(_plan_row(db, new_plan)[0]) == recipient and _plan_row(db, new_plan)[1] == 2
    assert _plan_row(db, plan["id"])[1] == 8
    assert _balance(db, sender) == D("1688.00") - D("0.60")
    _all_plans_add_up(db, original, 10, pid)
    note = db(
        "SELECT message FROM notifications WHERE user_id=:u AND type='transfer'", u=recipient
    )[0][0]
    assert "installment plan in your name" in note and "5 installment(s) remain" in note

    # the whole of what is left goes as the plan itself
    whole = await _send(client, sender_tok, plan["id"], 8, "pt.recipient@x.io")
    assert whole.status_code in (200, 201), whole.text
    assert str(_plan_row(db, plan["id"])[0]) == recipient
    assert db("SELECT count(*) FROM installment_plans")[0][0] == 2
    _all_plans_add_up(db, original, 10, pid)
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_a_transfer_waits_for_nothing_overdue(client, db, asession):
    pid = _property(db)
    sender_tok, sender = await _investor(client, db, "po.sender@x.io", funds=2000)
    _rtok, recipient = await _investor(client, db, "po.recipient@x.io")
    db("UPDATE users SET email_verified=true WHERE id IN (:a,:b)", a=sender, b=recipient)
    plan = await _plan(client, sender_tok, pid, amount=1000)
    db(
        "UPDATE installment_payments SET status='overdue', due_date = current_date - 3 "
        "WHERE plan_id=:p AND seq=1",
        p=plan["id"],
    )
    late = await _send(client, sender_tok, plan["id"], 2, "po.recipient@x.io")
    assert late.status_code == 409 and _code(late) == "PLAN_OVERDUE"
    assert db("SELECT count(*) FROM transfers")[0][0] == 0
    # what the sender is offered shows it
    opts = (await client.get("/api/v1/transfers/options", headers=_h(sender_tok))).json()
    assert opts["plans"][0]["overdue_amount"] == "145.60"
    await _reconciles(asession)
