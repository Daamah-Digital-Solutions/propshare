"""Task 3 — DB-backed tests for the MANUAL, admin-settled money flow.

Covers: saved payout methods (bank + crypto CRUD, one-default invariant); manual
withdrawal (holds funds -> admin mark-paid settles / reject releases; NO_PAYOUT_METHOD
when nothing saved); and manual bank-transfer deposit claims (pending -> admin confirm
credits the wallet / reject leaves it untouched).

Manual mode is the live default (platform_settings is truncated per test, so
``manual_payouts_enabled`` falls back to the DEFAULTS "true") — no setup needed here.
Admin actions are exposed via the SQLAdmin panel, so they're exercised by calling the
service functions directly on a raw session (``asession``).
"""

from __future__ import annotations

import uuid

import pytest

from app.services import manual_deposit_service, platform_accounts_service, withdrawal_service

PW = "Passw0rd!23"


async def _verified(client, db, email: str) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "M"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    return r.json()["access_token"], uid


def _fund(db, uid: str, amount) -> None:
    db(
        "INSERT INTO transactions (user_id, type, amount, status) "
        "VALUES (:u,'deposit',:a,'completed')",
        u=uid,
        a=amount,
    )
    db("UPDATE wallets SET balance=:a WHERE user_id=:u", a=amount, u=uid)


def _bal(db, uid):
    return db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]


def _pending(db, uid):
    return db("SELECT pending_balance FROM wallets WHERE user_id=:i", i=uid)[0][0]


def _auth(token: str, idem: bool = False) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if idem:
        h["Idempotency-Key"] = str(uuid.uuid4())
    return h


# --- saved payout methods --------------------------------------------------- #
@pytest.mark.asyncio
async def test_bank_account_crud_and_single_default(client, db):
    tok, uid = await _verified(client, db, "pm-bank@w.com")
    h = _auth(tok)
    a1 = (
        await client.post(
            "/api/v1/wallet/bank-accounts",
            json={"account_holder": "Ali", "bank_name": "Emirates NBD", "iban": "AE07033120000123"},
            headers=h,
        )
    ).json()
    assert a1["is_default"] is True  # first is auto-default
    a2 = (
        await client.post(
            "/api/v1/wallet/bank-accounts",
            json={"account_holder": "Ali", "bank_name": "ADCB", "account_number": "998877"},
            headers=h,
        )
    ).json()
    assert a2["is_default"] is False
    listed = (await client.get("/api/v1/wallet/bank-accounts", headers=h)).json()
    assert len(listed) == 2

    # switch default -> exactly one default remains
    d = await client.post(f"/api/v1/wallet/bank-accounts/{a2['id']}/default", headers=h)
    assert d.json()["is_default"] is True
    n_default = db(
        "SELECT count(*) FROM user_bank_accounts WHERE user_id=:u AND is_default", u=uid
    )[0][0]
    assert n_default == 1

    # deleting the default promotes the remaining account
    dele = await client.delete(f"/api/v1/wallet/bank-accounts/{a2['id']}", headers=h)
    assert dele.status_code == 204
    rows = db("SELECT id, is_default FROM user_bank_accounts WHERE user_id=:u", u=uid)
    assert len(rows) == 1 and rows[0][1] is True


@pytest.mark.asyncio
async def test_crypto_wallet_crud(client, db):
    tok, uid = await _verified(client, db, "pm-crypto@w.com")
    h = _auth(tok)
    w = (
        await client.post(
            "/api/v1/wallet/crypto-wallets",
            json={"network": "USDT-TRC20", "address": "TXhelloworldaddress"},
            headers=h,
        )
    ).json()
    assert w["is_default"] is True and w["network"] == "USDT-TRC20"
    dele = await client.delete(f"/api/v1/wallet/crypto-wallets/{w['id']}", headers=h)
    assert dele.status_code == 204
    assert db("SELECT count(*) FROM user_crypto_wallets WHERE user_id=:u", u=uid)[0][0] == 0


# --- manual withdrawal ------------------------------------------------------ #
@pytest.mark.asyncio
async def test_manual_bank_withdrawal_holds_then_marked_paid(client, db, asession):
    tok, uid = await _verified(client, db, "mw-paid@w.com")
    _fund(db, uid, 500)
    h = _auth(tok)
    acct = (
        await client.post(
            "/api/v1/wallet/bank-accounts",
            json={"account_holder": "Ali", "bank_name": "NBD", "iban": "AE9911112222"},
            headers=h,
        )
    ).json()
    res = await client.post(
        "/api/v1/wallet/withdrawals",
        json={"amount": 200, "method": "bank", "payout_method_id": acct["id"]},
        headers=_auth(tok, idem=True),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "pending_review"
    wid = body["withdrawal_id"]
    row = db("SELECT provider, destination FROM withdrawals WHERE id=:i", i=wid)[0]
    assert row[0] == "manual"
    assert row[1]["bank_name"] == "NBD"  # snapshot for the admin to pay
    assert _bal(db, uid) == 300 and _pending(db, uid) == 200  # held

    await withdrawal_service.admin_mark_paid(
        asession, withdrawal_id=uuid.UUID(wid), actor_id=None, reference="TRX-777"
    )
    await asession.commit()
    assert db("SELECT status FROM withdrawals WHERE id=:i", i=wid)[0][0] == "completed"
    assert _pending(db, uid) == 0 and _bal(db, uid) == 300  # money left; balance stays debited


@pytest.mark.asyncio
async def test_manual_withdrawal_reject_releases_funds(client, db, asession):
    tok, uid = await _verified(client, db, "mw-reject@w.com")
    _fund(db, uid, 300)
    h = _auth(tok)
    await client.post(
        "/api/v1/wallet/crypto-wallets",
        json={"network": "USDT-TRC20", "address": "TXrejectme"},
        headers=h,
    )
    res = await client.post(
        "/api/v1/wallet/withdrawals",
        json={"amount": 120, "method": "crypto"},
        headers=_auth(tok, idem=True),
    )
    assert res.status_code == 200, res.text
    wid = res.json()["withdrawal_id"]
    assert _bal(db, uid) == 180 and _pending(db, uid) == 120

    await withdrawal_service.admin_review(
        asession, withdrawal_id=uuid.UUID(wid), approve=False, actor_id=None, reason="bad address"
    )
    await asession.commit()
    assert db("SELECT status FROM withdrawals WHERE id=:i", i=wid)[0][0] == "rejected"
    assert _bal(db, uid) == 300 and _pending(db, uid) == 0  # funds returned


@pytest.mark.asyncio
async def test_bank_withdrawal_without_saved_method_errors(client, db):
    tok, uid = await _verified(client, db, "mw-nomethod@w.com")
    _fund(db, uid, 100)
    res = await client.post(
        "/api/v1/wallet/withdrawals",
        json={"amount": 50, "method": "bank"},
        headers=_auth(tok, idem=True),
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "NO_PAYOUT_METHOD"
    assert _bal(db, uid) == 100  # nothing held
    assert db("SELECT count(*) FROM withdrawals WHERE user_id=:i", i=uid)[0][0] == 0


# --- manual bank-transfer deposit ------------------------------------------- #
@pytest.mark.asyncio
async def test_bank_deposit_claim_confirm_credits(client, db, asession):
    tok, uid = await _verified(client, db, "dep-ok@w.com")
    acct = await platform_accounts_service.create(
        asession,
        actor_id=None,
        bank_name="CapiMax Bank",
        account_holder="CapiMax LTD",
        iban="AE000CAPIMAX",
    )
    await asession.commit()
    h = _auth(tok)
    listed = (await client.get("/api/v1/wallet/deposit/bank-accounts", headers=h)).json()
    assert len(listed) == 1 and listed[0]["bank_name"] == "CapiMax Bank"

    res = await client.post(
        "/api/v1/wallet/deposit/bank-transfer",
        json={"amount": 300, "platform_account_id": str(acct.id), "reference": "ref-abc"},
        headers=_auth(tok, idem=True),
    )
    assert res.status_code == 200, res.text
    pid = res.json()["payment_id"]
    assert res.json()["status"] == "pending"
    assert _bal(db, uid) == 0  # NOT credited until an admin confirms

    await manual_deposit_service.admin_confirm(
        asession, payment_id=uuid.UUID(pid), actor_id=None
    )
    await asession.commit()
    assert _bal(db, uid) == 300
    assert db("SELECT status FROM payments WHERE id=:i", i=pid)[0][0] == "succeeded"


@pytest.mark.asyncio
async def test_bank_deposit_claim_reject_no_credit(client, db, asession):
    tok, uid = await _verified(client, db, "dep-reject@w.com")
    res = await client.post(
        "/api/v1/wallet/deposit/bank-transfer",
        json={"amount": 150, "reference": "nope"},
        headers=_auth(tok, idem=True),
    )
    assert res.status_code == 200, res.text
    pid = res.json()["payment_id"]

    await manual_deposit_service.admin_reject(
        asession, payment_id=uuid.UUID(pid), actor_id=None, reason="not received"
    )
    await asession.commit()
    assert _bal(db, uid) == 0
    assert db("SELECT status FROM payments WHERE id=:i", i=pid)[0][0] == "cancelled"
