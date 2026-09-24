"""Application-level encryption for AI-assistant conversations (plan §3).

Why app-level AES-256-GCM and not pgcrypto: pgcrypto puts the key into the SQL statement
(so it can leak into ``pg_stat_statements`` and query logs) and leaves database dumps
readable to anyone holding the key plus the dump. Encrypting in the application keeps every
dump and nightly backup as ciphertext, supports key rotation, and works the same in tests.

Keys live OUTSIDE the app tree and outside the backup tree, one per line:

    k1:<base64 of 32 random bytes>
    k2:<base64 of 32 random bytes>

``ASSISTANT_ENCRYPTION_KEYS_FILE`` points at that file and ``ASSISTANT_ENCRYPTION_ACTIVE_KEY``
names the key new rows are written with; every other key stays loaded so old rows still
decrypt. A blob is self-describing (``k1:`` + nonce + ciphertext), so rotation never needs a
migration: write with the new key, keep reading the old ones, re-encrypt in the background.

There is NO plaintext fallback: if the key is missing the assistant is disabled rather than
storing conversations in the clear.
"""

from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings

NONCE_BYTES = 12  # 96-bit nonce, the size AES-GCM is defined for
KEY_BYTES = 32  # AES-256
_SEP = b":"


class CryptoNotConfigured(RuntimeError):
    """No usable key: callers must disable the feature, never fall back to plaintext."""


class DecryptionFailed(RuntimeError):
    """Wrong key, unknown key id, or tampered ciphertext."""


def _parse_keys(text: str) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise CryptoNotConfigured("Key file lines must look like 'k1:<base64 32 bytes>'.")
        key_id, b64 = line.split(":", 1)
        key_id = key_id.strip()
        if not key_id or _SEP.decode() in key_id:
            raise CryptoNotConfigured(f"Invalid key id {key_id!r}.")
        try:
            material = base64.b64decode(b64.strip(), validate=True)
        except Exception as exc:  # noqa: BLE001 — any base64 problem is a config problem
            raise CryptoNotConfigured(f"Key {key_id!r} is not valid base64.") from exc
        if len(material) != KEY_BYTES:
            raise CryptoNotConfigured(f"Key {key_id!r} must be {KEY_BYTES} bytes (AES-256).")
        keys[key_id] = material
    if not keys:
        raise CryptoNotConfigured("Key file contains no keys.")
    return keys


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, bytes], str]:
    settings = get_settings()
    path = settings.assistant_encryption_keys_file
    active = settings.assistant_encryption_active_key
    if not path or not active:
        raise CryptoNotConfigured(
            "ASSISTANT_ENCRYPTION_KEYS_FILE and ASSISTANT_ENCRYPTION_ACTIVE_KEY must be set."
        )
    if not os.path.isfile(path):
        raise CryptoNotConfigured(f"Key file not found: {path}")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        # e.g. wrong owner/mode on the server: the features switch off, the app still boots
        raise CryptoNotConfigured(f"Key file not readable: {path} ({exc})") from exc
    keys = _parse_keys(text)
    if active not in keys:
        raise CryptoNotConfigured(f"Active key {active!r} is not in the key file.")
    return keys, active


def reset_cache() -> None:
    """Forget the loaded keys (used after rotation and by tests)."""
    _load.cache_clear()


def is_configured() -> bool:
    try:
        _load()
    except CryptoNotConfigured:
        return False
    return True


def active_key_id() -> str:
    return _load()[1]


def encrypt(data: bytes) -> bytes:
    """Encrypt with the active key. Returns ``key_id:nonce+ciphertext``."""
    keys, active = _load()
    nonce = os.urandom(NONCE_BYTES)
    blob = AESGCM(keys[active]).encrypt(nonce, data, active.encode())
    return active.encode() + _SEP + nonce + blob


def decrypt(blob: bytes) -> bytes:
    """Decrypt a blob written by :func:`encrypt`, with whichever key wrote it."""
    keys, _active = _load()
    key_id_raw, _, rest = bytes(blob).partition(_SEP)
    key_id = key_id_raw.decode("utf-8", "replace")
    if key_id not in keys:
        raise DecryptionFailed(f"Unknown key id {key_id!r}: the key file cannot read this row.")
    nonce, ciphertext = rest[:NONCE_BYTES], rest[NONCE_BYTES:]
    try:
        return AESGCM(keys[key_id]).decrypt(nonce, ciphertext, key_id.encode())
    except InvalidTag as exc:
        raise DecryptionFailed("Ciphertext failed authentication (wrong key or tampered).") from exc


def key_id_of(blob: bytes) -> str:
    return bytes(blob).partition(_SEP)[0].decode("utf-8", "replace")


class EncryptedText(TypeDecorator):
    """``str`` in Python, AES-GCM ciphertext (BYTEA) in the database."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> bytes | None:  # noqa: ANN001
        if value is None:
            return None
        return encrypt(value.encode("utf-8"))

    def process_result_value(self, value: bytes | None, dialect) -> str | None:  # noqa: ANN001
        if value is None:
            return None
        return decrypt(value).decode("utf-8")


class EncryptedJSON(TypeDecorator):
    """Any JSON-serialisable value in Python, AES-GCM ciphertext (BYTEA) in the database."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> bytes | None:  # noqa: ANN001
        if value is None:
            return None
        return encrypt(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))

    def process_result_value(self, value: bytes | None, dialect) -> Any:  # noqa: ANN001
        if value is None:
            return None
        return json.loads(decrypt(value).decode("utf-8"))
