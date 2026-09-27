"""Broker "Listings & Referrals" (client feedback #2).

* a broker invites a client by email: the invitation carries the broker's share link, and the
  client joins the broker's clients only by signing up through it (password or Google) — the
  signed-off signup-only attribution rule is unchanged, existing accounts are never linked;
* a broker introduces a property / project with the owner contact and documents; staff are
  told, review it in Broker Leads, mark it contacted, decline it with a message, or create
  the listing from it in the Listing Editor — which marks the lead "listed";
* the broker's table lists everything with its status, never a storage key.
"""

# ruff: noqa: E501
from __future__ import annotations

import json

import pytest

from app.core.config import get_settings
from app.services import broker_lead_service
from app.services.integrations import oauth

PW = "Passw0rd!23"


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "storage_provider", "local", raising=False)
    monkeypatch.setattr(s, "storage_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(s, "support_inbox_email", "support@t.io", raising=False)
    yield


async def _account(
    client, db, email: str, *, role: str | None = None, name="Nour Broker"
) -> tuple[str, dict]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": name}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    if role:
        db(
            "INSERT INTO user_roles (user_id, role) VALUES (:i,:r) ON CONFLICT DO NOTHING",
            i=uid,
            r=role,
        )
        db("UPDATE users SET active_role=:r WHERE id=:i", r=role, i=uid)
    tok = (await client.post("/api/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]
    return str(uid), {"Authorization": f"Bearer {tok}"}


def _code(db, broker_id: str) -> str:
    return db("SELECT code FROM broker_codes WHERE broker_id=:b", b=broker_id)[0][0]


@pytest.mark.asyncio
async def test_invited_client_joins_only_through_the_brokers_link(client, db):
    bid, bh = await _account(client, db, "nour@brk.io", role="broker")
    r = await client.post(
        "/api/v1/broker/leads/client",
        json={
            "name": "Omar Client",
            "email": "Omar@Client.io",
            "phone": "+97150",
            "notes": "met at expo",
        },
        headers=bh,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "invited" and r.json()["email"] == "omar@client.io"
    # the invitee gets the broker's share link by email; the broker gets an in-app notice
    mail = db("SELECT subject, body FROM email_outbox WHERE to_email='omar@client.io'")
    assert len(mail) == 1 and "Nour Broker invites you" in mail[0][0]
    assert f"/auth?ref={_code(db, bid)}" in mail[0][1]
    assert (
        db("SELECT count(*) FROM notifications WHERE user_id=:b AND title='Client invited'", b=bid)[
            0
        ][0]
        == 1
    )

    # one pending invitation per address; not yourself; brokers only
    dup = await client.post(
        "/api/v1/broker/leads/client", json={"name": "O", "email": "omar@client.io"}, headers=bh
    )
    assert dup.status_code == 409
    me = await client.post(
        "/api/v1/broker/leads/client", json={"name": "Me", "email": "nour@brk.io"}, headers=bh
    )
    assert me.status_code == 422
    _, ih = await _account(client, db, "inv@brk.io")
    assert (
        await client.post(
            "/api/v1/broker/leads/client", json={"name": "X", "email": "x@y.io"}, headers=ih
        )
    ).status_code == 403

    # signing up through the link links the client and marks the invitation joined
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "omar@client.io",
            "password": PW,
            "full_name": "Omar",
            "referral_code": _code(db, bid),
        },
    )
    assert r.status_code == 201, r.text
    cid = db("SELECT id FROM users WHERE email='omar@client.io'")[0][0]
    assert str(db("SELECT broker_id FROM broker_referrals WHERE client_id=:c", c=cid)[0][0]) == bid
    lead = db(
        "SELECT status, client_id FROM broker_leads WHERE kind='client' AND email='omar@client.io'"
    )[0]
    assert lead[0] == "joined" and str(lead[1]) == str(cid)
    assert (
        db(
            "SELECT count(*) FROM notifications WHERE user_id=:b AND title='Your client joined'",
            b=bid,
        )[0][0]
        == 1
    )
    joined = next(
        i
        for i in (await client.get("/api/v1/broker/leads", headers=bh)).json()["items"]
        if i["kind"] == "client"
    )
    assert joined["status"] == "joined"
    # a joined client can no longer be withdrawn
    assert (
        await client.post(f"/api/v1/broker/leads/{joined['id']}/cancel", headers=bh)
    ).status_code == 409


@pytest.mark.asyncio
async def test_signing_up_without_the_link_links_nobody(client, db):
    bid, bh = await _account(client, db, "nour2@brk.io", role="broker")
    await client.post(
        "/api/v1/broker/leads/client", json={"name": "Sara", "email": "sara@c.io"}, headers=bh
    )
    r = await client.post(
        "/api/v1/auth/register", json={"email": "sara@c.io", "password": PW, "full_name": "Sara"}
    )
    assert r.status_code == 201
    assert db("SELECT count(*) FROM broker_referrals")[0][0] == 0
    assert db("SELECT status FROM broker_leads WHERE email='sara@c.io'")[0][0] == "invited"


@pytest.mark.asyncio
async def test_google_sign_up_through_the_link_is_attributed_too(client, db, monkeypatch):
    bid, bh = await _account(client, db, "nour3@brk.io", role="broker")
    await client.post(
        "/api/v1/broker/leads/client", json={"name": "Lina", "email": "lina@c.io"}, headers=bh
    )

    async def fake_exchange(provider, code, redirect_uri):
        return oauth.OAuthProfile(subject="g-lina", email="lina@c.io", full_name="Lina")

    monkeypatch.setattr(oauth, "exchange", fake_exchange)
    r = await client.post(
        "/api/v1/auth/oauth/google",
        json={"code": "c", "redirect_uri": "https://x/cb", "referral_code": _code(db, bid)},
    )
    assert r.status_code == 200, r.text
    cid = db("SELECT id FROM users WHERE email='lina@c.io'")[0][0]
    assert str(db("SELECT broker_id FROM broker_referrals WHERE client_id=:c", c=cid)[0][0]) == bid
    assert db("SELECT status FROM broker_leads WHERE email='lina@c.io'")[0][0] == "joined"

    # an EXISTING account signing in with Google through a link is never linked afterwards
    await _account(client, db, "old@c.io")

    async def old_exchange(provider, code, redirect_uri):
        return oauth.OAuthProfile(subject="g-old", email="old@c.io", full_name="Old")

    monkeypatch.setattr(oauth, "exchange", old_exchange)
    r = await client.post(
        "/api/v1/auth/oauth/google",
        json={"code": "c", "redirect_uri": "https://x/cb", "referral_code": _code(db, bid)},
    )
    assert r.status_code == 200
    oid = db("SELECT id FROM users WHERE email='old@c.io'")[0][0]
    assert db("SELECT count(*) FROM broker_referrals WHERE client_id=:c", c=oid)[0][0] == 0


@pytest.mark.asyncio
async def test_daily_invitation_cap(client, db, monkeypatch):
    monkeypatch.setattr(broker_lead_service, "INVITES_PER_DAY", 2)
    _, bh = await _account(client, db, "nour4@brk.io", role="broker")
    for i in range(2):
        r = await client.post(
            "/api/v1/broker/leads/client", json={"name": f"C{i}", "email": f"c{i}@c.io"}, headers=bh
        )
        assert r.status_code == 201
    r = await client.post(
        "/api/v1/broker/leads/client", json={"name": "C9", "email": "c9@c.io"}, headers=bh
    )
    assert r.status_code == 429 and r.json()["error"]["code"] == "INVITE_LIMIT"


async def _introduce(client, bh, kind="property", **over) -> dict:
    fields = {
        "title": "Palm Villa 12",
        "location": "Palm Jumeirah, Dubai",
        "property_type": "villa",
        "estimated_value": "4,500,000",
        "owner_name": "Khaled Owner",
        "owner_email": "khaled@owner.io",
        "owner_phone": "+971555",
        "notes": "Owner wants to sell 40%.",
        **over,
    }
    r = await client.post(
        "/api/v1/broker/leads/listing",
        data={"kind": kind, "fields": json.dumps(fields)},
        files=[("files", ("title-deed.pdf", b"%PDF-1.4 deed", "application/pdf"))],
        headers=bh,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_broker_introduces_a_property_and_staff_are_told(client, db):
    admin_id, _ = await _account(client, db, "adm@brk.io", role="admin", name="Admin")
    bid, bh = await _account(client, db, "nour5@brk.io", role="broker")
    lead = await _introduce(client, bh)
    assert lead["status"] == "new" and lead["kind"] == "property"
    assert lead["documents"] == ["title-deed.pdf"]  # names only, never storage keys
    assert "broker-leads/" not in json.dumps(lead)
    assert lead["details"]["owner_name"] == "Khaled Owner" and lead["email"] == "khaled@owner.io"
    assert (
        db(
            "SELECT count(*) FROM notifications WHERE user_id=:a AND title='New property from a broker'",
            a=admin_id,
        )[0][0]
        == 1
    )
    inbox = db("SELECT subject, body FROM email_outbox WHERE to_email='support@t.io'")
    assert len(inbox) == 1 and "Palm Villa 12" in inbox[0][0] and "+971555" in inbox[0][1]
    # it is not a listing: nothing in properties
    assert db("SELECT count(*) FROM properties")[0][0] == 0

    # missing essentials are refused; a project is its own kind
    bad = await client.post(
        "/api/v1/broker/leads/listing",
        data={"kind": "property", "fields": json.dumps({"title": "x"})},
        headers=bh,
    )
    assert bad.status_code == 422
    project = await _introduce(
        client, bh, kind="project", title="Creek Rise", expected_completion="2028-06-30"
    )
    assert project["kind"] == "project"

    # the broker can withdraw one staff has not picked up yet
    r = await client.post(f"/api/v1/broker/leads/{project['id']}/cancel", headers=bh)
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    table = (await client.get("/api/v1/broker/leads", headers=bh)).json()
    assert {i["name"]: i["status"] for i in table["items"]} == {
        "Palm Villa 12": "new",
        "Creek Rise": "withdrawn",
    }


@pytest.mark.asyncio
async def test_staff_review_a_lead_and_list_it_from_the_listing_editor(client, db):
    await _account(client, db, "adm6@brk.io", role="admin", name="Admin")
    r = await client.post("/admin/login", data={"username": "adm6@brk.io", "password": PW})
    assert r.status_code in (200, 302, 303)
    bid, bh = await _account(client, db, "nour6@brk.io", role="broker")
    lead = await _introduce(client, bh)
    lid = lead["id"]

    page = await client.get("/admin/broker-leads")
    assert page.status_code == 200 and "Palm Villa 12" in page.text and "Nour Broker" in page.text
    detail = await client.get(f"/admin/broker-leads/{lid}")
    for text in (
        "Khaled Owner",
        "khaled@owner.io",
        "+971555",
        "title-deed.pdf",
        "Owner wants to sell 40%.",
    ):
        assert text in detail.text
    doc = await client.get(f"/admin/broker-lead-doc?lead={lid}&i=0")
    assert doc.status_code == 200 and doc.content == b"%PDF-1.4 deed"

    # decline needs a message; contacted tells the broker
    r = await client.post(f"/admin/broker-leads/{lid}", data={"action": "decline"})
    assert r.status_code == 400 and "Write why" in r.text
    r = await client.post(
        f"/admin/broker-leads/{lid}", data={"action": "contacted", "note": "Called the owner."}
    )
    assert r.status_code == 303
    assert db("SELECT status, admin_note FROM broker_leads WHERE id=:i", i=lid)[0] == (
        "contacted",
        "Called the owner.",
    )
    msg = db(
        "SELECT message FROM notifications WHERE user_id=:b AND title LIKE 'We are in touch%'",
        b=bid,
    )
    assert "Called the owner." in msg[0][0]

    # the Listing Editor starts from the lead, and creating the listing closes it as "listed"
    new = await client.get(f"/admin/listing/new?lead={lid}&model=ready-income")
    assert new.status_code == 200
    assert 'value="Palm Villa 12"' in new.text and "Filled in from the broker" in new.text
    form = {
        "title": "Palm Villa 12",
        "model": "ready-income",
        "property_type": "villa",
        "location": "Palm Jumeirah, Dubai",
        "total_value": "4500000",
        "unit_price": "100",
        "total_units": "45000",
        "minimum_investment": "500",
        "expected_yield": "6",
        "target_yield": "6",
        "capital_appreciation": "3",
        "total_return": "9",
    }
    r = await client.post(
        f"/admin/listing/new?lead={lid}&model=ready-income", data=form, follow_redirects=False
    )
    assert r.status_code == 303, r.text[:400]
    pid = r.headers["location"].split("/admin/listing/")[1].split("?")[0]
    row = db("SELECT status, property_id FROM broker_leads WHERE id=:i", i=lid)[0]
    assert row[0] == "listed" and str(row[1]) == pid
    assert (
        db(
            "SELECT count(*) FROM notifications WHERE user_id=:b AND title LIKE '%is being listed'",
            b=bid,
        )[0][0]
        == 1
    )
    # a closed lead offers no more decisions
    closed = await client.get(f"/admin/broker-leads/{lid}")
    assert "Mark as contacted" not in closed.text and "Open the listing" in closed.text
