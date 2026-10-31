"""Transfers of property units or wallet balance to another person (client, 2026-10-28, as on
Capimax BRX), and the gift fix that came with them.

What each test protects:
  * balance to a verified member: held, delivered at once, both wallets and both sides told,
    a TR- number on every row; the recipient sees the sender's name, never their email;
  * units to a verified member: -N/+N on the ledger with the transfer's id; only FREE units
    can be sent (listed ones cannot), and sent units are held until delivered;
  * to someone not verified (or with no account): it waits, units stay held, they are invited
    by email; it is handed over the moment they confirm and verify; after 30 days it comes
    back, exactly once (and the database refuses a second money-in row);
  * the sender cancels before delivery and gets everything back, the fee too; a delivered
    transfer cannot be cancelled; nobody else can cancel it;
  * a delivery date ahead: scheduled, held, delivered by the run on that date;
  * the fee setting: charged when sent, returned with a transfer that never arrives;
  * refused: to yourself, a past date, beyond a year, more than the balance, no verified
    identity, not an investor; the same Idempotency-Key sends once; the review step writes
    nothing;
  * the admin Transfers desk: list, detail with the recipient's state and the rows written,
    Deliver now (refused until the recipient is ready), Cancel and return with a reason;
  * gifts: a pending gift can be cancelled (cash refunded) and one nobody received within 30
    days goes back; the cron runs gifts and transfers together.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.services import account_service, transfer_service
from app.tests.test_documents_db import _seed_property

PW = "Passw0rd!23"
TR = re.compile(r"TR-[A-HJ-NP-Z2-9]{10}")


async def _member(
    client,
    db,
    email: str,
    *,
    name: str = "Member",
    balance: int = 0,
    verified: bool = True,
) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": name}
    )
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    if verified:
        db("UPDATE users SET email_verified=true WHERE id=:i", i=uid)
        db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    if balance:
        db(
            "INSERT INTO transactions (user_id, type, amount, status) "
            "VALUES (:u,'deposit',:a,'completed')",
            u=uid,
            a=balance,
        )
        db("UPDATE wallets SET balance=:a WHERE user_id=:u", u=uid, a=balance)
    return r.json()["access_token"], uid


def _h(tok: str, key: str | None = None) -> dict:
    return {"Authorization": f"Bearer {tok}", "Idempotency-Key": key or uuid.uuid4().hex}


def _balance(db, uid) -> str:
    return str(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0])


def _units(db, uid, pid) -> int:
    return int(
        db(
            "SELECT coalesce(sum(units),0) FROM ownership_ledger "
            "WHERE user_id=:u AND property_id=:p",
            u=uid,
            p=pid,
        )[0][0]
    )


def _fee(db, pct: str) -> None:
    # platform_settings is emptied between tests; production has the row from 0040
    db(
        "INSERT INTO platform_settings (key, value) VALUES ('transfer_fee_pct', :v) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        v=pct,
    )


def _hold(db, uid, pid, n) -> None:
    db(
        "INSERT INTO ownership_ledger (user_id,property_id,units,unit_price,reason) "
        "VALUES (:u,:p,:n,100,'purchase')",
        u=uid,
        p=pid,
        n=n,
    )


async def _send(client, tok, **body):
    return await client.post("/api/v1/transfers", json=body, headers=_h(tok))


@pytest.mark.asyncio
async def test_balance_to_a_verified_member_is_delivered_at_once(client, db):
    tok, a = await _member(client, db, "tr-a@x.com", name="Amira Saleh", balance=500)
    rtok, b = await _member(client, db, "tr-b@x.com", name="Bassel Nour")

    r = await _send(
        client, tok, asset="balance", amount="120.50", recipient_email="TR-B@x.com", message="Hi"
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert TR.fullmatch(out["reference"]) and out["status"] == "delivered"
    assert (out["direction"], out["counterparty"]) == ("sent", "tr-b@x.com")
    assert (_balance(db, a), _balance(db, b)) == ("379.50", "120.50")
    rows = db(
        "SELECT user_id::text, type::text, amount, description FROM transactions "
        "WHERE reference_id=:t ORDER BY amount",
        t=out["id"],
    )
    assert [(r[0], r[1], str(r[2])) for r in rows] == [
        (a, "transfer", "-120.50"),
        (b, "transfer", "120.50"),
    ]
    assert out["reference"] in rows[0][3] and "Amira Saleh" in rows[1][3]
    told = db("SELECT user_id::text, title FROM notifications WHERE type='transfer' ORDER BY title")
    assert {t[0] for t in told} == {a, b}

    mine = (await client.get("/api/v1/transfers", headers=_h(rtok))).json()["items"]
    assert len(mine) == 1 and mine[0]["direction"] == "received"
    assert mine[0]["counterparty"] == "Amira Saleh" and "tr-a@x.com" not in str(mine[0])
    assert mine[0]["can_cancel"] is False and mine[0]["recipient_email"] is None


@pytest.mark.asyncio
async def test_units_move_on_the_ledger_and_only_free_units_can_be_sent(client, db):
    tok, a = await _member(client, db, "tu-a@x.com", balance=0)
    _rt, b = await _member(client, db, "tu-b@x.com")
    pid = _seed_property(db, None, slug="tu-prop")
    _hold(db, a, pid, 10)
    db(
        "INSERT INTO secondary_listings (seller_id, property_id, units_for_sale, units_remaining, "
        "price_per_unit, status) VALUES (:u,:p,4,4,100,'active')",
        u=a,
        p=pid,
    )
    opts = (await client.get("/api/v1/transfers/options", headers=_h(tok))).json()
    assert opts["positions"][0]["free_units"] == 6 and opts["claim_days"] == 30

    too_many = await _send(
        client, tok, asset="units", property_id=pid, units=7, recipient_email="tu-b@x.com"
    )
    assert too_many.status_code == 422 and too_many.json()["error"]["code"] == "INSUFFICIENT_UNITS"
    assert "up to 6 units" in too_many.json()["error"]["message"]

    ok = await _send(
        client, tok, asset="units", property_id=pid, units=6, recipient_email="tu-b@x.com"
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["status"] == "delivered" and ok.json()["amount"] == "600.00"
    assert (_units(db, a, pid), _units(db, b, pid)) == (4, 6)
    led = db(
        "SELECT reason, units FROM ownership_ledger WHERE ref_id=:t ORDER BY units",
        t=ok.json()["id"],
    )
    assert [tuple(r) for r in led] == [("transfer_out", -6), ("transfer_in", 6)]


@pytest.mark.asyncio
async def test_to_someone_not_verified_it_waits_then_is_handed_over(client, db, asession):
    tok, a = await _member(client, db, "tw-a@x.com", name="Amira", balance=300)
    pid = _seed_property(db, None, slug="tw-prop")
    _hold(db, a, pid, 5)

    cash = await _send(client, tok, asset="balance", amount="100", recipient_email="new@x.com")
    units = await _send(
        client, tok, asset="units", property_id=pid, units=3, recipient_email="new@x.com"
    )
    for r in (cash, units):
        assert r.status_code == 201 and r.json()["status"] == "waiting", r.text
        assert r.json()["expires_at"]
    assert _balance(db, a) == "200.00"  # the amount is held
    opts = (await client.get("/api/v1/transfers/options", headers=_h(tok))).json()
    assert opts["positions"][0]["free_units"] == 2  # three are held for the transfer
    invites = db("SELECT to_email, subject, body FROM email_outbox WHERE to_email='new@x.com'")
    assert len(invites) == 2 and "Amira sent you" in invites[0][1]
    assert "verify your identity by" in invites[0][2]

    # they sign up: nothing moves until the email is confirmed AND identity verified
    _t, b = await _member(client, db, "new@x.com", verified=False)
    await account_service.release_waiting(asession, uuid.UUID(b))
    await asession.commit()
    assert _balance(db, b) == "0.00"
    db("UPDATE users SET email_verified=true WHERE id=:i", i=b)
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=b)
    await account_service.release_waiting(asession, uuid.UUID(b))
    await asession.commit()
    assert _balance(db, b) == "100.00" and _units(db, b, pid) == 3 and _units(db, a, pid) == 2
    statuses = db("SELECT status FROM transfers ORDER BY created_at")
    assert [s[0] for s in statuses] == ["delivered", "delivered"]


@pytest.mark.asyncio
async def test_unclaimed_transfers_come_back_once(client, db, asession):
    tok, a = await _member(client, db, "te-a@x.com", balance=200)
    pid = _seed_property(db, None, slug="te-prop")
    _hold(db, a, pid, 4)
    _fee(db, "2")
    cash = (
        await _send(client, tok, asset="balance", amount="100", recipient_email="x@x.com")
    ).json()
    assert cash["fee"] == "2.00" and _balance(db, a) == "98.00"
    await _send(client, tok, asset="units", property_id=pid, units=4, recipient_email="x@x.com")
    assert _balance(db, a) == "90.00"  # 2% of 4 x 100 = 8.00 for the units

    later = dt.datetime.now(dt.UTC) + dt.timedelta(days=31)
    out = await transfer_service.run_due(asession, now=later)
    await asession.commit()
    assert out["expired"] == 2
    assert _balance(db, a) == "200.00"  # amount and both fees back
    again = await transfer_service.run_due(asession, now=later)
    await asession.commit()
    assert again["expired"] == 0 and _balance(db, a) == "200.00"
    assert [s[0] for s in db("SELECT status FROM transfers")] == ["expired", "expired"]
    opts = (await client.get("/api/v1/transfers/options", headers=_h(tok))).json()
    assert opts["positions"][0]["free_units"] == 4  # released
    assert db("SELECT count(*) FROM notifications WHERE title LIKE '%returned to you'")[0][0] == 2

    # the database refuses a second money-in row for the same transfer
    with pytest.raises(IntegrityError):
        db(
            "INSERT INTO transactions (user_id, type, amount, reference_id, status) "
            "VALUES (:u, 'transfer', 1, :t, 'completed')",
            u=a,
            t=cash["id"],
        )


@pytest.mark.asyncio
async def test_the_sender_cancels_before_delivery(client, db):
    tok, a = await _member(client, db, "tc-a@x.com", balance=100)
    other, _ = await _member(client, db, "tc-b@x.com")
    _fee(db, "1")
    t = (
        await _send(client, tok, asset="balance", amount="50", recipient_email="tc-z@x.com")
    ).json()
    assert _balance(db, a) == "49.50"
    assert (
        await client.post(f"/api/v1/transfers/{t['id']}/cancel", headers=_h(other))
    ).status_code == 404
    done = await client.post(f"/api/v1/transfers/{t['id']}/cancel", headers=_h(tok))
    assert done.status_code == 200 and done.json()["status"] == "cancelled"
    assert _balance(db, a) == "100.00"
    twice = await client.post(f"/api/v1/transfers/{t['id']}/cancel", headers=_h(tok))
    assert twice.status_code == 409 and twice.json()["error"]["code"] == "NOT_OPEN"
    assert _balance(db, a) == "100.00"

    await _member(client, db, "tc-c@x.com")
    sent = (
        await _send(client, tok, asset="balance", amount="10", recipient_email="tc-c@x.com")
    ).json()
    late = await client.post(f"/api/v1/transfers/{sent['id']}/cancel", headers=_h(tok))
    assert late.status_code == 409  # delivered: nothing to take back


@pytest.mark.asyncio
async def test_a_date_ahead_is_scheduled_and_delivered_by_the_run(client, db, asession):
    tok, a = await _member(client, db, "ts-a@x.com", balance=100)
    _t, b = await _member(client, db, "ts-b@x.com")
    day = dt.date.today() + dt.timedelta(days=10)
    t = (
        await _send(
            client,
            tok,
            asset="balance",
            amount="40",
            recipient_email="ts-b@x.com",
            deliver_on=day.isoformat(),
        )
    ).json()
    assert t["status"] == "scheduled" and _balance(db, a) == "60.00" and _balance(db, b) == "0.00"
    early = await transfer_service.run_due(asession)
    await asession.commit()
    assert early["delivered"] == 0
    on_the_day = dt.datetime.combine(day, dt.time(9), tzinfo=dt.UTC)
    out = await transfer_service.run_due(asession, now=on_the_day)
    await asession.commit()
    assert out["delivered"] == 1 and _balance(db, b) == "40.00"


@pytest.mark.asyncio
async def test_what_is_refused(client, db):
    tok, a = await _member(client, db, "tx-a@x.com", balance=50)
    today = dt.date.today()
    cases = [
        (dict(asset="balance", amount="10", recipient_email="tx-a@x.com"), "SELF_TRANSFER"),
        (
            dict(
                asset="balance",
                amount="10",
                recipient_email="q@x.com",
                deliver_on=(today - dt.timedelta(days=1)).isoformat(),
            ),
            "DATE_IN_PAST",
        ),
        (
            dict(
                asset="balance",
                amount="10",
                recipient_email="q@x.com",
                deliver_on=(today + dt.timedelta(days=366)).isoformat(),
            ),
            "DATE_TOO_FAR",
        ),
        (dict(asset="balance", amount="50.01", recipient_email="q@x.com"), "INSUFFICIENT_FUNDS"),
        (dict(asset="balance", amount="0", recipient_email="q@x.com"), "INVALID_AMOUNT"),
    ]
    for body, code in cases:
        r = await _send(client, tok, **body)
        assert r.status_code == 422 and r.json()["error"]["code"] == code, (body, r.text)
    assert not db("SELECT 1 FROM transfers") and _balance(db, a) == "50.00"

    unverified, _u = await _member(client, db, "tx-u@x.com", balance=50, verified=False)
    r = await _send(client, unverified, asset="balance", amount="5", recipient_email="q@x.com")
    assert r.status_code == 403 and r.json()["error"]["code"] == "KYC_REQUIRED"

    owner_tok, owner = await _member(client, db, "tx-o@x.com", balance=50)
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'owner')", i=owner)
    db("DELETE FROM user_roles WHERE user_id=:i AND role='investor'", i=owner)
    r = await _send(client, owner_tok, asset="balance", amount="5", recipient_email="q@x.com")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_the_same_key_sends_once_and_the_review_writes_nothing(client, db):
    tok, a = await _member(client, db, "ti-a@x.com", balance=100)
    _fee(db, "2.5")
    q = await client.post(
        "/api/v1/transfers/quote",
        json={"asset": "balance", "amount": "40", "recipient_email": "w@x.com"},
        headers=_h(tok),
    )
    assert q.status_code == 200, q.text
    assert (q.json()["amount"], q.json()["fee"], q.json()["charged"]) == ("40.00", "1.00", "41.00")
    assert not db("SELECT 1 FROM transfers") and _balance(db, a) == "100.00"
    body = {"asset": "balance", "amount": "40", "recipient_email": "w@x.com"}
    one = await client.post("/api/v1/transfers", json=body, headers=_h(tok, "same-key"))
    two = await client.post("/api/v1/transfers", json=body, headers=_h(tok, "same-key"))
    assert one.json()["id"] == two.json()["id"]
    assert db("SELECT count(*) FROM transfers")[0][0] == 1 and _balance(db, a) == "59.00"


async def _admin(client, db, email="tr-desk@x.com"):
    _t, uid = await _member(client, db, email, name="Desk")
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert r.status_code in (200, 302, 303)


@pytest.mark.asyncio
async def test_the_admin_desk(client, db):
    tok, a = await _member(client, db, "td-a@x.com", name="Amira", balance=100)
    t = (
        await _send(client, tok, asset="balance", amount="30", recipient_email="td-z@x.com")
    ).json()
    assert (await client.get("/admin/transfers-desk", follow_redirects=False)).status_code in (
        302,
        303,
    )
    await _admin(client, db)
    page = await client.get("/admin/transfers-desk", params={"q": t["reference"]})
    assert page.status_code == 200 and t["reference"] in page.text and "td-a@x.com" in page.text
    one = await client.get(f"/admin/transfers-desk/{t['id']}")
    assert "No account with this email yet" in one.text and "−$30.00" in one.text

    early = await client.post(f"/admin/transfers-desk/{t['id']}", data={"action": "deliver"})
    assert early.status_code == 400 and "has not confirmed their email" in early.text
    _rt, b = await _member(client, db, "td-z@x.com")
    now = await client.post(f"/admin/transfers-desk/{t['id']}", data={"action": "deliver"})
    assert now.status_code == 200 and "Delivered." in now.text
    assert _balance(db, b) == "30.00"

    t2 = (
        await _send(client, tok, asset="balance", amount="20", recipient_email="td-y@x.com")
    ).json()
    no_reason = await client.post(f"/admin/transfers-desk/{t2['id']}", data={"action": "cancel"})
    assert no_reason.status_code == 400
    gone = await client.post(
        f"/admin/transfers-desk/{t2['id']}",
        data={"action": "cancel", "reason": "Reported as a mistake"},
    )
    assert gone.status_code == 200 and "went back to the sender" in gone.text
    assert _balance(db, a) == "70.00"
    reason = db("SELECT closed_reason FROM transfers WHERE id=:i", i=t2["id"])[0][0]
    assert reason == "Cancelled by Capimax PropShare: Reported as a mistake"
    told = db("SELECT message FROM notifications WHERE user_id=:u AND title LIKE '%returned%'", u=a)
    assert "Reported as a mistake" in told[0][0]


@pytest.mark.asyncio
async def test_pending_gifts_can_be_cancelled_and_expire(client, db, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "cron_secret", "cr0n", raising=False)
    cron = {"X-Cron-Secret": "cr0n"}
    tok, a = await _member(client, db, "tg-a@x.com", balance=100)
    gift = await client.post(
        "/api/v1/gifts",
        json={
            "recipient_name": "Nobody yet",
            "recipient_email": "tg-none@x.com",
            "asset_type": "wallet",
            "amount": "30",
            "scheduled_for": dt.date.today().isoformat(),
        },
        headers=_h(tok),
    )
    assert gift.status_code == 201, gift.text
    second = await client.post(
        "/api/v1/gifts",
        json={
            "recipient_name": "Nobody either",
            "recipient_email": "tg-none2@x.com",
            "asset_type": "wallet",
            "amount": "20",
            "scheduled_for": dt.date.today().isoformat(),
        },
        headers=_h(tok),
    )
    assert _balance(db, a) == "50.00"
    run = await client.post("/api/v1/admin/gifts/run-due", headers=cron)
    assert run.status_code == 200, run.text
    assert run.json()["pending"] == 2 and "transfers" in run.json()
    left = db("SELECT claim_expires_at - executed_at FROM scheduled_gifts WHERE status='pending'")
    assert [r[0].days for r in left] == [30, 30]  # 30 days from when it started waiting

    cancelled = await client.post(f"/api/v1/gifts/{gift.json()['id']}/cancel", headers=_h(tok))
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert _balance(db, a) == "80.00"

    db(
        "UPDATE scheduled_gifts SET claim_expires_at = now() - interval '1 minute' WHERE id=:i",
        i=second.json()["id"],
    )
    run = await client.post("/api/v1/admin/gifts/run-due", headers=cron)
    assert run.json()["expired"] == 1 and _balance(db, a) == "100.00"
    row = db(
        "SELECT status, failure_reason FROM scheduled_gifts WHERE id=:i", i=second.json()["id"]
    )
    assert row[0][0] == "expired" and "30 days" in row[0][1]
    again = await client.post("/api/v1/admin/gifts/run-due", headers=cron)
    assert again.json()["expired"] == 0 and _balance(db, a) == "100.00"


@pytest.mark.asyncio
async def test_the_assistant_lists_the_members_transfers(client, db, asession):
    from app.services.assistant import agent, guard
    from app.services.assistant.context import AgentContext, load_context
    from app.services.assistant.tools import REGISTRY
    from app.services.assistant.tools.base import call_tool, parse_args

    tok, a = await _member(client, db, "ta-a@x.com", balance=100)
    await _send(
        client, tok, asset="balance", amount="25", recipient_email="ta-z@x.com", message="Do X"
    )
    ctx = await load_context(asession, user_id=uuid.UUID(a))
    conv = await agent.start_conversation(asession, ctx)
    await asession.commit()
    ctx = AgentContext(**{**ctx.__dict__, "conversation_id": conv.id})
    spec = REGISTRY["get_my_transfers"]
    guard.authorize(spec, ctx)
    out = await call_tool(spec, asession, ctx, parse_args(spec, "{}"))
    item = out["items"][0]
    assert TR.fullmatch(item["reference"]) and item["status"] == "waiting" and item["can_cancel"]
    assert item["message"] == {"untrusted_text": "Do X"}  # typed by a person: data, not orders
    assert "30 days" in out["note"]
    assert guard.make_link("transfers")["path"] == "/dashboard?tab=transfers"


@pytest.mark.asyncio
async def test_unit_movements_name_the_other_side_and_the_tr_number(client, db, asession):
    tok, a = await _member(client, db, "tm-a@x.com", name="Amira Saleh")
    rtok, b = await _member(client, db, "tm-b@x.com", name="Bassel Nour")
    pid = _seed_property(db, None, slug="tm-prop")
    _hold(db, a, pid, 8)
    t = (
        await _send(
            client,
            tok,
            asset="units",
            property_id=pid,
            units=2,
            recipient_email="tm-b@x.com",
            recipient_name="My brother",
        )
    ).json()
    sent = (await client.get("/api/v1/investments/movements", headers=_h(tok))).json()["items"]
    got = (await client.get("/api/v1/investments/movements", headers=_h(rtok))).json()["items"]
    assert (sent[0]["label"], sent[0]["counterparty"]) == ("Transfer sent", "My brother")
    assert (got[0]["label"], got[0]["counterparty"]) == ("Transfer received", "Amira Saleh")
    assert "tm-a@x.com" not in str(got)  # the recipient never sees the sender's email
    from app.services import unit_movement_service

    today = dt.date.today()
    stmt = await unit_movement_service.build_statement(asession, uuid.UUID(a), today, today)
    assert [r.reference for r in stmt.rows if r.units == -2] == [t["reference"]]


@pytest.mark.asyncio
async def test_review_fixes_for_names_unconfirmed_accounts_and_retries(client, db, asession):
    """From the code review: typed text never becomes a link in an email to any address; an
    account that has not confirmed the address is told nothing in-app; a waiting transfer whose
    recipient became ready is delivered by the run, never sent back; the fee shown is the fee
    charged; a pending gift waits 30 days from when it started waiting."""
    tok, a = await _member(
        client, db, "tf-a@x.com", name="Win https://evil.example now", balance=100
    )
    # someone registered the address but cannot confirm it
    _st, squatter = await _member(client, db, "tf-owner@x.com", verified=False)
    t = (
        await _send(client, tok, asset="balance", amount="10", recipient_email="tf-owner@x.com")
    ).json()
    assert t["status"] == "waiting"
    mail = db(
        "SELECT subject, body FROM email_outbox "
        "WHERE to_email='tf-owner@x.com' AND category='invite'"
    )
    assert len(mail) == 1 and "evil.example" not in mail[0][0] + mail[0][1]
    assert not db("SELECT 1 FROM notifications WHERE user_id=:u AND type='transfer'", u=squatter)

    # the owner of the address confirms it and is verified, but the handover never reached them
    db("UPDATE users SET email_verified=true WHERE id=:i", i=squatter)
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=squatter)
    later = dt.datetime.now(dt.UTC) + dt.timedelta(days=31)  # even past its deadline
    out = await transfer_service.run_due(asession, now=later)
    await asession.commit()
    assert (out["delivered"], out["expired"]) == (1, 0) and _balance(db, squatter) == "10.00"

    # the fee changed between the review and the send: refused, nothing taken
    _fee(db, "3")
    stale = await client.post(
        "/api/v1/transfers",
        json={
            "asset": "balance",
            "amount": "20",
            "recipient_email": "tf-owner@x.com",
            "expected_charged": "20.00",
        },
        headers=_h(tok),
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "QUOTE_CHANGED"
    assert _balance(db, a) == "90.00"


@pytest.mark.asyncio
async def test_a_settled_estate_takes_back_what_was_not_received(client, db, asession):
    from app.services import gift_service

    tok, a = await _member(client, db, "tz-a@x.com", balance=100)
    pid = _seed_property(db, None, slug="tz-prop")
    _hold(db, a, pid, 5)
    await _send(client, tok, asset="units", property_id=pid, units=2, recipient_email="tz-q@x.com")
    await _send(client, tok, asset="balance", amount="40", recipient_email="tz-q@x.com")
    gift = await client.post(
        "/api/v1/gifts",
        json={
            "recipient_name": "Q",
            "recipient_email": "tz-q2@x.com",
            "asset_type": "wallet",
            "amount": "10",
            "scheduled_for": (dt.date.today() + dt.timedelta(days=5)).isoformat(),
        },
        headers=_h(tok),
    )
    assert gift.status_code == 201 and _balance(db, a) == "50.00"
    reason = "The account holder's estate is being settled."
    n = await transfer_service.close_open_for(asession, user_id=uuid.UUID(a), reason=reason)
    g = await gift_service.close_open_for(asession, giver_id=uuid.UUID(a), reason=reason)
    await asession.commit()
    assert (n, g) == (2, 1) and _balance(db, a) == "100.00"
    opts = (await client.get("/api/v1/transfers/options", headers=_h(tok))).json()
    assert opts["positions"][0]["free_units"] == 5
    assert [r[0] for r in db("SELECT closed_reason FROM transfers")] == [reason, reason]


@pytest.mark.asyncio
async def test_occasion_and_the_reminder_before_a_scheduled_transfer(client, db, asession):
    tok, a = await _member(client, db, "to-a@x.com", balance=100)
    await _member(client, db, "to-b@x.com")
    day = dt.date.today() + dt.timedelta(days=20)
    t = (
        await _send(
            client,
            tok,
            asset="balance",
            amount="5",
            recipient_email="to-b@x.com",
            occasion="birthday",
            deliver_on=day.isoformat(),
        )
    ).json()
    assert t["occasion"] == "birthday"
    bad = await _send(
        client, tok, asset="balance", amount="5", recipient_email="to-b@x.com", occasion="x"
    )
    assert bad.status_code == 422

    title = "%goes out soon"
    count = lambda: db(  # noqa: E731
        "SELECT count(*) FROM notifications WHERE user_id=:u AND title LIKE :t", u=a, t=title
    )[0][0]
    await transfer_service.run_due(asession)  # 20 days away: not yet
    await asession.commit()
    assert count() == 0
    near = dt.datetime.combine(day - dt.timedelta(days=5), dt.time(9), tzinfo=dt.UTC)
    await transfer_service.run_due(asession, now=near)
    await transfer_service.run_due(asession, now=near)  # reminded once
    await asession.commit()
    assert count() == 1
