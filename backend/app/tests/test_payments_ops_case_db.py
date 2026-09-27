"""Ops cases for card / crypto payments no webhook settled.

The hourly sweep first lets the Stripe lookup settle or fail whatever it can. A case is only
for what stays pending AFTER that, and only when it means something:

* a card payment still pending past ``ops_payment_stale_hours`` (25 h: Stripe expires an
  unpaid checkout at 24 h and the lookup then fails it) — the lookup cannot reach Stripe;
  high priority. A member who simply closed the checkout never opens a case.
* a crypto invoice still pending past ``ops_stale_hours`` (48 h) — usually abandoned; a
  normal-priority case that says so.
* one case per payment, ever: once staff close it, it is not reopened.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import AppError
from app.services import ops_case_service, ticket_service
from app.services.integrations.payments import ParsedWebhook
from app.services.integrations.payments import stripe_gateway as stripe

PW = "Passw0rd!23"


async def _member(client, db, email: str, *, admin: bool = False) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "O"}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    if admin:
        db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    return uid


def _pending(db, *, uid: str, ref: str, hours_old: float, provider: str = "stripe") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO payments (id, user_id, provider, provider_payment_id, amount, currency,"
        " status, purpose, payment_method, created_at) VALUES"
        " (:id,:uid,:prov,:ref,60,'USD','pending','deposit',:pm,"
        " now() - make_interval(mins => :m))",
        id=pid,
        uid=uid,
        prov=provider,
        ref=ref,
        pm="card" if provider == "stripe" else "crypto",
        m=int(hours_old * 60),
    )
    return pid


def _answers(monkeypatch, outcomes: dict[str, str]) -> None:
    async def lookup(session_id: str) -> ParsedWebhook:
        status = outcomes[session_id]
        if status == "error":
            raise AppError("PAYMENT_PROVIDER_ERROR", "Stripe refused (403).", status_code=502)
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
        "SELECT context->>'case_key', priority, subject, status FROM support_tickets"
        " WHERE kind='ops_case' AND context->>'case_key' LIKE 'provider_payment:%'"
        " ORDER BY created_at"
    )


@pytest.mark.asyncio
async def test_only_meaningful_stuck_payments_open_a_case_once(client, db, asession, monkeypatch):
    admin = await _member(client, db, "adm@ops.io", admin=True)
    uid = await _member(client, db, "stuck@ops.io")
    paid = _pending(db, uid=uid, ref="cs_paid", hours_old=2)  # Stripe says paid -> credited
    abandoned = _pending(db, uid=uid, ref="cs_open", hours_old=3)  # checkout open: no case
    unreachable = _pending(db, uid=uid, ref="cs_err", hours_old=26)  # lookup fails past 24 h
    crypto_new = _pending(db, uid=uid, ref="inv_1", hours_old=5, provider="nowpayments")
    crypto_old = _pending(db, uid=uid, ref="inv_2", hours_old=50, provider="nowpayments")
    _answers(monkeypatch, {"cs_paid": "succeeded", "cs_open": "pending", "cs_err": "error"})

    out = await ops_case_service.sweep(asession)
    await asession.commit()
    assert db("SELECT status FROM payments WHERE id=:p", p=paid)[0][0] == "succeeded"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 60
    cases = {c[0]: c for c in _payment_cases(db)}
    assert set(cases) == {f"provider_payment:{unreachable}", f"provider_payment:{crypto_old}"}
    card = cases[f"provider_payment:{unreachable}"]
    assert card[1] == "high" and "still pending 26h after checkout" in card[2]
    crypto = cases[f"provider_payment:{crypto_old}"]
    assert crypto[1] == "normal" and "Crypto deposit invoice pending" in crypto[2]
    assert f"provider_payment:{abandoned}" not in cases
    assert f"provider_payment:{crypto_new}" not in cases
    assert out["opened"] == 2

    # idempotent while open, and a CLOSED case is not reopened by the next hourly sweep
    assert (await ops_case_service.sweep(asession))["opened"] == 0
    await asession.commit()
    tid = db(
        "SELECT id FROM support_tickets WHERE context->>'case_key' = :k",
        k=f"provider_payment:{crypto_old}",
    )[0][0]
    await ticket_service.set_status(asession, actor_id=admin, ticket_id=tid, status="closed")
    await asession.commit()
    assert (await ops_case_service.sweep(asession))["opened"] == 0
    await asession.commit()
    assert len(_payment_cases(db)) == 2
