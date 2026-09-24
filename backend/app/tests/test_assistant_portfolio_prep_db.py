"""Batch 2 of "prepare everything, stop at the user's click": selling units, paying the next
installment, and comparing properties.

What each test protects:
  * prepare_sale finds the holding by name, slug or id (an ambiguous or unknown name is an
    error the model relays), applies the listing rules before anything is listed (sellable
    units after reservations, lock-up, price limits, verification) and says what the seller
    receives vs what a buyer pays; its card opens the sell form pre-filled; nothing is listed;
  * prepare_installment_payment picks the earliest unpaid installment (never the down
    payment), checks the wallet covers it, and its card opens that payment's confirmation;
    nothing is charged;
  * compare_properties is public, resolves slugs or names, skips unpublished listings, needs
    two, and carries the listing's own risk and exit data into a comparison card;
  * a property slug the link allow-list refuses gives a card without a link, never a crash.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import uuid

import pytest

from app.core.errors import AppError
from app.services.assistant import guard
from app.services.assistant.agent import _card_for
from app.services.assistant.context import AgentContext, load_context
from app.services.assistant.tools import REGISTRY
from app.services.assistant.tools.base import call_tool, parse_args

PW = "Passw0rd!23"
VISITOR = AgentContext(None, "vis-compare", (), None, "none", False, None)
CONTENT = {
    "risks": [
        {"label": "Construction delay", "level": "medium", "note": "x"},
        {"label": "Market", "level": "high"},
        {"label": "Liquidity", "level": "low"},
    ],
    "exitMechanisms": [{"name": "Secondary market", "eta": "any time"}, {"name": "Buy-back"}],
    "fees": {"exit": 2},
}


async def _user(client, db, email: str, *, kyc="verified", balance=5000) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Port User"}
    )
    assert r.status_code == 201, r.text
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    db("UPDATE kyc_verifications SET status=:s WHERE user_id=:i", s=kyc, i=uid)
    db("UPDATE wallets SET balance=:b WHERE user_id=:u", b=balance, u=uid)
    return uid


def _prop(
    db, *, title: str, slug: str, model="ready-income", status="active", price=100, content=None
) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,slug,location,city,country,property_type,model,status,total_value,unit_price,"
        "total_units,available_units,minimum_investment,expected_yield,total_return,description,content) VALUES "
        "(:id,:t,:s,'Dubai Marina','Dubai','UAE','apartment',:m,:st,100000,:p,1000,1000,:p,7.5,11,'x',CAST(:c AS jsonb))",
        id=pid,
        t=title,
        s=slug,
        m=model,
        st=status,
        p=price,
        c=json.dumps(content or {}),
    )
    return pid


def _own(db, uid: str, pid: str, units: int) -> None:
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) VALUES (:u,:p,:n,100,'purchase')",
        u=uid,
        p=pid,
        n=units,
    )


def _setting(db, key: str, value: str) -> None:
    db(
        "INSERT INTO platform_settings (key, value) VALUES (:k,:v) ON CONFLICT (key) DO UPDATE SET value=:v",
        k=key,
        v=value,
    )


async def _ctx(asession, uid: str) -> AgentContext:
    return await load_context(asession, user_id=uuid.UUID(uid), conversation_id=uuid.uuid4())


async def _run(asession, ctx, name: str, args: dict) -> dict:
    spec = REGISTRY[name]
    guard.authorize(spec, ctx)
    return await call_tool(spec, asession, ctx, parse_args(spec, json.dumps(args)))


# --- selling units ------------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_sale_is_prepared_up_to_create_listing(client, db, asession):
    _setting(db, "secondary_resale_fee_pct", "1.0")
    loft = _prop(db, title="Marina Loft Income Suite", slug="marina-loft")
    heights = _prop(db, title="Marina Heights", slug="marina-heights")
    uid = await _user(client, db, "seller@p.io")
    _own(db, uid, loft, 10)
    _own(db, uid, heights, 4)
    ctx = await _ctx(asession, uid)

    out = await _run(
        asession,
        ctx,
        "prepare_sale",
        {"property": "marina loft", "units": 5, "price_per_unit": 110},
    )
    assert (out["property_title"], out["units"], out["price_per_unit"]) == (
        "Marina Loft Income Suite",
        5,
        "110.00",
    )
    assert (out["reference_price"], out["vs_reference_pct"]) == ("100.00", "10.00")
    # the seller gets the full gross; the 1% resale fee is paid by the buyer on top
    assert (out["you_receive"], out["buyer_fee"], out["buyer_pays"]) == ("550.00", "5.50", "555.50")
    assert out["ready"] is True and out["notes"] == []
    card = _card_for("prepare_sale", out, [])
    assert card["kind"] == "sale" and card["ready"] is True
    assert card["path"] == f"/secondary-market?tab=sell&property={loft}&units=5&price=110.00"
    assert db("SELECT count(*) FROM secondary_listings")[0][0] == 0  # nothing listed

    # by slug or id too; no price = the reference price, said so
    by_slug = await _run(asession, ctx, "prepare_sale", {"property": "marina-heights", "units": 1})
    assert (by_slug["property_title"], by_slug["price_per_unit"]) == ("Marina Heights", "100.00")
    assert "reference price" in by_slug["notes"][0] and by_slug["ready"] is True
    by_id = await _run(asession, ctx, "prepare_sale", {"property": loft, "units": 1})
    assert by_id["property_id"] == loft

    with pytest.raises(AppError) as exc:  # both holdings match
        await _run(asession, ctx, "prepare_sale", {"property": "Marina", "units": 1})
    assert exc.value.code == "AMBIGUOUS" and "Marina Heights" in exc.value.message
    with pytest.raises(AppError) as exc:
        await _run(asession, ctx, "prepare_sale", {"property": "Creek Tower", "units": 1})
    assert exc.value.code == "NOT_FOUND" and "Marina Loft Income Suite" in exc.value.message


@pytest.mark.asyncio
async def test_sale_rules_block_the_listing_before_it_is_made(client, db, asession):
    loft = _prop(db, title="Rule Loft", slug="rule-loft")
    uid = await _user(client, db, "rules@p.io")
    _own(db, uid, loft, 10)
    db(
        "INSERT INTO secondary_listings (seller_id, property_id, units_for_sale, units_remaining, price_per_unit, status) "
        "VALUES (:u,:p,8,8,100,'active')",
        u=uid,
        p=loft,
    )
    _setting(db, "secondary_lockup_days", "365")
    _setting(db, "secondary_price_max_pct", "105")
    ctx = await _ctx(asession, uid)

    out = await _run(
        asession, ctx, "prepare_sale", {"property": "Rule Loft", "units": 5, "price_per_unit": 110}
    )
    assert out["ready"] is False and out["sellable_units"] == 2
    notes = " ".join(out["notes"])
    assert "up to 2 units of this property (8 are already listed or reserved)" in notes
    assert "365-day lock-up until" in notes
    assert "at most 105.00 (105% of the reference price)" in notes
    assert _card_for("prepare_sale", out, [])["ready"] is False

    kyc = await _user(client, db, "rules-kyc@p.io", kyc="rejected")
    _own(db, kyc, loft, 3)
    _setting(db, "secondary_lockup_days", "0")
    out = await _run(
        asession,
        await _ctx(asession, kyc),
        "prepare_sale",
        {"property": "rule-loft", "units": 1, "price_per_unit": 100},
    )
    assert out["ready"] is False and "not approved" in out["notes"][0]

    nobody = await _user(client, db, "empty@p.io")
    with pytest.raises(AppError) as exc:
        await _run(
            asession,
            await _ctx(asession, nobody),
            "prepare_sale",
            {"property": "Rule Loft", "units": 1},
        )
    assert exc.value.code == "NOTHING_HELD"


# --- installments --------------------------------------------------------------------------- #
async def _plan(client, db, email: str) -> tuple[str, str]:
    uid = await _user(client, db, email, balance=100000)
    pid = _prop(db, title="Plan Tower", slug=f"plan-{uid[:6]}", model="installment")
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    r = await client.post(
        "/api/v1/installments",
        json={"property_id": pid, "amount": 1200, "duration_months": 12},
        headers={
            "Authorization": f"Bearer {login.json()['access_token']}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 201, r.text
    return uid, pid


@pytest.mark.asyncio
async def test_next_installment_is_prepared_up_to_pay(client, db, asession):
    uid, _pid = await _plan(client, db, "plan@p.io")
    rows = db(
        "SELECT p.id, p.seq, p.total_amount, p.status FROM installment_payments p "
        "JOIN installment_plans pl ON pl.id = p.plan_id WHERE pl.investor_id=:u ORDER BY p.seq",
        u=uid,
    )
    assert rows[0][1] == 0 and rows[0][3] == "paid"  # the down payment is paid at creation
    first = rows[1]
    ctx = await _ctx(asession, uid)

    out = await _run(asession, ctx, "prepare_installment_payment", {})
    assert (out["payment_id"], out["label"], out["status"]) == (
        str(first[0]),
        "Month 1",
        "scheduled",
    )
    # a 12-month plan = the down payment + 11 installments: 10 remain after Month 1
    assert out["total_amount"] == f"{first[2]:.2f}" and out["unpaid_after"] == 10
    assert out["ready"] is True and out["notes"] == []
    assert "automatically on the due date" in out["auto_charge"]
    card = _card_for("prepare_installment_payment", out, [])
    assert card["kind"] == "installment"
    assert card["path"] == f"/dashboard?tab=installments&pay={first[0]}"
    paid_before = db("SELECT count(*) FROM installment_payments WHERE status='paid'")[0][0]

    # overdue and the wallet cannot cover it: say so, block the button, charge nothing
    db("UPDATE installment_payments SET status='overdue' WHERE id=:i", i=first[0])
    db("UPDATE wallets SET balance=10 WHERE user_id=:u", u=uid)
    late = await _run(asession, ctx, "prepare_installment_payment", {"property": "plan tower"})
    assert late["ready"] is False and late["status"] == "overdue"
    assert late["notes"][0].startswith("Your wallet has 10.00; add at least")
    assert "no late fee" in late["notes"][1]
    assert db("SELECT count(*) FROM installment_payments WHERE status='paid'")[0][0] == paid_before


@pytest.mark.asyncio
async def test_quoted_schedule_is_the_schedule_the_platform_creates(client, db, asession):
    """Regression: the quote split a 12-month plan into 12 installments after the down
    payment, while the platform creates the down payment + 11, so every quoted monthly amount
    was too low. Both now come from installment_service.schedule_bases."""
    uid, pid = await _plan(client, db, "same@p.io")
    real = [
        (seq, kind, f"{base:.2f}", f"{fee:.2f}", f"{total:.2f}")
        for seq, kind, base, fee, total in db(
            "SELECT p.seq, p.kind, p.base_amount, p.fee_amount, p.total_amount FROM installment_payments p "
            "JOIN installment_plans pl ON pl.id = p.plan_id WHERE pl.investor_id=:u ORDER BY p.seq",
            u=uid,
        )
    ]
    quote = await _run(
        asession,
        await _ctx(asession, uid),
        "quote_investment",
        {"id_or_slug": pid, "amount": 1200, "duration_months": 12},
    )
    quoted = [
        (
            r["seq"],
            {"down_payment": "downpayment"}.get(r["kind"], r["kind"]),
            r["base_amount"],
            r["fee_amount"],
            r["total_amount"],
        )
        for r in quote["schedule"]
    ]
    assert quoted == real and len(real) == 12


@pytest.mark.asyncio
async def test_nothing_to_pay_is_said_plainly(client, db, asession):
    uid = await _user(client, db, "noplan@p.io")
    with pytest.raises(AppError) as exc:
        await _run(asession, await _ctx(asession, uid), "prepare_installment_payment", {})
    assert (exc.value.code, exc.value.message) == ("NOTHING_DUE", "You have no installment plans.")


# --- comparing ---------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_compare_properties_side_by_side(db, asession):
    _prop(db, title="Compare Ready", slug="compare-ready", content=CONTENT)
    _prop(db, title="Compare Plan", slug="compare-plan", model="installment", price=250)
    _prop(db, title="Compare Draft", slug="compare-draft", status="draft")

    out = await _run(
        asession,
        VISITOR,  # public information: visitors may compare
        "compare_properties",
        {"properties": ["compare-ready", "Compare Plan", "compare-draft", "compare-ready"]},
    )
    ready, plan = out["items"]
    assert (ready["title"], plan["title"]) == ("Compare Ready", "Compare Plan")
    assert (ready["purchase"], plan["purchase"]) == ("direct", "installment")
    assert (ready["unit_price"], plan["unit_price"]) == (100.0, 250.0)
    assert ready["risks"] == ["Construction delay: medium", "Market: high", "Liquidity: low"]
    assert ready["highest_risk"] == "high" and plan["highest_risk"] is None
    assert (
        ready["exit_options"] == ["Secondary market", "Buy-back"] and ready["exit_fee_pct"] == 2.0
    )
    assert out["not_found"] == ["compare-draft"]  # a draft never appears
    assert "not a recommendation" in out["note"]
    card = _card_for("compare_properties", out, [])
    assert card["kind"] == "comparison" and card["platform_fee_pct"] == out["platform_fee_pct"]
    assert [i["path"] for i in card["items"]] == [
        "/property/compare-ready",
        "/property/compare-plan",
    ]

    with pytest.raises(AppError) as exc:
        await _run(
            asession, VISITOR, "compare_properties", {"properties": ["compare-ready", "nope-x"]}
        )
    assert exc.value.code == "NEED_TWO" and "nope-x" in exc.value.message


def test_a_refused_slug_gives_no_link_and_no_crash():
    assert _card_for("get_property", {"slug": "Bad Slug", "title": "X"}, []) is None
    card = _card_for("search_properties", {"items": [{"slug": "Bad Slug", "title": "X"}]}, [])
    assert card["items"][0]["path"] is None
