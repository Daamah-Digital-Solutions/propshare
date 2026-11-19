"""Client (2026-11-19): cards are not issued; their section reads "Coming soon · Join the
Waitlist" and a member who clicks it joins the waitlist with the card they want."""

# ruff: noqa: E501
from __future__ import annotations

import pytest

from app.tests.test_installments_db import _h, _user
from app.tests.test_listing_translation_db import _admin


@pytest.mark.asyncio
async def test_a_member_joins_the_waitlist_and_can_change_the_card(client, db):
    tok, uid = await _user(client, db, "card-wait@x.com")
    r = await client.get("/api/v1/cards/waitlist", headers=_h(tok))
    assert r.json() == {"joined": False, "card_type": None, "joined_at": None}

    r = await client.post("/api/v1/cards/waitlist", json={"card_type": "family"}, headers=_h(tok))
    assert r.status_code == 200 and r.json()["joined"] and r.json()["card_type"] == "family"
    told = db("SELECT title FROM notifications WHERE user_id=:u AND type='card_waitlist'", u=uid)
    assert [t[0] for t in told] == ["You're on the card waitlist"]

    # asking again for the same card changes nothing; another card replaces the choice
    await client.post("/api/v1/cards/waitlist", json={"card_type": "family"}, headers=_h(tok))
    r = await client.post("/api/v1/cards/waitlist", json={"card_type": "personal"}, headers=_h(tok))
    assert r.json()["card_type"] == "personal"
    rows = db("SELECT card_type FROM card_waitlist WHERE user_id=:u", u=uid)
    assert rows == [("personal",)]
    assert (
        db("SELECT count(*) FROM notifications WHERE user_id=:u AND type='card_waitlist'", u=uid)[
            0
        ][0]
        == 2
    )

    # an unknown card is refused; signing in is needed
    r = await client.post("/api/v1/cards/waitlist", json={"card_type": "gold"}, headers=_h(tok))
    assert r.status_code == 422
    assert (await client.get("/api/v1/cards/waitlist")).status_code == 401


@pytest.mark.asyncio
async def test_the_admins_see_who_is_waiting(client, db):
    tok, _uid = await _user(client, db, "card-wait-2@x.com")
    await client.post("/api/v1/cards/waitlist", json={"card_type": "broker"}, headers=_h(tok))
    await _admin(client, db)
    page = await client.get("/admin/card-waitlist")
    assert page.status_code == 200
    assert (
        "card-wait-2@x.com" in page.text and "Broker card" in page.text and "1 member" in page.text
    )
