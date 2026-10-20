"""Manual withdrawals beside the automatic ones (owner brief, 2026-10-20).

A member asks for a withdrawal to a SAVED bank account or crypto wallet; the amount is held at
once; the team pays it by hand and closes it on the Withdrawals desk: processing -> PAID (with
the transfer number) or FAILED (with the reason: the amount goes back to the wallet, once).
Only a request that says route="auto" takes the automatic path (covered, unchanged, by
test_withdrawal_db / test_payout_auto_mode_db).
"""

from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.services import wallet_service, withdrawal_service

PW = "Passw0rd!23"


async def _member(client, db, email: str, *, confirmed: bool = True) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Mona Ali"}
    )
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    if confirmed:
        db("UPDATE users SET email_verified=true WHERE id=:i", i=uid)
    db(
        "INSERT INTO transactions (user_id, type, amount, status) "
        "VALUES (:u,'deposit',500,'completed')",
        u=uid,
    )
    db("UPDATE wallets SET balance=500 WHERE user_id=:u", u=uid)
    return r.json()["access_token"], uid


async def _admin(client, db, email: str = "desk-admin@w.com") -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Desk"}
    )
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert r.status_code in (200, 302, 303)
    return uid


def _h(tok: str, idem: bool = False) -> dict:
    h = {"Authorization": f"Bearer {tok}"}
    if idem:
        h["Idempotency-Key"] = str(uuid.uuid4())
    return h


async def _bank(client, tok) -> dict:
    r = await client.post(
        "/api/v1/wallet/bank-accounts",
        json={
            "account_holder": "Mona Ali",
            "bank_name": "CIB",
            "iban": "EG38 0019 0005 0000 0000 2631 4321",
            "swift_bic": "CIBEEGCX",
            "country": "Egypt",
            "currency": "USD",
        },
        headers=_h(tok),
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


async def _ask(client, tok, amount, method="bank", **extra):
    return await client.post(
        "/api/v1/wallet/withdrawals",
        json={"amount": amount, "method": method, **extra},
        headers=_h(tok, idem=True),
    )


def _wallet(db, uid):
    return tuple(db("SELECT balance, pending_balance FROM wallets WHERE user_id=:u", u=uid)[0])


def _refunds(db, wid):
    return db(
        "SELECT count(*) FROM transactions WHERE reference_id=:w AND type='withdrawal' "
        "AND status='reversed'",
        w=wid,
    )[0][0]


# --- asking ----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_asking_needs_a_confirmed_email_a_saved_destination_and_the_balance(client, db):
    tok, uid = await _member(client, db, "unconfirmed@w.com", confirmed=False)
    await _bank(client, tok)
    r = await _ask(client, tok, 100)
    assert r.status_code == 403 and r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

    tok2, uid2 = await _member(client, db, "nodest@w.com")
    r = await _ask(client, tok2, 100)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_PAYOUT_METHOD"
    # never a typed-in crypto address: only a saved wallet
    r = await _ask(client, tok2, 100, method="crypto", address="TTypedInAddress")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_PAYOUT_METHOD"

    await _bank(client, tok2)
    r = await _ask(client, tok2, 600)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    for u in (uid, uid2):
        assert _wallet(db, u) == (500, 0)  # nothing held anywhere
    assert db("SELECT count(*) FROM withdrawals")[0][0] == 0


@pytest.mark.asyncio
async def test_a_request_is_held_numbered_and_tells_the_member_and_the_team(
    client, db, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "support_inbox_email", "desk@capimax.test")
    await _admin(client, db)
    tok, uid = await _member(client, db, "asker@w.com")
    acct = await _bank(client, tok)

    r = await _ask(client, tok, 120, payout_method_id=acct["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending_review" and body["provider"] == "manual"
    assert re.fullmatch(r"WD-[A-HJ-NP-Z2-9]{10}", body["reference"]), body["reference"]
    assert body["destination_label"] == "CIB · ****4321"
    assert _wallet(db, uid) == (380, 120)  # held at once

    # the saved account goes; the request still says where to pay
    await client.delete(f"/api/v1/wallet/bank-accounts/{acct['id']}", headers=_h(tok))
    row = db(
        "SELECT destination_label, destination->>'iban' FROM withdrawals WHERE id=:w",
        w=body["withdrawal_id"],
    )[0]
    assert row[0] == "CIB · ****4321" and row[1].endswith("4321")

    mine = (await client.get("/api/v1/wallet/withdrawals", headers=_h(tok))).json()["items"]
    assert mine[0]["reference"] == body["reference"] and mine[0]["status"] == "pending_review"

    told = db("SELECT to_email, subject FROM email_outbox ORDER BY created_at")
    assert any(t == "asker@w.com" and body["reference"] in s for t, s in told), told
    staff = sorted(t for t, s in told if s.startswith("[Withdrawal]"))
    assert staff == ["desk-admin@w.com", "desk@capimax.test"], told


# --- closing it ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_processing_then_paid_with_the_transfer_number(client, db, asession):
    tok, uid = await _member(client, db, "paid@w.com")
    await _bank(client, tok)
    wid = uuid.UUID((await _ask(client, tok, 200)).json()["withdrawal_id"])

    await withdrawal_service.admin_mark_processing(asession, withdrawal_id=wid, actor_id=None)
    await asession.commit()
    assert db("SELECT status FROM withdrawals WHERE id=:w", w=wid)[0][0] == "processing"
    # a transfer the team started and never closed still waits for a person
    waiting = await withdrawal_service.list_awaiting_payout(asession)
    assert any(w.id == wid for w, _e in waiting)

    await withdrawal_service.admin_mark_paid(
        asession, withdrawal_id=wid, actor_id=None, reference="FT-2026-0042"
    )
    await asession.commit()
    st, ref, completed = db(
        "SELECT status, transfer_reference, completed_at FROM withdrawals WHERE id=:w", w=wid
    )[0]
    assert (st, ref) == ("completed", "FT-2026-0042") and completed is not None
    assert _wallet(db, uid) == (300, 0)  # stays debited, nothing in flight
    hold = db("SELECT status FROM transactions WHERE reference_id=:w AND type='withdrawal'", w=wid)
    assert hold == [("completed",)]  # the statement says it was paid, not "in progress"
    mail = db("SELECT body FROM email_outbox WHERE to_email='paid@w.com' AND subject LIKE '%paid'")
    assert mail and "FT-2026-0042" in mail[0][0]

    # a paid request cannot be failed
    with pytest.raises(Exception) as exc:
        await withdrawal_service.admin_mark_failed(
            asession, withdrawal_id=wid, actor_id=None, reason="changed my mind"
        )
    assert getattr(exc.value, "code", "") == "INVALID_TRANSITION"
    await asession.rollback()
    assert _wallet(db, uid) == (300, 0)


@pytest.mark.asyncio
async def test_failed_returns_the_money_once_and_never_twice(client, db, asession):
    tok, uid = await _member(client, db, "failed@w.com")
    await _bank(client, tok)
    wid = uuid.UUID((await _ask(client, tok, 150)).json()["withdrawal_id"])
    assert _wallet(db, uid) == (350, 150)

    with pytest.raises(Exception) as exc:  # the reason is required
        await withdrawal_service.admin_mark_failed(
            asession, withdrawal_id=wid, actor_id=None, reason=" "
        )
    assert getattr(exc.value, "code", "") == "REASON_REQUIRED"
    await asession.rollback()

    for _ in range(2):  # pressed twice
        await withdrawal_service.admin_mark_failed(
            asession, withdrawal_id=wid, actor_id=None, reason="IBAN rejected by the bank"
        )
        await asession.commit()
    assert _wallet(db, uid) == (500, 0)
    assert _refunds(db, wid) == 1
    st, reason = db("SELECT status, failure_reason FROM withdrawals WHERE id=:w", w=wid)[0]
    assert (st, reason) == ("failed", "IBAN rejected by the bank")
    mail = db(
        "SELECT body FROM email_outbox WHERE to_email='failed@w.com' AND subject LIKE '%not sent'"
    )
    assert mail and "IBAN rejected by the bank" in mail[0][0]

    # a failed request cannot be paid
    with pytest.raises(Exception) as exc:
        await withdrawal_service.admin_mark_paid(
            asession, withdrawal_id=wid, actor_id=None, reference="FT-1"
        )
    assert getattr(exc.value, "code", "") == "INVALID_TRANSITION"
    await asession.rollback()

    # and nothing else can return it a second time: the database refuses
    with pytest.raises(IntegrityError):
        await wallet_service.release_hold(
            asession, user_id=uuid.UUID(uid), amount=150, reference_id=wid, reason="again"
        )
        await asession.flush()
    await asession.rollback()
    assert _wallet(db, uid) == (500, 0) and _refunds(db, wid) == 1


@pytest.mark.asyncio
async def test_approve_is_for_the_automatic_path_only(client, db, asession):
    tok, _uid = await _member(client, db, "approve@w.com")
    await _bank(client, tok)
    wid = uuid.UUID((await _ask(client, tok, 50)).json()["withdrawal_id"])
    with pytest.raises(Exception) as exc:
        await withdrawal_service.admin_review(
            asession, withdrawal_id=wid, approve=True, actor_id=None
        )
    assert getattr(exc.value, "code", "") == "MANUAL_WITHDRAWAL"
    await asession.rollback()
    assert db("SELECT status FROM withdrawals WHERE id=:w", w=wid)[0][0] == "pending_review"


@pytest.mark.asyncio
async def test_a_stuck_automatic_withdrawal_can_be_finished_by_hand(client, db, asession):
    tok, uid = await _member(client, db, "stuck@w.com")
    await _bank(client, tok)
    wid = uuid.UUID((await _ask(client, tok, 80)).json()["withdrawal_id"])
    # as if Stripe's balance had been short: an automatic request waiting with its hold
    db(
        "UPDATE withdrawals SET provider='stripe', "
        'destination=\'{"connect_account_id":"acct_1"}\' '
        "WHERE id=:w",
        w=wid,
    )
    await withdrawal_service.admin_mark_processing(asession, withdrawal_id=wid, actor_id=None)
    await withdrawal_service.admin_mark_failed(
        asession, withdrawal_id=wid, actor_id=None, reason="Stripe balance too low"
    )
    await asession.commit()
    assert _wallet(db, uid) == (500, 0) and _refunds(db, wid) == 1

    # one handed to the provider settles there: the desk does not fail it
    wid2 = uuid.UUID((await _ask(client, tok, 40)).json()["withdrawal_id"])
    db(
        "UPDATE withdrawals SET provider='stripe', status='processing', provider_payout_id='po_1' "
        "WHERE id=:w",
        w=wid2,
    )
    with pytest.raises(Exception) as exc:
        await withdrawal_service.admin_mark_failed(
            asession, withdrawal_id=wid2, actor_id=None, reason="give up"
        )
    assert getattr(exc.value, "code", "") == "WITH_PROVIDER"
    await asession.rollback()


@pytest.mark.asyncio
async def test_asking_for_the_automatic_path_when_it_is_off(client, db):
    tok, _uid = await _member(client, db, "noauto@w.com")
    await _bank(client, tok)
    r = await _ask(client, tok, 50, route="auto")
    assert r.status_code == 409 and r.json()["error"]["code"] == "AUTO_NOT_AVAILABLE"
    assert db("SELECT count(*) FROM withdrawals")[0][0] == 0


# --- receipts --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_every_movement_has_a_numbered_receipt_for_its_owner_only(client, db, asession):
    tok, uid = await _member(client, db, "receipt@w.com")
    await _bank(client, tok)
    wid = uuid.UUID((await _ask(client, tok, 90)).json()["withdrawal_id"])
    await withdrawal_service.admin_mark_failed(
        asession, withdrawal_id=wid, actor_id=None, reason="Wrong SWIFT"
    )
    await asession.commit()
    rows = db(
        "SELECT id, amount FROM transactions WHERE reference_id=:w ORDER BY created_at", w=wid
    )
    assert len(rows) == 2  # the debit and its refund
    for tx_id, _amount in rows:
        r = await client.get(f"/api/v1/wallet/transactions/{tx_id}/receipt", headers=_h(tok))
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        number = "RCT-" + uuid.UUID(str(tx_id)).hex[:10].upper()
        assert number in r.headers["content-disposition"]
        assert number.encode() in r.content
    ref = db("SELECT reference FROM withdrawals WHERE id=:w", w=wid)[0][0]
    assert ref.encode() in r.content

    other, _ = await _member(client, db, "nosy@w.com")
    r = await client.get(f"/api/v1/wallet/transactions/{rows[0][0]}/receipt", headers=_h(other))
    assert r.status_code == 404


# --- the desk --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_desk_lists_finds_and_closes_a_request(client, db):
    tok, uid = await _member(client, db, "deskcase@w.com")
    await _bank(client, tok)
    body = (await _ask(client, tok, 70)).json()
    wid, ref = body["withdrawal_id"], body["reference"]

    anon = await client.get("/admin/withdrawals-desk", follow_redirects=False)
    assert anon.status_code in (302, 307)
    await _admin(client, db)

    page = await client.get("/admin/withdrawals-desk", params={"q": ref})
    assert page.status_code == 200 and ref in page.text and "deskcase@w.com" in page.text
    none = await client.get("/admin/withdrawals-desk", params={"q": "WD-NOTHING", "kind": "auto"})
    assert ref not in none.text

    one = await client.get(f"/admin/withdrawals-desk/{wid}")
    assert one.status_code == 200 and "CIBEEGCX" in one.text and "Mark as PAID" in one.text

    no_ref = await client.post(f"/admin/withdrawals-desk/{wid}", data={"action": "paid"})
    assert no_ref.status_code == 400 and "transfer number" in no_ref.text
    paid = await client.post(
        f"/admin/withdrawals-desk/{wid}",
        data={"action": "paid", "transfer_reference": "FT-77"},
    )
    assert paid.status_code == 200 and "Marked as PAID" in paid.text
    assert "Mark as FAILED" not in paid.text  # nothing left to do on a paid request
    assert db("SELECT status FROM withdrawals WHERE id=:w", w=wid)[0][0] == "completed"
    assert _wallet(db, uid) == (430, 0)
