"""The beneficiary's record, certificate and claim (client, 2026-10-07).

* the holder keeps a copy of the person's identity document with their record, can edit the
  record at any time, and downloads a certificate for them;
* that person submits a claim on a public page with the certificate and their own identity
  document; the holder and staff are told; the answer never says whether a record matched;
* staff review it in the admin panel beside the register and approve it: the claimant's
  share moves to the claimant's OWN verified account, the other beneficiaries' shares wait
  for their own claims, and the register closes.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import uuid

import pytest

from app.core.config import get_settings
from app.services import estate_service

PW = "Passw0rd!23"
PDF = b"%PDF-1.4 beneficiary certificate"
JPG = b"\xff\xd8\xff\xe0 a photo of an identity card"
PNG = b"\x89PNG\r\n\x1a\n the other side"


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "storage_provider", "local", raising=False)
    monkeypatch.setattr(s, "storage_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(s, "support_inbox_email", "support@t.io", raising=False)
    monkeypatch.setattr(s, "app_base_url", "https://capimaxpropshare.com", raising=False)
    yield


# --- arrange helpers -------------------------------------------------------- #
async def _user(
    client, db, email: str, name: str, *, verified: bool = True, role: str | None = None
) -> tuple[str, dict]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": name}
    )
    assert r.status_code == 201, r.text
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    if verified:
        db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    if role:
        db(
            "INSERT INTO user_roles (user_id, role) VALUES (:i,:r) ON CONFLICT DO NOTHING",
            i=uid,
            r=role,
        )
        db("UPDATE users SET active_role=:r WHERE id=:i", r=role, i=uid)
    tok = (await client.post("/api/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]
    return uid, {"Authorization": f"Bearer {tok}"}


def _property(db, title: str = "Marina Heights") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,:t,'Dubai','residential','ready-income','active',100000,100,1000,1000,100)",
        id=pid,
        t=title,
    )
    return pid


def _grant(db, uid: str, pid: str, units: int) -> None:
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) "
        "VALUES (:u,:p,:n,100,'purchase')",
        u=uid,
        p=pid,
        n=units,
    )


def _holding(db, uid: str, pid: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger "
            "WHERE user_id=:u AND property_id=:p",
            u=uid,
            p=pid,
        )[0][0]
    )


async def _beneficiary(client, h, **over) -> dict:
    body = {
        "full_name": "Fatima Mansouri",
        "relationship": "Daughter",
        "email": "fatima@heirs.io",
        "phone": "+971500000001",
        "allocation_pct": 60,
        "notes": "My eldest",
        "meta": {
            "role": "heir",
            "idType": "Passport",
            "idNumber": "A1234567",
            "scope": ["ownership", "wallet"],
            "trigger": "death",
        },
    }
    body.update(over)
    r = await client.post("/api/v1/estate/beneficiaries", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _claim_fields(certificate_no: str, **over) -> dict:
    fields = {
        "claimant_name": "Fatima Mansouri",
        "claimant_email": "fatima@heirs.io",
        "claimant_phone": "+971500000001",
        "claimant_country": "United Arab Emirates",
        "claimant_id_type": "Passport",
        "claimant_id_number": "a-1234567",
        "relationship": "Daughter",
        "holder_name": "Ahmed Mansouri",
        "holder_email": "ahmed@holders.io",
        "certificate_no": certificate_no,
        "reason": "death",
        "date_of_death": "2026-09-01",
        "details": "My father passed away in September.",
    }
    fields.update(over)
    return fields


async def _submit(client, fields: dict, *, headers: dict | None = None, evidence: bool = False):
    files = [
        ("certificate", ("certificate.pdf", PDF, "application/pdf")),
        ("identity", ("passport.jpg", JPG, "image/jpeg")),
    ]
    if evidence:
        files.append(("evidence", ("death-certificate.pdf", PDF + b" death", "application/pdf")))
    return await client.post(
        "/api/v1/estate/claims",
        data={"fields": json.dumps(fields)},
        files=files,
        headers=headers or {},
    )


async def _admin_login(client, db, email: str = "staff@adm.io") -> str:
    uid, _h = await _user(client, db, email, "Staff Admin", role="admin")
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert r.status_code in (200, 302, 303)
    return uid


# --- the record: edit, identity document, certificate ------------------------------ #
@pytest.mark.asyncio
async def test_a_record_can_be_edited_and_says_which_version_it_is(client, db):
    _owner, h = await _user(client, db, "ahmed@holders.io", "Ahmed Mansouri")
    b = await _beneficiary(client, h)
    assert b["certificate_no"].startswith("CPB-") and b["version"] == 1 and b["locked"] is False

    # a change to what the certificate prints is a new version...
    r = await client.patch(
        f"/api/v1/estate/beneficiaries/{b['id']}",
        json={
            "full_name": "Fatima A. Mansouri",
            "allocation_pct": 45,
            "phone": None,  # an optional field sent empty is cleared
            "meta": {**b["meta"], "idNumber": "B7654321"},
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    edited = r.json()
    assert (edited["full_name"], edited["allocation_pct"], edited["phone"]) == (
        "Fatima A. Mansouri",
        45,
        None,
    )
    assert edited["meta"]["idNumber"] == "B7654321" and edited["version"] == 2
    assert edited["certificate_no"] == b["certificate_no"]  # the number is the record's own
    assert edited["email"] == "fatima@heirs.io" and edited["notes"] == "My eldest"  # untouched

    # ...a private note is not
    r = await client.patch(
        f"/api/v1/estate/beneficiaries/{b['id']}", json={"notes": "Changed my mind"}, headers=h
    )
    assert r.json()["version"] == 2 and r.json()["notes"] == "Changed my mind"

    # the form's extras are kept to what the form has
    r = await client.patch(
        f"/api/v1/estate/beneficiaries/{b['id']}",
        json={"meta": {"role": "emperor", "scope": ["ownership", "the moon"], "extra": {"x": 1}}},
        headers=h,
    )
    assert r.json()["meta"] == {
        "role": "beneficiary",
        "idType": "Passport",
        "idNumber": "",
        "scope": ["ownership"],
        "trigger": "death",
    }
    # the name cannot be blanked, the total cannot pass 100%
    r = await client.patch(
        f"/api/v1/estate/beneficiaries/{b['id']}", json={"allocation_pct": 101}, headers=h
    )
    assert r.status_code == 422
    await _beneficiary(client, h, full_name="Omar Mansouri", email=None, allocation_pct=50)
    r = await client.patch(
        f"/api/v1/estate/beneficiaries/{b['id']}", json={"allocation_pct": 51}, headers=h
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "ALLOCATION_EXCEEDS_100"

    actions = [
        r[0]
        for r in db(
            "SELECT action FROM audit_log WHERE entity_id=:i ORDER BY created_at", i=b["id"]
        )
    ]
    assert actions[0] == "estate.beneficiary.added"
    assert actions.count("estate.beneficiary.updated") == 3
    # the trail says which fields changed, never their values
    changed = db(
        "SELECT after FROM audit_log WHERE entity_id=:i AND action='estate.beneficiary.updated' "
        "ORDER BY created_at LIMIT 1",
        i=b["id"],
    )[0][0]
    assert changed == {
        "changed": ["allocation_pct", "full_name", "id_number"],
        "version": 2,
    }


@pytest.mark.asyncio
async def test_the_holder_keeps_a_copy_of_the_persons_identity_document(client, db):
    _owner, h = await _user(client, db, "ahmed2@holders.io", "Ahmed Mansouri")
    _other, oh = await _user(client, db, "other2@holders.io", "Someone Else")
    b = await _beneficiary(client, h)
    url = f"/api/v1/estate/beneficiaries/{b['id']}/documents"

    r = await client.post(url, files={"file": ("passport.jpg", JPG, "image/jpeg")}, headers=h)
    assert r.status_code == 201, r.text
    docs = r.json()["documents"]
    assert [(d["filename"], d["content_type"], d["size"]) for d in docs] == [
        ("passport.jpg", "image/jpeg", len(JPG))
    ]
    assert "key" not in docs[0] and "estate-beneficiaries" not in json.dumps(r.json())

    # the holder alone can fetch it back
    got = await client.get(f"{url}/{docs[0]['id']}", headers=h)
    assert got.status_code == 200 and got.content == JPG
    assert got.headers["content-type"] == "image/jpeg"
    assert (await client.get(f"{url}/{docs[0]['id']}", headers=oh)).status_code == 404
    assert (await client.get(f"{url}/{docs[0]['id']}")).status_code == 401
    assert (
        await client.post(url, files={"file": ("x.jpg", JPG, "image/jpeg")}, headers=oh)
    ).status_code == 404

    # a photo or a PDF, by what the file is and not only by its name
    for name, data in (
        ("script.html", b"<script>alert(1)</script>"),
        ("fake.jpg", b"<html>not a photo</html>"),
        ("empty.pdf", b""),
    ):
        r = await client.post(url, files={"file": (name, data, "image/jpeg")}, headers=h)
        assert r.status_code in (415, 422), (name, r.status_code)
    r = await client.post(
        url,
        files={"file": ("big.pdf", b"%PDF" + b"0" * estate_service.MAX_UPLOAD_BYTES, "x")},
        headers=h,
    )
    assert r.status_code == 413

    # a few sides of a document, not a file store
    for i in range(estate_service.MAX_ID_DOCUMENTS - 1):
        r = await client.post(url, files={"file": (f"side{i}.png", PNG, "image/png")}, headers=h)
        assert r.status_code == 201
    r = await client.post(url, files={"file": ("one-more.png", PNG, "image/png")}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "TOO_MANY_FILES"

    r = await client.delete(f"{url}/{docs[0]['id']}", headers=h)
    assert r.status_code == 200
    assert len(r.json()["documents"]) == estate_service.MAX_ID_DOCUMENTS - 1
    assert (await client.get(f"{url}/{docs[0]['id']}", headers=h)).status_code == 404
    # adding or removing a copy changes nothing the certificate prints
    assert r.json()["version"] == 1


@pytest.mark.asyncio
async def test_the_certificate_states_the_record_and_where_to_claim(client, db):
    _owner, h = await _user(client, db, "ahmed3@holders.io", "Ahmed Mansouri")
    _other, oh = await _user(client, db, "other3@holders.io", "Someone Else")
    b = await _beneficiary(client, h)
    url = f"/api/v1/estate/beneficiaries/{b['id']}/certificate"

    r = await client.get(url, headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert f"beneficiary-certificate-{b['certificate_no']}.pdf" in r.headers["content-disposition"]
    for text in (
        "Certificate of Designation",
        "Fatima Mansouri",
        "Ahmed Mansouri",
        "as heir, with an allocation of 60%,",
        "Daughter",
        "Passport",
        "A1234567",
        "Ownership Rights, Wallet Balance",
        "On verified death",
        b["certificate_no"],
        "Version 1",
        "capimaxpropshare.com/estate-claim",
        "not a will",
    ):
        assert text.encode() in r.content, text
    # the QR code's page, with the number filled in
    assert (
        f"https://capimaxpropshare.com/estate-claim?certificate={b['certificate_no']}".encode()
        in r.content
    )
    assert (
        db(
            "SELECT count(*) FROM audit_log WHERE action='estate.certificate.issued' AND entity_id=:i",
            i=b["id"],
        )[0][0]
        == 1
    )

    # after an edit the same number, a new version
    await client.patch(
        f"/api/v1/estate/beneficiaries/{b['id']}", json={"allocation_pct": 30}, headers=h
    )
    r = await client.get(url, headers=h)
    assert b"Version 2" in r.content and b"with an allocation of 30%," in r.content

    # only the holder's own record
    assert (await client.get(url, headers=oh)).status_code == 404
    assert (await client.get(url)).status_code == 401

    # it is issued in English: a name the fonts cannot print is refused with what to do...
    arabic = await _beneficiary(
        client, h, full_name="فاطمة المنصوري", email=None, allocation_pct=10
    )
    r = await client.get(f"/api/v1/estate/beneficiaries/{arabic['id']}/certificate", headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "CERTIFICATE_LATIN_NAME"
    assert "Latin letters" in r.json()["error"]["message"]
    # ...and it must identify the person
    no_id = await _beneficiary(
        client,
        h,
        full_name="Omar Mansouri",
        email=None,
        allocation_pct=10,
        meta={"role": "beneficiary"},
    )
    r = await client.get(f"/api/v1/estate/beneficiaries/{no_id['id']}/certificate", headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "CERTIFICATE_NEEDS_ID"


# --- the public claim ---------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_claim_from_the_public_page_reaches_staff_and_the_holder(client, db):
    owner, h = await _user(client, db, "ahmed4@holders.io", "Ahmed Mansouri")
    b = await _beneficiary(client, h)
    # typed the way people type: lower case, spaces, no dashes
    typed = b["certificate_no"].lower().replace("-", " ")

    r = await _submit(client, _claim_fields(typed))
    assert r.status_code == 201, r.text
    claim = r.json()
    assert claim["reference"].startswith("CLM-") and claim["status"] == "submitted"
    assert claim["certificate_no"] == b["certificate_no"]
    assert [d["kind"] for d in claim["documents"]] == ["certificate", "identity"]
    # nothing in the answer says whether the number matched, or anything about the holder
    assert set(claim) == {
        "id",
        "reference",
        "status",
        "status_label",
        "reason",
        "holder_name",
        "certificate_no",
        "message",
        "documents",
        "can_add_documents",
        "created_at",
        "updated_at",
    }
    assert "estate-claims/" not in json.dumps(claim)

    row = db(
        "SELECT subject_user_id, beneficiary_id, claimant_user_id, date_of_death, documents "
        "FROM estate_claims WHERE reference=:r",
        r=claim["reference"],
    )[0]
    assert (str(row[0]), str(row[1]), row[2]) == (owner, b["id"], None)
    assert str(row[3]) == "2026-09-01" and len(row[4]) == 2

    # the claimant is written to (no account needed), with what happens next
    subject, body = db("SELECT subject, body FROM email_outbox WHERE to_email='fatima@heirs.io'")[0]
    assert subject == f"We received your claim ({claim['reference']})"
    assert "your own Capimax PropShare account" in body and "/auth" in body
    assert "Nobody is given access to the account holder's account." in body
    # staff are told, with whether the number is a record
    inbox = db("SELECT subject, body FROM email_outbox WHERE to_email='support@t.io'")[0]
    assert claim["reference"] in inbox[0]
    assert "matches a beneficiary record" in inbox[1] and "/admin/estate-claims/" in inbox[1]
    # the holder is told at once: a living holder is the one who can say it is false
    told = db(
        "SELECT title, message FROM notifications WHERE user_id=:u AND type='estate'", u=owner
    )[0]
    assert told[0] == "A claim was submitted about your account"
    assert "contact support now" in told[1]
    assert (
        db("SELECT count(*) FROM email_outbox WHERE user_id=:u AND category='security'", u=owner)[
            0
        ][0]
        == 1
    )

    # the same claim twice is one claim
    again = await _submit(client, _claim_fields(b["certificate_no"]))
    assert again.status_code == 409 and again.json()["error"]["code"] == "CLAIM_OPEN"

    # a number that is no record is accepted the same way: staff see it does not match
    unknown = await _submit(
        client, _claim_fields("CPB-0000-0000", claimant_email="someone@else.io")
    )
    assert unknown.status_code == 201 and set(unknown.json()) == set(claim)
    assert (
        db(
            "SELECT beneficiary_id FROM estate_claims WHERE reference=:r",
            r=unknown.json()["reference"],
        )[0][0]
        is None
    )
    assert (
        "matches NO beneficiary record"
        in db(
            "SELECT body FROM email_outbox WHERE to_email='support@t.io' ORDER BY created_at DESC"
        )[0][0]
    )


@pytest.mark.asyncio
async def test_a_claim_needs_its_fields_and_its_two_documents(client, db):
    async def post(fields: dict, files: list):
        return await client.post(
            "/api/v1/estate/claims", data={"fields": json.dumps(fields)}, files=files
        )

    cert = ("certificate", ("certificate.pdf", PDF, "application/pdf"))
    ident = ("identity", ("id.jpg", JPG, "image/jpeg"))
    good = _claim_fields("CPB-1111-2222")

    for change, code in (
        ({"claimant_name": ""}, "MISSING_FIELDS"),
        ({"holder_name": " "}, "MISSING_FIELDS"),
        ({"claimant_country": ""}, "MISSING_FIELDS"),
        ({"claimant_email": "not-an-address"}, "INVALID_EMAIL"),
        ({"reason": "because"}, "INVALID_REASON"),
        ({"date_of_death": None}, "DATE_REQUIRED"),
        ({"date_of_death": "2999-01-01"}, "INVALID_DATE"),
        ({"reason": "other", "details": ""}, "DETAILS_REQUIRED"),
    ):
        r = await post({**good, **change}, [cert, ident])
        assert r.status_code == 422 and r.json()["error"]["code"] == code, (change, r.text)

    # both documents, and real ones
    r = await client.post("/api/v1/estate/claims", data={"fields": json.dumps(good)}, files=[cert])
    assert r.status_code == 422
    r = await post(good, [cert, ("identity", ("id.jpg", b"<html>", "image/jpeg"))])
    assert r.status_code == 415
    r = await post(good, [("certificate", ("c.exe", b"MZ", "application/pdf")), ident])
    assert r.status_code == 415
    assert db("SELECT count(*) FROM estate_claims")[0][0] == 0

    # a reason that is not a death needs no date
    r = await post({**good, "reason": "incapacity", "date_of_death": None}, [cert, ident])
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_a_signed_in_claimant_follows_their_claim_and_adds_what_is_asked(client, db):
    _owner, h = await _user(client, db, "ahmed5@holders.io", "Ahmed Mansouri")
    b = await _beneficiary(client, h)
    claimant, ch = await _user(client, db, "fatima@heirs.io", "Fatima Mansouri")
    _stranger, xh = await _user(client, db, "stranger@heirs.io", "A Stranger")

    r = await _submit(client, _claim_fields(b["certificate_no"]), headers=ch)
    assert r.status_code == 201, r.text
    claim = r.json()
    assert (
        str(db("SELECT claimant_user_id FROM estate_claims WHERE id=:i", i=claim["id"])[0][0])
        == claimant
    )
    assert "We received your claim" in [
        r[0] for r in db("SELECT title FROM notifications WHERE user_id=:u", u=claimant)
    ]

    mine = (await client.get("/api/v1/estate/claims/mine", headers=ch)).json()
    assert [c["reference"] for c in mine] == [claim["reference"]]
    assert (await client.get("/api/v1/estate/claims/mine", headers=xh)).json() == []
    assert (await client.get("/api/v1/estate/claims/mine")).status_code == 401

    # staff ask for the death certificate; the claimant adds it from their account
    await _admin_login(client, db)
    r = await client.post(f"/admin/estate-claims/{claim['id']}", data={"action": "ask"})
    assert r.status_code == 400 and "Write what the claimant must send" in r.text
    r = await client.post(
        f"/admin/estate-claims/{claim['id']}",
        data={"action": "ask", "note": "The official death certificate."},
    )
    assert r.status_code == 303
    mine = (await client.get("/api/v1/estate/claims/mine", headers=ch)).json()[0]
    assert mine["status"] == "needs_info" and mine["message"] == "The official death certificate."
    asked = db(
        "SELECT body FROM email_outbox WHERE to_email='fatima@heirs.io' AND subject LIKE 'We need more%'"
    )[0][0]
    assert "The official death certificate." in asked and "/estate-claim" in asked

    url = f"/api/v1/estate/claims/{claim['id']}/documents"
    r = await client.post(
        url,
        data={"kind": "evidence"},
        files={"file": ("death-certificate.pdf", PDF, "application/pdf")},
        headers=xh,
    )
    assert r.status_code == 404  # not their claim
    r = await client.post(
        url,
        data={"kind": "evidence"},
        files={"file": ("death-certificate.pdf", PDF, "application/pdf")},
        headers=ch,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_review"
    assert [d["kind"] for d in r.json()["documents"]] == ["certificate", "identity", "evidence"]
    assert (
        "added a document"
        in db(
            "SELECT body FROM email_outbox WHERE to_email='support@t.io' ORDER BY created_at DESC"
        )[0][0]
    )


@pytest.mark.asyncio
async def test_a_claim_sent_as_a_guest_is_the_members_once_their_address_is_verified(client, db):
    _owner, h = await _user(client, db, "ahmed6@holders.io", "Ahmed Mansouri")
    b = await _beneficiary(client, h)
    ref = (await _submit(client, _claim_fields(b["certificate_no"]))).json()["reference"]

    claimant, ch = await _user(client, db, "fatima@heirs.io", "Fatima Mansouri")
    cid = db("SELECT id FROM estate_claims WHERE reference=:r", r=ref)[0][0]
    await _admin_login(client, db)

    def told() -> list[str]:
        rows = db("SELECT title FROM notifications WHERE user_id=:u AND type='estate'", u=claimant)
        return [r[0] for r in rows]

    # an address anyone could have typed at sign-up shows nothing until it is verified,
    # and what staff write about the claim goes to the address alone
    assert (await client.get("/api/v1/estate/claims/mine", headers=ch)).json() == []
    r = await client.post(
        f"/admin/estate-claims/{cid}", data={"action": "ask", "note": "A clearer photo."}
    )
    assert r.status_code == 303 and told() == []

    db("UPDATE users SET email_verified=true WHERE id=:i", i=claimant)
    assert [
        c["reference"] for c in (await client.get("/api/v1/estate/claims/mine", headers=ch)).json()
    ] == [ref]
    # ...and from then on it reaches their notifications too
    r = await client.post(
        f"/admin/estate-claims/{cid}", data={"action": "ask", "note": "Both sides, please."}
    )
    assert r.status_code == 303 and told() == ["We need more information for your claim"]


@pytest.mark.asyncio
async def test_an_address_nobody_confirmed_ties_no_account_to_a_claim(client, db):
    owner, h = await _user(client, db, "ahmed8@holders.io", "Ahmed Mansouri")
    pid = _property(db)
    _grant(db, owner, pid, 10)
    b = await _beneficiary(client, h)  # Fatima Mansouri <fatima@heirs.io>, 60%
    # an account was opened with her address and its identity verified, but the address was
    # never confirmed: whoever knew the address could have opened it
    account, ah = await _user(client, db, "fatima@heirs.io", "Fatima Mansouri")

    r = await _submit(client, _claim_fields(b["certificate_no"]), evidence=True)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert db("SELECT claimant_user_id FROM estate_claims WHERE id=:i", i=cid)[0][0] is None
    assert (
        db("SELECT count(*) FROM notifications WHERE user_id=:u AND type='estate'", u=account)[0][0]
        == 0
    )
    assert (await client.get("/api/v1/estate/claims/mine", headers=ah)).json() == []

    # staff are shown the account and why it is not taken as the claimant's; nothing moves
    await _admin_login(client, db)
    page = await client.get(f"/admin/estate-claims/{cid}")
    assert page.status_code == 200 and "Not ready to approve" in page.text
    assert "An account is registered with fatima@heirs.io (in the name Fatima Mansouri" in page.text
    assert "the address was never confirmed in it" in page.text
    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "approve"})
    assert r.status_code == 400 and "the address was never confirmed in it" in r.text
    assert _holding(db, account, pid) == 0
    assert db("SELECT count(*) FROM estate_events")[0][0] == 0

    # she confirms the address from her account: the claim is hers, and the share can move
    db("UPDATE users SET email_verified=true WHERE id=:i", i=account)
    mine = (await client.get("/api/v1/estate/claims/mine", headers=ah)).json()
    assert [c["id"] for c in mine] == [cid]
    page = await client.get(f"/admin/estate-claims/{cid}")
    assert "never confirmed" not in page.text and "Not ready to approve" not in page.text
    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "approve"})
    assert r.status_code == 303, r.text
    assert (_holding(db, account, pid), _holding(db, owner, pid)) == (6, 4)
    assert str(db("SELECT claimant_user_id FROM estate_claims WHERE id=:i", i=cid)[0][0]) == account

    # from then on, a claim a visitor sends with that address is hers from the start
    again = await _submit(client, _claim_fields(b["certificate_no"]))
    assert again.status_code == 201, again.text
    later = again.json()["id"]
    assert (
        str(db("SELECT claimant_user_id FROM estate_claims WHERE id=:i", i=later)[0][0]) == account
    )
    mine = (await client.get("/api/v1/estate/claims/mine", headers=ah)).json()
    assert {c["id"] for c in mine} == {cid, later}


@pytest.mark.asyncio
async def test_staff_can_say_an_account_with_an_unconfirmed_address_is_the_claimants(client, db):
    owner, h = await _user(client, db, "ahmed9@holders.io", "Ahmed Mansouri")
    pid = _property(db)
    _grant(db, owner, pid, 10)
    b = await _beneficiary(client, h)
    account, _ah = await _user(client, db, "fatima@heirs.io", "Fatima Mansouri")
    cid = (await _submit(client, _claim_fields(b["certificate_no"]), evidence=True)).json()["id"]

    staff = await _admin_login(client, db)
    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "approve"})
    assert r.status_code == 400 and _holding(db, account, pid) == 0

    # a decision of staff, on the record with who made it
    r = await client.post(
        f"/admin/estate-claims/{cid}",
        data={"action": "match", "account_email": "fatima@heirs.io"},
    )
    assert r.status_code == 303
    audit = db(
        "SELECT actor_id, after FROM audit_log WHERE action='estate.claim.matched' AND entity_id=:i",
        i=cid,
    )[0]
    assert (str(audit[0]), audit[1]["claimant_user_id"]) == (staff, account)
    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "approve"})
    assert r.status_code == 303, r.text
    assert _holding(db, account, pid) == 6


# --- staff review and the transfer ------------------------------------------------------- #
@pytest.mark.asyncio
async def test_staff_review_a_claim_and_the_share_moves_to_the_claimants_own_account(client, db):
    owner, h = await _user(client, db, "ahmed7@holders.io", "Ahmed Mansouri")
    pid, pid2 = _property(db, "Marina Heights"), _property(db, "Palm Court")
    _grant(db, owner, pid, 10)
    _grant(db, owner, pid2, 5)
    db("UPDATE wallets SET balance=750 WHERE user_id=:u", u=owner)
    first = await _beneficiary(client, h)  # Fatima, 60%
    second = await _beneficiary(
        client,
        h,
        full_name="Omar Mansouri",
        relationship="Son",
        email="omar@heirs.io",
        allocation_pct=40,
        meta={"role": "heir", "idType": "National ID", "idNumber": "784-1990-1"},
    )
    await client.post(
        f"/api/v1/estate/beneficiaries/{first['id']}/documents",
        files={"file": ("passport-on-file.jpg", JPG, "image/jpeg")},
        headers=h,
    )
    # the other heir already has a verified account with the address on the record
    omar, oh = await _user(client, db, "omar@heirs.io", "Omar Mansouri")

    claim = (await _submit(client, _claim_fields(first["certificate_no"]))).json()
    cid = claim["id"]

    # the pages are staff's alone
    anon = await client.get("/admin/estate-claims", follow_redirects=False)
    assert anon.status_code in (302, 307) and "/admin/login" in anon.headers["location"]
    staff = await _admin_login(client, db)

    page = await client.get("/admin/estate-claims")
    assert page.status_code == 200 and claim["reference"] in page.text
    assert "Fatima Mansouri" in page.text and "matches a record" in page.text

    detail = await client.get(f"/admin/estate-claims/{cid}")
    assert detail.status_code == 200
    for text in (
        "The claimant&#39;s name is the name on the record.",
        "The identity document number is the one on the record.",  # a-1234567 == A1234567
        "The account holder&#39;s name is as the claimant wrote it.",
        f"must show Version {first['version']}",
        "passport-on-file.jpg",  # the copy the holder kept, beside the claimant's
        "passport.jpg",
        "No account is registered with fatima@heirs.io yet",
        "The claimant has no account yet",
        "No official supporting document is on file",
        "Omar Mansouri (40%)",
        "$750.00",
        "Marina Heights",
    ):
        assert text in detail.text, text
    # a preview of what an approval moves: 60% of each holding
    assert "6 unit(s)" in detail.text and "3 unit(s)" in detail.text

    # the documents open for staff only
    doc_id = db("SELECT documents FROM estate_claims WHERE id=:i", i=cid)[0][0][1]["id"]
    got = await client.get(f"/admin/estate-claim-doc?claim={cid}&doc={doc_id}&inline=1")
    assert got.status_code == 200 and got.content == JPG
    assert got.headers["content-disposition"].startswith("inline")
    kept = db("SELECT id_documents FROM estate_beneficiaries WHERE id=:i", i=first["id"])[0][0]
    got = await client.get(f"/admin/estate-beneficiary-doc?b={first['id']}&doc={kept[0]['id']}")
    assert got.status_code == 200 and got.content == JPG
    assert got.headers["content-disposition"].startswith("attachment")

    # an approval is refused while anything stands in the way
    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "approve"})
    assert r.status_code == 400 and "The claimant has no account yet" in r.text
    assert db("SELECT count(*) FROM estate_events")[0][0] == 0

    # the claimant registers (another address than the one on the claim) and verifies
    fatima, fh = await _user(client, db, "fatima.m@personal.io", "Fatima Mansouri", verified=False)
    r = await client.post(
        f"/admin/estate-claims/{cid}", data={"action": "match", "account_email": "nobody@x.io"}
    )
    assert r.status_code == 400 and "No account is registered with nobody@x.io" in r.text
    r = await client.post(
        f"/admin/estate-claims/{cid}",
        data={"action": "match", "account_email": "Fatima.M@personal.io"},
    )
    assert r.status_code == 303
    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "approve"})
    assert r.status_code == 400 and "identity is not verified" in r.text
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=fatima)
    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "approve"})
    assert r.status_code == 400 and "No official supporting document" in r.text

    # staff attach the death certificate they received
    r = await client.post(
        f"/admin/estate-claims/{cid}",
        data={"action": "attach", "kind": "evidence"},
        files={"file": ("death-certificate.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 303
    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "review"})
    assert r.status_code == 303
    ready = await client.get(f"/admin/estate-claims/{cid}")
    assert "Not ready to approve" not in ready.text

    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "approve"})
    assert r.status_code == 303, r.text

    # her 60% is in HER account; his 40% stays in the holder's, written for him
    assert (_holding(db, fatima, pid), _holding(db, fatima, pid2)) == (6, 3)
    assert (_holding(db, owner, pid), _holding(db, owner, pid2)) == (4, 2)
    assert (_holding(db, omar, pid), _holding(db, omar, pid2)) == (0, 0)
    statuses = db(
        "SELECT b.full_name, t.units, t.status FROM estate_transfers t "
        "JOIN estate_beneficiaries b ON b.id = t.beneficiary_id ORDER BY b.full_name, t.units"
    )
    assert [tuple(r) for r in statuses] == [
        ("Fatima Mansouri", 3, "completed"),
        ("Fatima Mansouri", 6, "completed"),
        ("Omar Mansouri", 2, "awaiting_claim"),
        ("Omar Mansouri", 4, "awaiting_claim"),
    ]
    row = db(
        "SELECT status, decided_by, estate_event_id, claimant_user_id FROM estate_claims WHERE id=:i",
        i=cid,
    )[0]
    assert (row[0], str(row[1]), str(row[3])) == ("approved", staff, fatima)
    event = db(
        "SELECT claim_id, reason, date_of_death, status FROM estate_events WHERE id=:i", i=row[2]
    )[0]
    assert (str(event[0]), event[1], str(event[2]), event[3]) == (
        cid,
        "death",
        "2026-09-01",
        "executed",
    )
    assert (
        str(
            db("SELECT beneficiary_user_id FROM estate_beneficiaries WHERE id=:i", i=first["id"])[
                0
            ][0]
        )
        == fatima
    )

    # she is told, by notification and by email, and sees where the units came from
    told = db(
        "SELECT message FROM notifications WHERE user_id=:u AND title='Assets were transferred to your account'",
        u=fatima,
    )[0][0]
    assert "designated beneficiary of Ahmed Mansouri" in told
    assert "6 units of Marina Heights" in told and "3 units of Palm Court" in told
    assert (
        db(
            "SELECT count(*) FROM email_outbox WHERE user_id=:u AND subject='Assets were transferred to your account'",
            u=fatima,
        )[0][0]
        == 1
    )
    # ...and at the address she claimed with, which is not her account's
    assert (
        db(
            "SELECT count(*) FROM email_outbox WHERE to_email='fatima@heirs.io' AND subject LIKE 'Your claim was approved%'"
        )[0][0]
        == 1
    )
    moves = (await client.get("/api/v1/investments/movements", headers=fh)).json()["items"]
    assert sorted((m["units"], m["label"], m["counterparty"]) for m in moves) == [
        (3, "Received as a designated beneficiary", "Ahmed Mansouri"),
        (6, "Received as a designated beneficiary", "Ahmed Mansouri"),
    ]
    assert (await client.get("/api/v1/estate/claims/mine", headers=fh)).json()[0][
        "status"
    ] == "approved"

    # the register is what it was that day: closed to whoever holds the account's password
    locked = (await client.get("/api/v1/estate/beneficiaries", headers=h)).json()
    assert all(b["locked"] for b in locked)
    for call in (
        client.patch(
            f"/api/v1/estate/beneficiaries/{second['id']}", json={"allocation_pct": 1}, headers=h
        ),
        client.delete(f"/api/v1/estate/beneficiaries/{second['id']}", headers=h),
        client.post(
            "/api/v1/estate/beneficiaries",
            json={"full_name": "Late Entry", "allocation_pct": 0},
            headers=h,
        ),
    ):
        r = await call
        assert r.status_code == 409 and r.json()["error"]["code"] == "REGISTER_CLOSED"
    # the certificate can still be downloaded
    assert (
        await client.get(f"/api/v1/estate/beneficiaries/{second['id']}/certificate", headers=h)
    ).status_code == 200

    # a decided claim stays decided
    r = await client.post(f"/admin/estate-claims/{cid}", data={"action": "approve"})
    assert r.status_code == 400 and "already decided" in r.text
    assert _holding(db, fatima, pid) == 6

    # the other heir's verified account receives nothing by itself: his share awaits HIS claim
    assert await _materialize(db, omar) == 0
    assert _holding(db, omar, pid) == 0

    second_claim = await _submit(
        client,
        _claim_fields(
            second["certificate_no"],
            claimant_name="Omar Mansouri",
            claimant_email="omar@heirs.io",
            claimant_id_type="National ID",
            claimant_id_number="784-1990-1",
            relationship="Son",
        ),
        headers=oh,
        evidence=True,
    )
    assert second_claim.status_code == 201, second_claim.text
    cid2 = second_claim.json()["id"]
    page = await client.get(f"/admin/estate-claims/{cid2}")
    assert "4 unit(s)" in page.text and "2 unit(s)" in page.text
    assert "the register is closed" in page.text
    r = await client.post(f"/admin/estate-claims/{cid2}", data={"action": "approve"})
    assert r.status_code == 303, r.text
    assert (_holding(db, omar, pid), _holding(db, omar, pid2)) == (4, 2)
    assert (_holding(db, owner, pid), _holding(db, owner, pid2)) == (0, 0)
    # every unit is somewhere, exactly once
    assert (
        db("SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE property_id=:p", p=pid)[0][0]
        == 10
    )
    assert (
        db("SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE property_id=:p", p=pid2)[0][0]
        == 5
    )
    assert db("SELECT count(*) FROM estate_events")[0][0] == 1  # one event per holder
    assert db("SELECT count(*) FROM estate_transfers WHERE status <> 'completed'")[0][0] == 0
    # the wallet is not part of an approval
    assert db("SELECT balance FROM wallets WHERE user_id=:u", u=owner)[0][0] == 750


async def _materialize(db, user_id: str) -> int:
    """What the identity-verification hook does for a user, in its own transaction."""
    from app.core.db import session_scope

    async with session_scope() as session:
        return await estate_service.materialize_for_user(session, user_id=uuid.UUID(user_id))


@pytest.mark.asyncio
async def test_staff_see_what_does_not_add_up_and_reject_with_a_message(client, db):
    owner, h = await _user(client, db, "ahmed8@holders.io", "Ahmed Mansouri")
    pid = _property(db)
    _grant(db, owner, pid, 10)
    b = await _beneficiary(client, h)
    # the record was written after the stated date of death, and the claimant is not the
    # person on it
    claim = (
        await _submit(
            client,
            _claim_fields(
                b["certificate_no"],
                claimant_name="Karim Stranger",
                claimant_email="karim@elsewhere.io",
                claimant_id_number="Z999",
                holder_name="Somebody Else",
                date_of_death="2020-01-01",
            ),
            evidence=True,
        )
    ).json()
    await _admin_login(client, db)
    page = await client.get(f"/admin/estate-claims/{claim['id']}")
    for text in (
        "The claimant&#39;s name is NOT the name on the record.",
        "The identity document number is NOT the one on the record.",
        "The account holder&#39;s name differs from what the claimant wrote.",
        "AFTER the stated date of death (2020-01-01)",
        "The holder kept no copy of this person&#39;s identity document.",
    ):
        assert text in page.text, text

    r = await client.post(f"/admin/estate-claims/{claim['id']}", data={"action": "reject"})
    assert r.status_code == 400 and "Write why" in r.text
    r = await client.post(
        f"/admin/estate-claims/{claim['id']}",
        data={"action": "reject", "note": "The documents do not match our records."},
    )
    assert r.status_code == 303
    assert db("SELECT status FROM estate_claims WHERE id=:i", i=claim["id"])[0][0] == "rejected"
    mail = db(
        "SELECT body FROM email_outbox WHERE to_email='karim@elsewhere.io' AND subject LIKE 'Your claim was not approved%'"
    )[0][0]
    assert "The documents do not match our records." in mail and "/support" in mail
    # nothing moved, nothing was recorded, the holder's register stays open
    assert _holding(db, owner, pid) == 10 and db("SELECT count(*) FROM estate_events")[0][0] == 0
    r = await client.patch(
        f"/api/v1/estate/beneficiaries/{b['id']}", json={"allocation_pct": 10}, headers=h
    )
    assert r.status_code == 200
    # a rejected claim does not stop a new one
    assert (
        await _submit(
            client, _claim_fields(b["certificate_no"], claimant_email="karim@elsewhere.io")
        )
    ).status_code == 201


@pytest.mark.asyncio
async def test_a_mistyped_certificate_number_is_matched_by_staff(client, db):
    _owner, h = await _user(client, db, "ahmed9@holders.io", "Ahmed Mansouri")
    b = await _beneficiary(client, h)
    claim = (await _submit(client, _claim_fields("CPB-9999-9999"))).json()
    await _admin_login(client, db)
    page = await client.get(f"/admin/estate-claims/{claim['id']}")
    assert "matches no beneficiary record" in page.text
    r = await client.post(
        f"/admin/estate-claims/{claim['id']}",
        data={"action": "match", "certificate_no": "CPB-0000-0001"},
    )
    assert r.status_code == 400 and "No beneficiary record has the number" in r.text
    r = await client.post(
        f"/admin/estate-claims/{claim['id']}",
        data={"action": "match", "certificate_no": b["certificate_no"].lower()},
    )
    assert r.status_code == 303
    row = db("SELECT beneficiary_id, certificate_no FROM estate_claims WHERE id=:i", i=claim["id"])[
        0
    ]
    assert (str(row[0]), row[1]) == (b["id"], b["certificate_no"])
    assert (
        db(
            "SELECT count(*) FROM audit_log WHERE action='estate.claim.matched' AND entity_id=:i",
            i=claim["id"],
        )[0][0]
        == 1
    )


@pytest.mark.asyncio
async def test_the_claim_pages_are_for_full_admins(client, db):
    _owner, h = await _user(client, db, "ahmed10@holders.io", "Ahmed Mansouri")
    b = await _beneficiary(client, h)
    claim = (await _submit(client, _claim_fields(b["certificate_no"]))).json()
    for path in (
        "/admin/estate-claims",
        f"/admin/estate-claims/{claim['id']}",
        f"/admin/estate-claim-doc?claim={claim['id']}&doc=x",
        f"/admin/estate-beneficiary-doc?b={b['id']}&doc=x",
    ):
        r = await client.get(path, follow_redirects=False)
        assert r.status_code in (302, 307) and "/admin/login" in r.headers["location"], path
    r = await client.post(
        f"/admin/estate-claims/{claim['id']}", data={"action": "approve"}, follow_redirects=False
    )
    assert r.status_code in (302, 307)
    assert db("SELECT status FROM estate_claims WHERE id=:i", i=claim["id"])[0][0] == "submitted"
