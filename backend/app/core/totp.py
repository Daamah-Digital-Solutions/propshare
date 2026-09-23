"""Time-based one-time passwords (RFC 6238 over RFC 4226), standard library only.

Compatible with every authenticator app (Google Authenticator, Microsoft Authenticator, Authy,
1Password, …): SHA-1, 6 digits, 30-second steps — the defaults those apps assume when they
scan an ``otpauth://`` QR code. Verified against the RFC 6238 Appendix B test vectors.

What this module does NOT do (the caller's job, see ``mfa_service``): storing the secret
encrypted, remembering the last accepted step so a code cannot be replayed, and locking the
account after repeated wrong codes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

DIGITS = 6
PERIOD = 30
# Accept the previous and next step too: phones drift, and a code typed at :29 arrives at :31.
DRIFT_STEPS = 1
SECRET_BYTES = 20  # 160 bits, the RFC 4226 recommendation for HMAC-SHA1


def clock() -> float:
    """Wall-clock seconds. A module function so tests can move time without touching the
    global ``time`` module (which asyncio and the DB driver also use)."""
    return time.time()


def new_secret() -> str:
    """A fresh base32 secret (no padding), as authenticator apps expect it."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def _key(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def step_at(ts: float) -> int:
    return int(ts // PERIOD)


def hotp(key: bytes, counter: int, digits: int = DIGITS, digest=hashlib.sha1) -> str:
    """RFC 4226 §5.3 dynamic truncation."""
    mac = hmac.new(key, struct.pack(">Q", counter), digest).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**digits)).zfill(digits)


def code_at(secret_b32: str, ts: float) -> str:
    return hotp(_key(secret_b32), step_at(ts))


def matching_step(secret_b32: str, code: str, *, now: float | None = None) -> int | None:
    """The time step ``code`` belongs to (within the drift window), or None.

    Returns the step rather than a bool so the caller can refuse a step it already accepted
    (replay). Comparison is constant-time."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != DIGITS:
        return None
    key = _key(secret_b32)
    current = step_at(clock() if now is None else now)
    for step in range(current - DRIFT_STEPS, current + DRIFT_STEPS + 1):
        if hmac.compare_digest(hotp(key, step), code):
            return step
    return None


def provisioning_uri(secret_b32: str, *, account: str, issuer: str) -> str:
    """The ``otpauth://`` URI an authenticator app reads from the QR code."""
    label = quote(f"{issuer}:{account}", safe="@:")
    params = urlencode(
        {
            "secret": secret_b32,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": PERIOD,
        }
    )
    return f"otpauth://totp/{label}?{params}"
