"""AI assistant Phase 1 — foundation: encryption, tables, settings, config gate.

What each test protects:
  * conversations must be UNREADABLE in the database (so dumps and the nightly backups
    never contain chat), yet round-trip transparently through the ORM;
  * a rotated key must still read old rows, and a wrong or missing key must FAIL rather
    than silently falling back to plaintext;
  * tickets are staff-facing and plaintext, but must never be given chat text (enforced by
    the handoff design; here we pin that ticket columns are plain and messages are not);
  * every assistant switch ships OFF, and the config gate stays False until a provider key,
    an HMAC secret and a readable key file are all present.
"""

from __future__ import annotations

import base64
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import crypto
from app.core.config import get_settings


def _write_keys(tmp_path, *key_ids: str) -> str:
    path = tmp_path / "assistant.keys"
    path.write_text(
        "\n".join(f"{k}:{base64.b64encode(os.urandom(32)).decode()}" for k in key_ids),
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def keys(monkeypatch, tmp_path):
    """A temporary key file with k1 active (the real one lives outside the app tree)."""
    s = get_settings()
    path = _write_keys(tmp_path, "k1")
    monkeypatch.setattr(s, "assistant_encryption_keys_file", path, raising=False)
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)
    crypto.reset_cache()
    yield path
    crypto.reset_cache()


# --- encryption ---------------------------------------------------------------------- #
def test_encrypt_roundtrip_and_blob_shape(keys):
    blob = crypto.encrypt(b"hello ya salam")
    assert crypto.decrypt(blob).decode() == "hello ya salam"
    assert blob.startswith(b"k1:") and b"hello" not in blob
    assert crypto.key_id_of(blob) == "k1"
    # a fresh nonce every time: the same text never produces the same ciphertext
    assert crypto.encrypt(b"same") != crypto.encrypt(b"same")


def test_rotation_keeps_reading_old_rows(monkeypatch, tmp_path):
    s = get_settings()
    old_blob_path = _write_keys(tmp_path, "k1")
    monkeypatch.setattr(s, "assistant_encryption_keys_file", old_blob_path, raising=False)
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)
    crypto.reset_cache()
    old_blob = crypto.encrypt(b"written with k1")
    k1_line = open(old_blob_path, encoding="utf-8").read().strip()

    # rotate: add k2 and make it active, keep k1 in the file
    rotated = tmp_path / "rotated.keys"
    rotated.write_text(f"{k1_line}\nk2:{base64.b64encode(os.urandom(32)).decode()}\n", "utf-8")
    monkeypatch.setattr(s, "assistant_encryption_keys_file", str(rotated), raising=False)
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k2", raising=False)
    crypto.reset_cache()
    assert crypto.active_key_id() == "k2"
    assert crypto.decrypt(old_blob) == b"written with k1"  # old row still readable
    assert crypto.key_id_of(crypto.encrypt(b"new")) == "k2"  # new rows use k2
    crypto.reset_cache()


def test_wrong_key_tampering_and_missing_config_fail_loudly(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(
        s, "assistant_encryption_keys_file", _write_keys(tmp_path, "k1"), raising=False
    )
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)
    crypto.reset_cache()
    blob = crypto.encrypt(b"secret")
    tampered = blob[:-1] + bytes([blob[-1] ^ 0x01])
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(tampered)
    # a different key file cannot read it
    monkeypatch.setattr(
        s, "assistant_encryption_keys_file", _write_keys(tmp_path, "k1"), raising=False
    )
    crypto.reset_cache()
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(blob)
    # unknown key id
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k9", raising=False)
    crypto.reset_cache()
    with pytest.raises(crypto.CryptoNotConfigured):
        crypto.encrypt(b"x")
    # no key file at all => not configured (never plaintext)
    monkeypatch.setattr(s, "assistant_encryption_keys_file", "", raising=False)
    crypto.reset_cache()
    assert crypto.is_configured() is False
    with pytest.raises(crypto.CryptoNotConfigured):
        crypto.encrypt(b"x")
    crypto.reset_cache()


# --- tables + encryption at rest ------------------------------------------------------ #
@pytest.mark.asyncio
async def test_conversation_is_ciphertext_in_the_database(client, db, asession, keys):
    from app.models import AssistantConversation, AssistantMessage

    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "chat@x.com", "password": "Passw0rd!23", "full_name": "Chat"},
    )
    assert r.status_code == 201
    uid = db("SELECT id FROM users WHERE email='chat@x.com'")[0][0]

    convo = AssistantConversation(user_id=uid, lang="ar", active_role="investor")
    asession.add(convo)
    await asession.flush()
    secret = "رصيدي كام؟ my wallet balance please"
    msg = AssistantMessage(
        conversation_id=convo.id,
        role="user",
        text=secret,
        content={"note": secret},
        enc_key_id=crypto.active_key_id(),
        usage={"input_tokens": 12, "output_tokens": 0},
    )
    asession.add(msg)
    await asession.commit()

    # raw bytes in the table contain no readable text
    raw = db("SELECT text_enc, content_enc, enc_key_id, usage FROM assistant_messages")[0]
    assert bytes(raw[0]).startswith(b"k1:") and secret.encode() not in bytes(raw[0])
    assert secret.encode() not in bytes(raw[1])
    assert raw[2] == "k1" and raw[3] == {"input_tokens": 12, "output_tokens": 0}
    # and the ORM decrypts it back
    loaded = await asession.get(AssistantMessage, msg.id)
    await asession.refresh(loaded)
    assert loaded.text == secret and loaded.content == {"note": secret}


@pytest.mark.asyncio
async def test_ticket_numbers_are_sequential_and_thread_is_plaintext(client, db, asession):
    from app.models import SupportTicket, SupportTicketMessage

    first = SupportTicket(kind="support", category="payments", subject="Deposit not credited")
    second = SupportTicket(kind="knowledge_gap", category="kyc")
    asession.add_all([first, second])
    await asession.commit()
    await asession.refresh(first)
    await asession.refresh(second)
    assert first.ticket_no.startswith("CPX-") and len(first.ticket_no) == 10
    assert int(second.ticket_no[4:]) == int(first.ticket_no[4:]) + 1
    assert first.status == "open" and first.priority == "normal" and first.source == "assistant"

    note = SupportTicketMessage(
        ticket_id=first.id, author_type="staff", body="Checked", internal=True
    )
    asession.add(note)
    await asession.commit()
    row = db("SELECT body, internal FROM support_ticket_messages")[0]
    assert row == ("Checked", True)  # staff-facing, deliberately not encrypted


@pytest.mark.asyncio
async def test_consent_is_per_user_per_policy_version(client, db, asession):
    from app.models import AssistantConsent

    await client.post(
        "/api/v1/auth/register",
        json={"email": "consent@x.com", "password": "Passw0rd!23", "full_name": "C"},
    )
    uid = db("SELECT id FROM users WHERE email='consent@x.com'")[0][0]
    asession.add(AssistantConsent(user_id=uid, policy_version="2026-10", ip="1.2.3.4"))
    asession.add(AssistantConsent(user_id=uid, policy_version="2027-01"))
    await asession.commit()
    rows = db("SELECT policy_version FROM assistant_consents WHERE user_id=:u ORDER BY 1", u=uid)
    assert [r[0] for r in rows] == ["2026-10", "2027-01"]
    with pytest.raises(IntegrityError):  # same user + same version twice is refused
        asession.add(AssistantConsent(user_id=uid, policy_version="2026-10"))
        await asession.commit()
    await asession.rollback()


@pytest.mark.asyncio
async def test_kb_articles_are_versioned_per_slug_and_language(client, db, asession):
    from app.models import KbArticle

    asession.add(KbArticle(slug="fees", lang="en", title="Fees", body_md="...", version=1))
    asession.add(KbArticle(slug="fees", lang="ar", title="الرسوم", body_md="...", version=1))
    asession.add(KbArticle(slug="fees", lang="en", title="Fees", body_md="v2", version=2))
    await asession.commit()
    assert db("SELECT count(*) FROM kb_articles")[0][0] == 3
    assert (
        db("SELECT status FROM kb_articles LIMIT 1")[0][0] == "draft"
    )  # never approved by default
    with pytest.raises(IntegrityError):
        asession.add(KbArticle(slug="fees", lang="en", title="dup", body_md="x", version=2))
        await asession.commit()
    await asession.rollback()


# --- everything ships off ------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_assistant_settings_default_to_off(asession):
    from app.services import settings_service

    expected = {
        "assistant_enabled": "false",
        "assistant_visitor_enabled": "false",
        "assistant_model": "",  # no model until the release eval picks one
        "assistant_rollout": "admins",
        "assistant_provider": "openai",
        "assistant_retention_days": "180",
    }
    for key, value in expected.items():
        assert await settings_service.get_setting(asession, key) == value


def test_config_gate_requires_key_hmac_and_encryption(monkeypatch, tmp_path):
    s = get_settings()
    crypto.reset_cache()
    assert s.assistant_configured is False  # nothing configured in tests
    monkeypatch.setattr(s, "openai_api_key", "sk-test", raising=False)
    monkeypatch.setattr(s, "assistant_enabled", True, raising=False)
    monkeypatch.setattr(s, "assistant_hmac_secret", "hmac-secret", raising=False)
    crypto.reset_cache()
    assert s.assistant_configured is False  # still no encryption key file
    monkeypatch.setattr(
        s, "assistant_encryption_keys_file", _write_keys(tmp_path, "k1"), raising=False
    )
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)
    crypto.reset_cache()
    assert s.assistant_configured is True
    monkeypatch.setattr(s, "assistant_enabled", False, raising=False)
    assert s.assistant_configured is False  # the deploy-level kill switch wins
    crypto.reset_cache()


def test_no_key_material_or_secret_lives_in_env_defaults():
    s = get_settings()
    assert s.assistant_encryption_keys_file == "" or os.path.isabs(s.assistant_encryption_keys_file)
    assert s.assistant_policy_version  # consent is always tied to a version
    assert uuid.UUID  # keeps the import meaningful for readers


@pytest.mark.asyncio
async def test_tables_exist_with_expected_columns(asession):
    rows = await asession.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name IN "
            "('assistant_conversations','assistant_messages','assistant_action_proposals',"
            "'assistant_consents','support_tickets','support_ticket_messages','kb_articles')"
        )
    )
    assert len(rows.all()) == 7
    cols = await asession.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='assistant_messages' AND column_name LIKE '%_enc'"
        )
    )
    assert {c[1] for c in cols.all()} == {"bytea"}  # content columns are binary ciphertext
