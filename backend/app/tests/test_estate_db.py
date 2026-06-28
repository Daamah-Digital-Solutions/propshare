"""Group 4 — DB-backed tests for estate / inheritance.

Acceptance: free-allocation beneficiary register (sum ≤ 100 enforced); owner/user-scoped;
admin-only death verification (non-admin → 403, unauth → 401) with the death-certificate
stored via the storage seam; execution is a REAL atomic ownership move (conservation),
idempotent (second confirm = no double move); pending (non-user) beneficiary materializes
to a real move on registration+KYC; free split honored (Hamilton; unallocated stays).
"""

from __future__ import annotations

import uuid

import pytest

PW = "Passw0rd!23"


@pytest.fixture(autouse=True)
def _local_storage(monkeypatch, tmp_path):
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


async def _admin(client, db, email: str) -> tuple[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Admin"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"], str(uid)


def _kyc_verify(db, uid: str) -> None:
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:u", u=uid)


def _seed_property(db, *, unit_price: int = 100) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Prop','Dubai','residential','ready-income','active',1000000,:up,100,100,100)",
        id=pid,
        up=unit_price,
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


def _net(db, user_id: str, property_id: str) -> int:
    sql = (
        "SELECT COALESCE(SUM(units),0) FROM ownership_ledger " "WHERE user_id=:u AND property_id=:p"
    )
    return int(db(sql, u=user_id, p=property_id)[0][0])


def _total_units(db, property_id: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE property_id=:p",
            p=property_id,
        )[0][0]
    )


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


async def _add_ben(client, tok, **body):
    return await client.post("/api/v1/estate/beneficiaries", json=body, headers=_h(tok))


async def _verify_death(client, admin_tok, subject_id):
    return await client.post(
        "/api/v1/admin/estate/verify-death",
        data={"subject_user_id": subject_id},
        files={"file": ("death.pdf", b"%PDF-1.4 death certificate", "application/pdf")},
        headers=_h(admin_tok),
    )


# --- register --------------------------------------------------------------- #
async def test_register_free_allocation_sum_validated(client, db):
    tok, _uid = await _user(client, db, "es-owner1@x.com")
    assert (await _add_ben(client, tok, full_name="Spouse", allocation_pct=60)).status_code == 201
    assert (await _add_ben(client, tok, full_name="Son", allocation_pct=40)).status_code == 201
    # exceeding 100% total is rejected
    over = await _add_ben(client, tok, full_name="Extra", allocation_pct=10)
    assert over.status_code == 422 and over.json()["error"]["code"] == "ALLOCATION_EXCEEDS_100"
    listed = (await client.get("/api/v1/estate/beneficiaries", headers=_h(tok))).json()
    assert sorted(b["allocation_pct"] for b in listed) == [40, 60]


async def test_register_meta_round_trips(client, db):
    tok, _uid = await _user(client, db, "es-meta@x.com")
    r = await _add_ben(
        client,
        tok,
        full_name="Heir",
        allocation_pct=50,
        meta={"role": "heir", "scope": ["ownership"], "trigger": "death"},
    )
    assert r.json()["meta"]["role"] == "heir"  # UI extras persist (no markup change needed)


async def test_register_owner_scoped(client, db):
    tok_a, _a = await _user(client, db, "es-a@x.com")
    tok_b, _b = await _user(client, db, "es-b@x.com")
    await _add_ben(client, tok_a, full_name="A-Ben", allocation_pct=50)
    assert (await client.get("/api/v1/estate/beneficiaries", headers=_h(tok_b))).json() == []


async def test_register_requires_auth(client, db):
    assert (await client.get("/api/v1/estate/beneficiaries")).status_code == 401


# --- admin death verification + execution ----------------------------------- #
async def test_verify_death_admin_only(client, db):
    tok, uid = await _user(client, db, "es-deceased1@x.com")
    r = await _verify_death(client, tok, uid)  # caller is not an admin
    assert r.status_code == 403


async def test_execution_atomic_move_and_idempotent(client, db):
    # deceased holder with 10 units; one real (KYC'd) beneficiary at 100%
    dec_tok, dec_id = await _user(client, db, "es-dec@x.com")
    heir_tok, heir_id = await _user(client, db, "es-heir@x.com")
    _kyc_verify(db, heir_id)
    pid = _seed_property(db)
    _ledger(db, dec_id, pid, 10)
    await _add_ben(client, dec_tok, full_name="Heir", email="es-heir@x.com", allocation_pct=100)

    admin_tok, _aid = await _admin(client, db, "es-admin1@x.com")
    r = await _verify_death(client, admin_tok, dec_id)
    assert r.status_code == 200, r.text
    assert r.json()["executed"] is True and r.json()["transfers"] == 1
    # real atomic move: deceased 0, heir 10, total conserved
    assert _net(db, dec_id, pid) == 0
    assert _net(db, heir_id, pid) == 10
    assert _total_units(db, pid) == 10
    # death certificate stored (user-scoped document)
    assert db("SELECT 1 FROM documents WHERE user_id=:u AND type='death_certificate'", u=dec_id)

    # idempotent: a second confirm does NOT transfer again
    r2 = await _verify_death(client, admin_tok, dec_id)
    assert r2.json()["replayed"] is True and r2.json()["transfers"] == 0
    assert _net(db, heir_id, pid) == 10  # unchanged


async def test_free_split_honored_and_remainder_stays(client, db):
    dec_tok, dec_id = await _user(client, db, "es-split-dec@x.com")
    _h1tok, h1 = await _user(client, db, "es-split-h1@x.com")
    _h2tok, h2 = await _user(client, db, "es-split-h2@x.com")
    _kyc_verify(db, h1)
    _kyc_verify(db, h2)
    pid = _seed_property(db)
    _ledger(db, dec_id, pid, 10)
    await _add_ben(client, dec_tok, full_name="H1", email="es-split-h1@x.com", allocation_pct=60)
    await _add_ben(client, dec_tok, full_name="H2", email="es-split-h2@x.com", allocation_pct=30)
    # total alloc = 90% -> 6 + 3 move, 1 unit (10%) stays with the estate

    admin_tok, _aid = await _admin(client, db, "es-admin2@x.com")
    await _verify_death(client, admin_tok, dec_id)
    assert _net(db, h1, pid) == 6
    assert _net(db, h2, pid) == 3
    assert _net(db, dec_id, pid) == 1  # unallocated remainder stays
    assert _total_units(db, pid) == 10  # conserved


# --- pending beneficiary materializes on KYC -------------------------------- #
async def test_pending_beneficiary_materializes_on_kyc(client, db, asession):
    from app.services import estate_service

    dec_tok, dec_id = await _user(client, db, "es-pend-dec@x.com")
    pid = _seed_property(db)
    _ledger(db, dec_id, pid, 8)
    # beneficiary is not a user yet -> pending allocation
    await _add_ben(
        client, dec_tok, full_name="Future Heir", email="es-pend-heir@x.com", allocation_pct=100
    )

    admin_tok, _aid = await _admin(client, db, "es-admin3@x.com")
    await _verify_death(client, admin_tok, dec_id)
    # pending: units stay with the deceased until the heir registers + KYCs
    assert _net(db, dec_id, pid) == 8
    assert db("SELECT 1 FROM estate_transfers WHERE status='pending'")

    # heir registers + KYC -> materialize moves the units
    _htok, heir_id = await _user(client, db, "es-pend-heir@x.com")
    _kyc_verify(db, heir_id)
    moved = await estate_service.materialize_for_user(asession, user_id=uuid.UUID(heir_id))
    await asession.commit()
    assert moved == 1
    assert _net(db, dec_id, pid) == 0
    assert _net(db, heir_id, pid) == 8
    assert _total_units(db, pid) == 8  # conserved
