"""A success answer means the work is saved.

The request session used to commit AFTER the response had been sent (FastAPI's default for a
dependency with ``yield`` since 0.118). The client was told "done" first, so:
  * its very next request could read the state from before (a position just listed still
    showed as not listed; found in the browser, 2026-10-05);
  * a commit that failed had already been reported as a success;
  * a background task started before the commit and could not see a row the request had
    just written (the instant payout of an approved withdrawal had to commit by hand).

``api.deps.SessionDep`` is function-scoped: the commit happens when the route returns, before
the first byte of the response.
"""

from __future__ import annotations

import json

import pytest

from app.main import app

PW = "Passw0rd!23"


@pytest.mark.asyncio
async def test_the_row_is_committed_when_the_response_starts(client, db):
    email = "committed.first@x.io"
    body = json.dumps({"email": email, "password": PW, "full_name": "Early"}).encode()
    seen: dict[str, int] = {}
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            seen["status"] = message["status"]
            # another connection, exactly what the client's next request would use
            seen["rows"] = db("SELECT count(*) FROM users WHERE email=:e", e=email)[0][0]

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/auth/register",
        "raw_path": b"/api/v1/auth/register",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"test"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("test", 80),
    }
    await app(scope, receive, send)
    assert seen == {"status": 201, "rows": 1}


@pytest.mark.asyncio
async def test_a_commit_that_fails_is_not_answered_as_a_success(client, db, monkeypatch):
    """Two payments may not share a provider id (``payments_provider_pid_key``), and a deposit
    writes that id only when the session commits. The second deposit here used to be answered
    200 with a checkout link, and its payment was then rolled back behind the client's back."""
    from app.services.integrations.payments import CheckoutResult
    from app.services.integrations.payments import stripe_gateway as stripe

    async def same_session_twice(**kwargs):
        return CheckoutResult(
            provider_payment_id="cs_same", checkout_url="https://s/c", status="pending"
        )

    monkeypatch.setattr(stripe, "is_configured", lambda: True)
    monkeypatch.setattr(stripe, "create_checkout", same_session_twice)
    reg = await client.post(
        "/api/v1/auth/register", json={"email": "twice@x.io", "password": PW, "full_name": "T"}
    )
    token = reg.json()["access_token"]
    db(
        "UPDATE kyc_verifications SET status='verified' "
        "WHERE user_id=(SELECT id FROM users WHERE email='twice@x.io')"
    )

    async def deposit(key: str):
        return await client.post(
            "/api/v1/wallet/deposit",
            json={"amount": 40, "method": "card"},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )

    assert (await deposit("first")).status_code == 200
    second = await deposit("second")
    assert second.status_code >= 400, second.text
    assert db("SELECT count(*) FROM payments")[0][0] == 1


@pytest.mark.asyncio
async def test_a_refused_request_still_saves_nothing(client, db):
    await client.post(
        "/api/v1/auth/register", json={"email": "once@x.io", "password": PW, "full_name": "A"}
    )
    again = await client.post(
        "/api/v1/auth/register", json={"email": "once@x.io", "password": PW, "full_name": "B"}
    )
    assert again.status_code >= 400
    assert db("SELECT count(*) FROM users WHERE email='once@x.io'")[0][0] == 1
    assert db("SELECT full_name FROM profiles")[0][0] == "A"
