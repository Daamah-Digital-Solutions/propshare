"""What the independent review of the off-plan exit found (2026-10-05), one test per defect.

* units vesting to someone who BOUGHT a position are booked at the price they got in at, so
  the holding's average cost is theirs, not the first holder's;
* the nightly charge reads a plan as it is now: a plan that changed hands since the session
  first saw it is charged to its new holder;
* the market shows a position's own figures (what was paid on the plan, the price change
  since it started), never what its seller paid someone else for it; the seller sees their
  own, and what a sold position brought;
* the buyer confirms the resale fee too; a fee of zero is not a line; a replayed request key
  answers only the person who made the request;
* an exit request priced at a price the property no longer has cannot be funded;
* an order confirmed at a unit price is refused when the price has changed, and an amount is
  money before it is units (3 units at 110.10 are 3 units);
* a position worth less than what is still to pay on it is worth nothing, not a debt, and a
  sale to a liquidity provider counts for what it brought after the liquidity fee;
* a plan says why its position cannot be listed; a listing closed by the nightly run is
  audited and its seller is told; a holder with an active listing is told it keeps its
  price when the property's price changes.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

from app.core.errors import AppError
from app.models import InstallmentPlan
from app.services import installment_service, liquidity_service
from app.tests.test_offplan_exit_db import (
    _balance,
    _buy_full,
    _buy_position,
    _code,
    _h,
    _held,
    _investor,
    _list_position,
    _plan,
    _property,
    _reconciles,
    _reprice,
)

D = decimal.Decimal


def _setting(db, key: str, value: str) -> None:
    db(
        "INSERT INTO platform_settings (key, value) VALUES (:k,:v) "
        "ON CONFLICT (key) DO UPDATE SET value=:v",
        k=key,
        v=value,
    )


async def _pay_next(client, token: str) -> dict:
    mine = (await client.get("/api/v1/installments", headers=_h(token))).json()[0]
    nxt = next(p for p in mine["payments"] if p["status"] != "paid")
    r = await client.post(
        f"/api/v1/installments/payments/{nxt['id']}/pay", headers=_h(token, idem=True)
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _holding(client, token: str) -> dict:
    return (await client.get("/api/v1/secondary/holdings", headers=_h(token))).json()["items"][0]


# --- what a position buyer's units cost ----------------------------------------------------- #
@pytest.mark.asyncio
async def test_units_vest_to_a_position_buyer_at_the_price_they_got_in_at(client, db, asession):
    pid = _property(db)
    first_tok, first = await _investor(client, db, "vest.first@x.io", funds=1000)
    buyer_tok, buyer = await _investor(client, db, "vest.buyer@x.io", funds=3000)
    plan = await _plan(client, first_tok, pid, amount=1000)  # 3 units vest at 100
    assert (await _holding(client, first_tok))["average_cost"] == "100.00"
    await _reprice(asession, pid, "110")
    listing = (await _list_position(client, first_tok, plan["id"], 110)).json()
    bought = await _buy_position(client, buyer_tok, listing["listing_id"], 10, "400.00")
    assert bought.status_code == 200, bought.text

    # he pays every remaining installment: 400 for the position + 700 = 1,100 for 10 units
    for _ in range(5):
        await _pay_next(client, buyer_tok)
    assert db("SELECT status FROM installment_plans")[0][0] == "completed"
    assert _held(db, buyer, pid) == 10 and _held(db, first, pid) == 0
    prices = {
        r[0]
        for r in db(
            "SELECT unit_price FROM ownership_ledger WHERE user_id=:u AND units > 0", u=buyer
        )
    }
    assert prices == {D("110.00")}  # every unit at 110, not 3 at 110 and 7 at 100
    held = await _holding(client, buyer_tok)
    assert (held["units"], held["average_cost"], held["sellable_units"]) == (10, "110.00", 10)
    await _reconciles(asession)


# --- the nightly charge reads the plan as it is now ----------------------------------------- #
@pytest.mark.asyncio
async def test_the_nightly_charge_uses_the_plans_holder_of_now(client, db, asession):
    pid = _property(db)
    old_tok, old = await _investor(client, db, "was.holder@x.io", funds=1000)
    _new_tok, new = await _investor(client, db, "is.holder@x.io", funds=1000)
    plan = await _plan(client, old_tok, pid, amount=1000)
    first = next(p for p in plan["payments"] if p["seq"] == 1)
    db("UPDATE installment_payments SET due_date = current_date WHERE id=:i", i=first["id"])

    # the session has seen the plan (as the reminder pass used to leave it) ...
    seen = await asession.get(InstallmentPlan, uuid.UUID(plan["id"]))
    assert str(seen.investor_id) == old
    # ... and the position changed hands since, in another transaction
    db("UPDATE installment_plans SET investor_id=:n WHERE id=:p", n=new, p=plan["id"])
    db(
        "UPDATE ownership_ledger SET user_id=:n WHERE user_id=:o AND property_id=:p",
        n=new,
        o=old,
        p=pid,
    )
    before = (_balance(db, old), _balance(db, new))
    out = await installment_service.run_due(asession, now=dt.datetime.now(dt.UTC))
    await asession.commit()
    assert out["paid"] == 1
    # charged to who holds it now, and vested to them
    assert _balance(db, old) == before[0]
    assert _balance(db, new) == before[1] - D("145.60")
    assert _held(db, new, pid) > 3 and _held(db, old, pid) == 0
    assert db("SELECT vested_units FROM installment_plans")[0][0] == _held(db, new, pid)


# --- what the market shows about a position, and what its seller sees ------------------------ #
@pytest.mark.asyncio
async def test_the_market_shows_the_plans_figures_not_what_its_seller_paid(client, db, asession):
    pid = _property(db)
    a_tok, _a = await _investor(client, db, "pub.first@x.io", funds=1000)
    b_tok, _b = await _investor(client, db, "pub.second@x.io", funds=3000)
    c_tok, _c = await _investor(client, db, "pub.third@x.io", funds=3000)
    plan = await _plan(client, a_tok, pid, amount=1000)
    await _reprice(asession, pid, "110")
    first = (await _list_position(client, a_tok, plan["id"], 110)).json()
    taken = await _buy_position(client, b_tok, first["listing_id"], 10, "400.00")
    assert taken.status_code == 200, taken.text
    await _reprice(asession, pid, "121")
    mine = (await _list_position(client, b_tok, plan["id"], 121)).json()
    # the seller's own view: he put 400 in and gained 11 a unit
    assert (mine["position"]["entry_price"], mine["position"]["cost"], mine["cash"]) == (
        "110.00",
        "400.00",
        "510.00",
    )
    assert mine["position"]["gain"] == "110.00"

    # the market: 300 was paid on the plan, the price moved 21 a unit since it started. The
    # same cash, and nothing about what the seller paid the first holder
    seen = (await client.get("/api/v1/secondary/listings", headers=_h(c_tok))).json()["items"][0]
    pos = seen["position"]
    assert (pos["cash"], pos["paid_principal"], pos["gain"]) == ("510.00", "300.00", "210.00")
    assert (pos["entry_price"], pos["cost"]) == ("100.00", "300.00")
    assert seen["cash"] == "510.00"
    own = (await client.get("/api/v1/secondary/listings/mine", headers=_h(b_tok))).json()["items"]
    assert (own[0]["position"]["cost"], own[0]["cash"]) == ("400.00", "510.00")

    # sold: the position is gone from the row, what it brought stays
    assert (await _buy_position(client, c_tok, mine["listing_id"], 10, "510.00")).status_code == 200
    sold = (await client.get("/api/v1/secondary/listings/mine", headers=_h(b_tok))).json()["items"]
    assert (sold[0]["status"], sold[0]["position"], sold[0]["cash"]) == ("sold", None, "510.00")
    # the first holder's own sold listing likewise
    first_row = (await client.get("/api/v1/secondary/listings/mine", headers=_h(a_tok))).json()
    assert first_row["items"][0]["cash"] == "400.00"
    await _reconciles(asession)


# --- the fee is confirmed too; a zero fee is no line; keys answer their owner ----------------- #
@pytest.mark.asyncio
async def test_the_buyer_confirms_the_fee_and_a_zero_fee_is_charged_as_nothing(
    client, db, asession
):
    pid = _property(db)
    seller_tok, seller = await _investor(client, db, "fee.seller@x.io", funds=1000)
    buyer_tok, buyer = await _investor(client, db, "fee.buyer@x.io", funds=1000)
    plan = await _plan(client, seller_tok, pid, amount=1000)
    listing = (await _list_position(client, seller_tok, plan["id"], 100)).json()
    assert (listing["position"]["cash"], listing["position"]["resale_fee"]) == ("300.00", "3.00")

    async def buy(fee: str | None):
        body = {"units": 10, "expected_cash": "300.00"}
        if fee is not None:
            body["expected_fee"] = fee
        return await client.post(
            f"/api/v1/secondary/listings/{listing['listing_id']}/buy",
            json=body,
            headers=_h(buyer_tok, idem=True),
        )

    # staff set the resale fee to zero after the buyer opened the listing
    _setting(db, "secondary_resale_fee_pct", "0")
    stale = await buy("3.00")
    assert stale.status_code == 409 and _code(stale) == "POSITION_CHANGED"
    assert stale.json()["error"]["details"]["position"]["resale_fee"] == "0.00"
    assert _balance(db, buyer) == D("1000")
    # confirmed again with the fee of now: charged the cash alone, with no empty fee line
    ok = await buy("0.00")
    assert ok.status_code == 200, ok.text
    assert (ok.json()["resale_fee"], ok.json()["total_charged"]) == ("0.00", "300.00")
    assert _balance(db, buyer) == D("700.00")
    fees = db("SELECT count(*) FROM transactions WHERE user_id=:u AND type='fee'", u=buyer)
    assert fees[0][0] == 0
    assert str(seller)
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_a_listing_of_units_can_be_bought_when_the_resale_fee_is_zero(client, db, asession):
    pid = _property(db, payment="full")
    seller_tok, _s = await _investor(client, db, "zero.seller@x.io", funds=2000)
    buyer_tok, buyer = await _investor(client, db, "zero.buyer@x.io", funds=2000)
    assert (await _buy_full(client, seller_tok, pid, 1000)).status_code == 200
    listing = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": 4, "price_per_unit": 100},
        headers=_h(seller_tok),
    )
    _setting(db, "secondary_resale_fee_pct", "0")
    r = await client.post(
        f"/api/v1/secondary/listings/{listing.json()['listing_id']}/buy",
        json={"units": 4},
        headers=_h(buyer_tok, idem=True),
    )
    assert r.status_code == 200, r.text
    assert (r.json()["resale_fee"], r.json()["total_charged"]) == ("0.00", "400.00")
    assert _held(db, buyer, pid) == 4
    await _reconciles(asession)


@pytest.mark.asyncio
async def test_a_replayed_request_key_answers_only_whoever_made_the_request(client, db, asession):
    pid = _property(db)
    seller_tok, _s = await _investor(client, db, "key.seller@x.io", funds=1000)
    buyer_tok, _b = await _investor(client, db, "key.buyer@x.io", funds=2000)
    other_tok, _o = await _investor(client, db, "key.other@x.io", funds=2000)
    plan_key, buy_key = str(uuid.uuid4()), str(uuid.uuid4())
    body = {"property_id": pid, "amount": 1000, "duration_months": 6}
    made = await client.post(
        "/api/v1/installments", json=body, headers={**_h(seller_tok), "Idempotency-Key": plan_key}
    )
    assert made.status_code == 201, made.text
    plan = made.json()
    # the same key again, still his plan: the same plan
    again = await client.post(
        "/api/v1/installments", json=body, headers={**_h(seller_tok), "Idempotency-Key": plan_key}
    )
    assert again.status_code == 201 and again.json()["id"] == plan["id"]

    listing = (await _list_position(client, seller_tok, plan["id"], 100)).json()
    bought = await _buy_position(client, buyer_tok, listing["listing_id"], 10, "300.00", buy_key)
    assert bought.status_code == 200, bought.text
    # the plan is the buyer's now: its old key no longer reads it to the seller
    replay = await client.post(
        "/api/v1/installments", json=body, headers={**_h(seller_tok), "Idempotency-Key": plan_key}
    )
    assert replay.status_code == 409 and _code(replay) == "IDEMPOTENCY_KEY_REUSED"
    assert "payments" not in replay.text
    # and someone else's purchase key does not hand over that purchase
    theirs = await _buy_position(client, other_tok, listing["listing_id"], 10, "300.00", buy_key)
    assert theirs.status_code == 409 and _code(theirs) == "IDEMPOTENCY_KEY_REUSED"
    mine = await _buy_position(client, buyer_tok, listing["listing_id"], 10, "300.00", buy_key)
    assert mine.status_code == 200 and mine.json()["trade_id"] == bought.json()["trade_id"]


# --- an exit request at a price the property no longer has ------------------------------------ #
@pytest.mark.asyncio
async def test_an_exit_request_at_an_old_price_cannot_be_funded(client, db, asession):
    pid = _property(db, payment="full")
    tok, seller = await _investor(client, db, "stale.seller@x.io", funds=2000)
    _lp_tok, lp = await _investor(client, db, "stale.lp@x.io", funds=5000)
    await _buy_full(client, tok, pid, 1000)
    made = await client.post(
        "/api/v1/liquidity/exit-requests", json={"property_id": pid, "units": 10}, headers=_h(tok)
    )
    request_id = made.json()["request_id"]
    await _reprice(asession, pid, "108")
    # one that slipped past the price change (made in the same instant): still open, at 100
    db("UPDATE lp_exit_requests SET status='open' WHERE id=:i", i=request_id)

    # liquidity providers are not offered it, and funding it is refused: nothing moves
    assert await liquidity_service.list_open_requests(asession) == []
    with pytest.raises(AppError) as refused:
        await liquidity_service.fund_exit_request(
            asession,
            lp_user_id=uuid.UUID(lp),
            request_id=uuid.UUID(request_id),
            units=10,
            idempotency_key=str(uuid.uuid4()),
        )
    assert refused.value.code == "PRICE_CHANGED"
    await asession.rollback()
    assert (_held(db, seller, pid), _balance(db, lp)) == (10, D("5000"))
    # the sweep closes it, so the seller's units are free again
    assert await liquidity_service.expire_open_requests(asession) == 1
    await asession.commit()
    assert db("SELECT status FROM lp_exit_requests")[0][0] == "expired"
    assert (await _holding(client, tok))["sellable_units"] == 10


# --- an order is placed at the price its buyer saw -------------------------------------------- #
@pytest.mark.asyncio
async def test_an_order_confirmed_at_one_price_is_not_placed_at_another(client, db, asession):
    pid = _property(db, payment="both")
    tok, uid = await _investor(client, db, "saw.100@x.io", funds=5000)
    await _reprice(asession, pid, "110")  # while his page still shows 100

    full = await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 1000, "method": "wallet", "expected_unit_price": 100},
        headers=_h(tok, idem=True),
    )
    assert full.status_code == 409 and _code(full) == "PRICE_CHANGED"
    assert full.json()["error"]["details"]["unit_price"] == "110.00"
    plan = await client.post(
        "/api/v1/installments",
        json={
            "property_id": pid,
            "amount": 1000,
            "duration_months": 6,
            "expected_unit_price": 100,
        },
        headers=_h(tok, idem=True),
    )
    assert plan.status_code == 409 and _code(plan) == "PRICE_CHANGED"
    assert _balance(db, uid) == D("5000")
    assert db("SELECT count(*) FROM installment_plans")[0][0] == 0
    assert db("SELECT available_units FROM properties WHERE id=:p", p=pid)[0][0] == 1000

    # confirmed again at the price of now
    ok = await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 1100, "method": "wallet", "expected_unit_price": 110},
        headers=_h(tok, idem=True),
    )
    assert ok.status_code == 200 and ok.json()["units"] == 10, ok.text
    # a client that sends no price (an older page) is served as before
    older = await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 110, "method": "wallet"},
        headers=_h(tok, idem=True),
    )
    assert older.status_code == 200 and older.json()["units"] == 1


@pytest.mark.asyncio
async def test_an_amount_is_money_before_it_is_units(client, db, asession):
    pid = _property(db, payment="both", unit_price=100)
    tok, _uid = await _investor(client, db, "cents@x.io", funds=5000)
    await _reprice(asession, pid, "110.10")
    # 3 x 110.10 as a browser computes it: 330.29999999999995
    amount = 3 * 110.10
    assert amount != 330.30
    full = await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": amount, "method": "wallet"},
        headers=_h(tok, idem=True),
    )
    assert full.status_code == 200 and full.json()["units"] == 3, full.text
    plan = await client.post(
        "/api/v1/installments",
        json={"property_id": pid, "amount": amount, "duration_months": 6},
        headers=_h(tok, idem=True),
    )
    assert plan.status_code == 201 and plan.json()["units_total"] == 3, plan.text


# --- what a portfolio says ------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_position_under_water_is_worth_nothing_not_a_debt(client, db, asession):
    pid = _property(db)
    tok, _uid = await _investor(client, db, "under.water@x.io", funds=1000)
    await _plan(client, tok, pid, amount=1000)  # 300 paid, 700 still to pay
    for price in ("80", "65"):  # two steps down (each under the one-step limit)
        await _reprice(asession, pid, price)
    mine = (await client.get("/api/v1/installments", headers=_h(tok))).json()[0]
    # 10 x 65 = 650, less than the 700 still to pay: the figures say so
    assert (mine["position"]["value"], mine["position"]["equity"]) == ("650.00", "-50.00")
    summary = (await client.get("/api/v1/investments/portfolio", headers=_h(tok))).json()
    assert (summary["invested"], summary["current_value"]) == ("300.00", "0.00")
    # and it cannot be listed at that price
    refused = await _list_position(client, tok, mine["id"], 65)
    assert refused.status_code == 422 and _code(refused) == "PRICE_TOO_LOW"


@pytest.mark.asyncio
async def test_a_sale_to_a_liquidity_provider_counts_for_what_it_brought(client, db, asession):
    pid = _property(db, payment="full")
    tok, seller = await _investor(client, db, "lp.net@x.io", funds=2000)
    _lp_tok, lp = await _investor(client, db, "lp.net.buyer@x.io", funds=5000)
    await _buy_full(client, tok, pid, 1000)  # 10 units for 1,000 (+ the platform fee)
    made = await client.post(
        "/api/v1/liquidity/exit-requests", json={"property_id": pid, "units": 10}, headers=_h(tok)
    )
    req = made.json()
    before = _balance(db, seller)
    await liquidity_service.fund_exit_request(
        asession,
        lp_user_id=uuid.UUID(lp),
        request_id=uuid.UUID(req["request_id"]),
        units=10,
        idempotency_key=str(uuid.uuid4()),
    )
    await asession.commit()
    net = D(req["seller_net"])
    assert _balance(db, seller) == before + net and D(req["liquidity_fee"]) > 0
    summary = (await client.get("/api/v1/investments/portfolio", headers=_h(tok))).json()
    # what the sale brought is what reached the wallet, not the price before the fee
    assert (summary["sold"], summary["current_value"]) == (str(net), "0.00")
    await _reconciles(asession)


# --- the plan says why it cannot be listed; a closed listing is said so ------------------------ #
@pytest.mark.asyncio
async def test_a_plan_says_why_its_position_cannot_be_listed_now(client, db, asession):
    pid = _property(db)
    tok, uid = await _investor(client, db, "why.not@x.io", funds=1000)
    plan = await _plan(client, tok, pid, amount=1000)

    async def position() -> dict:
        return (await client.get("/api/v1/installments", headers=_h(tok))).json()[0]["position"]

    assert ((await position())["blocked"], (await position())["lockup_until"]) == (None, None)
    await _list_position(client, tok, plan["id"], 100)
    assert (await position())["blocked"] == "listed"
    db("UPDATE secondary_listings SET status='cancelled'")
    _setting(db, "secondary_lockup_days", "30")
    locked = await position()
    assert locked["blocked"] == "lockup" and locked["lockup_until"] is not None
    _setting(db, "secondary_lockup_days", "0")
    db(
        "INSERT INTO sukuk_certificates (user_id, property_id, plan_id, units, amount_due, "
        "file_key, file_name, content_type, file_size, status) VALUES "
        "(:u,:p,:pl,3,300,'k','c.pdf','application/pdf',1,'approved')",
        u=uid,
        p=pid,
        pl=plan["id"],
    )
    assert (await position())["blocked"] == "pledged"


@pytest.mark.asyncio
async def test_a_listing_closed_by_the_nightly_run_is_recorded_and_its_seller_told(
    client, db, asession
):
    pid = _property(db)
    tok, uid = await _investor(client, db, "tidy@x.io", funds=3000)
    plan = await _plan(client, tok, pid, amount=1000)
    await _list_position(client, tok, plan["id"], 100)
    for _ in range(5):
        await _pay_next(client, tok)
    assert await installment_service.close_stale_position_listings(asession) == 1
    await asession.commit()
    assert db("SELECT status FROM secondary_listings")[0][0] == "cancelled"
    assert (
        db("SELECT count(*) FROM audit_log WHERE action='secondary.position_listing_closed'")[0][0]
        == 1
    )
    note = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title='Position listing closed'",
        u=uid,
    )
    assert len(note) == 1 and "fully paid" in note[0][0] and "like any others" in note[0][0]
    # nothing left to close on the next run
    assert await installment_service.close_stale_position_listings(asession) == 0


@pytest.mark.asyncio
async def test_a_holder_with_a_listing_is_told_it_keeps_its_price(client, db, asession):
    pid = _property(db, payment="full")
    lister_tok, lister = await _investor(client, db, "has.listing@x.io", funds=2000)
    holder_tok, holder = await _investor(client, db, "just.holds@x.io", funds=2000)
    for token in (lister_tok, holder_tok):
        assert (await _buy_full(client, token, pid, 1000)).status_code == 200
    await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": 5, "price_per_unit": 100},
        headers=_h(lister_tok),
    )
    await _reprice(asession, pid, "110", label="Phase 2")

    def told(uid: str) -> str:
        return db(
            "SELECT message FROM notifications WHERE user_id=:u AND title LIKE 'New unit price%'",
            u=uid,
        )[0][0]

    assert "keeps the price you set" in told(lister)
    assert "keeps the price you set" not in told(holder)
    # the listing itself is the seller's price, untouched
    assert db("SELECT price_per_unit FROM secondary_listings")[0][0] == D("100.00")
    # and the listing says how far the price has moved since launch, without a second request
    listed = (await client.get(f"/api/v1/properties/{pid}")).json()
    assert (listed["unit_price"], listed["launch_price"]) == (110.0, 100.0)
    untouched = _property(db, payment="full")
    assert (await client.get(f"/api/v1/properties/{untouched}")).json()["launch_price"] is None
    assert str(holder_tok)
