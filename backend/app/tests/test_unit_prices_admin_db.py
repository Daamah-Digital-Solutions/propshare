"""Unit prices in the admin panel (0034): where staff give a property its new price.

What each test protects:
  * the page lists every published listing with its price now, at launch and the change, and
    flags an under-construction listing that has had no new price for over a month;
  * recording a price from the page changes the price everything reads, keeps the history
    with who recorded it, and tells the holders; a mistyped price (a change over 25%) is
    refused until it is confirmed;
  * only a full admin can open it or record a price: a content editor, who edits listings,
    cannot move the value of investors' holdings;
  * the listing editor points to it, stops recomputing the units of a listing investors hold,
    and lets staff choose how an under-construction listing is bought.
"""

# ruff: noqa: E501
from __future__ import annotations

import decimal
import uuid

import pytest

PW = "Passw0rd!23"
D = decimal.Decimal


async def _panel_user(client, db, email: str, role: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Staff"}
    )
    assert r.status_code == 201, r.text
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    db(
        "INSERT INTO user_roles (user_id, role) VALUES (:i,:r) ON CONFLICT DO NOTHING",
        i=uid,
        r=role,
    )
    db("UPDATE users SET active_role=:r WHERE id=:i", i=uid, r=role)
    client.cookies.clear()
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert "session" in client.cookies, r.text[:200]
    return uid


def _listing(db, *, model="installment", status="active", title="Creek Tower", days_old=0) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,slug,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment,expected_yield,"
        "capital_appreciation,total_return,expected_completion,created_at) VALUES "
        "(:id,:t,:s,'Dubai Creek','apartment',:m,:st,100000,100,1000,1000,500,7,3,10,"
        "'2028-06-30', now() - make_interval(days => :d))",
        id=pid,
        t=title,
        s=f"p-{pid[:8]}",
        m=model,
        st=status,
        d=days_old,
    )
    return pid


async def _holder(client, db, pid: str, email: str = "holder@x.io") -> str:
    """An investor holding 10 units (and the pool reduced to match)."""
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Holder"}
    )
    assert r.status_code == 201, r.text
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) "
        "VALUES (:u,:p,10,100,'purchase')",
        u=uid,
        p=pid,
    )
    db("UPDATE properties SET available_units = available_units - 10 WHERE id=:p", p=pid)
    return uid


@pytest.mark.asyncio
async def test_staff_record_a_new_price_and_see_its_history(client, db):
    admin = await _panel_user(client, db, "prices-admin@x.io", "admin")
    due = _listing(db, title="Overdue Tower", days_old=45)  # no price for 45 days
    fresh = _listing(db, title="Fresh Tower", days_old=3)
    ready = _listing(db, title="Ready Flat", model="ready-income", days_old=400)
    _listing(db, title="Draft Tower", status="draft")
    # a sample listing is for show (nobody can buy it): it is listed, never chased
    sample = _listing(db, title="Sample Tower", days_old=90)
    db("UPDATE properties SET content='{\"sample\": true}'::jsonb WHERE id=:p", p=sample)
    holder = await _holder(client, db, due)

    index = await client.get("/admin/unit-prices")
    assert index.status_code == 200
    page = index.text
    assert "1 under-construction listing has had no new price for more than 31 days" in page
    assert page.count("price due") == 1 and "Draft Tower" not in page
    assert "Sample Tower" in page
    # what needs a price comes first; a ready listing is never "due"
    assert page.index("Overdue Tower") < page.index("Fresh Tower") < page.index("Ready Flat")
    assert "Unit prices" in (await client.get("/admin/")).text  # in the sidebar

    detail = await client.get(f"/admin/unit-prices/{due}")
    assert detail.status_code == 200 and "Record a new price" in detail.text
    assert "990 of 1000 units still for sale" in detail.text and "1 investor hold" in detail.text

    r = await client.post(
        f"/admin/unit-prices/{due}",
        data={"price": "103.50", "label": "Phase 2", "note": "Structure completed"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].endswith("?done=1")
    after = (await client.get(r.headers["location"])).text
    assert "Recorded. It is the price of a unit from now on" in after
    assert "$103.50" in after and "+3.50%" in after and "Phase 2" in after
    assert "Structure completed" in after and "launch price" in after
    assert db("SELECT unit_price, minimum_investment FROM properties WHERE id=:p", p=due)[0] == (
        D("103.50"),
        D("517.50"),
    )
    row = db("SELECT previous_price, price, label, created_by FROM property_prices")[0]
    assert (row[0], row[1], row[2], str(row[3])) == (D("100.00"), D("103.50"), "Phase 2", admin)
    audit = db("SELECT actor_id FROM audit_log WHERE action='property.price_recorded'")
    assert [str(a[0]) for a in audit] == [admin]
    assert db("SELECT count(*) FROM notifications WHERE user_id=:u", u=holder)[0][0] == 1
    # no longer due
    assert "price due" not in (await client.get("/admin/unit-prices")).text

    # a slip of the keyboard is not a revaluation
    r = await client.post(f"/admin/unit-prices/{due}", data={"price": "1035"})
    assert r.status_code == 400 and "is a change of +900.00% in one step" in r.text
    assert 'value="1035"' in r.text  # what was typed is kept
    assert db("SELECT unit_price FROM properties WHERE id=:p", p=due)[0][0] == D("103.50")
    r = await client.post(f"/admin/unit-prices/{due}", data={"price": "103.5"})
    assert r.status_code == 400 and "The unit price is already $103.50" in r.text
    r = await client.post(
        f"/admin/unit-prices/{due}",
        data={"price": "140", "confirm_large": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db("SELECT count(*) FROM property_prices")[0][0] == 2
    # a draft is priced in the listing editor, not here
    draft = _listing(db, title="Not Live", status="draft")
    r = await client.post(f"/admin/unit-prices/{draft}", data={"price": "120"})
    assert r.status_code == 400 and "not published yet" in r.text
    assert "This listing is not published" in (await client.get(f"/admin/unit-prices/{draft}")).text
    assert (await client.get(f"/admin/unit-prices/{uuid.uuid4()}")).status_code == 404
    assert str(fresh) and str(ready)


@pytest.mark.asyncio
async def test_only_a_full_admin_can_move_a_price(client, db):
    pid = _listing(db)
    await _panel_user(client, db, "prices-editor@x.io", "content_editor")
    for method, url in (
        ("GET", "/admin/unit-prices"),
        ("GET", f"/admin/unit-prices/{pid}"),
        ("POST", f"/admin/unit-prices/{pid}"),
    ):
        r = await client.request(method, url, data={"price": "150"}, follow_redirects=False)
        assert r.status_code == 403, (method, url, r.status_code)
    assert db("SELECT unit_price FROM properties WHERE id=:p", p=pid)[0][0] == D("100.00")
    # the editor's own page does not point to what they cannot open
    editor = (await client.get(f"/admin/listing/{pid}")).text
    assert "/admin/unit-prices/" not in editor
    assert "Unit prices" not in (await client.get("/admin/")).text
    # signed out: to the login page
    client.cookies.clear()
    r = await client.get("/admin/unit-prices", follow_redirects=False)
    assert r.status_code in (302, 303) and "/admin/login" in r.headers["location"]


@pytest.mark.asyncio
async def test_the_listing_editor_follows_the_price_and_sets_how_it_is_bought(client, db):
    await _panel_user(client, db, "prices-admin2@x.io", "admin")
    pid = _listing(db)
    page = (await client.get(f"/admin/listing/{pid}")).text
    assert f'href="/admin/unit-prices/{pid}"' in page
    assert "How investors pay" in page and "var LOCKED = false;" in page
    # choose how an under-construction listing is bought
    form = {
        "action": "save_core",
        "title": "Creek Tower",
        "model": "installment",
        "property_type": "apartment",
        "location": "Dubai Creek",
        "total_value": "100000",
        "unit_price": "100",
        "minimum_investment": "500",
        "expected_yield": "7",
        "capital_appreciation": "3",
        "total_return": "10",
    }
    r = await client.post(f"/admin/listing/{pid}", data={**form, "offplan_payment": "both"})
    assert r.status_code == 200 and "Listing details saved" in r.text, r.text[:300]
    assert db("SELECT offplan_payment FROM properties WHERE id=:p", p=pid)[0][0] == "both"
    # left out (a page opened before the field existed, a script): the stored choice stays;
    # it is never reset to the default behind the admin's back
    r = await client.post(f"/admin/listing/{pid}", data={**form, "title": "Creek Tower II"})
    assert r.status_code == 200 and "Listing details saved" in r.text
    assert db("SELECT title, offplan_payment FROM properties WHERE id=:p", p=pid)[0] == (
        "Creek Tower II",
        "both",
    )
    r = await client.post(f"/admin/listing/{pid}", data={**form, "offplan_payment": "barter"})
    assert r.status_code == 400 and "How investors pay: choose one of the options" in r.text
    listed = (await client.get(f"/api/v1/properties/{pid}")).json()
    assert listed["offplan_payment"] == "both"

    # a price that has a recorded history is changed under Unit prices only, even on a listing
    # nobody holds yet: a change made in the editor would not be in the history
    r = await client.post(
        f"/admin/unit-prices/{pid}", data={"price": "105"}, follow_redirects=False
    )
    assert r.status_code == 303
    r = await client.post(
        f"/admin/listing/{pid}",
        data={**form, "unit_price": "120", "total_value": "120000", "minimum_investment": "600"},
    )
    assert r.status_code == 400 and "change it under Unit prices" in r.text
    assert db("SELECT unit_price, launch_price FROM properties WHERE id=:p", p=pid)[0] == (
        D("105.00"),
        D("100.00"),
    )
    # a price that is not a number at all is refused with a sentence, not a crash
    for typed in ("NaN", "Infinity", "abc"):
        r = await client.post(f"/admin/unit-prices/{pid}", data={"price": typed})
        assert r.status_code == 400, (typed, r.status_code)
    assert db("SELECT count(*) FROM property_prices")[0][0] == 1

    # investors hold units and the price has moved: the editor shows the units as a fact
    # (100,000 / 103.50 is not a whole number, and must not be flagged as a mistake)
    await _holder(client, db, pid)
    r = await client.post(
        f"/admin/unit-prices/{pid}", data={"price": "103.50"}, follow_redirects=False
    )
    assert r.status_code == 303
    page = (await client.get(f"/admin/listing/{pid}")).text
    assert "var LOCKED = true;" in page
    saved = await client.post(
        f"/admin/listing/{pid}",
        data={
            **form,
            "unit_price": "103.50",
            "total_value": str(db("SELECT total_value FROM properties WHERE id=:p", p=pid)[0][0]),
            "minimum_investment": "517.50",
            "subtitle": "Edited after a price change",
        },
    )
    assert saved.status_code == 200 and "Listing details saved" in saved.text, saved.text[:400]
    assert db("SELECT total_units, unit_price FROM properties WHERE id=:p", p=pid)[0] == (
        1000,
        D("103.50"),
    )
    # the price itself still cannot be typed over in the editor
    r = await client.post(f"/admin/listing/{pid}", data={**form, "unit_price": "150"})
    assert r.status_code == 400 and "locked" in r.text
    # a ready listing has no such choice
    ready = _listing(db, model="ready-income", title="Ready Flat")
    ready_page = (await client.get(f"/admin/listing/{ready}")).text
    assert 'data-field="offplan_payment" hidden' in ready_page
