"""Client letter (2026-11-18): valuations, insurance and the legal due diligence on the property
page, each with who issued it, its date and its documents; and documents uploaded several at
once, each with its own title, category, issuer and date (as on Capimax BRX)."""

from __future__ import annotations

import pytest

from app.tests.test_listing_step2_db import _admin_session, _seed_property


def _docs(db, pid):
    return db(
        "SELECT title, type, issuer, issued_on::text FROM documents "
        "WHERE property_id=:p ORDER BY title",
        p=pid,
    )


@pytest.mark.asyncio
async def test_several_documents_at_once_each_with_its_own_details(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db, slug="dd-many")
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "upload_doc",
            "title": ["Q3 valuation", ""],  # the second is left blank: its file name is used
            "doc_type": ["valuation", "insurance"],
            "issuer": ["Knight Frank", "AXA Gulf"],
            "issued_on": ["2026-09-30", ""],
        },
        files=[
            ("file", ("q3.pdf", b"%PDF-1.4 a", "application/pdf")),
            ("file", ("insurance_policy-2026.pdf", b"%PDF-1.4 b", "application/pdf")),
        ],
    )
    assert "Uploaded 2 documents." in r.text
    assert sorted(_docs(db, pid), key=lambda d: d[1]) == [
        ("insurance policy 2026", "insurance", "AXA Gulf", None),
        ("Q3 valuation", "valuation", "Knight Frank", "2026-09-30"),
    ]


@pytest.mark.asyncio
async def test_one_refused_file_stores_none_of_the_batch(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db, slug="dd-refused")
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_doc", "title": ["Good", "Bad"], "doc_type": ["valuation", "other"]},
        files=[
            ("file", ("good.pdf", b"%PDF-1.4 a", "application/pdf")),
            ("file", ("bad.pdf", b"not a pdf", "application/pdf")),
        ],
    )
    assert "not a valid .pdf" in r.text
    assert _docs(db, pid) == []


@pytest.mark.asyncio
async def test_a_documents_details_are_edited_and_audited(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db, slug="dd-edit")
    await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_doc", "title": "dd", "doc_type": "other"},
        files={"file": ("dd.pdf", b"%PDF-1.4 x", "application/pdf")},
    )
    doc_id = db("SELECT id FROM documents WHERE property_id=:p", p=pid)[0][0]
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "doc_edit",
            "doc_id": str(doc_id),
            "title": "Legal Due Diligence Report",
            "doc_type": "due_diligence",
            "issuer": "Al Tamimi & Company",
            "issued_on": "2026-08-15",
        },
    )
    assert "Saved" in r.text
    assert _docs(db, pid) == [
        ("Legal Due Diligence Report", "due_diligence", "Al Tamimi & Company", "2026-08-15")
    ]
    assert (
        db(
            "SELECT count(*) FROM audit_log WHERE action='document.updated' AND entity_id=:i",
            i=str(doc_id),
        )[0][0]
        == 1
    )
    # a bad date is refused, nothing changes
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "doc_edit",
            "doc_id": str(doc_id),
            "title": "X",
            "doc_type": "other",
            "issued_on": "15/08",
        },
    )
    assert "must be a date" in r.text
    assert _docs(db, pid)[0][0] == "Legal Due Diligence Report"


@pytest.mark.asyncio
async def test_insurance_and_legal_review_are_saved_and_public(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db, slug="dd-public", status="active")
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "save_insurance",
            "insurance_provider": "AXA Gulf",
            "insurance_policy": "PRP-2026-00418",
            "insurance_coverage": "1,650,000",
            "insurance_summary": "Fire, flood and third-party liability.",
        },
    )
    assert "Insurance saved." in r.text
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "save_legal_dd",
            "legal_dd_provider": "Al Tamimi & Company",
            "legal_dd_date": "2026-08-15",
            "legal_dd_summary": "Title deed and SPV reviewed.",
        },
    )
    assert "Legal due diligence saved." in r.text
    await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "upload_doc",
            "title": "Policy",
            "doc_type": "insurance",
            "issuer": "AXA Gulf",
            "issued_on": "2026-03-12",
        },
        files={"file": ("p.pdf", b"%PDF-1.4 p", "application/pdf")},
    )
    content = (await client.get("/api/v1/properties/dd-public")).json()["content"]
    assert content["insurance"] == {
        "provider": "AXA Gulf",
        "policyNumber": "PRP-2026-00418",
        "coverage": 1650000,
        "summary": "Fire, flood and third-party liability.",
    }
    assert content["legalDueDiligence"] == {
        "provider": "Al Tamimi & Company",
        "date": "2026-08-15",
        "summary": "Title deed and SPV reviewed.",
    }
    docs = (await client.get("/api/v1/properties/dd-public/documents")).json()
    assert [(d["type"], d["issuer"], d["issued_on"]) for d in docs] == [
        ("insurance", "AXA Gulf", "2026-03-12")
    ]
    # clearing a field removes it
    await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "save_insurance",
            "insurance_provider": "AXA Gulf",
            "insurance_policy": "",
            "insurance_coverage": "",
            "insurance_summary": "",
        },
    )
    content = (await client.get("/api/v1/properties/dd-public")).json()["content"]
    assert content["insurance"] == {"provider": "AXA Gulf"}
    # the review date must be a date
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "save_legal_dd", "legal_dd_provider": "X", "legal_dd_date": "August"},
    )
    assert "must be a date" in r.text
