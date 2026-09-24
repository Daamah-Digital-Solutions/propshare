"""Batch F — operational cases opened by the platform itself (client doc §10, §12, §33).

* ledger drift found by the reconciliation check opens ONE case per failing check and
  never a second while it is open; closing the case re-arms it;
* a bank-transfer claim or a withdrawal older than ops_stale_hours opens one case each
  (keyed on the row), fresh ones do not; confirming/paying makes them disappear from the
  sweep; admins get one in-app notice and the inbox one email per sweep;
* the staff copilot lists ops cases; the cron endpoint is admin-or-secret only.
"""

# ruff: noqa: E501
from __future__ import annotations

import uuid

import pytest

from app.core.config import get_settings
from app.services import manual_deposit_service, ops_case_service, ticket_service
from app.services.assistant.context import load_context
from app.services.assistant.tools import REGISTRY
from app.services.assistant.tools.base import call_tool, parse_args

PW = "Passw0rd!23"


async def _user(client, db, email, *, admin=False, kyc="verified", balance=1000):
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "O"}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    if admin:
        db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE kyc_verifications SET status=:s WHERE user_id=:i", s=kyc, i=uid)
    db("UPDATE wallets SET balance=:b WHERE user_id=:u", b=balance, u=uid)
    tok = (await client.post("/api/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]
    return uid, {"Authorization": f"Bearer {tok}"}


def _cases(db):
    return db(
        "SELECT ticket_no, category, priority, status, context->>'case_key' FROM support_tickets WHERE kind='ops_case' ORDER BY created_at"
    )


@pytest.mark.asyncio
async def test_drift_and_stale_rows_open_cases_once(client, db, asession, monkeypatch):
    monkeypatch.setattr(get_settings(), "support_inbox_email", "support@t.io", raising=False)
    admin, _ = await _user(client, db, "adm@o.io", admin=True)
    uid, h = await _user(client, db, "m@o.io")
    # a stale bank claim (49h) and a fresh one (1h): rows exactly as the claim service
    # writes them (provider = manual bank transfer, status pending)
    provider = manual_deposit_service._PROVIDER
    db(
        "INSERT INTO payments (user_id, provider, amount, currency, status, purpose, raw_payload, created_at) VALUES (:u,:pr,250,'USD','pending','deposit',CAST('{\"reference\": \"REF-OLD\"}' AS jsonb), now() - interval '49 hours')",
        u=uid,
        pr=provider,
    )
    db(
        "INSERT INTO payments (user_id, provider, amount, currency, status, purpose, provider_payment_id) VALUES (:u,:pr,100,'USD','pending','deposit','REF-NEW')",
        u=uid,
        pr=provider,
    )
    # stale withdrawals (50h): one in review, one approved but never sent, one already paid
    for status in ("pending_review", "approved", "completed"):
        db(
            "INSERT INTO withdrawals (user_id, amount, method, provider, destination, status, created_at) VALUES (:u,100,'bank','manual','{}'::jsonb,:s, now() - interval '50 hours')",
            u=uid,
            s=status,
        )
    _ = h
    # ledger drift: a wallet whose balance disagrees with its ledger is one of the checks;
    # the simplest guaranteed drift is a negative ownership row
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,unit_price,total_units,available_units,minimum_investment) VALUES (:id,'Drift','Dubai','residential','ready-income','active',100000,100,1000,1000,100)",
        id=pid,
    )
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) VALUES (:u,:p,-5,100,'purchase')",
        u=uid,
        p=pid,
    )

    out = await ops_case_service.sweep(asession)
    await asession.commit()
    cases = _cases(db)
    keys = [c[4] for c in cases]
    assert out["opened"] == len(cases) >= 4 and out["drift_checks_failing"] >= 1
    assert any(k.startswith("reconciliation:") for k in keys)
    assert sum(1 for k in keys if k.startswith("bank_claim:")) == 1  # only the stale claim
    # regression: the sweep looked for status 'pending', which withdrawals never have, so
    # unpaid withdrawals never raised a case
    assert sum(1 for k in keys if k.startswith("withdrawal:")) == 2  # not the paid one
    claim = db("SELECT summary FROM support_tickets WHERE context->>'case_key' LIKE 'bank_claim:%'")
    assert "reference REF-OLD" in claim[0][0]  # the member's own reference, not 'n/a'
    assert {c[1] for c in cases} >= {"reconciliation", "payments", "withdrawals"}
    assert (
        db("SELECT count(*) FROM notifications WHERE user_id=:a AND type='ops_case'", a=admin)[0][0]
        == 1
    )
    assert db("SELECT count(*) FROM email_outbox WHERE subject LIKE '[Ops]%'")[0][0] == 1
    assert db("SELECT count(*) FROM audit_log WHERE action='ops_case.opened'")[0][0] == len(cases)

    # idempotent while open
    again = await ops_case_service.sweep(asession)
    await asession.commit()
    assert again["opened"] == 0 and len(_cases(db)) == len(cases)
    # closing the withdrawal case re-arms it (the withdrawal is still unpaid)
    wid = db(
        "SELECT id FROM support_tickets WHERE kind='ops_case' AND context->>'case_key' LIKE 'withdrawal:%' LIMIT 1"
    )[0][0]
    await ticket_service.set_status(asession, actor_id=admin, ticket_id=wid, status="closed")
    await asession.commit()
    assert (await ops_case_service.sweep(asession))["opened"] == 1
    await asession.commit()
    # the staff copilot sees them; members do not
    actx = await load_context(asession, user_id=admin)
    spec = REGISTRY["list_ops_queue"]
    q = await call_tool(spec, asession, actx, parse_args(spec, '{"queue":"ops_cases","limit":10}'))
    assert q["total"] >= 3 and all(i["reference"].startswith("CPX-") for i in q["items"])


@pytest.mark.asyncio
async def test_ops_cases_cron_is_gated_and_quiet_when_clean(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", "cr0n", raising=False)
    assert (await client.post("/api/v1/assistant/maintenance/ops-cases")).status_code == 401
    r = await client.post(
        "/api/v1/assistant/maintenance/ops-cases", headers={"X-Cron-Secret": "cr0n"}
    )
    assert r.status_code == 200 and r.json()["opened"] == 0 and r.json()["stale_hours"] == 48
    assert db("SELECT count(*) FROM support_tickets WHERE kind='ops_case'")[0][0] == 0
