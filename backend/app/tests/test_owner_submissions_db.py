"""Owner listing submissions (client feedback #4).

* submitting tells the owner (in-app + email), the admins (in-app) and the support inbox;
* a submission is "under listing", not listed: it waits in Owner Submissions and stays out
  of Listings / Properties until approved;
* staff decide with a message the owner sees (request changes -> the owner edits and
  resubmits; decline -> closed for good; approve -> live), and every step is recorded;
* the owner's file shows their account, identity check, listings and documents.
"""

# ruff: noqa: E501
from __future__ import annotations

import uuid

import pytest

from app.core.config import get_settings

PW = "Passw0rd!23"
LISTING = {
    "title": "Cristamar Residence",
    "property_type": "apartment",
    "location": "Marbella, Spain",
    "description": "Sea-view apartments.",
    "total_value": 1000000,
    "unit_price": 100,
    "total_units": 10000,
    "minimum_investment": 500,
    "expected_yield": 7,
    "capital_appreciation": 3,
    "total_return": 10,
}


@pytest.fixture(autouse=True)
def _local_storage(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "storage_provider", "local", raising=False)
    monkeypatch.setattr(s, "storage_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(s, "support_inbox_email", "support@t.io", raising=False)
    yield


async def _login(client, email: str) -> dict:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _user(client, db, email: str, role: str, phone: str | None = None) -> tuple[str, dict]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Hassan Owner"}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db(
        "INSERT INTO user_roles (user_id, role) VALUES (:i, :r) ON CONFLICT DO NOTHING",
        i=uid,
        r=role,
    )
    db("UPDATE users SET active_role=:r, phone=:p WHERE id=:i", r=role, p=phone, i=uid)
    return str(uid), await _login(client, email)


async def _admin_panel(client, db, email="owners-admin@x.com") -> tuple[str, dict]:
    uid, headers = await _user(client, db, email, "admin")
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert r.status_code in (200, 302, 303), r.text
    return uid, headers


async def _submitted(client, db, headers) -> str:
    created = await client.post("/api/v1/properties", json=LISTING, headers=headers)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    up = await client.post(
        f"/api/v1/properties/{pid}/documents",
        files={"file": ("title-deed.pdf", b"%PDF-1.4 deed", "application/pdf")},
        data={"title": "Title deed", "doc_type": "legal"},
        headers=headers,
    )
    assert up.status_code == 201, up.text
    r = await client.post(f"/api/v1/properties/{pid}/submit", headers=headers)
    assert r.status_code == 200, r.text
    return pid


def _notices(db, uid: str) -> list[str]:
    return [
        r[0]
        for r in db("SELECT title FROM notifications WHERE user_id=:u ORDER BY created_at", u=uid)
    ]


def _emails(db, to: str) -> list[str]:
    return [
        r[0]
        for r in db("SELECT subject FROM email_outbox WHERE to_email=:t ORDER BY created_at", t=to)
    ]


@pytest.mark.asyncio
async def test_submitting_tells_the_owner_the_admins_and_the_support_inbox(client, db):
    admin_id, _ = await _user(client, db, "adm@own.io", "admin")
    owner_id, oh = await _user(client, db, "hassan@own.io", "owner", phone="+971500000001")
    pid = await _submitted(client, db, oh)

    row = db("SELECT status, submitted_at, review_note FROM properties WHERE id=:p", p=pid)[0]
    assert row[0] == "under_review" and row[1] is not None and row[2] is None
    assert _notices(db, owner_id) == ["Listing received — under review"]
    assert _emails(db, "hassan@own.io") == ["Listing received — under review"]
    assert _notices(db, admin_id) == ["Owner listing waiting for review"]
    inbox = db("SELECT subject, body FROM email_outbox WHERE to_email='support@t.io'")
    assert len(inbox) == 1
    assert "Cristamar Residence" in inbox[0][0] and "Hassan Owner" in inbox[0][0]
    assert "+971500000001" in inbox[0][1] and f"/admin/owner-submissions/{pid}" in inbox[0][1]
    # the owner reads the real state, not a funding badge
    mine = (await client.get("/api/v1/owner/properties", headers=oh)).json()
    assert mine[0]["status"] == "under_review" and mine[0]["submitted_at"]


@pytest.mark.asyncio
async def test_request_changes_then_resubmit_then_approve(client, db):
    _, ah = await _user(client, db, "adm2@own.io", "admin")
    owner_id, oh = await _user(client, db, "owner2@own.io", "owner")
    pid = await _submitted(client, db, oh)

    # a message is required: the owner must know what to change
    r = await client.post(f"/api/v1/admin/properties/{pid}/request-changes", json={}, headers=ah)
    assert r.status_code == 422 and r.json()["error"]["code"] == "NOTE_REQUIRED"
    r = await client.post(
        f"/api/v1/admin/properties/{pid}/request-changes",
        json={"reason": "Please upload the latest valuation report."},
        headers=ah,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft" and r.json()["review_outcome"] == "changes_requested"
    mine = (await client.get("/api/v1/owner/properties", headers=oh)).json()[0]
    assert mine["review_note"] == "Please upload the latest valuation report."
    assert mine["reviewed_at"]
    notice = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title='Changes requested on your listing'",
        u=owner_id,
    )
    assert "latest valuation report" in notice[0][0]
    assert "Changes requested on your listing" in _emails(db, "owner2@own.io")

    # the owner fixes the listing (incl. the minimum, which PATCH used to drop) and resubmits
    r = await client.patch(
        f"/api/v1/properties/{pid}", json={"minimum_investment": 1000}, headers=oh
    )
    assert r.status_code == 200 and r.json()["minimum_investment"] == 1000
    r = await client.post(f"/api/v1/properties/{pid}/submit", headers=oh)
    assert r.status_code == 200
    assert r.json()["status"] == "under_review" and r.json()["review_note"] is None
    assert "Listing resubmitted — under review" in _notices(db, owner_id)
    assert (
        db(
            "SELECT count(*) FROM audit_log WHERE action='property.submit'"
            " AND entity_id=:p AND after->>'resubmission' = 'true'",
            p=pid,
        )[0][0]
        == 1
    )

    r = await client.post(f"/api/v1/admin/properties/{pid}/approve", headers=ah)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active" and r.json()["review_outcome"] == "approved"
    assert "Your listing is live" in _notices(db, owner_id)
    assert (await client.get(f"/api/v1/properties/{pid}")).status_code == 200


@pytest.mark.asyncio
async def test_decline_is_final_needs_a_message_and_stays_private(client, db):
    _, ah = await _user(client, db, "adm3@own.io", "admin")
    owner_id, oh = await _user(client, db, "owner3@own.io", "owner")
    pid = await _submitted(client, db, oh)

    r = await client.post(f"/api/v1/admin/properties/{pid}/decline", json={}, headers=ah)
    assert r.status_code == 422
    r = await client.post(
        f"/api/v1/admin/properties/{pid}/decline",
        json={"reason": "We only list income-producing assets for now."},
        headers=ah,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed" and r.json()["review_outcome"] == "declined"
    assert (await client.get(f"/api/v1/properties/{pid}")).status_code == 404
    assert (await client.post(f"/api/v1/properties/{pid}/submit", headers=oh)).status_code == 409
    # never listed, so never in the admin's Listings: it stays in Owner Submissions
    await client.post("/admin/login", data={"username": "adm3@own.io", "password": PW})
    assert "Cristamar Residence" not in (await client.get("/admin/listing/")).text
    assert "Cristamar Residence" not in (await client.get("/admin/property/list")).text
    decided = await client.get("/admin/owner-submissions?show=decided")
    assert "Cristamar Residence" in decided.text and "Not approved" in decided.text
    msg = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title='Your listing was not approved'",
        u=owner_id,
    )
    assert "income-producing" in msg[0][0]


@pytest.mark.asyncio
async def test_submissions_live_in_their_own_queue_not_in_listings(client, db):
    await _admin_panel(client, db)
    owner_id, oh = await _user(client, db, "owner4@own.io", "owner", phone="+971500000004")
    pid = await _submitted(client, db, oh)
    platform = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,slug,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES (:id,'Platform Tower',"
        "'platform-tower-x1','Dubai','apartment','ready-income','draft',100000,100,1000,1000,100)",
        id=platform,
    )

    queue = await client.get("/admin/owner-submissions")
    assert queue.status_code == 200, queue.text
    assert "Cristamar Residence" in queue.text and "Platform Tower" not in queue.text
    assert "owner4@own.io" in queue.text and "Waiting for review" in queue.text

    listings = await client.get("/admin/listing/")
    assert "Platform Tower" in listings.text and "Cristamar Residence" not in listings.text
    assert "waiting for review" in listings.text  # a pointer to the queue
    raw = await client.get("/admin/property/list")
    assert raw.status_code == 200
    assert "Platform Tower" in raw.text and "Cristamar Residence" not in raw.text

    # the review page: owner, contact, documents, history
    page = await client.get(f"/admin/owner-submissions/{pid}")
    assert page.status_code == 200
    for text in (
        "owner4@own.io",
        "+971500000004",
        "Title deed",
        "Submitted for review by the owner",
    ):
        assert text in page.text
    doc_id = db("SELECT id FROM documents WHERE property_id=:p", p=pid)[0][0]
    dl = await client.get(f"/admin/owner-document?doc={doc_id}")
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4 deed"

    # deciding from the page: a message is required for "request changes"
    r = await client.post(f"/admin/owner-submissions/{pid}", data={"action": "request_changes"})
    assert r.status_code == 400 and "Write what the owner should change" in r.text
    r = await client.post(
        f"/admin/owner-submissions/{pid}",
        data={"action": "request_changes", "note": "Add the service-charge statement."},
    )
    assert r.status_code == 303
    assert db("SELECT status, review_note FROM properties WHERE id=:p", p=pid)[0] == (
        "draft",
        "Add the service-charge statement.",
    )
    assert "Changes requested on your listing" in _notices(db, owner_id)
    page = await client.get(f"/admin/owner-submissions/{pid}?done=request_changes")
    assert (
        "Sent back to the owner" in page.text and "Add the service-charge statement." in page.text
    )
    # still not a listing
    assert "Cristamar Residence" not in (await client.get("/admin/listing/")).text

    # approving joins it to the listings
    await client.post(f"/api/v1/properties/{pid}/submit", headers=oh)
    r = await client.post(f"/admin/owner-submissions/{pid}", data={"action": "approve"})
    assert r.status_code == 303, r.text
    assert "Cristamar Residence" in (await client.get("/admin/listing/")).text
    assert "Cristamar Residence" in (await client.get("/admin/property/list")).text
    # a decided submission cannot be decided again from the page
    r = await client.post(
        f"/admin/owner-submissions/{pid}", data={"action": "decline", "note": "late"}
    )
    assert r.status_code == 400 and "already decided" in r.text


@pytest.mark.asyncio
async def test_owner_file_shows_account_identity_listings_and_documents(client, db):
    await _admin_panel(client, db, "file-admin@x.com")
    owner_id, oh = await _user(client, db, "owner5@own.io", "owner", phone="+971500000005")
    pid = await _submitted(client, db, oh)

    owners = await client.get("/admin/property-owners")
    assert owners.status_code == 200
    assert "owner5@own.io" in owners.text and "1 waiting" in owners.text
    page = await client.get(f"/admin/property-owners/{owner_id}")
    assert page.status_code == 200
    for text in ("Hassan Owner", "+971500000005", "Cristamar Residence", "Title deed", "KYB"):
        assert text in page.text
    assert f"/admin/owner-submissions/{pid}" in page.text


@pytest.mark.asyncio
async def test_owner_pages_are_for_full_admins_only(client, db):
    # anonymous -> login
    r = await client.get("/admin/owner-submissions")
    assert r.status_code in (302, 303) and "/admin/login" in r.headers.get("location", "")
    # a content editor reaches the Listing Editor but not the owners' files
    await _user(client, db, "editor@own.io", "content_editor")
    r = await client.post("/admin/login", data={"username": "editor@own.io", "password": PW})
    assert r.status_code in (200, 302, 303)
    assert (await client.get("/admin/owner-submissions")).status_code == 403
    assert (await client.get("/admin/property-owners")).status_code == 403
