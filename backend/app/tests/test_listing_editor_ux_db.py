"""Listing Editor — owner additions after Step 2.

Each test pins a gap the owner named:
  * COVERAGE: every optional block the public property page shows only when declared
    (terms, listing fees, developer, key facts, amenities, SPV extras, milestones, expected
    completion, construction %) must be editable in the Listing Editor;
  * UNDER-CONSTRUCTION: milestones (add / edit / reorder / status / date), the computed
    construction % and the expected completion date are editable in the editor and reach
    the public API;
  * NON-TECHNICAL OWNER: every field has a label, help text and an example, required
    fields are marked, validation errors are plain sentences (no codes / tracebacks), and
    technical links are hidden from non-admin roles;
  * create / core-field editing through the editor obey the offering lock.
"""

# ruff: noqa: E501
from __future__ import annotations

import re
import uuid

import pytest

from app.services import listing_service

PW = "Passw0rd!23"
ADMIN_EMAIL = "ux-admin@x.com"


@pytest.fixture(autouse=True)
def _local_storage(monkeypatch, tmp_path):
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "storage_provider", "local", raising=False)
    monkeypatch.setattr(s, "storage_dir", str(tmp_path), raising=False)
    yield


async def _admin_session(client, db) -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": ADMIN_EMAIL, "password": PW, "full_name": "Admin"},
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=ADMIN_EMAIL)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    r = await client.post("/admin/login", data={"username": ADMIN_EMAIL, "password": PW})
    assert "session" in client.cookies, (r.status_code, r.text[:300])
    return str(uid)


CREATE_FORM = {
    "title": "UX Tower — Phase 1",
    "subtitle": "Off-plan tower in Business Bay",
    "model": "future",
    "property_type": "apartment",
    "description": "Two towers, 40 floors.",
    "location": "Business Bay, Dubai",
    "city": "Dubai",
    "country": "United Arab Emirates",
    "total_value": "3200000",
    "unit_price": "100",
    "total_units": "32000",
    "minimum_investment": "500",
    "target_yield": "8",
    "expected_yield": "8",
    "capital_appreciation": "4",
    "total_return": "12",
}


async def _create(client, db, **over) -> str:
    form = {**CREATE_FORM, **over}
    r = await client.post("/admin/listing/new", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text[:400]
    loc = r.headers["location"]
    pid = loc.split("/admin/listing/")[1].split("?")[0]
    return pid


# --- coverage: page block -> editor input ---------------------------------------------------- #
# Every optional block on the public page, and the form control that edits it. Keys are the
# JSON/column the SPA reads; values are input names the editor must render.
PAGE_BLOCKS: dict[str, str] = {
    "content.terms.distributionFrequency": 'name="distribution_frequency"',
    "content.terms.investmentTerm": 'name="investment_term"',
    "content.terms.exitOptions": 'name="exit_options"',
    "content.fees.performance": 'name="performance_fee"',
    "content.fees.exit": 'name="exit_fee"',
    "content.developer.name": 'name="name"',
    "content.developer.rating": 'name="rating"',
    "content.developer.projectsCompleted": 'name="projects_completed"',
    "content.developer.logo": 'name="logo"',
    "content.details.bedrooms": 'name="bedrooms"',
    "content.details.bathrooms": 'name="bathrooms"',
    "content.details.area": 'name="area"',
    "content.details.parking": 'name="parking"',
    "content.details.maxInvestment": 'name="max_investment"',
    "content.details.amenities": 'name="amenities"',
    "content.spv.jurisdiction": 'name="jurisdiction"',
    "content.spv.trustee": 'name="trustee"',
    "content.spv.auditor": 'name="auditor"',
    "spv_name": 'name="spv_name"',
    "spv_registration": 'name="spv_registration"',
    "legal_structure": 'name="legal_structure"',
    "expected_completion": 'name="expected_completion"',
    "milestones (add)": 'value="ms_add"',
    "milestones (status/progress/date)": 'name="progress_pct"',
    "description": 'name="description"',
    "subtitle": 'name="subtitle"',
    "images": 'name="files"',
    "documents": 'value="upload_doc"',
}


@pytest.mark.asyncio
async def test_editor_covers_every_optional_page_block_with_labels_help_and_examples(client, db):
    await _admin_session(client, db)
    pid = await _create(client, db)
    html = (await client.get(f"/admin/listing/{pid}")).text
    missing = [block for block, needle in PAGE_BLOCKS.items() if needle not in html]
    assert not missing, f"page blocks with no editor control: {missing}"
    # every core column field: label, required mark where required, help + example
    for f in listing_service.CORE_FIELDS:
        wrapper = re.search(
            rf'<div class="f" data-field="{f.name}">(.*?)<div class="help">(.*?)</div>\s*</div>',
            html,
            re.S,
        )
        assert wrapper, f"{f.name}: no field wrapper rendered"
        body, help_text = wrapper.group(1), wrapper.group(2)
        assert f.label in body, f"{f.name}: label missing"
        assert (('class="req"' in body) == f.required), f"{f.name}: required marker wrong"
        assert f.help in help_text, f"{f.name}: help text missing"
        if f.example and f.kind != "select":
            assert "Example:" in help_text, f"{f.name}: example missing"
    # every content / milestone / upload control also carries help text
    for name in (
        "bedrooms", "bathrooms", "area", "parking", "max_investment", "amenities",
        "name", "rating", "projects_completed", "logo", "jurisdiction", "trustee", "auditor",
        "distribution_frequency", "investment_term", "exit_options", "performance_fee", "exit_fee",
        "files", "title", "doc_type", "file", "ms_title", "ms_status", "ms_progress", "ms_date", "ms_description",
    ):
        assert re.search(rf'data-field="{name}">.*?<div class="help">', html, re.S), f"{name}: no help text"
    # model + property type are dropdowns with human labels, not raw codes only
    assert "Under construction — future property" in html and "Apartment" in html


# --- under-construction: milestones + progress + completion date -------------------------- #
@pytest.mark.asyncio
async def test_editor_milestones_progress_and_completion_reach_public_page(client, db):
    await _admin_session(client, db)
    pid = await _create(client, db)
    ed = f"/admin/listing/{pid}"
    # expected completion date via the Construction card
    r = await client.post(ed, data={"action": "save_construction", "expected_completion": "2027-06-30"})
    assert r.status_code == 200 and "Completion date saved" in r.text
    # add three milestones (add appends in order)
    for title, status, pct in (("Foundation", "completed", ""), ("Structure", "in_progress", "40"), ("Handover", "planned", "")):
        r = await client.post(ed, data={"action": "ms_add", "title": title, "status": status, "progress_pct": pct, "target_date": "2027-01-31" if title == "Handover" else ""})
        assert r.status_code == 200 and "Milestone added" in r.text, r.text[:300]
    rows = db("SELECT id, title, status, sort_index, progress_pct FROM property_milestones WHERE property_id=:p ORDER BY sort_index", p=pid)
    assert [r[1] for r in rows] == ["Foundation", "Structure", "Handover"]
    assert "Construction progress shown to investors: 40%" in (await client.get(ed)).text
    # edit: status/progress/date of the current one
    ms_id = str(rows[1][0])
    r = await client.post(ed, data={"action": "ms_save", "ms_id": ms_id, "title": "Structure to roof", "status": "in_progress", "progress_pct": "65", "target_date": "2026-12-15", "description": "Concrete frame"})
    assert r.status_code == 200 and "Milestone saved" in r.text, r.text[:300]
    # reorder: move Handover up one slot
    hand_id = str(rows[2][0])
    r = await client.post(ed, data={"action": "ms_up", "ms_id": hand_id})
    assert "Milestone order updated" in r.text
    order = [r[0] for r in db("SELECT title FROM property_milestones WHERE property_id=:p ORDER BY sort_index", p=pid)]
    assert order == ["Foundation", "Handover", "Structure to roof"]
    # publish and read what investors get
    await client.post(ed, data={"action": "publish"})
    pub = (await client.get(f"/api/v1/properties/{pid}")).json()
    assert pub["expected_completion"] == "2027-06-30"
    assert pub["construction_progress"] == 65
    ms = sorted(pub["milestones"], key=lambda m: m["sort_index"])
    assert [(m["title"], m["status"], m["progress_pct"]) for m in ms] == [
        ("Foundation", "completed", None),
        ("Handover", "planned", None),
        ("Structure to roof", "in_progress", 65),
    ]
    assert ms[2]["target_date"] == "2026-12-15"
    # delete one
    r = await client.post(ed, data={"action": "ms_delete", "ms_id": hand_id})
    assert "Milestone deleted" in r.text
    assert db("SELECT count(*) FROM property_milestones WHERE property_id=:p", p=pid)[0][0] == 2
    acts = {a[0] for a in db("SELECT action FROM audit_log WHERE entity_id=:i", i=pid)}
    assert {"property.milestone.add", "property.milestone.update", "property.milestone.reorder", "property.milestone.delete", "property.approve"} <= acts


# --- create + core edits + lock, all through the editor ------------------------------------ #
@pytest.mark.asyncio
async def test_editor_create_and_core_edit_obey_offering_lock(client, db):
    uid = await _admin_session(client, db)
    pid = await _create(client, db)
    status, slug, avail, model = db("SELECT status, slug, available_units, model FROM properties WHERE id=:i", i=pid)[0]
    assert (status, avail, model) == ("draft", 32000, "future") and slug.startswith("ux-tower-phase-1-")
    ed = f"/admin/listing/{pid}"
    # core edit while unsold: units follow
    form = {**CREATE_FORM, "total_units": "16000", "unit_price": "200", "title": "UX Tower — Phase 1 (renamed)"}
    r = await client.post(ed, data={"action": "save_core", **form})
    assert r.status_code == 200 and "Listing details saved" in r.text, r.text[:300]
    assert db("SELECT total_units, available_units, unit_price, title FROM properties WHERE id=:i", i=pid)[0] == (16000, 16000, 200, "UX Tower — Phase 1 (renamed)")
    # an investor holds units -> offering locked, content edits still fine
    db("INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) VALUES (:u,:p,3,200,'purchase')", u=uid, p=pid)
    r = await client.post(ed, data={"action": "save_core", **form, "total_units": "999"})
    assert r.status_code == 400 and "locked" in r.text and "investor position" in r.text
    assert db("SELECT total_units FROM properties WHERE id=:i", i=pid)[0][0] == 16000
    r = await client.post(ed, data={"action": "save_core", **form, "subtitle": "New tagline"})
    assert r.status_code == 200 and "Listing details saved" in r.text
    assert db("SELECT subtitle FROM properties WHERE id=:i", i=pid)[0][0] == "New tagline"
    # delete refused with positions, allowed after they are gone
    r = await client.post(ed, data={"action": "delete_listing"})
    assert r.status_code == 400 and "cannot be deleted" in r.text
    db("DELETE FROM ownership_ledger WHERE property_id=:p", p=pid)
    r = await client.post(ed, data={"action": "delete_listing"}, follow_redirects=False)
    assert r.status_code == 303
    assert db("SELECT count(*) FROM properties WHERE id=:i", i=pid)[0][0] == 0


# --- human-readable errors, never codes or tracebacks -------------------------------------- #
@pytest.mark.asyncio
async def test_editor_errors_are_plain_sentences(client, db, monkeypatch):
    await _admin_session(client, db)
    # create: missing required + bad number -> sentence naming the field + example
    r = await client.post("/admin/listing/new", data={**CREATE_FORM, "title": ""})
    assert r.status_code == 400 and "Listing title: this field is required" in r.text
    r = await client.post("/admin/listing/new", data={**CREATE_FORM, "total_value": "1.2m"})
    assert r.status_code == 400 and "Total property value (USD): enter a number using digits only. Example: 1200000." in r.text
    r = await client.post("/admin/listing/new", data={**CREATE_FORM, "expected_yield": "150"})
    assert "Expected annual yield (%): must be between 0 and 100" in r.text
    pid = await _create(client, db)
    ed = f"/admin/listing/{pid}"
    r = await client.post(ed, data={"action": "ms_add", "title": "", "status": "planned"})
    assert r.status_code == 400 and "Milestone title: this field is required" in r.text
    r = await client.post(ed, data={"action": "ms_add", "title": "X", "status": "done"})
    assert "choose Planned, In progress or Completed" in r.text
    r = await client.post(ed, data={"action": "save_construction", "expected_completion": "30/06/2027"})
    assert "enter a date as YYYY-MM-DD" in r.text
    # an unexpected failure is logged and replaced by a generic sentence with a reference
    def boom(*_a, **_k):
        raise RuntimeError("db exploded: secret internals")

    monkeypatch.setattr(listing_service, "with_details", boom)
    r = await client.post(ed, data={"action": "save_facts", "bedrooms": "2"})
    assert r.status_code == 400
    assert "Something went wrong and nothing was saved" in r.text and "reference:" in r.text
    for leak in ("RuntimeError", "Traceback", "secret internals", "INVALID_INPUT", "AppError"):
        assert leak not in r.text, leak


# --- technical links hidden from non-admin sessions --------------------------------------- #
@pytest.mark.asyncio
async def test_editor_hides_raw_fields_link_from_content_editor_role(client, db):
    await _admin_session(client, db)
    pid = await _create(client, db)
    html = (await client.get(f"/admin/listing/{pid}")).text
    assert "Raw fields" in html  # full admin (no roles recorded = legacy admin session)
    from app import admin_listing

    class Req:
        session = {"admin_id": str(uuid.uuid4()), "admin_roles": ["content_editor"]}

    assert admin_listing.is_full_admin(Req()) is False
    Req.session["admin_roles"] = ["admin", "content_editor"]
    assert admin_listing.is_full_admin(Req()) is True
