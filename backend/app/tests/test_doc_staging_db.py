"""Client letter (2026-11-18), file upload as on Capimax BRX: each document is uploaded the moment
it is picked and kept until the rows are saved, and each has its name in English, Arabic and
French next to it."""

# ruff: noqa: E501
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.tests.test_listing_translation_db import _admin, _content, _listing, _post

PDF = b"%PDF-1.4\n%test\n"


async def _stage(client, pid, name="valuation_report-2026.pdf", data=PDF):
    return await client.post(
        f"/admin/listing/{pid}/stage-doc", files={"file": (name, data, "application/pdf")}
    )


def _stored(key: str) -> bool:
    from pathlib import Path

    return (Path(get_settings().storage_dir) / key).is_file()


@pytest.mark.asyncio
async def test_a_picked_file_is_uploaded_at_once_and_listed_on_save(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="stage-a")
    page = (await client.get(f"/admin/listing/{pid}")).text
    assert f'data-stage-url="/admin/listing/{pid}/stage-doc"' in page
    assert "Name in Arabic" in page and "Name in French" in page
    assert r"replace(/\.[^.]+$/" in page  # the script's patterns reach the page intact

    one = await _stage(client, pid)
    two = await _stage(client, pid, name="insurance-policy.pdf")
    assert one.status_code == 200 and two.status_code == 200
    a, b = one.json(), two.json()
    assert a["name"] == "valuation_report-2026.pdf" and a["image"] is False and a["token"]
    # stored already, but nothing is listed until the rows are saved
    assert db("SELECT count(*) FROM documents WHERE property_id=:p", p=pid)[0][0] == 0

    html = await _post(
        client,
        pid,
        action="upload_doc",
        staged=[a["token"], b["token"]],
        title=["Valuation Report 2026", "Insurance Policy"],
        title_ar=["تقرير التقييم 2026", ""],
        title_fr=["Rapport d'évaluation 2026", "Police d'assurance"],
        doc_type=["valuation", "insurance"],
        issuer=["Knight Frank", "AXA"],
        issued_on=["2026-11-01", ""],
    )
    assert "Uploaded 2 documents." in html
    docs = db(
        "SELECT id, title, type, issuer, issued_on, file_url FROM documents WHERE property_id=:p ORDER BY title DESC",
        p=pid,
    )
    assert [(d[1], d[2], d[3]) for d in docs] == [
        ("Valuation Report 2026", "valuation", "Knight Frank"),
        ("Insurance Policy", "insurance", "AXA"),
    ]
    assert str(docs[0][4]) == "2026-11-01" and all(_stored(d[5]) for d in docs)
    versions = _content(db, pid)["translations"]
    val, ins = str(docs[0][0]), str(docs[1][0])
    assert versions["ar"]["documents"] == {val: {"title": "تقرير التقييم 2026"}}
    assert versions["fr"]["documents"] == {
        val: {"title": "Rapport d'évaluation 2026"},
        ins: {"title": "Police d'assurance"},
    }
    # the public documents follow the site's language
    listed = await client.get(f"/api/v1/properties/{pid}/documents?lang=fr")
    assert sorted(d["title"] for d in listed.json()) == [
        "Police d'assurance",
        "Rapport d'évaluation 2026",
    ]
    listed = await client.get(f"/api/v1/properties/{pid}/documents?lang=ar")
    assert sorted(d["title"] for d in listed.json()) == ["Insurance Policy", "تقرير التقييم 2026"]

    # the same token cannot list the file twice
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_doc", "staged": a["token"], "title": "Again", "doc_type": "other"},
    )
    assert "already listed" in r.text


@pytest.mark.asyncio
async def test_a_removed_file_is_deleted_and_a_foreign_token_is_refused(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="stage-b")
    other = _listing(db, slug="stage-c")
    tok = (await _stage(client, pid)).json()["token"]
    r = await client.post(f"/admin/listing/{pid}/unstage-doc", data={"token": tok})
    assert r.status_code == 200 and r.json() == {"removed": True}
    # its file is gone: saving it now says so
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_doc", "staged": tok, "title": "Gone", "doc_type": "other"},
    )
    assert "removed before saving" in r.text

    # a token of one listing never lists a file on another, and a made-up one is refused
    tok = (await _stage(client, pid)).json()["token"]
    r = await client.post(
        f"/admin/listing/{other}",
        data={"action": "upload_doc", "staged": tok, "title": "X", "doc_type": "other"},
    )
    assert "belongs to another listing" in r.text
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "upload_doc",
            "staged": tok[:-3] + "abc",
            "title": "X",
            "doc_type": "other",
        },
    )
    assert "Choose it again" in r.text
    assert db("SELECT count(*) FROM documents")[0][0] == 0


@pytest.mark.asyncio
async def test_a_refused_file_type_is_said_at_once(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="stage-d")
    r = await _stage(client, pid, name="tool.exe", data=b"MZ\x90\x00")
    assert r.status_code == 415 and "Allowed file types" in r.json()["error"]


@pytest.mark.asyncio
async def test_a_documents_names_in_every_language_can_be_edited(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="stage-e")
    tok = (await _stage(client, pid)).json()["token"]
    await _post(
        client, pid, action="upload_doc", staged=tok, title="Valuation", doc_type="valuation"
    )
    doc_id = str(db("SELECT id FROM documents WHERE property_id=:p", p=pid)[0][0])
    assert "translations" not in _content(db, pid)

    await _post(
        client,
        pid,
        action="doc_edit",
        doc_id=doc_id,
        title="Valuation",
        doc_type="valuation",
        title_ar="التقييم",
        title_fr="Évaluation",
    )
    versions = _content(db, pid)["translations"]
    assert versions["ar"]["documents"][doc_id] == {"title": "التقييم"}
    page = (await client.get(f"/admin/listing/{pid}")).text
    assert 'value="التقييم"' in page and 'value="Évaluation"' in page
    # blank removes it
    await _post(
        client,
        pid,
        action="doc_edit",
        doc_id=doc_id,
        title="Valuation",
        doc_type="valuation",
        title_ar="",
        title_fr="Évaluation",
    )
    versions = _content(db, pid)["translations"]
    assert "ar" not in versions and versions["fr"]["documents"][doc_id] == {"title": "Évaluation"}


@pytest.mark.asyncio
async def test_without_the_script_the_files_still_upload_with_their_names(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="stage-f")
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "upload_doc",
            "title": "Brochure",
            "doc_type": "other",
            "title_ar": "الكتيب",
        },
        files={"file": ("brochure.pdf", PDF, "application/pdf")},
    )
    assert "Uploaded “Brochure”." in r.text
    doc_id = str(db("SELECT id FROM documents WHERE property_id=:p", p=pid)[0][0])
    assert _content(db, pid)["translations"]["ar"]["documents"][doc_id] == {"title": "الكتيب"}
