"""An account's standing: a confirmed email address, and open or closed (2026-10-11).

* What is sent to a person by email address (a family allocation and its returns, a gift)
  reaches the account registered with that address only once the account confirmed it.
  Anyone can type any address at sign-up, so an account that never confirmed its address
  receives nothing by address, even with its identity verified.
* The address is confirmed from inside the account (the link does nothing for a visitor or
  from another account), by a password reset, or by a provider that verified it: each one
  shows that whoever holds the account holds the mailbox.
* A closed account cannot sign in or act, and nothing it holds is touched. Staff close and
  reopen accounts.
"""

# ruff: noqa: E501
from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core.db import session_scope
from app.core.errors import AppError
from app.models.identity import User
from app.services import auth_service, kyc_service
from app.services.integrations import oauth

PW = "Passw0rd!23"


# --- arrange helpers -------------------------------------------------------- #
async def _user(
    client, db, email: str, name: str = "U", *, kyc: bool = True, confirmed: bool = False
) -> tuple[str, dict]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": name}
    )
    assert r.status_code == 201, r.text
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    if kyc:
        db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    if confirmed:
        db("UPDATE users SET email_verified=true WHERE id=:i", i=uid)
    return uid, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _property(db) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Marina Heights','Dubai','residential','ready-income','active',100000,100,1000,1000,100)",
        id=pid,
    )
    return pid


def _grant(db, uid: str, pid: str, units: int) -> None:
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason, fee_rate) "
        "VALUES (:u,:p,:n,100,'purchase','1.0')",
        u=uid,
        p=pid,
        n=units,
    )


def _fund(db, uid: str, amount) -> None:
    db(
        "INSERT INTO transactions (user_id, type, amount, status) VALUES (:u,'deposit',:a,'completed')",
        u=uid,
        a=amount,
    )
    db("UPDATE wallets SET balance=:a WHERE user_id=:u", a=amount, u=uid)


def _balance(db, uid: str):
    return db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]


def _holding(db, uid: str, pid: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE user_id=:u AND property_id=:p",
            u=uid,
            p=pid,
        )[0][0]
    )


async def _link_token(uid: str, kind: str) -> str:
    """A fresh link token for this account (what the email carries)."""
    async with session_scope() as session:
        return await auth_service.issue_email_token(
            session, await session.get(User, uuid.UUID(uid)), kind=kind
        )


async def _identity_verified(uid: str) -> None:
    """The identity check comes back verified (the hook that releases what waits runs)."""
    async with session_scope() as session:
        await kyc_service.admin_decide(session, user_id=uuid.UUID(uid), approve=True, actor_id=None)


async def _allocation_waiting(client, db, address: str) -> tuple[str, str, dict]:
    """A holder with 10 units and 300 in the wallet allocates 4 units and 50 of returns to a
    relative known by ``address`` alone. Returns (holder id, property id, holder headers)."""
    owner, oh = await _user(
        client, db, f"holder-{uuid.uuid4().hex[:6]}@fam.io", "Ahmed", confirmed=True
    )
    pid = _property(db)
    _grant(db, owner, pid, 10)
    _fund(db, owner, 300)
    r = await client.post("/api/v1/family/groups", json={"name": "Family"}, headers=oh)
    assert r.status_code == 200, r.text
    me = next(m["member_id"] for m in r.json()["members"] if m["relationship"] == "Self (Owner)")
    r = await client.post(
        "/api/v1/family/members",
        json={"name": "Omar", "relationship": "Son", "email": address},
        headers=oh,
    )
    assert r.status_code == 200, r.text
    member = r.json()["member_id"]
    r = await client.post(
        "/api/v1/family/transfers",
        json={"from_member_id": me, "to_member_id": member, "property_id": pid, "units": 4},
        headers={**oh, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200 and r.json()["status"] == "pending", r.text
    r = await client.post(
        "/api/v1/family/allocations",
        json={"member_id": member, "amount": 50},
        headers={**oh, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200 and r.json()["real"] is False, r.text
    return owner, pid, oh


def _linked(db, address: str):
    return db("SELECT user_id FROM family_members WHERE email=:e", e=address)[0][0]


# --- a confirmed address ---------------------------------------------------------- #
@pytest.mark.asyncio
async def test_what_is_sent_to_an_address_waits_until_the_account_confirms_it(client, db):
    owner, pid, _oh = await _allocation_waiting(client, db, "omar@fam.io")

    # someone opens an account with that address and has THEIR identity verified
    account, ah = await _user(client, db, "omar@fam.io", "Someone", kyc=False)
    await _identity_verified(account)
    assert (_holding(db, account, pid), _balance(db, account)) == (0, 0)
    assert (_holding(db, owner, pid), _balance(db, owner)) == (10, 300)
    assert _linked(db, "omar@fam.io") is None
    # ...and is told what is left to do, whether or not anything waits
    told = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title='Identity verified'",
        u=account,
    )[0][0]
    assert "confirm your email address" in told

    # the confirmation link works from inside the account only
    token = await _link_token(account, "verify")
    r = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 401
    _other, xh = await _user(client, db, "stranger@fam.io")
    r = await client.post("/api/v1/auth/verify-email", json={"token": token}, headers=xh)
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_YOUR_LINK"
    assert db("SELECT email_verified FROM users WHERE id=:i", i=account)[0][0] is False
    assert _holding(db, account, pid) == 0

    # ...and from there, what was sent to the address is the account's
    r = await client.post("/api/v1/auth/verify-email", json={"token": token}, headers=ah)
    assert r.status_code == 204, r.text
    assert db("SELECT email_verified FROM users WHERE id=:i", i=account)[0][0] is True
    assert (_holding(db, account, pid), _balance(db, account)) == (4, 50)
    assert (_holding(db, owner, pid), _balance(db, owner)) == (6, 250)
    assert str(_linked(db, "omar@fam.io")) == account
    assert "Units from a family member are in your account" in [
        r[0] for r in db("SELECT title FROM notifications WHERE user_id=:u", u=account)
    ]
    # the link is used: a second confirmation moves nothing more
    r = await client.post("/api/v1/auth/verify-email", json={"token": token}, headers=ah)
    assert r.status_code == 400
    assert (_holding(db, account, pid), _balance(db, account)) == (4, 50)


@pytest.mark.asyncio
async def test_a_confirmed_account_receives_when_its_identity_is_verified(client, db):
    owner, pid, _oh = await _allocation_waiting(client, db, "omar2@fam.io")
    account, _ah = await _user(client, db, "omar2@fam.io", "Omar", kyc=False, confirmed=True)
    assert _holding(db, account, pid) == 0  # identity not verified yet
    await _identity_verified(account)
    assert (_holding(db, account, pid), _balance(db, account)) == (4, 50)
    assert (_holding(db, owner, pid), _balance(db, owner)) == (6, 250)
    told = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title='Identity verified'",
        u=account,
    )[0][0]
    assert told == "Your identity has been verified. You're all set."


@pytest.mark.asyncio
async def test_a_password_reset_takes_an_account_back_and_confirms_the_address(client, db):
    owner, pid, _oh = await _allocation_waiting(client, db, "omar3@fam.io")
    # opened by someone else, who verified their own identity in it
    account, ah = await _user(client, db, "omar3@fam.io", "Someone")
    assert _holding(db, account, pid) == 0

    # the person the mailbox belongs to asks for a new password: the link reaches them alone
    token = await _link_token(account, "reset")
    r = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "TheirOwn!Pass9"}
    )
    assert r.status_code == 204, r.text
    # whoever opened it is out: the old password and the open sessions are gone
    client.cookies.clear()
    r = await client.post("/api/v1/auth/login", json={"email": "omar3@fam.io", "password": PW})
    assert r.status_code == 401
    assert (
        db(
            "SELECT count(*) FROM refresh_tokens WHERE user_id=:u AND revoked_at IS NULL", u=account
        )[0][0]
        == 0
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": "omar3@fam.io", "password": "TheirOwn!Pass9"}
    )
    assert r.status_code == 200, r.text
    # ...and the address is confirmed: what was sent to it is in the account
    assert db("SELECT email_verified FROM users WHERE id=:i", i=account)[0][0] is True
    assert (_holding(db, account, pid), _balance(db, account)) == (4, 50)
    assert (_holding(db, owner, pid), _balance(db, owner)) == (6, 250)
    _ = ah


@pytest.mark.asyncio
async def test_adding_a_relative_links_only_an_account_that_confirmed_the_address(client, db):
    owner, oh = await _user(client, db, "ahmed4@fam.io", "Ahmed", confirmed=True)
    never, _nh = await _user(client, db, "never@fam.io", "Never Confirmed")
    did, _dh = await _user(client, db, "did@fam.io", "Did Confirm", confirmed=True)
    await client.post("/api/v1/family/groups", json={"name": "Family"}, headers=oh)

    for name, address in (("Never", "never@fam.io"), ("Did", "did@fam.io")):
        r = await client.post(
            "/api/v1/family/members",
            json={"name": name, "relationship": "Son", "email": address},
            headers=oh,
        )
        assert r.status_code == 200, r.text
    assert _linked(db, "never@fam.io") is None
    assert str(_linked(db, "did@fam.io")) == did
    # the first is written to at the address, like a relative with no account; the second
    # is told in their account
    mail = db("SELECT body FROM email_outbox WHERE to_email='never@fam.io' AND user_id IS NULL")
    assert len(mail) == 1 and "confirm the address" in mail[0][0]
    assert db("SELECT count(*) FROM notifications WHERE user_id=:u", u=never)[0][0] == 0
    assert "You were added to a family group" in [
        r[0] for r in db("SELECT title FROM notifications WHERE user_id=:u", u=did)
    ]
    _ = owner


@pytest.mark.asyncio
async def test_a_gift_to_an_address_waits_for_the_confirmation_too(client, db, asession):
    from app.services import gift_service

    giver, gh = await _user(client, db, "giver@fam.io", "Giver", confirmed=True)
    _fund(db, giver, 500)
    r = await client.post(
        "/api/v1/gifts",
        json={
            "recipient_name": "Future",
            "recipient_email": "future@fam.io",
            "asset_type": "wallet",
            "amount": "200.00",
            "scheduled_for": (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1)).isoformat(),
        },
        headers={**gh, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code in (200, 201), r.text
    await gift_service.run_due(asession, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=1))
    await asession.commit()
    assert _balance(db, giver) == 300  # held for a recipient who cannot receive yet

    account, ah = await _user(client, db, "future@fam.io", "Someone", kyc=False)
    await _identity_verified(account)
    assert _balance(db, account) == 0

    token = await _link_token(account, "verify")
    r = await client.post("/api/v1/auth/verify-email", json={"token": token}, headers=ah)
    assert r.status_code == 204, r.text
    assert (_balance(db, account), _balance(db, giver)) == (200, 300)


@pytest.mark.asyncio
async def test_a_provider_sign_in_confirms_the_address_and_removes_the_unproven_password(
    client, db, monkeypatch
):
    owner, pid, _oh = await _allocation_waiting(client, db, "omar5@fam.io")
    account, _ah = await _user(client, db, "omar5@fam.io", "Someone")

    async def exchange(provider, code, redirect_uri):
        return oauth.OAuthProfile(subject="g-omar", email="omar5@fam.io", full_name="Omar")

    monkeypatch.setattr(oauth, "exchange", exchange)
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/oauth/google", json={"code": "c", "redirect_uri": "https://x/cb"}
    )
    assert r.status_code == 200 and r.json()["access_token"], r.text
    row = db("SELECT password_hash, email_verified FROM users WHERE id=:i", i=account)[0]
    assert row[0] is None and row[1] is True
    r = await client.post("/api/v1/auth/login", json={"email": "omar5@fam.io", "password": PW})
    assert r.status_code == 401
    # one session is open: the one the provider just proved
    assert (
        db(
            "SELECT count(*) FROM refresh_tokens WHERE user_id=:u AND revoked_at IS NULL", u=account
        )[0][0]
        == 1
    )
    assert (_holding(db, account, pid), _holding(db, owner, pid)) == (4, 6)


def test_a_provider_must_say_it_verified_the_address():
    for good in (True, "true", "True"):
        oauth._require_verified("Google", good)
    for bad in (False, "false", None, "", 0):
        with pytest.raises(AppError) as exc:
            oauth._require_verified("Google", bad)
        assert exc.value.code == "OAUTH_EMAIL_UNVERIFIED"


# --- open or closed ------------------------------------------------------------------ #
async def _staff(client, db, email: str = "staff@adm.io") -> str:
    uid, _h = await _user(client, db, email, "Staff Admin", confirmed=True)
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin') ON CONFLICT DO NOTHING", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert r.status_code in (200, 302, 303)
    return uid


@pytest.mark.asyncio
async def test_a_closed_account_cannot_sign_in_or_act_and_staff_reopen_it(client, db):
    member, mh = await _user(client, db, "member@acc.io", "Member", confirmed=True)
    pid = _property(db)
    _grant(db, member, pid, 5)
    _fund(db, member, 120)
    client.cookies.clear()
    r = await client.post("/api/v1/auth/login", json={"email": "member@acc.io", "password": PW})
    assert r.status_code == 200
    refresh = dict(client.cookies)
    client.cookies.clear()

    staff = await _staff(client, db)
    # nobody closes the account they are signed in with
    await client.get(f"/admin/user/action/close-account?pks={staff}")
    assert db("SELECT closed_at FROM users WHERE id=:i", i=staff)[0][0] is None

    r = await client.get(f"/admin/user/action/close-account?pks={member}", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    row = db("SELECT closed_at, closed_reason, closed_by FROM users WHERE id=:i", i=member)[0]
    assert row[0] is not None and row[1] == "closed by our team" and str(row[2]) == staff
    audit = db("SELECT actor_id, after FROM audit_log WHERE action='account.closed'")[0]
    assert str(audit[0]) == staff and audit[1]["reason"] == "closed by our team"
    # the holder is told at their address: someone who is there to read it can object
    mail = db(
        "SELECT subject, body FROM email_outbox WHERE user_id=:u ORDER BY created_at DESC", u=member
    )[0]
    assert mail[0] == "Your account was closed" and "contact support now" in mail[1]

    # no way in: the password, an open session, a new password
    client.cookies.clear()
    r = await client.post("/api/v1/auth/login", json={"email": "member@acc.io", "password": PW})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_CLOSED"
    r = await client.post(
        "/api/v1/auth/login", json={"email": "member@acc.io", "password": "wrong-password"}
    )
    assert r.status_code == 401  # only someone who knows the password learns it is closed
    r = await client.post("/api/v1/auth/refresh", cookies=refresh)
    assert r.status_code in (401, 403)
    token = await _link_token(member, "reset")
    r = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "Another!Pass9"}
    )
    assert r.status_code == 204
    r = await client.post(
        "/api/v1/auth/login", json={"email": "member@acc.io", "password": "Another!Pass9"}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_CLOSED"

    # a token minted before the closing: it still reads, it does nothing with money
    assert (await client.get("/api/v1/auth/me", headers=mh)).status_code == 200
    r = await client.post("/api/v1/family/materialize", headers=mh)
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_CLOSED"
    r = await client.post("/api/v1/family/groups", json={"name": "Mine"}, headers=mh)
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_CLOSED"
    # nothing it holds was touched
    assert (_holding(db, member, pid), _balance(db, member)) == (5, 120)

    # staff reopen it: its holder signs in again
    await _staff(client, db, "staff2@adm.io")
    # the list says which accounts are closed; the edit form cannot type the closing in
    listing = await client.get("/admin/user/list")
    assert listing.status_code == 200 and "Closed on" in listing.text
    form = await client.get(f"/admin/user/edit/{member}")
    assert form.status_code == 200 and 'name="email_verified"' in form.text
    assert 'name="closed_at"' not in form.text and 'name="closed_reason"' not in form.text
    r = await client.get(f"/admin/user/action/reopen-account?pks={member}", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert db("SELECT closed_at, closed_reason FROM users WHERE id=:i", i=member)[0] == (None, None)
    assert db("SELECT count(*) FROM audit_log WHERE action='account.reopened'")[0][0] == 1
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/login", json={"email": "member@acc.io", "password": "Another!Pass9"}
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_nothing_is_sent_into_a_closed_account_or_handed_to_one(client, db, asession):
    from app.services import account_service

    # a holder allocated units and returns to a relative known by address; the relative's
    # account (address confirmed) is closed before its identity is verified
    owner, pid, oh = await _allocation_waiting(client, db, "omar6@fam.io")
    account, _ah = await _user(client, db, "omar6@fam.io", "Omar", kyc=False, confirmed=True)
    await account_service.close(
        asession, user_id=uuid.UUID(account), reason="closed by our team", actor_id=None
    )
    await asession.commit()
    await _identity_verified(account)
    assert (_holding(db, account, pid), _balance(db, account)) == (0, 0)
    assert (_holding(db, owner, pid), _balance(db, owner)) == (10, 300)

    # reopened, what waited is handed over the next time its identity is confirmed
    await account_service.reopen(asession, user_id=uuid.UUID(account), actor_id=None)
    await asession.commit()
    await _identity_verified(account)
    assert (_holding(db, account, pid), _balance(db, account)) == (4, 50)

    # a member whose account is closed is sent nothing more
    await account_service.close(
        asession, user_id=uuid.UUID(account), reason="closed by our team", actor_id=None
    )
    await asession.commit()
    group = (await client.get("/api/v1/family/groups/me", headers=oh)).json()
    me = next(m["member_id"] for m in group["members"] if m["relationship"] == "Self (Owner)")
    member = next(m["member_id"] for m in group["members"] if m["relationship"] == "Son")
    r = await client.post(
        "/api/v1/family/transfers",
        json={"from_member_id": me, "to_member_id": member, "property_id": pid, "units": 1},
        headers={**oh, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACCOUNT_CLOSED", r.text
    assert "account is closed" in r.json()["error"]["message"]
    r = await client.post(
        "/api/v1/family/allocations",
        json={"member_id": member, "amount": 10},
        headers={**oh, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACCOUNT_CLOSED", r.text
    assert (_holding(db, account, pid), _balance(db, account)) == (4, 50)


@pytest.mark.asyncio
async def test_closing_an_account_is_for_full_admins(client, db):
    member, mh = await _user(client, db, "plain@acc.io", "Member", confirmed=True)
    other, _oh = await _user(client, db, "other@acc.io", "Other", confirmed=True)
    r = await client.get(f"/admin/user/action/close-account?pks={other}", follow_redirects=False)
    assert r.status_code in (302, 303, 307, 401, 403)
    r = await client.get(
        f"/admin/user/action/close-account?pks={other}", headers=mh, follow_redirects=False
    )
    assert db("SELECT closed_at FROM users WHERE id=:i", i=other)[0][0] is None
    _ = member


@pytest.mark.asyncio
async def test_a_closed_accounts_installments_are_left_alone(client, db, asession):
    from app.services import account_service, installment_service

    member, mh = await _user(client, db, "plan@acc.io", "Member", confirmed=True)
    db("UPDATE wallets SET balance=100000 WHERE user_id=:u", u=member)
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Tower','Dubai','residential','installment','active',10000,100,100,100,100)",
        id=pid,
    )
    r = await client.post(
        "/api/v1/installments",
        json={"property_id": pid, "amount": 1200, "duration_months": 12},
        headers={**mh, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code in (200, 201), r.text
    after_down_payment = _balance(db, member)

    await account_service.close(
        asession, user_id=uuid.UUID(member), reason="closed by our team", actor_id=None
    )
    await asession.commit()
    before = db(
        "SELECT count(*) FROM notifications WHERE user_id=:u AND type='installment'", u=member
    )[0][0]
    # a year on, everything is due: nothing is charged to the closed account, and it is
    # not reminded
    res = await installment_service.run_due(
        asession, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=32 * 13)
    )
    await asession.commit()
    assert (res["paid"], res["overdue"], res["reminders_sent"]) == (0, 0, 0)
    assert _balance(db, member) == after_down_payment
    assert (
        db("SELECT count(*) FROM notifications WHERE user_id=:u AND type='installment'", u=member)[
            0
        ][0]
        == before
    )

    # reopened, the plan runs again
    await account_service.reopen(asession, user_id=uuid.UUID(member), actor_id=None)
    await asession.commit()
    res = await installment_service.run_due(
        asession, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=32 * 13)
    )
    await asession.commit()
    assert res["paid"] == 11
