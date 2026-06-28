"""Rate limiting (Phase 13) — slowapi, IP-keyed.

A single shared ``Limiter`` protects abuse-prone unauthenticated endpoints (auth +
public webhooks) from brute-force / DoS. In-memory storage by default (per-process —
fine on a single VPS worker); point it at Redis for a multi-worker deployment. Over-limit
raises ``RateLimitExceeded`` → a 429 in the standard error envelope (see main.py).

``enabled`` is toggled off in tests so the register/login-heavy suites aren't throttled;
the dedicated rate-limit test flips it on for its own assertions.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])

# Per-endpoint limits (kept here so they're easy to tune / move to env later).
LOGIN_LIMIT = "10/minute"
REGISTER_LIMIT = "10/minute"
FORGOT_LIMIT = "5/minute"
WEBHOOK_LIMIT = "120/minute"
