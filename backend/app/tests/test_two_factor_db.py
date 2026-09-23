"""Two-factor authentication — real TOTP, end to end.

The bar: with 2FA on, NO path hands out a session without the second factor (password
login, Google login, admin panel); a code works once; brute force locks; recovery codes
work once and survive a lost key; the secret is never stored in plaintext; turning it off
needs proof; staff can reset it for a user who lost everything, and it is audited.
"""

from __future__ import annotations

import base64
import os
import uuid

import pytest

from app.core import crypto, totp
from app.core.config import get_settings
from app.services.integrations import oauth

PW = "Passw0rd!23"


@pytest.fixture
def keys(monkeypatch, tmp_path):
    """A temporary platform key file (2FA secrets are encrypted with it)."""
    path = tmp_path / "platform.keys"
    path.write_text(f"k1:{base64.b64encode(os.urandom(32)).decode()}", encoding="utf-8")
    s = get_settings()
    monkeypatch.setattr(s, "assistant_encryption_keys_file", str(path), raising=False)
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)
    crypto.reset_cache()
    yield path
    crypto.reset_cache()


class Clock:
    """Moves TOTP time forward without touching the global time module."""

    def __init__(self, monkeypatch):
        self.t = totp.clock()
        monkeypatch.setattr(totp, "clock", lambda: self.t)

    def tick(self, steps: int = 1) -> None:
        self.t += totp.PERIOD * steps


async def _user(client, db, email: str) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "T"}
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"], db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


async def _enable(client, tok: str, clock: Clock) -> tuple[str, list[str]]:
    setup = await client.post("/api/v1/auth/mfa/setup", headers=_h(tok))
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/Capimax%20PropShare:")
    assert setup.json()["qr_svg_data_uri"].startswith("data:image/svg+xml")
    r = await client.post(
        "/api/v1/auth/mfa/enable", json={"code": totp.code_at(secret, clock.t)}, headers=_h(tok)
    )
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


async def _password_login(client, email: str):
    client.cookies.clear()
    return await client.post("/api/v1/auth/login", json={"email": email, "password": PW})


# --------------------------------------------------------------------------- #
# Enrolment
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_enrol_needs_a_real_code_and_stores_the_secret_encrypted(
    client, db, keys, monkeypatch
):
    clock = Clock(monkeypatch)
    tok, uid = await _user(client, db, "enrol@x.com")

    setup = (await client.post("/api/v1/auth/mfa/setup", headers=_h(tok))).json()
    # nothing enforced until confirmed
    st = (await client.get("/api/v1/auth/mfa", headers=_h(tok))).json()
    assert (st["enabled"], st["available"]) == (False, True)

    wrong = await client.post("/api/v1/auth/mfa/enable", json={"code": "000000"}, headers=_h(tok))
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "MFA_INVALID_CODE"

    r = await client.post(
        "/api/v1/auth/mfa/enable",
        json={"code": totp.code_at(setup["secret"], clock.t)},
        headers=_h(tok),
    )
    assert r.status_code == 200, r.text
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(len(c) == 19 and c.count("-") == 3 for c in codes)

    st = (await client.get("/api/v1/auth/mfa", headers=_h(tok))).json()
    assert (st["enabled"], st["recovery_codes_remaining"]) == (True, 10)

    # at rest: ciphertext only; recovery codes only as hashes
    blob = bytes(db("SELECT secret_enc FROM user_mfa WHERE user_id=:u", u=uid)[0][0])
    assert setup["secret"].encode() not in blob
    assert crypto.decrypt(blob).decode() == setup["secret"]
    stored = {r[0] for r in db("SELECT code_hash FROM user_recovery_codes WHERE user_id=:u", u=uid)}
    assert not any(c in stored or c.replace("-", "") in stored for c in codes)
    # the user is told
    assert (
        db(
            "SELECT COUNT(*) FROM notifications WHERE user_id=:u AND title LIKE 'Two-factor%on'",
            u=uid,
        )[0][0]
        == 1
    )


@pytest.mark.asyncio
async def test_setup_is_refused_without_an_encryption_key(client, db):
    tok, _ = await _user(client, db, "nokey@x.com")
    r = await client.post("/api/v1/auth/mfa/setup", headers=_h(tok))
    assert r.status_code == 503 and r.json()["error"]["code"] == "MFA_UNAVAILABLE"
    assert (await client.get("/api/v1/auth/mfa", headers=_h(tok))).json()["available"] is False


@pytest.mark.asyncio
async def test_setup_expires(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, uid = await _user(client, db, "late@x.com")
    secret = (await client.post("/api/v1/auth/mfa/setup", headers=_h(tok))).json()["secret"]
    db(
        "UPDATE user_mfa SET pending_created_at = now() - interval '31 minutes' WHERE user_id=:u",
        u=uid,
    )
    r = await client.post(
        "/api/v1/auth/mfa/enable", json={"code": totp.code_at(secret, clock.t)}, headers=_h(tok)
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "MFA_SETUP_EXPIRED"


# --------------------------------------------------------------------------- #
# Sign-in
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_password_alone_no_longer_opens_a_session(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, _ = await _user(client, db, "login@x.com")
    secret, _codes = await _enable(client, tok, clock)

    r = await _password_login(client, "login@x.com")
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_required"] is True and body["mfa_token"]
    assert body["access_token"] is None
    assert get_settings().refresh_cookie_name not in r.cookies  # no refresh cookie either

    clock.tick()
    ok = await client.post(
        "/api/v1/auth/login/mfa",
        json={"mfa_token": body["mfa_token"], "code": totp.code_at(secret, clock.t)},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["access_token"] and ok.json()["mfa_required"] is False
    assert get_settings().refresh_cookie_name in ok.cookies
    me = await client.get("/api/v1/auth/me", headers=_h(ok.json()["access_token"]))
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_a_code_works_only_once(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, _ = await _user(client, db, "replay@x.com")
    secret, _ = await _enable(client, tok, clock)
    clock.tick()
    code = totp.code_at(secret, clock.t)

    ch = (await _password_login(client, "replay@x.com")).json()["mfa_token"]
    first = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": code})
    assert first.status_code == 200

    ch2 = (await _password_login(client, "replay@x.com")).json()["mfa_token"]
    again = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": ch2, "code": code})
    assert again.status_code == 401 and again.json()["error"]["code"] == "MFA_INVALID_CODE"


@pytest.mark.asyncio
async def test_the_enrolment_code_cannot_be_reused_to_sign_in(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, _ = await _user(client, db, "same@x.com")
    secret, _ = await _enable(client, tok, clock)
    ch = (await _password_login(client, "same@x.com")).json()["mfa_token"]
    r = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": totp.code_at(secret, clock.t)}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_five_wrong_codes_lock_the_second_step(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, uid = await _user(client, db, "brute@x.com")
    secret, _ = await _enable(client, tok, clock)
    ch = (await _password_login(client, "brute@x.com")).json()["mfa_token"]

    lefts = []
    for _ in range(4):
        r = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": "111111"})
        assert r.status_code == 401
        lefts.append(r.json()["error"]["details"]["attempts_left"])
    assert lefts == [4, 3, 2, 1]  # the counter survives the rolled-back requests
    fifth = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": "111111"})
    assert fifth.status_code == 429 and fifth.json()["error"]["code"] == "MFA_LOCKED"

    # even the right code is refused while locked
    clock.tick()
    right = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": totp.code_at(secret, clock.t)}
    )
    assert right.status_code == 429
    assert db("SELECT locked_until IS NOT NULL FROM user_mfa WHERE user_id=:u", u=uid)[0][0]
    assert (
        db("SELECT COUNT(*) FROM audit_log WHERE action='mfa.locked' AND entity_id=:u", u=str(uid))[
            0
        ][0]
        == 1
    )


@pytest.mark.asyncio
async def test_recovery_code_works_once_and_is_reported(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, uid = await _user(client, db, "lost@x.com")
    _secret, codes = await _enable(client, tok, clock)

    ch = (await _password_login(client, "lost@x.com")).json()["mfa_token"]
    typed = codes[0].lower().replace("-", " ")  # forgiving about case and separators
    ok = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": typed})
    assert ok.status_code == 200, ok.text

    ch2 = (await _password_login(client, "lost@x.com")).json()["mfa_token"]
    reuse = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": ch2, "code": codes[0]})
    assert reuse.status_code == 401

    st = (await client.get("/api/v1/auth/mfa", headers=_h(ok.json()["access_token"]))).json()
    assert st["recovery_codes_remaining"] == 9
    assert (
        db(
            "SELECT COUNT(*) FROM notifications WHERE user_id=:u "
            "AND title='A recovery code was used'",
            u=uid,
        )[0][0]
        == 1
    )


@pytest.mark.asyncio
async def test_recovery_codes_still_work_if_the_key_is_lost(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, _ = await _user(client, db, "keyloss@x.com")
    secret, codes = await _enable(client, tok, clock)
    ch = (await _password_login(client, "keyloss@x.com")).json()["mfa_token"]

    s = get_settings()
    monkeypatch.setattr(s, "assistant_encryption_keys_file", "", raising=False)
    crypto.reset_cache()
    clock.tick()
    by_app = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": totp.code_at(secret, clock.t)}
    )
    assert by_app.status_code == 503 and "recovery" in by_app.json()["error"]["message"]
    by_code = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": codes[1]})
    assert by_code.status_code == 200


@pytest.mark.asyncio
async def test_forged_or_stale_challenges_are_refused(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, uid = await _user(client, db, "forge@x.com")
    secret, _ = await _enable(client, tok, clock)
    clock.tick()
    code = totp.code_at(secret, clock.t)

    forged = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": "x" * 40, "code": code})
    assert forged.status_code == 401 and forged.json()["error"]["code"] == "MFA_CHALLENGE_EXPIRED"

    from itsdangerous import URLSafeTimedSerializer

    other_salt = URLSafeTimedSerializer(get_settings().jwt_secret, salt="property-preview")
    wrong_purpose = other_salt.dumps({"uid": str(uid), "via": "password"})
    r = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": wrong_purpose, "code": code})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_google_sign_in_also_asks_for_the_code(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, _ = await _user(client, db, "google@x.com")
    secret, _ = await _enable(client, tok, clock)

    async def fake_exchange(provider, code, redirect_uri):
        return oauth.OAuthProfile(subject="g-123", email="google@x.com", full_name="G")

    monkeypatch.setattr(oauth, "exchange", fake_exchange)
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/oauth/google", json={"code": "c", "redirect_uri": "https://x/cb"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["mfa_required"] is True and r.json()["access_token"] is None
    clock.tick()
    ok = await client.post(
        "/api/v1/auth/login/mfa",
        json={"mfa_token": r.json()["mfa_token"], "code": totp.code_at(secret, clock.t)},
    )
    assert ok.status_code == 200 and ok.json()["access_token"]


@pytest.mark.asyncio
async def test_accounts_without_2fa_sign_in_exactly_as_before(client, db):
    await _user(client, db, "plain@x.com")
    r = await _password_login(client, "plain@x.com")
    assert r.status_code == 200
    assert r.json()["access_token"] and r.json()["mfa_required"] is False


# --------------------------------------------------------------------------- #
# Turning it off / new recovery codes / staff reset
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_disable_needs_password_and_a_code(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, uid = await _user(client, db, "off@x.com")
    secret, _ = await _enable(client, tok, clock)
    clock.tick()
    code = totp.code_at(secret, clock.t)

    bad_pw = await client.post(
        "/api/v1/auth/mfa/disable", json={"password": "nope", "code": code}, headers=_h(tok)
    )
    assert bad_pw.status_code == 401
    assert (await client.get("/api/v1/auth/mfa", headers=_h(tok))).json()["enabled"] is True

    ok = await client.post(
        "/api/v1/auth/mfa/disable", json={"password": PW, "code": code}, headers=_h(tok)
    )
    assert ok.status_code == 204
    assert (await client.get("/api/v1/auth/mfa", headers=_h(tok))).json()["enabled"] is False
    assert db("SELECT COUNT(*) FROM user_recovery_codes WHERE user_id=:u", u=uid)[0][0] == 0
    assert (await _password_login(client, "off@x.com")).json()["access_token"]


@pytest.mark.asyncio
async def test_google_only_account_disables_with_the_code_alone(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, uid = await _user(client, db, "gonly@x.com")
    db("UPDATE users SET password_hash=NULL WHERE id=:u", u=uid)
    assert (await client.get("/api/v1/auth/mfa", headers=_h(tok))).json()["has_password"] is False
    secret, _ = await _enable(client, tok, clock)
    clock.tick()
    r = await client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": None, "code": totp.code_at(secret, clock.t)},
        headers=_h(tok),
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_new_recovery_codes_replace_the_old_ones(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, _ = await _user(client, db, "regen@x.com")
    secret, old = await _enable(client, tok, clock)
    clock.tick()
    r = await client.post(
        "/api/v1/auth/mfa/recovery-codes",
        json={"code": totp.code_at(secret, clock.t)},
        headers=_h(tok),
    )
    assert r.status_code == 200
    new = r.json()["recovery_codes"]
    assert len(new) == 10 and not set(new) & set(old)

    ch = (await _password_login(client, "regen@x.com")).json()["mfa_token"]
    stale = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": old[0]})
    assert stale.status_code == 401
    fresh = await client.post("/api/v1/auth/login/mfa", json={"mfa_token": ch, "code": new[0]})
    assert fresh.status_code == 200


@pytest.mark.asyncio
async def test_cannot_enrol_twice(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, _ = await _user(client, db, "twice@x.com")
    await _enable(client, tok, clock)
    r = await client.post("/api/v1/auth/mfa/setup", headers=_h(tok))
    assert r.status_code == 409 and r.json()["error"]["code"] == "MFA_ALREADY_ENABLED"


@pytest.mark.asyncio
async def test_mfa_endpoints_require_sign_in(client, db):
    assert (await client.get("/api/v1/auth/mfa")).status_code == 401
    assert (await client.post("/api/v1/auth/mfa/setup")).status_code == 401


# --------------------------------------------------------------------------- #
# Admin panel
# --------------------------------------------------------------------------- #
async def _admin_with_2fa(client, db, clock, email="boss@x.com") -> tuple[str, str]:
    tok, uid = await _user(client, db, email)
    db("INSERT INTO user_roles (user_id, role) VALUES (:u,'admin')", u=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:u", u=uid)
    secret, _ = await _enable(client, tok, clock)
    return uid, secret


@pytest.mark.asyncio
async def test_admin_panel_asks_for_the_code_before_anything_opens(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    _uid, secret = await _admin_with_2fa(client, db, clock)
    client.cookies.clear()
    await client.post("/admin/login", data={"username": "boss@x.com", "password": PW})

    blocked = await client.get("/admin/user/list", follow_redirects=False)
    assert blocked.status_code == 302 and blocked.headers["location"].endswith("/admin/two-factor")

    wrong = await client.post("/admin/two-factor", data={"code": "000000"})
    assert wrong.status_code == 400 and "not valid" in wrong.text
    still = await client.get("/admin/user/list", follow_redirects=False)
    assert still.status_code == 302

    clock.tick()
    ok = await client.post(
        "/admin/two-factor", data={"code": totp.code_at(secret, clock.t)}, follow_redirects=False
    )
    assert ok.status_code == 303
    assert (await client.get("/admin/user/list")).status_code == 200


@pytest.mark.asyncio
async def test_staff_can_reset_a_users_2fa_and_it_is_audited(client, db, keys, monkeypatch):
    clock = Clock(monkeypatch)
    tok, victim = await _user(client, db, "victim@x.com")
    await _enable(client, tok, clock)

    _atok, admin_uid = await _user(client, db, "staff@x.com")
    db("INSERT INTO user_roles (user_id, role) VALUES (:u,'admin')", u=admin_uid)
    db("UPDATE users SET active_role='admin' WHERE id=:u", u=admin_uid)
    client.cookies.clear()
    await client.post("/admin/login", data={"username": "staff@x.com", "password": PW})

    r = await client.get(f"/admin/user/action/reset-2fa?pks={victim}")
    assert r.status_code in (200, 302, 303)
    assert db("SELECT COUNT(*) FROM user_mfa WHERE user_id=:u", u=victim)[0][0] == 0
    audit = db(
        "SELECT actor_id FROM audit_log WHERE action='mfa.admin_reset' AND entity_id=:v",
        v=str(victim),
    )
    assert [str(a[0]) for a in audit] == [str(admin_uid)]
    assert (
        db(
            "SELECT COUNT(*) FROM notifications WHERE user_id=:u "
            "AND title LIKE '%reset by support'",
            u=victim,
        )[0][0]
        == 1
    )
    assert (await _password_login(client, "victim@x.com")).json()["access_token"]


def test_totp_matches_the_rfc_test_vectors():
    key = b"12345678901234567890"
    vectors = {
        59: "94287082",
        1111111109: "07081804",
        1234567890: "89005924",
        2000000000: "69279037",
        20000000000: "65353130",
    }
    for t, expected in vectors.items():
        assert totp.hotp(key, t // 30, digits=8) == expected


def test_recovery_code_alphabet_avoids_look_alikes():
    from app.services.mfa_service import _new_code

    for _ in range(50):
        code = _new_code().replace("-", "")
        assert len(code) == 16 and not set(code) & set("O0I1")


def test_challenge_uid_roundtrip():
    from app.services import mfa_service

    uid = uuid.uuid4()
    assert mfa_service.read_challenge(mfa_service.issue_challenge(uid, via="password")) == (
        uid,
        "password",
    )
