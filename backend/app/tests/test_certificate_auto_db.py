"""Client letter (2026-11-18): after KYC and the purchase, the certificate is issued
automatically (not only when the holder opens Certificates), and it states whether the units are
fully paid: "FINAL · FULLY PAID", or "PROVISIONAL · INSTALLMENTS OUTSTANDING" while an
installment plan on the property is still being paid."""

from __future__ import annotations

import pytest

from app.services import certificate_service
from app.tests.test_installments_db import _create, _h, _idem, _kyc_verify, _set_balance
from app.tests.test_installments_db import _seed_property as _seed_offplan
from app.tests.test_installments_db import _user as _plan_user
from app.tests.test_investment_db import _fund_wallet, _invest, _seed_property, _uid, _verified_user


def _valid(db, uid, pid):
    return db(
        "SELECT number, units, payment_status, verification_code FROM investment_certificates "
        "WHERE user_id=:u AND property_id=:p AND status='valid'",
        u=uid,
        p=pid,
    )


def _all(db, uid, pid):
    return db(
        "SELECT status, units, payment_status FROM investment_certificates "
        "WHERE user_id=:u AND property_id=:p ORDER BY issued_at",
        u=uid,
        p=pid,
    )


@pytest.mark.asyncio
async def test_a_purchase_issues_its_final_certificate_at_once(client, db):
    token = await _verified_user(client, db, "auto-cert@i.com")
    uid = str(_uid(db, "auto-cert@i.com"))
    _fund_wallet(db, uid, 10000)
    pid = _seed_property(db)
    res = await _invest(client, token, pid, 500, "wallet")
    assert res.status_code == 200, res.text
    # nothing was opened yet, the certificate is already there
    certs = _valid(db, uid, pid)
    assert len(certs) == 1 and certs[0][1] == 5 and certs[0][2] == "final"
    number = certs[0][0]

    # Certificates shows that same one, with its label
    listed = (await client.get("/api/v1/investments/certificates", headers=_h(token))).json()
    assert [(c["number"], c["payment_status"]) for c in listed["items"]] == [(number, "final")]
    pdf = (await client.get(f"/api/v1/investments/certificate/{pid}", headers=_h(token))).content
    assert b"FINAL" in pdf and b"FULLY PAID" in pdf and b"PROVISIONAL" not in pdf
    page = (await client.get(f"/api/v1/certificates/verify/{certs[0][3]}")).json()
    assert page["status"] == "valid" and page["payment_status"] == "final"

    # buying more issues the next one at once and supersedes the first
    res = await _invest(client, token, pid, 300, "wallet")
    assert res.status_code == 200, res.text
    assert [(s, u) for s, u, _p in _all(db, uid, pid)] == [("superseded", 5), ("valid", 8)]


@pytest.mark.asyncio
async def test_an_installment_plan_is_provisional_until_the_last_payment(client, db):
    tok, uid = await _plan_user(client, db, "auto-plan@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_offplan(db)
    plan = (await _create(client, tok, pid, amount=1200, duration=12)).json()
    # the down payment vested 3 units: certified at once, provisional
    certs = _valid(db, uid, pid)
    assert len(certs) == 1 and certs[0][1] == 3 and certs[0][2] == "provisional"
    pdf = (await client.get(f"/api/v1/investments/certificate/{pid}", headers=_h(tok))).content
    assert b"PROVISIONAL" in pdf and b"INSTALLMENTS OUTSTANDING" in pdf
    assert b"FULLY PAID" not in pdf
    page = (await client.get(f"/api/v1/certificates/verify/{certs[0][3]}")).json()
    assert page["payment_status"] == "provisional"

    for p in plan["payments"]:
        if p["status"] != "paid":
            r = await client.post(
                f"/api/v1/installments/payments/{p['id']}/pay", headers={**_h(tok), **_idem()}
            )
            assert r.status_code == 200, r.text
    # the last payment completes the plan: all 12 units, final
    certs = _valid(db, uid, pid)
    assert len(certs) == 1 and certs[0][1] == 12 and certs[0][2] == "final"
    history = _all(db, uid, pid)
    assert all(s == "superseded" for s, _u, _p in history[:-1])
    assert all(p == "provisional" for _s, _u, p in history[:-1])
    pdf = (await client.get(f"/api/v1/investments/certificate/{pid}", headers=_h(tok))).content
    assert b"FULLY PAID" in pdf and b"PROVISIONAL" not in pdf


@pytest.mark.asyncio
async def test_old_certificates_keep_their_signature(client, db):
    """A certificate issued before 0047 has no payment status; its signature is unchanged."""
    token = await _verified_user(client, db, "auto-old@i.com")
    uid = str(_uid(db, "auto-old@i.com"))
    _fund_wallet(db, uid, 10000)
    pid = _seed_property(db)
    await _invest(client, token, pid, 200, "wallet")
    from sqlalchemy import select

    from app.core.db import session_scope
    from app.models import InvestmentCertificate

    async with session_scope() as s:
        cert = (
            await s.execute(
                select(InvestmentCertificate).where(InvestmentCertificate.status == "valid")
            )
        ).scalar_one()
        signed = cert.signature
        assert certificate_service._signature(cert) == signed
        cert.payment_status = None  # as issued before 0047
        old = certificate_service._signature(cert)
        assert old != signed  # the status is part of what a new certificate signs
