"""A family action leaves a trace (client, 2026-10-07): "it does the whole job but has no
traces: no email, no notification in the application, nothing on the investments page,
nothing on the family page, and the receiver does not see that it came to him".

* adding a member and transferring to one tell BOTH sides, in their notifications and by
  email (an outsider gets the email alone);
* the family page reads what happened back from the tables: the owner's transfer history
  with names, property and dates, and an activity feed that also serves a member who was
  only ever on the receiving side;
* the investments page lists every unit movement with the other person named.

And what reading that code found:
* a transfer moves the caller's own units only (an owner could pick any member as sender);
* money already paid to a verified member is not paid a second time when their allocations
  are released; what a pending member is owed is released once;
* a group's page shows a member the units that reached them through the group, not their
  whole portfolio.
"""

from __future__ import annotations

import uuid

import pytest

PW = "Passw0rd!23"


# --- arrange helpers -------------------------------------------------------- #
async def _user(
    client, db, email: str, name: str, *, verified: bool = True, confirmed: bool = True
) -> tuple[str, dict]:
    """An account: its identity verified, and its email address confirmed (as after a real
    sign-up; only then is anything sent to the address tied to the account)."""
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": name}
    )
    assert r.status_code == 201, r.text
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    if verified:
        db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    if confirmed:
        db("UPDATE users SET email_verified=true WHERE id=:i", i=uid)
    return uid, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _property(db, title: str = "Marina Heights") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,:t,'Dubai','residential','ready-income','active',100000,100,1000,1000,100)",
        id=pid,
        t=title,
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
        "INSERT INTO transactions (user_id, type, amount, status) "
        "VALUES (:u,'deposit',:a,'completed')",
        u=uid,
        a=amount,
    )
    db("UPDATE wallets SET balance=:a WHERE user_id=:u", a=amount, u=uid)


def _balance(db, uid: str):
    return db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]


def _holding(db, uid: str, pid: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger "
            "WHERE user_id=:u AND property_id=:p",
            u=uid,
            p=pid,
        )[0][0]
    )


def _titles(db, uid: str) -> list[str]:
    rows = db("SELECT title FROM notifications WHERE user_id=:u ORDER BY created_at, title", u=uid)
    return [r[0] for r in rows]


def _mail(db, to: str) -> list[tuple[str, str]]:
    return [
        (r[0], r[1])
        for r in db(
            "SELECT subject, body FROM email_outbox WHERE to_email=:t ORDER BY created_at", t=to
        )
    ]


async def _group(client, h) -> dict:
    r = await client.post("/api/v1/family/groups", json={"name": "The Mansouris"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def _add(client, h, name: str, email: str | None, relationship: str = "Son") -> dict:
    body = {"name": name, "relationship": relationship}
    if email:
        body["email"] = email
    r = await client.post("/api/v1/family/members", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _self(group: dict) -> str:
    return next(m["member_id"] for m in group["members"] if m["relationship"] == "Self (Owner)")


async def _transfer(client, h, frm: str, to: str, pid: str, units: int):
    return await client.post(
        "/api/v1/family/transfers",
        json={"from_member_id": frm, "to_member_id": to, "property_id": pid, "units": units},
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
    )


# --- adding a member ---------------------------------------------------------- #
@pytest.mark.asyncio
async def test_adding_a_member_tells_both_sides(client, db):
    owner, oh = await _user(client, db, "ahmed@fam.io", "Ahmed Mansouri")
    son, _sh = await _user(client, db, "omar@fam.io", "Omar Mansouri")
    await _group(client, oh)

    # a member who already has a verified account: until now nobody was told anything
    await _add(client, oh, "Omar", "omar@fam.io")
    assert "Family member added" in _titles(db, owner)
    assert "You were added to a family group" in _titles(db, son)
    told = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title LIKE 'You were added%'",
        u=son,
    )[0][0]
    assert "Ahmed Mansouri" in told and "as Son" in told
    # both get the email too (the member's own, by their preferences: on by default)
    assert [s for s, _b in _mail(db, "ahmed@fam.io")] == ["Family member added"]
    subject, body = _mail(db, "omar@fam.io")[0]
    assert subject == "You were added to a family group" and "/dashboard?tab=family" in body

    # someone with no account: an email to the address the owner typed, with how to join
    await _add(client, oh, "Sara", "sara@outside.io", "Daughter")
    subject, body = _mail(db, "sara@outside.io")[0]
    assert subject == "You were added to a family group"
    assert "Hello Sara" in body and "Ahmed Mansouri" in body and "/auth" in body
    owner_told = db(
        "SELECT message FROM notifications WHERE user_id=:u AND message LIKE 'You added Sara%'",
        u=owner,
    )[0][0]
    assert "invited by email" in owner_told


@pytest.mark.asyncio
async def test_a_typed_name_never_becomes_a_link_in_our_email(client, db):
    _owner, oh = await _user(client, db, "link@fam.io", "Ahmed Mansouri")
    await _group(client, oh)
    await _add(client, oh, "Win now http://evil.example/claim <b>", "victim@outside.io")
    _subject, body = _mail(db, "victim@outside.io")[0]
    assert "evil.example" not in body and "<b>" not in body


# --- a transfer ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_a_transfer_tells_both_sides_and_shows_on_both_accounts(client, db):
    owner, oh = await _user(client, db, "ahmed2@fam.io", "Ahmed Mansouri")
    son, sh = await _user(client, db, "omar2@fam.io", "Omar Mansouri")
    pid = _property(db)
    _grant(db, owner, pid, 50)
    group = await _group(client, oh)
    member = await _add(client, oh, "Omar", "omar2@fam.io")

    r = await _transfer(client, oh, _self(group), member["member_id"], pid, 10)
    assert r.status_code == 200 and r.json()["status"] == "completed", r.text

    # 1) notifications and emails, both sides
    assert "Units transferred to a family member" in _titles(db, owner)
    sent = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title LIKE 'Units transferred%'",
        u=owner,
    )[0][0]
    assert sent == (
        "You transferred 10 units of Marina Heights to Omar. They are in their account now."
    )
    got = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title LIKE 'You received units%'",
        u=son,
    )[0][0]
    assert got == (
        "Ahmed Mansouri transferred 10 units of Marina Heights to you. "
        "They are in your account now."
    )
    assert "Units transferred to a family member" in [s for s, _b in _mail(db, "ahmed2@fam.io")]
    received = [b for s, b in _mail(db, "omar2@fam.io") if s.startswith("You received units")]
    assert len(received) == 1 and "/dashboard?tab=investments" in received[0]

    # 2) the owner's transfer history: who, what, when
    history = (await client.get("/api/v1/family/transfers", headers=oh)).json()["items"]
    assert len(history) == 1
    line = history[0]
    assert (line["from_name"], line["to_name"]) == ("Account Owner", "Omar")
    assert line["property_title"] == "Marina Heights" and line["units"] == 10
    assert line["created_at"] and line["completed_at"]

    # 3) the activity feed, each from their own side
    mine = (await client.get("/api/v1/family/activity", headers=oh)).json()
    sent_line = next(i for i in mine["items"] if i["kind"] == "transfer")
    assert (sent_line["direction"], sent_line["counterparty"]) == ("out", "Omar")
    assert sent_line["property_title"] == "Marina Heights" and sent_line["status"] == "completed"
    assert any(i["kind"] == "member" and i["counterparty"] == "Omar" for i in mine["items"])
    assert mine["memberships"] == []

    # the receiver has no group of their own: this is where they see what came to them
    theirs = (await client.get("/api/v1/family/activity", headers=sh)).json()
    got_line = next(i for i in theirs["items"] if i["kind"] == "transfer")
    assert (got_line["direction"], got_line["counterparty"]) == ("in", "Ahmed Mansouri")
    assert got_line["units"] == 10 and got_line["property_title"] == "Marina Heights"
    assert [m["owner_name"] for m in theirs["memberships"]] == ["Ahmed Mansouri"]
    assert theirs["memberships"][0]["relationship"] == "Son"
    assert (await client.get("/api/v1/family/groups/me", headers=sh)).json() is None

    # 4) the investments page: the movement, with the other person named
    out = (await client.get("/api/v1/investments/movements", headers=oh)).json()["items"]
    assert [(m["units"], m["label"], m["counterparty"]) for m in out] == [
        (-10, "Transferred to a family member", "Omar"),
        (50, "Purchase", None),
    ]
    into = (await client.get("/api/v1/investments/movements", headers=sh)).json()["items"]
    assert [(m["units"], m["label"], m["counterparty"], m["property_title"]) for m in into] == [
        (10, "Received from a family member", "Ahmed Mansouri", "Marina Heights")
    ]
    # the two ledger rows point at their transfer
    assert (
        db("SELECT count(*) FROM ownership_ledger WHERE ref_id=:t", t=line["transfer_id"])[0][0]
        == 2
    )


@pytest.mark.asyncio
async def test_a_pending_allocation_tells_both_sides_then_moves_on_verification(client, db):
    owner, oh = await _user(client, db, "ahmed3@fam.io", "Ahmed Mansouri")
    pid = _property(db)
    _grant(db, owner, pid, 20)
    group = await _group(client, oh)
    member = await _add(client, oh, "Sara", "sara3@fam.io", "Daughter")

    r = await _transfer(client, oh, _self(group), member["member_id"], pid, 8)
    assert r.json()["status"] == "pending"
    assert "Units allocated to a family member" in _titles(db, owner)
    waiting = [b for s, b in _mail(db, "sara3@fam.io") if s == "Units are waiting for you"]
    assert len(waiting) == 1 and "Ahmed Mansouri allocated 8 units of Marina Heights" in waiting[0]
    assert _holding(db, owner, pid) == 20  # nothing moved yet

    # she registers, verifies, and her allocation becomes real: both sides are told
    sara, sh = await _user(client, db, "sara3@fam.io", "Sara Mansouri")
    done = await client.post("/api/v1/family/materialize", headers=sh)
    assert done.json()["materialized"] == 1
    assert (_holding(db, owner, pid), _holding(db, sara, pid)) == (12, 8)
    assert "Units from a family member are in your account" in _titles(db, sara)
    assert "A family allocation was completed" in _titles(db, owner)
    into = (await client.get("/api/v1/investments/movements", headers=sh)).json()["items"]
    assert [(m["units"], m["counterparty"]) for m in into] == [(8, "Ahmed Mansouri")]
    feed = (await client.get("/api/v1/family/activity", headers=sh)).json()["items"]
    line = next(i for i in feed if i["kind"] == "transfer")
    assert (line["direction"], line["status"]) == ("in", "completed") and line["completed_at"]


@pytest.mark.asyncio
async def test_cancelling_an_allocation_tells_both_sides(client, db):
    owner, oh = await _user(client, db, "ahmed4@fam.io", "Ahmed Mansouri")
    pid = _property(db)
    _grant(db, owner, pid, 20)
    group = await _group(client, oh)
    member = await _add(client, oh, "Sara", "sara4@fam.io", "Daughter")
    tid = (await _transfer(client, oh, _self(group), member["member_id"], pid, 8)).json()[
        "transfer_id"
    ]
    r = await client.post(f"/api/v1/family/transfers/{tid}/cancel", headers=oh)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert "Family allocation cancelled" in _titles(db, owner)
    cancelled = [b for s, b in _mail(db, "sara4@fam.io") if "cancelled" in s]
    # she is told it was cancelled, and is not asked to register for something that is gone
    assert len(cancelled) == 1 and "/auth" not in cancelled[0]
    feed = (await client.get("/api/v1/family/activity", headers=oh)).json()["items"]
    assert next(i for i in feed if i["kind"] == "transfer")["status"] == "cancelled"


# --- whose units ----------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_only_your_own_units_can_be_transferred(client, db):
    # A group's owner adds members by their email address, with no say from them. The sender
    # of a transfer used to be any verified member of the group: an investor could add
    # another investor's address and move that investor's units to themselves.
    thief, th = await _user(client, db, "thief@fam.io", "Thief")
    victim, _vh = await _user(client, db, "victim@fam.io", "Victim Investor")
    pid = _property(db)
    _grant(db, victim, pid, 40)
    group = await _group(client, th)
    added = await _add(client, th, "My brother", "victim@fam.io", "Sibling")

    r = await _transfer(client, th, added["member_id"], _self(group), pid, 40)
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_YOUR_UNITS", r.text
    assert (_holding(db, victim, pid), _holding(db, thief, pid)) == (40, 0)
    assert db("SELECT count(*) FROM family_transfers")[0][0] == 0


@pytest.mark.asyncio
async def test_a_member_is_shown_what_reached_them_through_the_group_only(client, db):
    # ...and the same owner could read how many units that investor holds everywhere.
    owner, oh = await _user(client, db, "ahmed5@fam.io", "Ahmed Mansouri")
    other, _h = await _user(client, db, "rich@fam.io", "Rich Investor")
    mine, theirs = _property(db, "Marina Heights"), _property(db, "Palm Court")
    _grant(db, owner, mine, 30)
    _grant(db, other, theirs, 500)
    group = await _group(client, oh)
    added = await _add(client, oh, "Rich", "rich@fam.io", "Sibling")

    def units(view: dict, member_id: str) -> int:
        return next(m["real_units"] for m in view["members"] if m["member_id"] == member_id)

    view = (await client.get("/api/v1/family/groups/me", headers=oh)).json()
    assert units(view, added["member_id"]) == 0  # not their 500 units
    assert units(view, _self(group)) == 30  # the owner's own holding, as before

    moved = await _transfer(client, oh, _self(group), added["member_id"], mine, 5)
    assert moved.status_code == 200
    view = (await client.get("/api/v1/family/groups/me", headers=oh)).json()
    assert units(view, added["member_id"]) == 5 and units(view, _self(group)) == 25


# --- returns ----------------------------------------------------------------------- #
async def _allocate(client, h, member_id: str, amount: float):
    return await client.post(
        "/api/v1/family/allocations",
        json={"member_id": member_id, "amount": amount},
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
    )


@pytest.mark.asyncio
async def test_returns_paid_to_a_verified_member_are_not_paid_twice(client, db):
    # The amount paid at once was also counted as "to release when they verify": releasing
    # a verified member's allocations again (their own button, or a repeated verification
    # event) took the same money from the owner's wallet a second time.
    owner, oh = await _user(client, db, "ahmed6@fam.io", "Ahmed Mansouri")
    son, sh = await _user(client, db, "omar6@fam.io", "Omar Mansouri")
    _fund(db, owner, 1000)
    await _group(client, oh)
    member = await _add(client, oh, "Omar", "omar6@fam.io")

    r = await _allocate(client, oh, member["member_id"], 300)
    assert r.status_code == 200 and r.json()["real"] is True
    assert (_balance(db, owner), _balance(db, son)) == (700, 300)
    assert "Returns sent to a family member" in _titles(db, owner)
    assert "You received money from a family member" in _titles(db, son)

    for _ in range(2):
        assert (await client.post("/api/v1/family/materialize", headers=sh)).status_code == 200
    assert (_balance(db, owner), _balance(db, son)) == (700, 300)  # paid once
    row = db(
        "SELECT allocated_returns, pending_returns FROM family_members WHERE id=:i",
        i=member["member_id"],
    )[0]
    assert (row[0], row[1]) == (300, 0)  # the running total stays what the page shows

    feed = (await client.get("/api/v1/family/activity", headers=sh)).json()["items"]
    line = next(i for i in feed if i["kind"] == "returns")
    assert (line["direction"], line["amount"], line["counterparty"]) == (
        "in",
        "300.00",
        "Ahmed Mansouri",
    )


@pytest.mark.asyncio
async def test_what_a_pending_member_is_owed_is_released_once_when_they_verify(client, db):
    owner, oh = await _user(client, db, "ahmed7@fam.io", "Ahmed Mansouri")
    _fund(db, owner, 100)
    await _group(client, oh)
    member = await _add(client, oh, "Sara", "sara7@fam.io", "Daughter")

    r = await _allocate(client, oh, member["member_id"], 250)
    assert r.json()["real"] is False
    assert _balance(db, owner) == 100  # recorded only: nothing left the wallet
    assert [s for s, _b in _mail(db, "sara7@fam.io")][-1] == "Money is waiting for you"

    # she verifies while the owner's wallet cannot cover it: her verification is not
    # broken by that, nothing moves, and the owner is told
    sara, sh = await _user(client, db, "sara7@fam.io", "Sara Mansouri")
    assert (await client.post("/api/v1/family/materialize", headers=sh)).status_code == 200
    assert (_balance(db, owner), _balance(db, sara)) == (100, 0)
    assert "Family returns could not be released" in _titles(db, owner)

    # with the money there it is released, once
    _fund(db, owner, 400)
    for _ in range(2):
        assert (await client.post("/api/v1/family/materialize", headers=sh)).status_code == 200
    assert (_balance(db, owner), _balance(db, sara)) == (150, 250)
    assert "Family returns are in your wallet" in _titles(db, sara)
    assert "Family returns were released" in _titles(db, owner)
    view = (await client.get("/api/v1/family/groups/me", headers=oh)).json()
    row = next(m for m in view["members"] if m["member_id"] == member["member_id"])
    assert (row["allocated_returns"], row["pending_returns"]) == ("250.00", "0")


# --- gates ----------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_traces_are_each_members_own(client, db):
    assert (await client.get("/api/v1/family/activity")).status_code == 401
    assert (await client.get("/api/v1/investments/movements")).status_code == 401

    owner, oh = await _user(client, db, "ahmed8@fam.io", "Ahmed Mansouri")
    _son, _sh = await _user(client, db, "omar8@fam.io", "Omar Mansouri")
    _stranger, xh = await _user(client, db, "stranger@fam.io", "A Stranger")
    pid = _property(db)
    _grant(db, owner, pid, 10)
    group = await _group(client, oh)
    member = await _add(client, oh, "Omar", "omar8@fam.io")
    await _transfer(client, oh, _self(group), member["member_id"], pid, 4)

    feed = (await client.get("/api/v1/family/activity", headers=xh)).json()
    assert feed == {"items": [], "memberships": []}
    assert (await client.get("/api/v1/investments/movements", headers=xh)).json()["total"] == 0
