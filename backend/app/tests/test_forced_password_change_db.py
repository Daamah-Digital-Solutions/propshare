"""Staff-provisioned panel accounts: one-time password + forced change at first login.

Reproduces the gap: a password handed to the client out of band kept working forever
(nothing forced a change), and there was no safe way to provision a panel account at all.

Now: the provisioning service returns a strong random password exactly once (never logged,
audited or stored in clear), the account can open NOTHING in the panel except the
change-password page, the API refuses the one-time password, and after the change the
shared password is dead. The service refuses to re-key a platform admin.
"""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.services import auth_service

EMAIL = "client-editor@x.com"
NEW_PW = "my own long passphrase 2026"


async def _provision(asession, email=EMAIL, role="content_editor") -> str:
    pw = await auth_service.provision_panel_user(
        asession, email=email, role=role, full_name="Client"
    )
    await asession.commit()
    return pw


@pytest.mark.asyncio
async def test_provisioned_password_is_strong_and_never_persisted(client, db, asession):
    pw = await _provision(asession)
    assert len(pw) >= 16
    assert any(c.islower() for c in pw) and any(c.isupper() for c in pw)
    assert any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)
    row = db(
        "SELECT password_hash, must_change_password, email_verified FROM users WHERE email=:e",
        e=EMAIL,
    )[0]
    assert row[0] and row[0] != pw and row[1] is True and row[2] is True
    roles = {
        r[0]
        for r in db(
            "SELECT role FROM user_roles ur JOIN users u ON u.id=ur.user_id WHERE u.email=:e",
            e=EMAIL,
        )
    }
    assert roles == {"investor", "content_editor"}
    # the secret is nowhere in the audit trail or the email outbox
    blob = str(db("SELECT action, before, after FROM audit_log")) + str(
        db("SELECT * FROM email_outbox")
    )
    assert pw not in blob and "auth.panel_user_provisioned" in blob


@pytest.mark.asyncio
async def test_first_login_forces_change_and_kills_the_shared_password(client, db, asession):
    pw = await _provision(asession)
    # the API refuses the one-time password outright
    r = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": pw})
    assert r.status_code == 403 and r.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    # panel login works but every page bounces to the change-password screen
    r = await client.post("/admin/login", data={"username": EMAIL, "password": pw})
    assert "session" in client.cookies
    for url in ("/admin/", "/admin/listing/", "/admin/listing/new"):
        r = await client.get(url, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].endswith("/admin/change-password"), (
            url
        )
    page = await client.get("/admin/change-password")
    assert page.status_code == 200 and "Choose your own password" in page.text
    # plain-sentence validation
    bad = {"current_password": pw, "new_password": "short1", "confirm_password": "short1"}
    r = await client.post("/admin/change-password", data=bad)
    assert r.status_code == 400 and "use at least 12 characters" in r.text
    r = await client.post(
        "/admin/change-password",
        data={"current_password": "wrong", "new_password": NEW_PW, "confirm_password": NEW_PW},
    )
    assert r.status_code == 400 and "Current password is incorrect" in r.text
    r = await client.post(
        "/admin/change-password",
        data={"current_password": pw, "new_password": NEW_PW, "confirm_password": NEW_PW + "x"},
    )
    assert "do not match" in r.text
    r = await client.post(
        "/admin/change-password",
        data={"current_password": pw, "new_password": pw, "confirm_password": pw},
    )
    assert "different from the one you were given" in r.text
    assert db("SELECT must_change_password FROM users WHERE email=:e", e=EMAIL)[0][0] is True
    # the real change
    r = await client.post(
        "/admin/change-password",
        data={"current_password": pw, "new_password": NEW_PW, "confirm_password": NEW_PW},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db("SELECT must_change_password FROM users WHERE email=:e", e=EMAIL)[0][0] is False
    assert (await client.get("/admin/listing/")).status_code == 200
    home = (await client.get("/admin/")).text
    assert "Listings" in home and "Withdrawals" not in home
    # shared password is dead everywhere; the new one works
    await client.get("/admin/logout")
    client.cookies.clear()
    r = await client.post("/admin/login", data={"username": EMAIL, "password": pw})
    assert r.status_code == 400 and "session" not in client.cookies
    r = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": pw})
    assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": NEW_PW})
    assert r.status_code == 200
    audit = str(db("SELECT action, before, after FROM audit_log"))
    assert "auth.password_changed_first_login" in audit
    assert pw not in audit and NEW_PW not in audit


@pytest.mark.asyncio
async def test_provisioning_refuses_to_rekey_a_platform_admin(client, db, asession):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "boss@x.com", "password": "Passw0rd!23", "full_name": "Boss"},
    )
    assert r.status_code == 201
    uid = db("SELECT id FROM users WHERE email='boss@x.com'")[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    before = db("SELECT password_hash FROM users WHERE id=:i", i=uid)[0][0]
    with pytest.raises(AppError) as exc:
        await auth_service.provision_panel_user(asession, email="boss@x.com", role="content_editor")
    assert exc.value.code == "ADMIN_ACCOUNT"
    await asession.rollback()
    after = db("SELECT password_hash, must_change_password FROM users WHERE id=:i", i=uid)[0]
    assert after[0] == before and after[1] is False
    assert {x[0] for x in db("SELECT role FROM user_roles WHERE user_id=:i", i=uid)} == {
        "investor",
        "admin",
    }
    with pytest.raises(AppError):
        await auth_service.provision_panel_user(asession, email="new@x.com", role="admin")
