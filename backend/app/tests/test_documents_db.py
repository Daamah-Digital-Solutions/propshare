"""Group 2 — DB-backed tests for storage / documents / certificates.

Acceptance: real storage roundtrip + key safety; owner-scoped property-document upload
(non-owner → 403); public list + public download (draft property → 404; user-scoped doc
→ 403); size/empty guards; live PDF certificate from real holding (404 when none); real
property-image + avatar upload via the storage seam; public file route serves assets and
rejects non-public prefixes.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.integrations import storage

PW = "Passw0rd!23"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture(autouse=True)
def _local_storage(monkeypatch, tmp_path):
    """Point the storage seam at a per-test tmp dir (hermetic; no repo pollution)."""
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "storage_provider", "local", raising=False)
    monkeypatch.setattr(s, "storage_dir", str(tmp_path), raising=False)
    yield


# --- helpers ---------------------------------------------------------------- #
async def _user(client, db, email: str) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "U"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    return r.json()["access_token"], str(uid)


async def _owner(client, db, email: str) -> tuple[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Owner"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'owner')", i=uid)
    db("UPDATE users SET active_role='owner' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"], str(uid)


def _seed_property(
    db, owner_id: str | None, *, status: str = "active", slug: str | None = None
) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,owner_id,title,slug,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,:o,'Prop',:slug,'Dubai','residential','ready-income',:st,1000000,100,100,100,100)",
        id=pid,
        o=owner_id,
        slug=slug or f"p-{pid[:8]}",
        st=status,
    )
    return pid


def _ledger(db, user_id: str, property_id: str, units: int) -> None:
    db(
        "INSERT INTO ownership_ledger (user_id,property_id,units,unit_price,reason) "
        "VALUES (:u,:p,:n,100,'purchase')",
        u=user_id,
        p=property_id,
        n=units,
    )


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


# --- storage seam (direct) -------------------------------------------------- #
def test_storage_roundtrip_and_key_safety():
    storage.save("documents/x/a.txt", b"hello", "text/plain")
    assert storage.load("documents/x/a.txt") == b"hello"
    storage.delete("documents/x/a.txt")
    with pytest.raises(storage.StorageNotFound):
        storage.load("documents/x/a.txt")
    for bad in ("../etc/passwd", "/abs", "a/../b"):
        with pytest.raises(storage.StorageKeyError):
            storage.save(bad, b"x")
    assert storage.public_url("property-images/p/i.png") == "/api/v1/files/property-images/p/i.png"


# --- property documents ----------------------------------------------------- #
async def test_owner_uploads_then_public_lists_and_downloads(client, db):
    tok, oid = await _owner(client, db, "doc-owner@x.com")
    pid = _seed_property(db, oid, status="active")
    up = await client.post(
        f"/api/v1/properties/{pid}/documents",
        files={"file": ("valuation.pdf", b"%PDF-1.4 fake valuation", "application/pdf")},
        data={"title": "Valuation Report", "doc_type": "valuation"},
        headers=_h(tok),
    )
    assert up.status_code == 201, up.text
    doc = up.json()
    assert doc["title"] == "Valuation Report"

    # public list (no auth)
    listed = await client.get(f"/api/v1/properties/{pid}/documents")
    assert listed.status_code == 200
    assert [d["title"] for d in listed.json()] == ["Valuation Report"]

    # public download streams the real bytes
    dl = await client.get(doc["download_url"])
    assert dl.status_code == 200
    assert dl.content == b"%PDF-1.4 fake valuation"
    assert dl.headers["content-type"].startswith("application/pdf")


async def test_non_owner_cannot_upload_document(client, db):
    _tok_a, oid_a = await _owner(client, db, "doc-a@x.com")
    tok_b, _oid_b = await _owner(client, db, "doc-b@x.com")
    pid = _seed_property(db, oid_a)
    up = await client.post(
        f"/api/v1/properties/{pid}/documents",
        files={"file": ("x.pdf", b"x", "application/pdf")},
        data={"title": "Sneaky", "doc_type": "doc"},
        headers=_h(tok_b),
    )
    assert up.status_code == 403 and up.json()["error"]["code"] == "NOT_PROPERTY_OWNER"


async def test_draft_property_document_not_publicly_downloadable(client, db):
    tok, oid = await _owner(client, db, "doc-draft@x.com")
    pid = _seed_property(db, oid, status="draft")
    up = await client.post(
        f"/api/v1/properties/{pid}/documents",
        files={"file": ("x.pdf", b"secret", "application/pdf")},
        data={"title": "Draft Doc", "doc_type": "doc"},
        headers=_h(tok),
    )
    assert up.status_code == 201
    # public list 404s (property not public) and download 404s too
    assert (await client.get(f"/api/v1/properties/{pid}/documents")).status_code == 404
    assert (await client.get(up.json()["download_url"])).status_code == 404


async def test_empty_upload_rejected(client, db):
    tok, oid = await _owner(client, db, "doc-empty@x.com")
    pid = _seed_property(db, oid)
    up = await client.post(
        f"/api/v1/properties/{pid}/documents",
        files={"file": ("x.pdf", b"", "application/pdf")},
        data={"title": "Empty", "doc_type": "doc"},
        headers=_h(tok),
    )
    assert up.status_code == 422


# --- certificates ----------------------------------------------------------- #
async def test_certificate_pdf_from_real_holding(client, db):
    tok, uid = await _user(client, db, "cert-holder@x.com")
    pid = _seed_property(db, None, slug="cert-prop")
    _ledger(db, uid, pid, 12)
    r = await client.get(f"/api/v1/investments/certificate/{pid}", headers=_h(tok))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert b"Prop" in r.content  # real property title in the document
    assert b"12 fractional ownership" in r.content  # real units from the ledger (attestation)
    assert b"CapiMax PropShare" in r.content  # branded header


async def test_certificate_404_without_holding(client, db):
    tok, _uid = await _user(client, db, "cert-none@x.com")
    pid = _seed_property(db, None)
    r = await client.get(f"/api/v1/investments/certificate/{pid}", headers=_h(tok))
    assert r.status_code == 404 and r.json()["error"]["code"] == "NO_HOLDING"


async def test_certificate_requires_auth(client, db):
    pid = _seed_property(db, None)
    assert (await client.get(f"/api/v1/investments/certificate/{pid}")).status_code == 401


async def test_certificates_zip_bundles_all_holdings(client, db):
    import io
    import zipfile

    tok, uid = await _user(client, db, "cert-zip@x.com")
    p1 = _seed_property(db, None, slug="zip-a")
    p2 = _seed_property(db, None, slug="zip-b")
    _ledger(db, uid, p1, 5)
    _ledger(db, uid, p2, 7)
    r = await client.get("/api/v1/investments/certificates.zip", headers=_h(tok))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert len(names) == 2 and all(n.endswith(".pdf") for n in names)
    assert zf.read(names[0]).startswith(b"%PDF")


async def test_certificates_zip_404_without_holdings(client, db):
    tok, _uid = await _user(client, db, "cert-zip-none@x.com")
    r = await client.get("/api/v1/investments/certificates.zip", headers=_h(tok))
    assert r.status_code == 404 and r.json()["error"]["code"] == "NO_HOLDING"


# --- property image + avatar uploads (storage seam, no more 503) ------------ #
async def test_property_image_upload_appends_and_serves(client, db):
    tok, oid = await _owner(client, db, "img-owner@x.com")
    pid = _seed_property(db, oid)
    up = await client.post(
        f"/api/v1/properties/{pid}/images",
        files={"file": ("photo.png", PNG, "image/png")},
        headers=_h(tok),
    )
    assert up.status_code == 201, up.text
    images = up.json()["images"]
    assert len(images) == 1 and "/api/v1/files/property-images/" in images[0]
    # the public file route serves the stored bytes inline
    served = await client.get(images[0])
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"


async def test_avatar_upload_sets_profile_url(client, db):
    tok, _uid = await _user(client, db, "avatar@x.com")
    up = await client.post(
        "/api/v1/profiles/me/avatar",
        files={"file": ("me.png", PNG, "image/png")},
        headers=_h(tok),
    )
    assert up.status_code == 200, up.text
    assert "/api/v1/files/avatars/" in up.json()["avatar_url"]


async def test_public_file_route_rejects_non_public_prefix(client, db):
    # documents/ is not a public prefix — must not be served inline
    assert (await client.get("/api/v1/files/documents/whatever.pdf")).status_code == 404
