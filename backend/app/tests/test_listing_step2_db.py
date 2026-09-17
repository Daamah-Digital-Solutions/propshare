"""Go-live audit, Step 2 — admin listing capabilities.

Each test reproduces the audited gap first:
  * a `.txt` renamed `.png` was accepted as a gallery image; a 2.3 MB PNG was stored verbatim
    -> now rejected / normalised (max 2000 px, JPEG);
  * no reorder / cover / delete for images (delete orphaned the file) -> Listing Editor
    actions, storage cleaned;
  * documents accepted any category and any file type; no delete/replace -> validated,
    delete removes the file, replace swaps it;
  * drafts were invisible with no way to preview -> signed 24h preview token;
  * admins could not create a property -> one place to create: the old raw create page
    redirects to the Listing Editor's New listing form;
  * content JSON was raw -> structured editors write validated sections.
"""

# ruff: noqa: E501  (long literal form payloads keep the scenarios readable)
from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from app.services import listing_media_service, listing_service, property_service
from app.services.integrations import storage

PW = "Passw0rd!23"
ADMIN_EMAIL = "step2-admin@x.com"


def _png(w: int, h: int, alpha: bool = False) -> bytes:
    im = Image.new(
        "RGBA" if alpha else "RGB", (w, h), (30, 120, 80, 128) if alpha else (30, 120, 80)
    )
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


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
    assert "session" in client.cookies, (r.status_code, r.headers.get("location"), r.text[:300])
    return str(uid)


async def _owner(client, db, email: str) -> tuple[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Owner"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'owner')", i=uid)
    db("UPDATE users SET active_role='owner' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"], str(uid)


def _seed_property(db, *, owner_id=None, status="draft", slug="step2-tower") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,owner_id,title,slug,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,:o,'Step2 Tower',:s,'London','residential','ready-income',:st,1000000,100,100,100,100)",
        id=pid,
        o=owner_id,
        s=slug,
        st=status,
    )
    return pid


# --- image processing ------------------------------------------------------------------ #
def test_process_image_rejects_non_images_and_normalises_large_ones():
    from app.core.errors import AppError

    with pytest.raises(AppError) as exc:
        listing_media_service.process_image(b"hello, not an image")
    assert exc.value.code == "INVALID_IMAGE"
    blob, ext, ctype = listing_media_service.process_image(_png(3000, 1500))
    im = Image.open(io.BytesIO(blob))
    assert (ext, ctype, im.format) == ("jpg", "image/jpeg", "JPEG")
    assert max(im.size) == 2000 and im.size == (2000, 1000)  # aspect kept, longest edge capped
    blob2, ext2, _ = listing_media_service.process_image(_png(50, 50, alpha=True))
    assert ext2 == "png" and Image.open(io.BytesIO(blob2)).mode == "RGBA"  # transparency kept


@pytest.mark.asyncio
async def test_owner_image_upload_validates_and_resizes(client, db):
    tok, oid = await _owner(client, db, "img2@x.com")
    pid = _seed_property(db, owner_id=oid)
    h = {"Authorization": f"Bearer {tok}"}
    bad = await client.post(
        f"/api/v1/properties/{pid}/images",
        files={"file": ("not-an-image.png", b"plain text", "image/png")},
        headers=h,
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_IMAGE"
    ok = await client.post(
        f"/api/v1/properties/{pid}/images",
        files={"file": ("big.png", _png(2600, 1300), "image/png")},
        headers=h,
    )
    assert ok.status_code == 201, ok.text
    url = ok.json()["images"][0]
    assert url.endswith(".jpg")
    stored = Image.open(io.BytesIO(storage.load(listing_media_service.url_to_key(url))))
    assert stored.size == (2000, 1000)


# --- Listing Editor page ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_listing_editor_media_reorder_cover_delete_cleans_storage(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db)
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_images"},
        files=[
            ("files", ("a.png", _png(400, 300), "image/png")),
            ("files", ("b.png", _png(400, 300), "image/png")),
            ("files", ("c.png", _png(400, 300), "image/png")),
        ],
    )
    assert r.status_code == 200 and "Added 3 photo(s)" in r.text
    imgs = db("SELECT images FROM properties WHERE id=:i", i=pid)[0][0]
    assert len(imgs) == 3
    a, b, c = imgs
    # make the last one the cover
    r = await client.post(f"/admin/listing/{pid}", data={"action": "image_cover", "url": c})
    assert r.status_code == 200
    assert db("SELECT images FROM properties WHERE id=:i", i=pid)[0][0] == [c, a, b]
    # move b up one slot
    r = await client.post(f"/admin/listing/{pid}", data={"action": "image_up", "url": b})
    assert db("SELECT images FROM properties WHERE id=:i", i=pid)[0][0] == [c, b, a]
    # delete a -> row entry gone AND the file gone
    key = listing_media_service.url_to_key(a)
    assert storage.load(key)
    r = await client.post(f"/admin/listing/{pid}", data={"action": "image_delete", "url": a})
    assert db("SELECT images FROM properties WHERE id=:i", i=pid)[0][0] == [c, b]
    with pytest.raises(storage.StorageNotFound):
        storage.load(key)
    acts = [r[0] for r in db("SELECT action FROM audit_log WHERE entity_id=:i", i=pid)]
    assert {"property.images.add", "property.images.reorder", "property.images.remove"} <= set(acts)


@pytest.mark.asyncio
async def test_listing_editor_documents_validate_delete_replace(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db)
    # invalid category
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_doc", "title": "DD", "doc_type": "due_diligence"},
        files={"file": ("dd.pdf", b"%PDF-1.4 x", "application/pdf")},
    )
    assert r.status_code == 400 and "category must be one of" in r.text
    # disallowed type (extension) and spoofed type (magic bytes)
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_doc", "title": "Bad", "doc_type": "other"},
        files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
    )
    assert "Allowed file types" in r.text
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_doc", "title": "Fake", "doc_type": "other"},
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert "not a valid .pdf" in r.text
    assert db("SELECT count(*) FROM documents WHERE property_id=:p", p=pid)[0][0] == 0
    # valid upload
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_doc", "title": "Valuation", "doc_type": "valuation"},
        files={"file": ("val.pdf", b"%PDF-1.4 v1", "application/pdf")},
    )
    assert "Uploaded" in r.text
    doc_id, key = db("SELECT id, file_url FROM documents WHERE property_id=:p", p=pid)[0]
    # replace swaps the file (old one removed)
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "doc_replace", "doc_id": str(doc_id)},
        files={"file": ("val-v2.pdf", b"%PDF-1.4 v2", "application/pdf")},
    )
    assert "replaced" in r.text
    key2 = db("SELECT file_url FROM documents WHERE id=:i", i=doc_id)[0][0]
    assert key2 != key and storage.load(key2) == b"%PDF-1.4 v2"
    with pytest.raises(storage.StorageNotFound):
        storage.load(key)
    # delete removes row + file
    r = await client.post(
        f"/admin/listing/{pid}", data={"action": "doc_delete", "doc_id": str(doc_id)}
    )
    assert "deleted" in r.text
    assert db("SELECT count(*) FROM documents WHERE id=:i", i=doc_id)[0][0] == 0
    with pytest.raises(storage.StorageNotFound):
        storage.load(key2)


@pytest.mark.asyncio
async def test_admin_property_delete_cleans_storage_and_refuses_with_positions(client, db):
    """Deleting a property row used to orphan its photos and document files; and a property
    with investor positions could be deleted outright (ledger rows pointing nowhere)."""
    uid = await _admin_session(client, db)
    pid = _seed_property(db)
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_images"},
        files=[("files", ("a.png", _png(200, 100), "image/png"))],
    )
    assert "Added 1 photo(s)" in r.text
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "upload_doc", "title": "Deed", "doc_type": "legal"},
        files={"file": ("deed.pdf", b"%PDF-1.4 deed", "application/pdf")},
    )
    assert "Uploaded" in r.text
    (img_url,) = db("SELECT images FROM properties WHERE id=:i", i=pid)[0][0]
    img_key = listing_media_service.url_to_key(img_url)
    doc_key = db("SELECT file_url FROM documents WHERE property_id=:p", p=pid)[0][0]
    assert storage.load(img_key) and storage.load(doc_key)

    # investors hold units -> refused, nothing removed
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) "
        "VALUES (:u,:p,2,100,'purchase')",
        u=uid,
        p=pid,
    )
    r = await client.delete(f"/admin/property/delete?pks={pid}")
    assert r.status_code in (200, 302, 303)
    assert db("SELECT count(*) FROM properties WHERE id=:i", i=pid)[0][0] == 1
    assert storage.load(img_key) and storage.load(doc_key)

    # no positions -> row, cascaded document row, and BOTH stored files are gone (+ audit)
    db("DELETE FROM ownership_ledger WHERE property_id=:p", p=pid)
    r = await client.delete(f"/admin/property/delete?pks={pid}")
    assert r.status_code in (200, 302, 303), r.text[:300]
    assert db("SELECT count(*) FROM properties WHERE id=:i", i=pid)[0][0] == 0
    assert db("SELECT count(*) FROM documents WHERE property_id=:p", p=pid)[0][0] == 0
    for key in (img_key, doc_key):
        with pytest.raises(storage.StorageNotFound):
            storage.load(key)
    acts = [r[0] for r in db("SELECT action FROM audit_log WHERE entity_id=:i", i=pid)]
    assert "property.admin_delete" in acts


@pytest.mark.asyncio
async def test_preview_token_shows_draft_only_with_valid_token(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db, status="draft", slug="draft-preview")
    other = _seed_property(db, status="draft", slug="other-draft")
    assert (await client.get(f"/api/v1/properties/{pid}")).status_code == 404
    r = await client.post(f"/admin/listing/{pid}", data={"action": "make_preview"})
    assert r.status_code == 200 and "?preview=" in r.text
    token = r.text.split("?preview=", 1)[1].split('"', 1)[0]
    ok = await client.get(f"/api/v1/properties/draft-preview?preview={token}")
    assert ok.status_code == 200 and ok.json()["status"] == "draft"
    assert (
        await client.get(f"/api/v1/properties/draft-preview/documents?preview={token}")
    ).status_code == 200
    # token is property-scoped and tamper-proof
    assert (await client.get(f"/api/v1/properties/{other}?preview={token}")).status_code == 404
    assert (await client.get(f"/api/v1/properties/{pid}?preview={token}x")).status_code == 404
    assert property_service.verify_preview_token(token, uuid.UUID(pid))
    # still hidden from the public list
    assert all(p["id"] != pid for p in (await client.get("/api/v1/properties")).json()["items"])


@pytest.mark.asyncio
async def test_old_raw_create_form_redirects_to_new_listing_form(client, db):
    """There used to be two places to add a property. The raw SQLAdmin create page skipped the
    listing rules (typed units, unchecked minimum, no returns), so it now redirects to the
    Listing Editor's New listing form, and a POST to it creates nothing."""
    await _admin_session(client, db)
    r = await client.get("/admin/property/create", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/listing/new"
    # trailing slash: Starlette strips it first, then the same redirect applies
    slash = await client.get("/admin/property/create/", follow_redirects=True)
    assert str(slash.url).endswith("/admin/listing/new") and slash.status_code == 200
    r = await client.post(
        "/admin/property/create",
        data={
            "title": "Admin Created Tower",
            "model": "installment",
            "property_type": "residential",
            "location": "Docklands, London",
            "total_value": "1700000",
            "unit_price": "100",
            "total_units": "17000",
            "minimum_investment": "100",
            "content": "{}",
            "fees": "{}",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/admin/listing/new"
    assert db("SELECT count(*) FROM properties WHERE title='Admin Created Tower'")[0][0] == 0
    # the redirect lands on the working New listing form
    landing = await client.get("/admin/property/create", follow_redirects=True)
    assert landing.status_code == 200 and "Create draft listing" in landing.text
    # the Properties list no longer offers a create button; raw edit still works for admins
    listing = await client.get("/admin/property/list")
    assert listing.status_code == 200 and "/admin/property/create" not in listing.text
    # ...and instead links to the Listing Editor from its header
    assert (
        '<a href="/admin/listing/new" class="btn btn-primary" data-new-listing>+ New listing</a>'
        in listing.text
    )
    assert (
        '<a href="/admin/listing/" class="btn btn-secondary" data-listing-index>All listings</a>'
        in listing.text
    )
    assert "Export" in listing.text  # the standard header buttons are still there
    pid = _seed_property(db)
    assert (await client.get(f"/admin/property/edit/{pid}")).status_code == 200


@pytest.mark.asyncio
async def test_listing_editor_structured_content_sections(client, db):
    await _admin_session(client, db)
    pid = _seed_property(db)
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "save_facts",
            "bedrooms": "2",
            "bathrooms": "2",
            "area": "1235",
            "parking": "1",
            "max_investment": "",
            "amenities": "Concierge\nSpa\nConcierge\n",
        },
    )
    assert "Key facts saved" in r.text
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "save_terms",
            "distribution_frequency": "Monthly",
            "investment_term": "7–10 years",
            "exit_options": "",
            "performance_fee": "8",
            "exit_fee": "",
        },
    )
    assert "Terms saved" in r.text
    r = await client.post(
        f"/admin/listing/{pid}",
        data={
            "action": "save_developer",
            "name": "Crestmark Estates",
            "rating": "4.8",
            "projects_completed": "184",
        },
    )
    assert "Developer saved" in r.text
    content = db("SELECT content FROM properties WHERE id=:i", i=pid)[0][0]
    assert content["details"] == {
        "bedrooms": 2,
        "bathrooms": 2,
        "area": 1235.0,
        "parking": 1,
        "amenities": ["Concierge", "Spa"],
    }
    assert content["terms"] == {"distributionFrequency": "Monthly", "investmentTerm": "7–10 years"}
    assert content["fees"] == {"performance": 8.0}
    assert content["developer"] == {
        "name": "Crestmark Estates",
        "rating": 4.8,
        "projectsCompleted": 184,
    }
    # validation: rating out of range -> error, nothing changed
    r = await client.post(
        f"/admin/listing/{pid}", data={"action": "save_developer", "name": "X", "rating": "7"}
    )
    assert "between 0 and 5" in r.text
    assert (
        db("SELECT content->'developer'->>'name' FROM properties WHERE id=:i", i=pid)[0][0]
        == "Crestmark Estates"
    )


def test_listing_service_pure_validators():
    assert listing_service.parse_amenities("a, b,, a\n c ") == ["a", "b", "c"]
    c = listing_service.with_spv(
        {"other": 1}, {"jurisdiction": " England  & Wales ", "trustee": "", "auditor": "KPMG"}
    )
    assert c == {"other": 1, "spv": {"jurisdiction": "England & Wales", "auditor": "KPMG"}}
