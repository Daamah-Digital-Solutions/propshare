"""The market fees (client, 2026-11-18, PropShare; migration 0045), at their default rates:

  deal                                   seller   buyer   platform   liquidity provider
  ordinary secondary-market sale          0.5%     1.5%     2%         —
  a provider buys through the LP market   1.5%     0%       1%         0.5% (of the seller fee)
  a provider resells those units          0%       1.5%     1%         0.5% (of the buyer fee)

What each party is shown before confirming must equal what lands in the wallets.
"""

from __future__ import annotations

import decimal
import uuid

import pytest

from app.tests.test_liquidity_db import (
    _assert_balance_invariant,
    _create_request,
    _fund,
    _fund_wallet,
    _grant_units,
    _holding,
    _lp_user,
    _ownership_sum,
    _seed_property,
    _uid,
    _verified_user,
)

D = decimal.Decimal


def _bal(db, uid) -> D:
    return D(db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0])


def _rows(db, uid, ref=None):
    sql = "SELECT type::text, amount, description FROM transactions WHERE user_id=:u"
    if ref:
        sql += " AND reference_id=:r"
    return [
        (t, D(a), d)
        for t, a, d in db(
            sql + " ORDER BY created_at, amount", u=uid, **({"r": ref} if ref else {})
        )
    ]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


async def _list(client, token, pid, units, price):
    r = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": units, "price_per_unit": price},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _buy(client, token, listing_id, units):
    r = await client.post(
        f"/api/v1/secondary/listings/{listing_id}/buy",
        json={"units": units},
        headers={**_h(token), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_settings_give_the_new_rates(client, db):
    t = await _verified_user(client, db, "rates@f.com")
    sec = (await client.get("/api/v1/secondary/settings", headers=_h(t))).json()
    liq = (await client.get("/api/v1/liquidity/settings", headers=_h(t))).json()
    assert (sec["resale_fee_pct"], sec["seller_fee_pct"], sec["lp_fee_share_pct"]) == (
        "1.5",
        "0.5",
        "0.5",
    )
    # the provider pays the units' value: no discount (owner, 2026-11-18)
    assert (liq["discount_pct"], liq["fee_pct"], liq["fee_share_pct"]) == ("0", "1.5", "0.5")


@pytest.mark.asyncio
async def test_an_ordinary_sale_half_a_percent_from_the_seller_one_and_a_half_from_the_buyer(
    client, db
):
    ts = await _verified_user(client, db, "s1@f.com")
    tb = await _verified_user(client, db, "b1@f.com")
    sid, bid = _uid(db, "s1@f.com"), _uid(db, "b1@f.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 20)
    _fund_wallet(db, bid, 5000)
    s0, b0 = _bal(db, sid), _bal(db, bid)

    listing = await _list(client, ts, pid, 10, 100)
    assert listing["lp_units"] == 0
    trade = await _buy(client, tb, listing["listing_id"], 10)
    assert (trade["gross"], trade["resale_fee"], trade["total_charged"]) == (
        "1000.00",
        "15.00",
        "1015.00",
    )
    assert (trade["seller_fee"], trade["lp_fee_share"]) == ("5.00", "0.00")
    assert _bal(db, bid) == b0 - D("1015.00")
    assert _bal(db, sid) == s0 + D("995.00")
    assert [(t, a) for t, a, _ in _rows(db, sid, listing["listing_id"])] == [
        ("fee", D("-5.00")),
        ("secondary_sale", D("1000.00")),
    ]
    # the seller's own listing says what it brought
    mine = (await client.get("/api/v1/secondary/listings/mine", headers=_h(ts))).json()
    row = next(i for i in mine["items"] if i["listing_id"] == listing["listing_id"])
    assert (row["seller_fee"], row["seller_net"]) == ("5.00", "995.00")
    _assert_balance_invariant(db, sid)
    _assert_balance_invariant(db, bid)


@pytest.mark.asyncio
async def test_the_clients_example_a_provider_buys_for_10000_and_resells_for_11000(client, db):
    """The provider's purchase: the seller pays 150 (100 platform, 50 provider) and receives
    9,850; the resale: the buyer pays 11,165 (110 platform, 55 provider) and the provider is
    credited 11,055. The provider gains 1,105: 1,000 of price and 105 of fee shares."""
    ts = await _verified_user(client, db, "ex_s@f.com")
    tl = await _lp_user(client, db, "ex_l@f.com")
    tb = await _verified_user(client, db, "ex_b@f.com")
    sid, lid, bid = _uid(db, "ex_s@f.com"), _uid(db, "ex_l@f.com"), _uid(db, "ex_b@f.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 100)
    _fund_wallet(db, lid, 20000)
    _fund_wallet(db, bid, 20000)
    s0, l0, b0 = _bal(db, sid), _bal(db, lid), _bal(db, bid)

    req = (await _create_request(client, ts, pid, 100)).json()
    assert (req["lp_price"], req["liquidity_fee"], req["seller_net"]) == (
        "10000.00",
        "150.00",
        "9850.00",
    )
    assert (await _fund(client, tl, req["request_id"], 100)).status_code == 200
    assert _bal(db, sid) == s0 + D("9850.00")
    assert _bal(db, lid) == l0 - D("10000.00") + D("50.00")
    # its own line in the provider's statement
    share = [(t, a) for t, a, d in _rows(db, lid, req["request_id"]) if t == "lp_fee_share"]
    assert share == [("lp_fee_share", D("50.00"))]
    pos = db("SELECT liquidity_fee, lp_fee_share FROM lp_positions WHERE lp_user_id=:u", u=lid)
    assert [(D(a), D(b)) for a, b in pos] == [(D("150.00"), D("50.00"))]

    # the provider resells: its units sell under its fees
    held = (await client.get("/api/v1/secondary/holdings", headers=_h(tl))).json()["items"]
    assert next(h for h in held if str(h["property_id"]) == str(pid))["lp_units"] == 100
    listing = await _list(client, tl, pid, 100, 110)
    assert listing["lp_units"] == 100
    l1 = _bal(db, lid)
    trade = await _buy(client, tb, listing["listing_id"], 100)
    assert (trade["gross"], trade["resale_fee"], trade["total_charged"]) == (
        "11000.00",
        "165.00",
        "11165.00",
    )
    assert (trade["seller_fee"], trade["lp_fee_share"]) == ("0.00", "55.00")
    assert _bal(db, bid) == b0 - D("11165.00")
    assert _bal(db, lid) == l1 + D("11055.00")
    # in all: 1,000 of price difference + 50 + 55 of fee shares
    assert _bal(db, lid) - l0 == D("1105.00")
    assert _holding(db, bid, pid) == 100 and _ownership_sum(db, pid) == 100
    for uid in (sid, lid, bid):
        _assert_balance_invariant(db, uid)


@pytest.mark.asyncio
async def test_a_providers_own_purchases_are_not_sold_under_its_fees(client, db):
    """Only the units bought through the LP market sell without a seller fee: a provider that
    also bought units the ordinary way sells the LP ones first, then the rest as anyone."""
    ts = await _verified_user(client, db, "mx_s@f.com")
    tl = await _lp_user(client, db, "mx_l@f.com")
    tb = await _verified_user(client, db, "mx_b@f.com")
    sid, lid, bid = _uid(db, "mx_s@f.com"), _uid(db, "mx_l@f.com"), _uid(db, "mx_b@f.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 10)
    _grant_units(db, lid, pid, 6)  # bought the ordinary way
    _fund_wallet(db, lid, 5000)
    _fund_wallet(db, bid, 5000)
    req = (await _create_request(client, ts, pid, 4)).json()["request_id"]
    assert (await _fund(client, tl, req, 4)).status_code == 200  # 4 LP-market units

    listing = await _list(client, tl, pid, 10, 100)
    assert listing["lp_units"] == 4
    first = await _buy(client, tb, listing["listing_id"], 3)  # all LP units
    assert (first["seller_fee"], first["lp_fee_share"]) == ("0.00", "1.50")
    second = await _buy(client, tb, listing["listing_id"], 3)  # 1 LP unit + 2 ordinary
    assert (second["seller_fee"], second["lp_fee_share"]) == ("1.00", "0.50")
    # nothing of the LP lot is left to list again
    held = (await client.get("/api/v1/secondary/holdings", headers=_h(tl))).json()["items"]
    assert next(h for h in held if str(h["property_id"]) == str(pid))["lp_units"] == 0
    _assert_balance_invariant(db, lid)


@pytest.mark.asyncio
async def test_a_sale_counts_for_what_it_brought_after_the_seller_fee(client, db):
    ts = await _verified_user(client, db, "pf_s@f.com")
    tb = await _verified_user(client, db, "pf_b@f.com")
    sid, bid = _uid(db, "pf_s@f.com"), _uid(db, "pf_b@f.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 10)
    _fund_wallet(db, bid, 5000)
    listing = await _list(client, ts, pid, 10, 100)
    await _buy(client, tb, listing["listing_id"], 10)
    portfolio = (await client.get("/api/v1/investments/portfolio", headers=_h(ts))).json()
    assert portfolio["sold"] == "995.00"
