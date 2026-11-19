"""Client letter (2026-11-18), Investment Model: an under-construction property is revalued every
3 months after purchase, and a new valuation updates the unit price, the investment's value and
the change since purchase, with the investor told by email and in the app.

  * a valuation saved in the Listing Editor can be adopted as the unit price in the same step
    (price history "Valuation", repricing, the notice to every holder);
  * the editor and the Listings page show when the last valuation was and when the next one is
    due; the hourly installment job reminds the admins (in the app and by email) once per 14
    days while a published under-construction listing has gone 3 months without one.
"""

# ruff: noqa: E501
from __future__ import annotations

import datetime as dt

import pytest

from app.services import valuation_service
from app.tests.test_listing_translation_db import _admin, _listing, _post

PW = "Passw0rd!23"


def _holder(db, pid, email="val-holder@x.com", units=10) -> str:
    db(
        "INSERT INTO users (id, email, password_hash, full_name) VALUES (gen_random_uuid(), :e, 'x', 'H')",
        e=email,
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) "
        "VALUES (:u, :p, :n, 100, 'purchase')",
        u=uid,
        p=pid,
        n=units,
    )
    return str(uid)


def _age(db, pid, days):
    db(
        "UPDATE properties SET created_at = now() - make_interval(days => :d) WHERE id=:p",
        d=days,
        p=pid,
    )


def _admin_notes(db, pid):
    return db(
        "SELECT n.title FROM notifications n JOIN users u ON u.id = n.user_id "
        "WHERE n.type = :t ORDER BY n.created_at",
        t=f"valuation_due:{pid}",
    )


@pytest.mark.asyncio
async def test_a_valuation_can_set_the_unit_price_and_tell_the_holders(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="val-price")  # installment, active, $100 x 10,000 units
    holder = _holder(db, pid)
    page = (await client.get(f"/admin/listing/{pid}")).text
    assert "No valuation on record yet." in page and 'name="valuation_unit_price"' in page

    html = await _post(
        client,
        pid,
        action="save_valuation",
        valuation_provider="Knight Frank",
        valuation_date="November 2026",
        valuation_value="1080000",
        valuation_unit_price="108",
    )
    assert "Valuation saved and adopted as the unit price: $100 to $108." in html
    assert float(db("SELECT unit_price FROM properties WHERE id=:p", p=pid)[0][0]) == 108.0
    row = db("SELECT price, label, note FROM property_prices WHERE property_id=:p", p=pid)
    assert [(float(r[0]), r[1], r[2]) for r in row] == [
        (108.0, "Valuation", "Knight Frank, November 2026")
    ]
    # the holder is told, in the app and by email
    told = db("SELECT title FROM notifications WHERE user_id=:u", u=holder)
    assert any("New unit price" in t[0] for t in told)
    assert db("SELECT count(*) FROM email_outbox WHERE user_id=:u", u=holder)[0][0] >= 1
    # the day of the valuation is kept and the editor says when the next one is due
    content = db("SELECT content FROM properties WHERE id=:p", p=pid)[0][0]
    assert content["valuation"]["recordedOn"] == dt.date.today().isoformat()
    page = (await client.get(f"/admin/listing/{pid}")).text
    assert "Latest valuation on record" in page and "The next quarterly valuation is due by" in page
    # the hint: this valuation over the units
    assert "$108.00" in page


@pytest.mark.asyncio
async def test_a_price_jump_needs_the_confirmation_and_nothing_is_half_saved(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="val-jump")
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "save_valuation",
            "valuation_value": "2000000",
            "valuation_unit_price": "200",
        },
    )
    html = r.text
    assert r.status_code == 400
    assert "tick the confirmation" in html
    assert float(db("SELECT unit_price FROM properties WHERE id=:p", p=pid)[0][0]) == 100.0
    content = db("SELECT content FROM properties WHERE id=:p", p=pid)[0][0]
    assert "valuation" not in content  # the valuation was not saved without its price either
    html = await _post(
        client,
        pid,
        action="save_valuation",
        valuation_value="2000000",
        valuation_unit_price="200",
        confirm_large="1",
    )
    assert "adopted as the unit price" in html


@pytest.mark.asyncio
async def test_a_valuation_without_a_price_keeps_the_price(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="val-only")
    html = await _post(client, pid, action="save_valuation", valuation_provider="CBRE")
    assert "Valuation saved." in html
    assert float(db("SELECT unit_price FROM properties WHERE id=:p", p=pid)[0][0]) == 100.0
    assert db("SELECT count(*) FROM property_prices WHERE property_id=:p", p=pid)[0][0] == 0


@pytest.mark.asyncio
async def test_a_draft_sets_its_price_elsewhere(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="val-draft", status="draft")
    page = (await client.get(f"/admin/listing/{pid}")).text
    assert (
        'name="valuation_unit_price"' not in page
        and "Until then the price is set under Listing details" in page
    )


@pytest.mark.asyncio
async def test_the_admins_are_reminded_of_a_quarterly_valuation(client, db, monkeypatch):
    from app.core.config import get_settings

    await _admin(client, db)
    due = _listing(db, slug="val-due")
    _age(db, due, 100)
    fresh = _listing(db, slug="val-fresh")
    _age(db, fresh, 30)
    ready = _listing(db, slug="val-ready")
    db("UPDATE properties SET model='ready-income' WHERE id=:p", p=ready)
    _age(db, ready, 300)
    sample = _listing(db, slug="val-sample")  # a demo listing takes no investments
    db("""UPDATE properties SET content = '{"sample": true}'::jsonb WHERE id=:p""", p=sample)
    _age(db, sample, 300)

    # the Listings page and the editor say so
    listing_page = (await client.get("/admin/listing/")).text
    assert "gone 3 months without a valuation" in listing_page and "Valuation due" in listing_page
    page = (await client.get(f"/admin/listing/{due}")).text
    assert "The quarterly valuation is due" in page

    # the hourly job reminds every admin once, in the app and by email
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cr3t", raising=False)
    run = await client.post(
        "/api/v1/admin/installments/run-due", headers={"X-Cron-Secret": "s3cr3t"}
    )
    assert run.status_code == 200 and run.json()["valuation_reminders"] == 1
    notes = _admin_notes(db, due)
    assert [n[0] for n in notes] == ["Quarterly valuation due: Creek Tower"]
    assert (
        db(
            "SELECT count(*) FROM email_outbox WHERE subject = 'Quarterly valuation due: Creek Tower'"
        )[0][0]
        == 1
    )
    assert _admin_notes(db, fresh) == [] and _admin_notes(db, ready) == []
    assert _admin_notes(db, sample) == []

    # not again the next hour
    run = await client.post(
        "/api/v1/admin/installments/run-due", headers={"X-Cron-Secret": "s3cr3t"}
    )
    assert run.json()["valuation_reminders"] == 0 and len(_admin_notes(db, due)) == 1

    # still missing two weeks later: reminded again
    db(
        "UPDATE notifications SET created_at = now() - interval '15 days' WHERE type=:t",
        t=f"valuation_due:{due}",
    )
    run = await client.post(
        "/api/v1/admin/installments/run-due", headers={"X-Cron-Secret": "s3cr3t"}
    )
    assert run.json()["valuation_reminders"] == 1

    # a valuation saved ends it
    await _post(
        client, due, action="save_valuation", valuation_provider="CBRE", valuation_date="Nov 2026"
    )
    db(
        "UPDATE notifications SET created_at = now() - interval '15 days' WHERE type=:t",
        t=f"valuation_due:{due}",
    )
    run = await client.post(
        "/api/v1/admin/installments/run-due", headers={"X-Cron-Secret": "s3cr3t"}
    )
    assert run.json()["valuation_reminders"] == 0
    assert "gone 3 months without a valuation" not in (await client.get("/admin/listing/")).text


@pytest.mark.asyncio
async def test_a_valuation_report_counts_as_the_latest_valuation(client, db, asession):
    pid = _listing(db, slug="val-doc")
    _age(db, pid, 200)
    db(
        "INSERT INTO documents (property_id, title, type, file_url, issued_on) "
        "VALUES (:p, 'Q3 valuation', 'valuation', 'x', current_date - 10)",
        p=pid,
    )
    due = await valuation_service.due_listings(asession)
    assert all(str(r["property"].id) != pid for r in due)
