"""Admin-panel listing safety (go-live audit, Step 1).

Reproduces the original bugs, then proves the fixes:
  * editing ``total_units`` on a property that has investor positions was accepted and left
    ``available_units`` untouched (units invariant broken) -> now rejected with a form error;
  * editing ``total_units`` on an unsold property left ``available_units`` stale -> now follows;
  * a duplicate slug was saved (public page then 500s) -> now rejected;
  * the /admin/upload-document page 500'd after committing the row (retry = duplicates)
    -> now returns 200 and creates exactly one row;
  * hand edits were unaudited -> an audit row is written with before/after.
"""

from __future__ import annotations

import uuid

import pytest

PW = "Passw0rd!23"
ADMIN_EMAIL = "guard-admin@x.com"


async def _admin_session(client, db) -> None:
    """Register an admin user and log the httpx client into the SQLAdmin session."""
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": ADMIN_EMAIL, "password": PW, "full_name": "Admin"},
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=ADMIN_EMAIL)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    r = await client.post("/admin/login", data={"username": ADMIN_EMAIL, "password": PW})
    assert r.status_code in (200, 302, 303), r.text
    assert "session" in client.cookies


def _seed_property(db, *, title="Guard Tower", slug="guard-tower-abc123", units=100) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,slug,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,:t,:s,'Dubai','residential','ready-income','active',:tv,100,:u,:u,100)",
        id=pid,
        t=title,
        s=slug,
        tv=100 * units,
        u=units,
    )
    return pid


def _form(db, pid: str, **overrides) -> dict:
    """A complete SQLAdmin edit form for the property (all form_columns)."""
    row = db(
        "SELECT title, slug, model, property_type, location, total_value, unit_price, "
        "total_units, minimum_investment FROM properties WHERE id=:i",
        i=pid,
    )[0]
    data = {
        "title": row[0],
        "slug": row[1],
        "model": row[2],
        "property_type": row[3],
        "location": row[4],
        "total_value": str(row[5]),
        "unit_price": str(row[6]),
        "total_units": str(row[7]),
        "minimum_investment": str(row[8]),
        "content": "{}",
        "fees": "{}",
    }
    data.update({k: str(v) for k, v in overrides.items()})
    return data


@pytest.mark.asyncio
async def test_admin_edit_total_units_follows_available_when_unsold(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db)
    r = await client.post(f"/admin/property/edit/{pid}", data=_form(db, pid, total_units=250))
    assert r.status_code in (200, 302, 303), r.text[:300]
    total, avail = db("SELECT total_units, available_units FROM properties WHERE id=:i", i=pid)[0]
    assert (total, avail) == (250, 250)
    # hand edits are now audited with the changed fields
    rows = db(
        "SELECT before, after FROM audit_log WHERE action='property.admin_edit' AND entity_id=:i",
        i=pid,
    )
    assert rows, "no audit row for the admin edit"
    assert rows[-1][1].get("total_units") == "250"


@pytest.mark.asyncio
async def test_admin_edit_units_and_price_locked_once_investors_hold_units(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db)
    # an investor holds 3 units (ledger row) -> the offering is frozen
    uid = db("SELECT id FROM users WHERE email=:e", e=ADMIN_EMAIL)[0][0]
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) "
        "VALUES (:u,:p,3,100,'purchase')",
        u=uid,
        p=pid,
    )
    r = await client.post(f"/admin/property/edit/{pid}", data=_form(db, pid, total_units=999))
    # SQLAdmin re-renders the form with the validation error as HTTP 400 — nothing saved.
    assert r.status_code == 400 and "locked" in r.text, r.text[:300]
    r2 = await client.post(f"/admin/property/edit/{pid}", data=_form(db, pid, unit_price=150))
    assert r2.status_code == 400 and "locked" in r2.text
    total, avail, price = db(
        "SELECT total_units, available_units, unit_price FROM properties WHERE id=:i", i=pid
    )[0]
    assert (total, avail, float(price)) == (100, 100, 100.0)  # unchanged
    # content-only edits are still allowed on a live property
    r3 = await client.post(f"/admin/property/edit/{pid}", data=_form(db, pid, title="Renamed"))
    assert r3.status_code in (200, 302, 303) and "locked" not in r3.text
    assert db("SELECT title FROM properties WHERE id=:i", i=pid)[0][0] == "Renamed"


@pytest.mark.asyncio
async def test_admin_edit_rejects_duplicate_slug_and_invalid_model(client, db):
    await _admin_session(client, db)
    a = _seed_property(db, title="A", slug="tower-a")
    b = _seed_property(db, title="B", slug="tower-b")
    r = await client.post(f"/admin/property/edit/{b}", data=_form(db, b, slug="tower-a"))
    assert r.status_code == 400 and "already used" in r.text
    assert db("SELECT slug FROM properties WHERE id=:i", i=b)[0][0] == "tower-b"
    r2 = await client.post(f"/admin/property/edit/{a}", data=_form(db, a, model="tokenized"))
    assert r2.status_code == 400 and "model must be one of" in r2.text
    assert db("SELECT model FROM properties WHERE id=:i", i=a)[0][0] == "ready-income"
    # a blanked slug is regenerated, never saved as NULL
    r3 = await client.post(f"/admin/property/edit/{a}", data=_form(db, a, slug=""))
    assert r3.status_code in (200, 302, 303)
    assert db("SELECT slug FROM properties WHERE id=:i", i=a)[0][0]


@pytest.mark.asyncio
async def test_admin_document_upload_creates_exactly_one_row(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db)
    r = await client.post(
        "/admin/upload-document",
        data={"property_id": pid, "title": "Valuation", "doc_type": "valuation"},
        files={"file": ("val.pdf", b"%PDF-1.4 guard", "application/pdf")},
    )
    assert r.status_code == 200, r.text[:300]
    assert "Uploaded" in r.text and "Upload failed" not in r.text
    n = db("SELECT count(*) FROM documents WHERE property_id=:p", p=pid)[0][0]
    assert n == 1
    # and it is served through the public property documents endpoint
    docs = (await client.get(f"/api/v1/properties/{pid}/documents")).json()
    assert [d["title"] for d in docs] == ["Valuation"]
