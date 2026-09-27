"""Ops cases for card/crypto payments the provider webhook never settled.

The hourly sweep first lets the provider lookup settle whatever it can; only what is STILL
pending afterwards (older than ``ops_payment_stale_minutes``) becomes a case for a person —
the sign of a dead endpoint, a wrong signing secret, or a provider-side problem.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import ops_case_service
from app.services.integrations.payments import ParsedWebhook
from app.services.integrations.payments import stripe_gateway as stripe

PW = "Passw0rd!23"


async def _member(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "O"}
    )
    assert r.status_code == 201, r.text
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _pending(db, *, uid: str, cs: str, minutes_old: int) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO payments (id, user_id, provider, provider_payment_id, amount, currency,"
        " status, purpose, payment_method, created_at) VALUES"
        " (:id,:uid,'stripe',:cs,60,'USD','pending','deposit','card',"
        " now() - make_interval(mins => :m))",
        id=pid,
        uid=uid,
        cs=cs,
        m=minutes_old,
    )
    return pid


def _answers(monkeypatch, outcomes: dict[str, str]) -> None:
    async def lookup(session_id: str) -> ParsedWebhook:
        status = outcomes[session_id]
        return ParsedWebhook(
            event_id=f"sync:{session_id}:{status}",
            provider_payment_id=session_id,
            order_id=None,
            status=status,
            captured_amount=60 if status == "succeeded" else None,
            type="checkout.session.lookup",
            raw={},
        )

    monkeypatch.setattr(stripe, "lookup_configured", lambda: True)
    monkeypatch.setattr(stripe, "get_checkout_status", lookup)


def _payment_cases(db):
    return db(
        "SELECT context->>'case_key', priority, subject FROM support_tickets"
        " WHERE kind='ops_case' AND context->>'case_key' LIKE 'provider_payment:%'"
        " ORDER BY created_at"
    )


@pytest.mark.asyncio
async def test_sweep_settles_what_it_can_and_opens_a_case_for_the_rest(
    client, db, asession, monkeypatch
):
    uid = await _member(client, db, "stuck@ops.io")
    paid = _pending(db, uid=uid, cs="cs_paid", minutes_old=45)  # provider says paid
    stuck = _pending(db, uid=uid, cs="cs_stuck", minutes_old=45)  # provider has no outcome
    fresh = _pending(db, uid=uid, cs="cs_fresh", minutes_old=5)  # too young for a case
    _answers(monkeypatch, {"cs_paid": "succeeded", "cs_stuck": "pending", "cs_fresh": "pending"})

    out = await ops_case_service.sweep(asession)
    await asession.commit()
    assert out["opened"] == 1
    # the paid one was credited by the lookup, not escalated
    assert db("SELECT status FROM payments WHERE id=:p", p=paid)[0][0] == "succeeded"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 60
    cases = _payment_cases(db)
    assert [c[0] for c in cases] == [f"provider_payment:{stuck}"]
    assert cases[0][1] == "high" and "stripe deposit still pending" in cases[0][2]
    assert db("SELECT status FROM payments WHERE id=:p", p=fresh)[0][0] == "pending"

    # idempotent while the case is open
    again = await ops_case_service.sweep(asession)
    await asession.commit()
    assert again["opened"] == 0 and len(_payment_cases(db)) == 1
