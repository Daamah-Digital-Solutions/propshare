"""Phone numbers as the platform stores them when it changes one itself (the assistant's
"change my phone" action): international form, digits only after an optional leading +.

There is no SMS on the platform, so a number is never "verified"; this only refuses what
cannot be a phone number and stores one shape (E.164: up to 15 digits).
"""

from __future__ import annotations

import re

from app.core.errors import AppError

_ALLOWED = re.compile(r"^\+?[0-9 ().\-]{6,30}$")


def normalise_phone(value: str) -> str:
    """'+20 100 123-4567' -> '+201001234567'; '00971…' -> '+971…'. 7 to 15 digits."""
    raw = (value or "").strip()
    if not _ALLOWED.match(raw):
        raise AppError(
            "INVALID_PHONE",
            "That is not a phone number: use digits, with the country code, e.g. +971 50 123 4567.",
            status_code=422,
        )
    digits = re.sub(r"\D", "", raw)
    international = raw.startswith("+") or digits.startswith("00")
    if digits.startswith("00"):
        digits = digits[2:]
    if not 7 <= len(digits) <= 15:
        raise AppError(
            "INVALID_PHONE",
            "A phone number has 7 to 15 digits, including the country code.",
            status_code=422,
        )
    return f"+{digits}" if international else digits


def mask_phone(value: str | None) -> str:
    """'+201001234567' -> '+20•••••4567' for messages and audit rows."""
    if not value:
        return ""
    keep = 4
    head = value[:3] if value.startswith("+") else value[:2]
    return f"{head}{'•' * max(0, len(value) - len(head) - keep)}{value[-keep:]}"
