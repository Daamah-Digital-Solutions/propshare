"""Investment certificates verified by their QR code (client, 2026-10-28, as on Capimax BRX).

What each test protects:
  * a certificate is issued once per holding and kept: a unique PSC- number, a secret
    22-character verification code, the QR code and the line under it open /verify/{code};
    downloading again gives the same certificate;
  * anyone can check a code without an account, and sees what the certificate states (no
    email, no account id); an unknown code is not found; each check is counted;
  * a certificate that no longer matches the ledger never reads as valid: when the units
    change it shows as superseded and the next download is a new certificate for the new
    count; when the units are gone it is superseded and nothing new is issued;
  * the platform can revoke one (with its reason on the page); the holder's next download is
    a new certificate; a holder's renamed account gets a new one too;
  * one valid certificate per holder and property, even if two issuers race;
  * the holder's list gives each current certificate with its number, code and page.
"""

from __future__ import annotations

import asyncio
import re
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services import certificate_service
from app.tests.test_documents_db import _h, _ledger, _seed_property, _user

NUMBER = re.compile(r"PSC-\d{4}-[A-HJ-NP-Z2-9]{8}")


def _certs(db, uid):
    return db(
        "SELECT number, verification_code, status, units, superseded_by, id "
        "FROM investment_certificates WHERE user_id=:u ORDER BY issued_at, created_at",
        u=uid,
    )


async def _download(client, tok, pid):
    return await client.get(f"/api/v1/investments/certificate/{pid}", headers=_h(tok))


@pytest.mark.asyncio
async def test_a_certificate_is_issued_once_and_its_qr_opens_its_page(client, db):
    tok, uid = await _user(client, db, "cert-qr@x.com")
    pid = _seed_property(db, None, slug="cert-qr")
    _ledger(db, uid, pid, 7)

    first = await _download(client, tok, pid)
    assert first.status_code == 200 and first.headers["content-type"] == "application/pdf"
    rows = _certs(db, uid)
    assert len(rows) == 1
    number, code, status, units, _by, _id = rows[0]
    assert NUMBER.fullmatch(number) and status == "valid" and units == 7
    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", code)
    url = certificate_service.verify_url(code)
    pdf = first.content
    assert number.encode() in pdf and code.encode() in pdf
    assert f"/URI ({url})".encode() in pdf  # the QR code and the line under it
    assert b"SCAN TO VERIFY" in pdf and b"cimglobalfinancial" not in pdf

    again = await _download(client, tok, pid)
    assert number.encode() in again.content
    assert len(_certs(db, uid)) == 1  # the same certificate, not a second one


@pytest.mark.asyncio
async def test_anyone_checks_a_code_without_an_account(client, db):
    tok, uid = await _user(client, db, "cert-public@x.com")
    db("UPDATE users SET full_name='Layla Hassan' WHERE id=:u", u=uid)
    pid = _seed_property(db, None, slug="cert-public")
    db("UPDATE properties SET spv_name='Marina SPV LLC', country='UAE' WHERE id=:p", p=pid)
    _ledger(db, uid, pid, 5)
    await _download(client, tok, pid)
    number, code, *_ = _certs(db, uid)[0]

    r = await client.get(f"/api/v1/certificates/verify/{code}")  # no token at all
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["number"] == number and body["status"] == "valid"
    assert body["holder_name"] == "Layla Hassan"
    assert body["holder_ref"].startswith("****") and uid.replace("-", "") not in str(body)
    assert (body["property_title"], body["spv_name"], body["jurisdiction"]) == (
        "Prop",
        "Marina SPV LLC",
        "UAE",
    )
    assert (body["units"], body["ownership"], body["unit_price"], body["value"]) == (
        5,
        "5%",
        "100.00",
        "500.00",
    )
    assert body["issuer"] == "Capimax PropShare" and len(body["signature"]) == 64
    assert "cert-public@x.com" not in r.text  # no email on a public page
    await client.get(f"/api/v1/certificates/verify/{code}")
    count = db("SELECT verification_count FROM investment_certificates WHERE number=:n", n=number)
    assert count[0][0] == 2

    for bad in ("nope", "x" * 22, code[:-1] + ("A" if code[-1] != "A" else "B")):
        miss = await client.get(f"/api/v1/certificates/verify/{bad}")
        assert miss.status_code == 404 and miss.json()["error"]["code"] == "CERTIFICATE_NOT_FOUND"


@pytest.mark.asyncio
async def test_a_paper_the_holder_has_outgrown_never_reads_as_valid(client, db):
    tok, uid = await _user(client, db, "cert-change@x.com")
    pid = _seed_property(db, None, slug="cert-change")
    _ledger(db, uid, pid, 10)
    await _download(client, tok, pid)
    old_number, old_code, *_ = _certs(db, uid)[0]

    _ledger(db, uid, pid, 5)  # bought 5 more
    page = (await client.get(f"/api/v1/certificates/verify/{old_code}")).json()
    assert page["status"] == "superseded" and page["superseded_at"] and page["units"] == 10

    pdf = (await _download(client, tok, pid)).content
    rows = _certs(db, uid)
    assert [(r[2], r[3]) for r in rows] == [("superseded", 10), ("valid", 15)]
    new_number, new_code, _st, _u, _by, new_id = rows[1]
    assert rows[0][4] == new_id  # the old one points at the one that replaced it
    assert new_number.encode() in pdf and old_number.encode() not in pdf
    assert (await client.get(f"/api/v1/certificates/verify/{new_code}")).json()["status"] == "valid"

    _ledger(db, uid, pid, -15)  # sold everything
    gone = await _download(client, tok, pid)
    assert gone.status_code == 404 and gone.json()["error"]["code"] == "NO_HOLDING"
    assert len(_certs(db, uid)) == 2  # nothing new issued for no units
    # the last paper they had now reads superseded, to anyone who checks it
    page = (await client.get(f"/api/v1/certificates/verify/{new_code}")).json()
    assert page["status"] == "superseded"
    assert [r[2] for r in _certs(db, uid)] == ["superseded", "superseded"]


@pytest.mark.asyncio
async def test_a_holding_changed_since_issue_is_superseded_when_checked(client, db):
    """Checked before the holder ever downloads again: the page already says superseded."""
    tok, uid = await _user(client, db, "cert-sold@x.com")
    pid = _seed_property(db, None, slug="cert-sold")
    _ledger(db, uid, pid, 4)
    await _download(client, tok, pid)
    code = _certs(db, uid)[0][1]
    _ledger(db, uid, pid, -4)
    page = (await client.get(f"/api/v1/certificates/verify/{code}")).json()
    assert page["status"] == "superseded"


@pytest.mark.asyncio
async def test_a_revoked_certificate_says_so_and_the_next_download_is_new(client, db, asession):
    tok, uid = await _user(client, db, "cert-revoke@x.com")
    pid = _seed_property(db, None, slug="cert-revoke")
    _ledger(db, uid, pid, 3)
    await _download(client, tok, pid)
    _number, code, _st, _u, _by, cert_id = _certs(db, uid)[0]

    with pytest.raises(Exception) as exc:
        await certificate_service.revoke(asession, certificate_id=cert_id, actor_id=None, reason="")
    assert getattr(exc.value, "code", "") == "REASON_REQUIRED"
    await asession.rollback()
    await certificate_service.revoke(
        asession, certificate_id=cert_id, actor_id=None, reason="Issued in error"
    )
    await asession.commit()
    page = (await client.get(f"/api/v1/certificates/verify/{code}")).json()
    assert (page["status"], page["revocation_reason"]) == ("revoked", "Issued in error")
    assert page["revoked_at"]

    await _download(client, tok, pid)
    assert [r[2] for r in _certs(db, uid)] == ["revoked", "valid"]


@pytest.mark.asyncio
async def test_a_renamed_holder_gets_a_certificate_in_their_name(client, db):
    tok, uid = await _user(client, db, "cert-rename@x.com")
    pid = _seed_property(db, None, slug="cert-rename")
    _ledger(db, uid, pid, 2)
    await _download(client, tok, pid)
    db("UPDATE users SET full_name='Omar Khalid' WHERE id=:u", u=uid)
    pdf = (await _download(client, tok, pid)).content
    assert b"Omar Khalid" in pdf
    assert [r[2] for r in _certs(db, uid)] == ["superseded", "valid"]


@pytest.mark.asyncio
async def test_one_valid_certificate_even_when_two_issuers_race(client, db, _test_db):
    tok, uid = await _user(client, db, "cert-race@x.com")
    pid = _seed_property(db, None, slug="cert-race")
    _ledger(db, uid, pid, 6)
    async_url, _sync = _test_db
    engine = create_async_engine(async_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def issue():
        async with maker() as session:
            cert = await certificate_service.current_certificate(
                session, user_id=uuid.UUID(uid), property_id=uuid.UUID(pid)
            )
            await session.commit()
            return cert.number

    numbers = await asyncio.gather(issue(), issue())
    await engine.dispose()
    assert numbers[0] == numbers[1]
    assert [r[2] for r in _certs(db, uid)] == ["valid"]

    # and the database refuses a second valid one outright
    with pytest.raises(IntegrityError):
        db(
            "INSERT INTO investment_certificates (number, verification_code, user_id, "
            "property_id, holder_name, holder_ref, property_title, units, ownership, "
            "unit_price, value, signature) VALUES ('PSC-0000-X', 'c0de0000000000000000xx', "
            ":u, :p, 'U', '****', 'Prop', 6, '6%', 100, 600, 's')",
            u=uid,
            p=pid,
        )


@pytest.mark.asyncio
async def test_the_holder_lists_their_current_certificates(client, db):
    tok, uid = await _user(client, db, "cert-list@x.com")
    p1 = _seed_property(db, None, slug="cert-list-a")
    p2 = _seed_property(db, None, slug="cert-list-b")
    db("UPDATE properties SET title='Zeta Tower' WHERE id=:p", p=p1)
    db("UPDATE properties SET title='Alpha Residence' WHERE id=:p", p=p2)
    _ledger(db, uid, p1, 2)
    _ledger(db, uid, p2, 9)

    r = await client.get("/api/v1/investments/certificates", headers=_h(tok))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["property_title"] for i in items] == ["Alpha Residence", "Zeta Tower"]
    first = items[0]
    assert NUMBER.fullmatch(first["number"]) and first["units"] == 9
    assert first["verify_path"] == f"/verify/{first['verification_code']}"
    assert first["verify_url"].endswith(first["verify_path"]) and first["status"] == "valid"
    # the PDF downloaded afterwards is the same certificate
    pdf = (await _download(client, tok, p2)).content
    assert first["number"].encode() in pdf

    other, _ = await _user(client, db, "cert-other@x.com")
    mine = await client.get("/api/v1/investments/certificates", headers=_h(other))
    assert mine.json()["items"] == []
    assert (await client.get("/api/v1/investments/certificates")).status_code == 401


@pytest.mark.asyncio
async def test_an_account_without_a_name_is_never_named_by_its_email(client, db):
    tok, uid = await _user(client, db, "cert-noname@x.com")
    db("UPDATE users SET full_name=NULL WHERE id=:u", u=uid)
    pid = _seed_property(db, None, slug="cert-noname")
    _ledger(db, uid, pid, 1)
    pdf = (await _download(client, tok, pid)).content
    code = _certs(db, uid)[0][1]
    page = (await client.get(f"/api/v1/certificates/verify/{code}")).json()
    assert page["holder_name"] == "Capimax PropShare investor"
    assert "cert-noname@x.com" not in str(page) and b"cert-noname@x.com" not in pdf
