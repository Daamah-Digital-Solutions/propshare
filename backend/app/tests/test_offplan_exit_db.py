"""Exit for properties under construction (0034; client meeting 2026-10-01).

"A unit of a property under construction earns by its price going up. Every month we give
the property its new price; the holder can exit at it at any time. Fully paid: he sells like
a ready unit. On installments: the buyer pays him what he paid plus the increase on the
whole position, and carries on with the remaining installments."

What each test protects:
  * a new price is recorded once, with its history, and everything reads it: a new buyer pays
    it, a holding is valued at it, the offering's total and minimum follow, holders are told;
    an open liquidity-provider exit request priced at the old price is closed;
  * a running installment plan is valued as a POSITION (all its units at the price, less the
    principal still to pay), in the portfolio and for a sale;
  * a position changes hands whole and exactly: the buyer pays the seller paid + increase,
    takes the vested units and the plan, and pays the remaining installments; units and money
    are conserved; nothing can be charged that the buyer did not confirm;
  * a position that was bought is measured from what ITS holder paid: no gain the day it is
    bought, and on a resale the next buyer pays that holder's own cost plus the change since;
  * what refuses: a partial purchase, a stale amount, an own or second listing, a price that
    does not cover the remainder, someone else's plan, a paid-off plan, a Nova pledge, no KYC,
    no funds;
  * an under-construction listing is bought the way the listing says: by installments, in
    full, or either;
  * the assistant knows all of it: the price now and its history, how each listing is bought,
    an order prepared either way, and it no longer calls phased sales "not built".
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

from app.core.errors import AppError
from app.services import (
    installment_service,
    investment_service,
    price_service,
    reconciliation_service,
)
from app.services.assistant import platform_gaps, prompts
from app.services.assistant.agent import _card_for
from app.tests.test_assistant_portfolio_prep_db import _ctx, _run

PW = "Passw0rd!23"
D = decimal.Decimal


# --- arrange ------------------------------------------------------------------------------- #
async def _investor(client, db, email: str, *, funds: int = 0, kyc: bool = True) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Inv"}
    )
    assert r.status_code == 201, r.text
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    if kyc:
        db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    if funds:
        # a real deposit row, so the wallet reconciles (balance == sum of transactions)
        db(
            "INSERT INTO transactions (user_id, type, amount, status) "
            "VALUES (:u,'deposit',:a,'completed')",
            u=uid,
            a=funds,
        )
        db("UPDATE wallets SET balance=:a WHERE user_id=:u", a=funds, u=uid)
    return r.json()["access_token"], uid


def _property(
    db,
    *,
    model: str = "installment",
    payment: str = "installments",
    unit_price: int = 100,
    units: int = 1000,
    minimum: int = 100,
    status: str = "active",
) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment,offplan_payment) VALUES "
        "(:id,'Creek Tower','Dubai','residential',:m,:st,:tv,:up,:tu,:tu,:mn,:pay)",
        id=pid,
        m=model,
        st=status,
        tv=unit_price * units,
        up=unit_price,
        tu=units,
        mn=minimum,
        pay=payment,
    )
    return pid


def _h(token: str, *, idem: bool = False) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if idem:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    return headers


async def _plan(client, token: str, pid: str, *, amount: int = 1000, months: int = 6) -> dict:
    """A plan paid from the wallet: 10 units at $100 over 6 months = $300 down (3 units vest),
    then 5 installments of $140."""
    r = await client.post(
        "/api/v1/installments",
        json={"property_id": pid, "amount": amount, "duration_months": months},
        headers=_h(token, idem=True),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _buy_full(client, token: str, pid: str, amount: int):
    return await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": amount, "method": "wallet"},
        headers=_h(token, idem=True),
    )


async def _reprice(asession, pid: str, price, **kw):
    row = await price_service.record_price(asession, property_id=uuid.UUID(pid), price=price, **kw)
    await asession.commit()
    return row


async def _list_position(client, token: str, plan_id: str, price):
    return await client.post(
        "/api/v1/secondary/listings",
        json={"plan_id": plan_id, "price_per_unit": price},
        headers=_h(token),
    )


async def _buy_position(
    client, token: str, listing_id: str, units: int, cash: str | None, key=None
):
    headers = _h(token)
    headers["Idempotency-Key"] = key or str(uuid.uuid4())
    body: dict = {"units": units}
    if cash is not None:
        body["expected_cash"] = cash
    return await client.post(
        f"/api/v1/secondary/listings/{listing_id}/buy", json=body, headers=headers
    )


def _balance(db, uid: str) -> D:
    return db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0]


def _held(db, uid: str, pid: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger "
            "WHERE user_id=:u AND property_id=:p",
            u=uid,
            p=pid,
        )[0][0]
    )


async def _reconciles(asession) -> None:
    """Nothing drifted: wallets equal their transactions, units are conserved."""
    result = await reconciliation_service.run(asession)
    drift = {c["name"]: c["samples"] for c in result["checks"] if c["drift_count"]}
    assert not drift, drift


def _code(response) -> str:
    return response.json()["error"]["code"]


# --- the unit price moves ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_a_new_price_is_recorded_once_and_everything_reads_it(client, db, asession):
    pid = _property(db, payment="both", minimum=500)
    full_tok, full_uid = await _investor(client, db, "paid.full@x.io", funds=5000)
    plan_tok, plan_uid = await _investor(client, db, "on.plan@x.io", funds=5000)
    _late_tok, late_uid = await _investor(client, db, "later@x.io", funds=5000)
    admin = str(db("SELECT id FROM users WHERE email='later@x.io'")[0][0])
    assert (await _buy_full(client, full_tok, pid, 1000)).status_code == 200  # 10 units at $100
    await _plan(client, plan_tok, pid, amount=1000)  # 10 more on a plan, 3 vested

    row = await _reprice(
        asession, pid, "110", label="Phase 2", note="Structure complete", actor_id=uuid.UUID(admin)
    )
    assert (row.previous_price, row.price, row.label) == (D("100.00"), D("110.00"), "Phase 2")

    prop = db(
        "SELECT unit_price, total_value, minimum_investment, available_units FROM properties"
    )[0]
    # 980 units are still for sale, now at $110: the offering's total follows them, and the
    # minimum stays 5 whole units
    assert prop == (D("110.00"), D("100000.00") + 980 * 10, D("550.00"), 980)
    history = db("SELECT previous_price, price, label, note, created_by FROM property_prices")
    assert history == [
        (D("100.00"), D("110.00"), "Phase 2", "Structure complete", uuid.UUID(admin))
    ]
    audit = db("SELECT before, after FROM audit_log WHERE action='property.price_recorded'")
    assert len(audit) == 1 and audit[0][1]["unit_price"] == "110.00"
    assert audit[0][0]["unit_price"] == "100.00" and audit[0][1]["change_pct"] == "10.00"
    # the holder and the investor on a plan are told; someone who holds nothing is not
    told = {
        str(r[0])
        for r in db("SELECT user_id FROM notifications WHERE title='New unit price: Creek Tower'")
    }
    assert told == {full_uid, plan_uid}
    msg = db("SELECT message FROM notifications WHERE title LIKE 'New unit price%' LIMIT 1")[0][0]
    assert "is now $110 (+10.00% from $100). Phase 2." in msg

    # the public price line: launch, then the change
    r = await client.get(f"/api/v1/properties/{pid}/prices")
    assert r.status_code == 200, r.text
    line = r.json()
    assert (line["launch_price"], line["current_price"], line["change_pct"]) == (
        "100.00",
        "110.00",
        "10.00",
    )
    assert line["phase"] == "Phase 2" and line["updated_at"] is not None
    assert [(p["price"], p["label"], p["change_pct"]) for p in line["points"]] == [
        ("100.00", "Launch price", "0.00"),
        ("110.00", "Phase 2", "10.00"),
    ]

    # a new buyer pays the new price; the plan started before keeps its own
    late = await _buy_full(client, _late_tok, pid, 1100)
    assert late.status_code == 200 and (late.json()["units"], late.json()["amount"]) == (
        10,
        "1100.00",
    )
    plans = (await client.get("/api/v1/installments", headers=_h(plan_tok))).json()
    assert plans[0]["unit_price"] == "100.00"
    assert [p["base_amount"] for p in plans[0]["payments"]][:2] == ["300.00", "140.00"]
    assert str(late_uid) and _held(db, late_uid, pid) == 10
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_a_price_change_refuses_what_it_must(client, db, asession):
    pid = _property(db)
    draft = _property(db, status="draft")
    for price, code in (("100", "SAME_PRICE"), ("0", "INVALID_PRICE"), ("abc", "INVALID_PRICE")):
        with pytest.raises(AppError) as exc:
            await price_service.record_price(asession, property_id=uuid.UUID(pid), price=price)
        assert exc.value.code == code, price
        await asession.rollback()
    # a typing mistake (1100 for 110) is not a revaluation
    with pytest.raises(AppError) as exc:
        await price_service.record_price(asession, property_id=uuid.UUID(pid), price="1100")
    assert exc.value.code == "LARGE_CHANGE" and "+1000.00%" in exc.value.message
    await asession.rollback()
    await _reprice(asession, pid, "140", confirm_large=True)  # a real big step, confirmed
    with pytest.raises(AppError) as exc:
        await price_service.record_price(asession, property_id=uuid.UUID(draft), price="120")
    assert exc.value.code == "NOT_PUBLISHED"
    await asession.rollback()
    assert db("SELECT count(*) FROM property_prices")[0][0] == 1
    # a listing whose price never changed has a history of one point
    r = await client.get(f"/api/v1/properties/{_property(db)}/prices")
    assert r.json()["updated_at"] is None and len(r.json()["points"]) == 1


@pytest.mark.asyncio
async def test_holdings_and_positions_are_valued_at_the_new_price(client, db, asession):
    pid = _property(db, payment="both")
    full_tok, _full = await _investor(client, db, "v.full@x.io", funds=5000)
    plan_tok, _plan_uid = await _investor(client, db, "v.plan@x.io", funds=5000)
    await _buy_full(client, full_tok, pid, 1000)
    await _plan(client, plan_tok, pid, amount=1000)
    before = (await client.get("/api/v1/investments/portfolio", headers=_h(plan_tok))).json()
    # $300 paid, nothing gained yet: the position is worth what was paid in (not the $300 of
    # the 3 vested units by luck: 10 x 100 - 700 still to pay)
    assert (before["invested"], before["current_value"]) == ("300.00", "300.00")
    await _reprice(asession, pid, "110")

    full = (await client.get("/api/v1/investments/portfolio", headers=_h(full_tok))).json()
    assert (full["invested"], full["current_value"], full["sold"]) == ("1000.00", "1100.00", "0.00")
    plan = (await client.get("/api/v1/investments/portfolio", headers=_h(plan_tok))).json()
    # paid 300, and the WHOLE position (10 units) rose $10 a unit: 300 + 100
    assert (plan["invested"], plan["current_value"]) == ("300.00", "400.00")

    holding = (await client.get("/api/v1/secondary/holdings", headers=_h(full_tok))).json()[
        "items"
    ][0]
    assert (
        holding["unit_price"],
        holding["launch_price"],
        holding["price_change_pct"],
        holding["average_cost"],
        holding["sellable_units"],
    ) == ("110.00", "100.00", "10.00", "100.00", 10)
    assert holding["price_updated_at"] is not None
    on_plan = (await client.get("/api/v1/secondary/holdings", headers=_h(plan_tok))).json()[
        "items"
    ][0]
    assert (on_plan["units"], on_plan["plan_units"], on_plan["sellable_units"]) == (3, 3, 0)
    assert on_plan["held_back"]["installment_plan"] == 3

    position = (await client.get("/api/v1/secondary/positions", headers=_h(plan_tok))).json()
    assert position["total"] == 1
    p = position["items"][0]
    assert (p["units"], p["vested_units"], p["locked_price"], p["price"]) == (
        10,
        3,
        "100.00",
        "110.00",
    )
    assert (p["value"], p["paid_principal"], p["remaining_principal"]) == (
        "1100.00",
        "300.00",
        "700.00",
    )
    # who started the plan got in at the price it locked: what he put in is what he paid
    assert (p["entry_price"], p["cost"]) == ("100.00", "300.00")
    assert (p["gain"], p["cash"], p["resale_fee"], p["total_now"]) == (
        "100.00",
        "400.00",
        "4.00",
        "404.00",
    )
    assert p["installments_left"] == 5 and p["remaining_fees"] == "28.00" and p["blocked"] is None
    # the plan itself says the same on the Installments tab
    mine = (await client.get("/api/v1/installments", headers=_h(plan_tok))).json()[0]
    assert mine["position"]["equity"] == "400.00" and mine["listing_id"] is None
    assert (mine["position"]["entry_price"], mine["position"]["cost"], mine["acquired_at"]) == (
        "100.00",
        "300.00",
        None,
    )


@pytest.mark.asyncio
async def test_an_open_liquidity_exit_is_closed_when_the_price_changes(client, db, asession):
    pid = _property(db, payment="full")
    tok, uid = await _investor(client, db, "lp.seller@x.io", funds=2000)
    await _buy_full(client, tok, pid, 1000)
    r = await client.post(
        "/api/v1/liquidity/exit-requests", json={"property_id": pid, "units": 4}, headers=_h(tok)
    )
    assert r.status_code == 200 and r.json()["unit_price"] == "100.00", r.text
    held = (await client.get("/api/v1/secondary/holdings", headers=_h(tok))).json()["items"][0]
    assert held["sellable_units"] == 6

    await _reprice(asession, pid, "108")
    assert db("SELECT status FROM lp_exit_requests")[0][0] == "expired"
    held = (await client.get("/api/v1/secondary/holdings", headers=_h(tok))).json()["items"][0]
    assert held["sellable_units"] == 10  # free again
    note = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title LIKE 'Exit request closed%'",
        u=uid,
    )[0][0]
    assert "priced at $100 a unit" in note and "now $108" in note
    # a new request is priced at the new price
    r = await client.post(
        "/api/v1/liquidity/exit-requests", json={"property_id": pid, "units": 4}, headers=_h(tok)
    )
    assert (r.json()["unit_price"], r.json()["gross"]) == ("108.00", "432.00")


# --- a position on an installment plan changes hands ---------------------------------------- #
@pytest.mark.asyncio
async def test_an_installment_position_changes_hands_whole(client, db, asession):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "pos.seller@x.io", funds=1000)
    buyer_tok, buyer = await _investor(client, db, "pos.buyer@x.io", funds=1000)
    plan = await _plan(client, seller_tok, pid, amount=1000)  # $312 paid (300 + 4% fee)
    await _reprice(asession, pid, "110")

    listed = await _list_position(client, seller_tok, plan["id"], 110)
    assert listed.status_code == 200, listed.text
    listing = listed.json()
    assert listing["plan_id"] == plan["id"] and listing["units_remaining"] == 10
    pos = listing["position"]
    # the client's own example: $1,000 bought, $200... here $300 paid, +10%: the buyer pays
    # the $300 and the $100 the whole position gained, then the $700 still to pay
    assert (pos["cash"], pos["remaining_principal"], pos["resale_fee"], pos["total_now"]) == (
        "400.00",
        "700.00",
        "4.00",
        "404.00",
    )
    assert [(s["seq"], s["base_amount"], s["fee_amount"]) for s in pos["schedule"]] == [
        (n, "140.00", "5.60") for n in range(1, 6)
    ]
    # the listed position holds no extra units of the seller's: only the plan's 3 are held
    held = (await client.get("/api/v1/secondary/holdings", headers=_h(seller_tok))).json()["items"]
    assert (held[0]["listed_units"], held[0]["sellable_units"]) == (3, 0)
    market = (await client.get("/api/v1/secondary/listings", headers=_h(buyer_tok))).json()
    assert market["items"][0]["position"]["cash"] == "400.00"
    mine = (await client.get("/api/v1/installments", headers=_h(seller_tok))).json()[0]
    assert mine["listing_id"] == listing["listing_id"]

    key = str(uuid.uuid4())
    bought = await _buy_position(client, buyer_tok, listing["listing_id"], 10, "400.00", key)
    assert bought.status_code == 200, bought.text
    trade = bought.json()
    assert (trade["gross"], trade["resale_fee"], trade["total_charged"]) == (
        "400.00",
        "4.00",
        "404.00",
    )
    assert (trade["plan_id"], trade["position_value"], trade["paid_principal"]) == (
        plan["id"],
        "1100.00",
        "300.00",
    )
    assert (trade["assumed_principal"], trade["assumed_fees"]) == ("700.00", "28.00")

    # money: the buyer paid 404, the seller got 400 (he had paid 312: 300 + the fee)
    assert _balance(db, buyer) == D("596.00") and _balance(db, seller) == D("1088.00")
    # units: the 3 vested moved; the plan and its 7 units to come are the buyer's
    assert (_held(db, seller, pid), _held(db, buyer, pid)) == (0, 3)
    plan_row = db("SELECT investor_id, status, vested_units, units_total FROM installment_plans")[0]
    assert (str(plan_row[0]), plan_row[1], plan_row[2], plan_row[3]) == (buyer, "active", 3, 10)
    assert db("SELECT status, units_remaining FROM secondary_listings")[0] == ("sold", 0)
    assert (await client.get("/api/v1/installments", headers=_h(seller_tok))).json() == []
    theirs = (await client.get("/api/v1/installments", headers=_h(buyer_tok))).json()[0]
    assert theirs["id"] == plan["id"] and theirs["acquired_at"] is not None
    assert theirs["position"]["equity"] == "400.00"
    # he bought at 110 a unit: the 400 he paid is his cost, and he has gained nothing yet
    # (the 100 the position had gained was the seller's, and he paid for it)
    assert (
        theirs["position"]["entry_price"],
        theirs["position"]["cost"],
        theirs["position"]["gain"],
    ) == ("110.00", "400.00", "0.00")
    # the same request again is the same trade, not a second charge
    again = await _buy_position(client, buyer_tok, listing["listing_id"], 10, "400.00", key)
    assert again.status_code == 200 and again.json()["trade_id"] == trade["trade_id"]
    assert _balance(db, buyer) == D("596.00")

    # what each sees afterwards: the seller sold for 400 what he put 300 into
    sold = (await client.get("/api/v1/investments/portfolio", headers=_h(seller_tok))).json()
    assert (sold["invested"], sold["current_value"], sold["sold"]) == ("300.00", "0.00", "400.00")
    owns = (await client.get("/api/v1/investments/portfolio", headers=_h(buyer_tok))).json()
    assert (owns["invested"], owns["current_value"]) == ("400.00", "400.00")
    notes = {r[0] for r in db("SELECT title FROM notifications WHERE type='secondary'")}
    assert notes == {"Installment position sold", "Installment position bought"}
    assert db("SELECT count(*) FROM audit_log WHERE action='secondary.position_traded'")[0][0] == 1
    await _reconciles(asession)

    # the buyer carries on: the next installment is charged to him and vests to him
    nxt = next(p for p in theirs["payments"] if p["status"] != "paid")
    paid = await client.post(
        f"/api/v1/installments/payments/{nxt['id']}/pay", headers=_h(buyer_tok, idem=True)
    )
    assert paid.status_code == 200, paid.text
    assert _balance(db, buyer) == D("596.00") - D("145.60")
    assert _held(db, buyer, pid) > 3 and _held(db, seller, pid) == 0
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_a_bought_position_is_measured_from_what_its_buyer_paid(client, db, asession):
    pid = _property(db)
    first_tok, first = await _investor(client, db, "first.holder@x.io", funds=1000)
    second_tok, second = await _investor(client, db, "second.holder@x.io", funds=2000)
    third_tok, third = await _investor(client, db, "third.holder@x.io", funds=2000)
    plan = await _plan(client, first_tok, pid, amount=1000)  # 10 units at 100, 300 paid
    await _reprice(asession, pid, "110")
    listing = (await _list_position(client, first_tok, plan["id"], 110)).json()
    # what the buyer is shown: the seller's own cost and gain make up the cash
    assert (
        listing["position"]["entry_price"],
        listing["position"]["cost"],
        listing["position"]["gain"],
        listing["position"]["cash"],
    ) == ("100.00", "300.00", "100.00", "400.00")
    bought = await _buy_position(client, second_tok, listing["listing_id"], 10, "400.00")
    assert bought.status_code == 200, bought.text

    async def position_of(token: str) -> dict:
        return (await client.get("/api/v1/installments", headers=_h(token))).json()[0]["position"]

    # the second holder pays an installment: his cost follows, and there is still no gain
    mine = (await client.get("/api/v1/installments", headers=_h(second_tok))).json()[0]
    nxt = next(p for p in mine["payments"] if p["status"] != "paid")
    paid = await client.post(
        f"/api/v1/installments/payments/{nxt['id']}/pay", headers=_h(second_tok, idem=True)
    )
    assert paid.status_code == 200, paid.text
    pos = await position_of(second_tok)
    assert (pos["cost"], pos["gain"], pos["equity"]) == ("540.00", "0.00", "540.00")

    # the price goes from 110 to 121: 11 a unit on all 10 units is HIS gain (not 21)
    await _reprice(asession, pid, "121")
    pos = await position_of(second_tok)
    assert (pos["price"], pos["entry_price"], pos["value"]) == ("121.00", "110.00", "1210.00")
    assert (pos["cost"], pos["gain"], pos["equity"]) == ("540.00", "110.00", "650.00")
    listed = (await client.get("/api/v1/secondary/positions", headers=_h(second_tok))).json()
    assert (
        listed["items"][0]["entry_price"],
        listed["items"][0]["cost"],
        listed["items"][0]["gain"],
        listed["items"][0]["cash"],
    ) == ("110.00", "540.00", "110.00", "650.00")

    # the assistant tells him the same: his own cost, his own gain
    ctx = await _ctx(asession, second)
    holdings = await _run(asession, ctx, "get_my_holdings", {})
    p = holdings["positions"][0]
    assert (p["entry_price"], p["cost"], p["gain"], p["you_would_receive"]) == (
        "110.00",
        "540.00",
        "110.00",
        "650.00",
    )
    plans = await _run(asession, ctx, "list_my_installment_plans", {})
    item = plans["items"][0]
    assert (item["taken_over"], item["entry_price"], item["cost"], item["gain"]) == (
        True,
        "110.00",
        "540.00",
        "110.00",
    )
    sale = await _run(asession, ctx, "prepare_sale", {"property": "Creek Tower", "position": True})
    assert (sale["kind"], sale["you_receive"], sale["cost"], sale["gain"]) == (
        "position",
        "650.00",
        "540.00",
        "110.00",
    )
    assert (
        "The buyer pays you what you have put in (540.00) plus the price increase on all the "
        "units (110.00)" in " ".join(sale["notes"])
    )
    card = _card_for("prepare_sale", sale, [])
    assert (card["position"]["cost"], card["position"]["gain"]) == ("540.00", "110.00")

    # he sells it on: the third holder pays his cost plus his gain, and starts from there
    again = (await _list_position(client, second_tok, plan["id"], 121)).json()
    assert (again["position"]["cost"], again["position"]["gain"], again["position"]["cash"]) == (
        "540.00",
        "110.00",
        "650.00",
    )
    resold = await _buy_position(client, third_tok, again["listing_id"], 10, "650.00")
    assert resold.status_code == 200, resold.text
    pos = await position_of(third_tok)
    assert (pos["entry_price"], pos["cost"], pos["gain"]) == ("121.00", "650.00", "0.00")
    # what each made: the first 100 on 300, the second 110 on 540
    books = {}
    for name, token in (("first", first_tok), ("second", second_tok), ("third", third_tok)):
        s = (await client.get("/api/v1/investments/portfolio", headers=_h(token))).json()
        books[name] = (s["invested"], s["current_value"], s["sold"])
    assert books == {
        "first": ("300.00", "0.00", "400.00"),
        "second": ("540.00", "0.00", "650.00"),
        "third": ("650.00", "650.00", "0.00"),
    }
    assert str(first) and str(third)
    await _reconciles(asession)

    # a price that falls is a loss, and the assistant says so in words
    await _reprice(asession, pid, "115")
    ctx = await _ctx(asession, third)
    sale = await _run(asession, ctx, "prepare_sale", {"property": "Creek Tower", "position": True})
    assert (sale["you_receive"], sale["cost"], sale["gain"]) == ("590.00", "650.00", "-60.00")
    assert "less the price decrease on all the units (60.00)" in " ".join(sale["notes"])


@pytest.mark.asyncio
async def test_the_amount_follows_an_installment_paid_while_listed(client, db, asession):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "paid.since@x.io", funds=2000)
    buyer_tok, buyer = await _investor(client, db, "saw.old@x.io", funds=2000)
    plan = await _plan(client, seller_tok, pid, amount=1000)
    await _reprice(asession, pid, "110")
    listing = (await _list_position(client, seller_tok, plan["id"], 110)).json()
    # the seller pays an installment after the buyer opened the listing
    nxt = next(p for p in plan["payments"] if p["status"] != "paid")
    await client.post(
        f"/api/v1/installments/payments/{nxt['id']}/pay", headers=_h(seller_tok, idem=True)
    )
    before = (_balance(db, buyer), _balance(db, seller))
    stale = await _buy_position(client, buyer_tok, listing["listing_id"], 10, "400.00")
    # never an amount the buyer did not confirm: he is shown the position as it is now
    assert stale.status_code == 409 and _code(stale) == "POSITION_CHANGED"
    now = stale.json()["error"]["details"]["position"]
    assert (now["cash"], now["remaining_principal"], now["installments_left"]) == (
        "540.00",
        "560.00",
        4,
    )
    assert (_balance(db, buyer), _balance(db, seller)) == before
    assert db("SELECT status FROM secondary_listings")[0][0] == "active"
    missing = await _buy_position(client, buyer_tok, listing["listing_id"], 10, None)
    assert _code(missing) == "POSITION_CHANGED"
    ok = await _buy_position(client, buyer_tok, listing["listing_id"], 10, "540.00")
    assert ok.status_code == 200 and ok.json()["gross"] == "540.00"
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_a_position_sale_refuses_what_it_must(client, db, asession):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "r.seller@x.io", funds=3000)
    other_tok, _other = await _investor(client, db, "r.other@x.io", funds=3000)
    poor_tok, _poor = await _investor(client, db, "r.poor@x.io", funds=10)
    nokyc_tok, _nokyc = await _investor(client, db, "r.nokyc@x.io", funds=3000, kyc=False)
    plan = await _plan(client, seller_tok, pid, amount=1000)

    # not his plan; a price that does not cover what is still to pay
    assert (await _list_position(client, other_tok, plan["id"], 110)).status_code == 404
    low = await _list_position(client, seller_tok, plan["id"], 60)
    assert low.status_code == 422 and _code(low) == "PRICE_TOO_LOW"
    assert low.json()["error"]["details"]["minimum_price"] == "70.00"
    both = await client.post(
        "/api/v1/secondary/listings",
        json={"plan_id": plan["id"], "property_id": pid, "units": 3, "price_per_unit": 110},
        headers=_h(seller_tok),
    )
    assert both.status_code == 422
    # the plan's vested units cannot be listed one by one, as before
    loose = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": 1, "price_per_unit": 110},
        headers=_h(seller_tok),
    )
    assert _code(loose) == "INSUFFICIENT_UNITS"

    listing = (await _list_position(client, seller_tok, plan["id"], 105)).json()
    assert listing["position"]["cash"] == "350.00"
    again = await _list_position(client, seller_tok, plan["id"], 120)
    assert again.status_code == 409 and _code(again) == "ALREADY_LISTED"

    lid = listing["listing_id"]
    assert _code(await _buy_position(client, seller_tok, lid, 10, "350.00")) == (
        "CANNOT_BUY_OWN_LISTING"
    )
    part = await _buy_position(client, other_tok, lid, 3, "350.00")
    assert part.status_code == 422 and _code(part) == "WHOLE_POSITION"
    assert _code(await _buy_position(client, nokyc_tok, lid, 10, "350.00")) == "KYC_REQUIRED"
    assert _code(await _buy_position(client, poor_tok, lid, 10, "350.00")) == "INSUFFICIENT_FUNDS"
    # nothing moved through any of that
    assert db("SELECT status FROM secondary_listings")[0][0] == "active"
    assert str(db("SELECT investor_id FROM installment_plans")[0][0]) == seller
    assert _held(db, seller, pid) == 3 and db("SELECT count(*) FROM secondary_trades")[0][0] == 0

    # a plan started with a Nova Sukuk certificate is pledged until Nova releases it
    db(
        "INSERT INTO sukuk_certificates (user_id, property_id, plan_id, units, amount_due, "
        "file_key, file_name, content_type, file_size, status) VALUES "
        "(:u,:p,:pl,3,300,'k','c.pdf','application/pdf',1,'approved')",
        u=seller,
        p=pid,
        pl=plan["id"],
    )
    pledged = await _buy_position(client, other_tok, lid, 10, "350.00")
    assert pledged.status_code == 409 and _code(pledged) == "UNITS_PLEDGED"
    blocked = (await client.get("/api/v1/secondary/positions", headers=_h(seller_tok))).json()
    assert blocked["items"][0]["blocked"] == "pledged"
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_a_listing_closes_when_its_plan_is_paid_off(client, db, asession):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "paid.off@x.io", funds=3000)
    buyer_tok, _buyer = await _investor(client, db, "too.late@x.io", funds=3000)
    plan = await _plan(client, seller_tok, pid, amount=1000)
    listing = (await _list_position(client, seller_tok, plan["id"], 100)).json()
    for p in plan["payments"]:
        if p["status"] != "paid":
            r = await client.post(
                f"/api/v1/installments/payments/{p['id']}/pay", headers=_h(seller_tok, idem=True)
            )
            assert r.status_code == 200, r.text
    assert db("SELECT status FROM installment_plans")[0][0] == "completed"
    # it is no longer a position: nobody sees it on the market, nobody can buy it
    market = (await client.get("/api/v1/secondary/listings", headers=_h(buyer_tok))).json()
    assert market["items"] == []
    late = await _buy_position(client, buyer_tok, listing["listing_id"], 10, "300.00")
    assert late.status_code == 409 and _code(late) == "LISTING_NOT_ACTIVE"
    relist = await _list_position(client, seller_tok, plan["id"], 100)
    assert (
        _code(relist) == "PLAN_NOT_RUNNING"
        and "list its units like any others" in (relist.json()["error"]["message"])
    )
    # the nightly run tidies the listing away; the units are ordinary units now
    await installment_service.run_due(asession)
    await asession.commit()
    assert db("SELECT status FROM secondary_listings")[0][0] == "cancelled"
    held = (await client.get("/api/v1/secondary/holdings", headers=_h(seller_tok))).json()["items"]
    assert (held[0]["units"], held[0]["sellable_units"], held[0]["plan_units"]) == (10, 10, 0)
    ordinary = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": 10, "price_per_unit": 100},
        headers=_h(seller_tok),
    )
    assert ordinary.status_code == 200 and ordinary.json()["plan_id"] is None
    assert _held(db, seller, pid) == 10


@pytest.mark.asyncio
async def test_installments_already_due_go_to_the_buyer(client, db, asession):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "behind@x.io", funds=400)
    buyer_tok, buyer = await _investor(client, db, "catches.up@x.io", funds=2000)
    plan = await _plan(client, seller_tok, pid, amount=1000)
    # the seller fell behind: the first installment is two weeks late
    first = next(p for p in plan["payments"] if p["seq"] == 1)
    db(
        "UPDATE installment_payments SET due_date = current_date - 14, status='overdue', "
        "reminder_sent_at = now() WHERE id=:i",
        i=first["id"],
    )
    listing = (await _list_position(client, seller_tok, plan["id"], 100)).json()
    assert listing["position"]["overdue"] == 1
    ok = await _buy_position(client, buyer_tok, listing["listing_id"], 10, "300.00")
    assert ok.status_code == 200, ok.text
    assert db(
        "SELECT status, reminder_sent_at FROM installment_payments WHERE id=:i", i=first["id"]
    )[0] == ("scheduled", None)
    spent = _balance(db, buyer)
    out = await installment_service.run_due(asession, now=dt.datetime.now(dt.UTC))
    await asession.commit()
    assert out["paid"] == 1  # charged to the buyer, not the seller
    assert _balance(db, buyer) == spent - D("145.60")
    assert _balance(db, seller) == D("400") - D("312") + D("300")
    await _reconciles(asession)


# --- how an under-construction listing is bought -------------------------------------------- #
@pytest.mark.asyncio
async def test_an_under_construction_listing_is_bought_the_way_it_says(client, db, asession):
    tok, _uid = await _investor(client, db, "modes@x.io", funds=20000)
    plan_only = _property(db)  # the default: the installment plan
    phases = _property(db, payment="full")  # sold in phases, paid in full
    either = _property(db, payment="both")
    ready = _property(db, model="ready-income")

    refused = await _buy_full(client, tok, plan_only, 1000)
    assert refused.status_code == 409 and _code(refused) == "INSTALLMENTS_ONLY"
    assert (await _buy_full(client, tok, phases, 1000)).status_code == 200
    assert (await _buy_full(client, tok, either, 1000)).status_code == 200
    assert (await _buy_full(client, tok, ready, 1000)).status_code == 200

    async def plan(pid):
        return await client.post(
            "/api/v1/installments",
            json={"property_id": pid, "amount": 1000, "duration_months": 6},
            headers=_h(tok, idem=True),
        )

    assert (await plan(plan_only)).status_code == 201
    assert (await plan(either)).status_code == 201
    no_plan = await plan(phases)
    assert no_plan.status_code == 409 and _code(no_plan) == "FULL_PAYMENT_ONLY"
    # the listing says how it is bought
    listed = (await client.get(f"/api/v1/properties/{phases}")).json()
    assert listed["offplan_payment"] == "full"
    # units paid in full on a property under construction sell like any others, at once
    sell = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": phases, "units": 10, "price_per_unit": 105},
        headers=_h(tok),
    )
    assert sell.status_code == 200, sell.text
    modes = investment_service.payment_modes
    prop = type("P", (), {"model": "installment", "offplan_payment": "both"})()
    assert modes(prop) == ("full", "installments")
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_units_that_come_back_are_offered_at_todays_price(client, db, asession):
    """A purchase reserved before a price change and never paid gives its units back: they
    are for sale at the new price, so the offering's total counts them at it."""
    pid = _property(db, payment="full", units=100)
    tok, uid = await _investor(client, db, "never.paid@x.io", funds=0)
    # a reservation at $100 waiting for its payment (as a card checkout would leave it)
    db(
        "INSERT INTO investments (user_id, property_id, units, amount, status, "
        "unit_price_snapshot, reservation_expires_at) VALUES "
        "(:u,:p,10,1000,'pending',100, now() - interval '1 hour')",
        u=uid,
        p=pid,
    )
    db("UPDATE properties SET available_units = 90 WHERE id=:p", p=pid)
    await _reprice(asession, pid, "110")
    assert db("SELECT total_value FROM properties WHERE id=:p", p=pid)[0][0] == D("10900.00")
    assert await investment_service.expire_reservations(asession) == 1
    await asession.commit()
    # 100 units for sale at $110: the offering totals what it would take in
    assert db("SELECT available_units, total_value FROM properties WHERE id=:p", p=pid)[0] == (
        100,
        D("11000.00"),
    )
    assert str(tok)


# --- the assistant -------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_assistant_knows_the_price_and_how_each_listing_is_bought(client, db, asession):
    either = _property(db, payment="both")
    db("UPDATE properties SET slug='either-tower', title='Either Tower' WHERE id=:p", p=either)
    plan_only = _property(db)
    db("UPDATE properties SET slug='plan-tower', title='Plan Tower' WHERE id=:p", p=plan_only)
    phases = _property(db, payment="full")
    db("UPDATE properties SET slug='phase-tower', title='Phase Tower' WHERE id=:p", p=phases)
    tok, uid = await _investor(client, db, "asks@x.io", funds=5000)
    # 10 of the 1,000 units are sold at 100 before the price moves
    assert (await _buy_full(client, tok, either, 1000)).status_code == 200
    await _reprice(asession, either, "108", label="Phase 2")
    ctx = await _ctx(asession, uid)

    found = await _run(asession, ctx, "search_properties", {"search": "Tower"})
    cards = {c["slug"]: c for c in found["items"]}
    assert {s: c["payment"] for s, c in cards.items()} == {
        "either-tower": "both",
        "plan-tower": "installments",
        "phase-tower": "full",
    }
    assert cards["either-tower"]["model_label"] == "Off-plan, paid in full or in installments"
    assert cards["phase-tower"]["model_label"] == "Off-plan, paid in full"
    assert cards["plan-tower"]["model_label"] == "Off-plan, paid in installments"
    assert (
        cards["either-tower"]["unit_price"],
        cards["either-tower"]["launch_price"],
        cards["either-tower"]["price_change_pct"],
    ) == (108.0, 100.0, 8.0)
    assert cards["plan-tower"]["price_change_pct"] == 0.0

    detail = await _run(asession, ctx, "get_property", {"id_or_slug": "either-tower"})
    assert detail["phase"] == "Phase 2"
    # the property's value is every unit at today's price, not the offering's blended total
    # (10 units paid for at 100 + 990 still for sale at 108 = 107,920)
    assert db("SELECT total_value FROM properties WHERE id=:p", p=either)[0][0] == D("107920.00")
    assert detail["total_value"] == 108000.0 and cards["either-tower"]["total_value"] == 108000.0
    assert [(pt["price"], pt["label"]) for pt in detail["price_history"]] == [
        (100.0, "Launch price"),
        (108.0, "Phase 2"),
    ]

    # an order on a listing bought either way: in full unless the plan is asked for
    full = await _run(
        asession, ctx, "quote_investment", {"id_or_slug": "either-tower", "units": 10}
    )
    assert (full["purchase_type"], full["payment_options"], full["subtotal"]) == (
        "direct",
        ["full", "installments"],
        "1080.00",
    )
    assert "can also be bought through the installment plan" in " ".join(full["eligibility_notes"])
    assert _card_for("quote_investment", full, [])["path"] == (
        "/property/either-tower?units=10&pay=full"
    )
    by_plan = await _run(
        asession,
        ctx,
        "quote_investment",
        {"id_or_slug": "either-tower", "units": 10, "pay": "installments"},
    )
    assert (by_plan["purchase_type"], by_plan["duration_months"]) == ("installment", 12)
    assert "can also be paid in full" in " ".join(by_plan["eligibility_notes"])
    assert _card_for("quote_investment", by_plan, [])["path"] == (
        "/property/either-tower?units=10&months=12"
    )
    months = await _run(
        asession,
        ctx,
        "quote_investment",
        {"id_or_slug": "either-tower", "units": 10, "duration_months": 6},
    )
    assert months["purchase_type"] == "installment"
    # a listing with one way only says so
    only = await _run(
        asession, ctx, "quote_investment", {"id_or_slug": "plan-tower", "units": 10, "pay": "full"}
    )
    assert only["purchase_type"] == "installment"
    assert "bought through its installment plan, not paid in full" in " ".join(
        only["eligibility_notes"]
    )
    phase = await _run(
        asession,
        ctx,
        "quote_investment",
        {"id_or_slug": "phase-tower", "units": 10, "duration_months": 12},
    )
    assert (phase["purchase_type"], phase["duration_months"]) == ("direct", None)
    assert "paid in full: it has no installment plan" in " ".join(phase["eligibility_notes"])
    assert _card_for("quote_investment", phase, [])["path"] == "/property/phase-tower?units=10"

    compared = await _run(
        asession,
        ctx,
        "compare_properties",
        {"properties": ["either-tower", "plan-tower", "phase-tower"]},
    )
    assert [i["purchase"] for i in compared["items"]] == ["either", "installment", "direct"]


def test_the_assistant_no_longer_calls_phased_sales_unbuilt():
    core = prompts.CORE_SYSTEM
    for phrase in (
        "sold with the plan, whole,\n  as one position",
        "Never tell a user with a running plan\n  that they have nothing to sell",
        "you_would_receive = cost + gain",
        "unit_price is the price of a unit NOW",
        "never predict a price",
        "in full at the current price, or either",
        "ways to exit at any time, for ready and under-construction properties alike",
    ):
        assert phrase in core, phrase
    assert "phased funding" not in core
    assert "become sellable after the" not in core
    # a library passage about a phased sale no longer gets a "not built" warning
    assert platform_gaps.notes_for("phased sale at different prices", []) == []
    assert platform_gaps.notes_for("is funding released to the developer in tranches?", [])
