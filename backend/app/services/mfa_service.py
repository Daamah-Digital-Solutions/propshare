"""Two-factor authentication: authenticator-app codes (TOTP) + one-time recovery codes.

Enrolment
  1. ``begin_setup`` creates a secret, stores it ENCRYPTED as *pending*, and returns the QR
     code + the secret for manual entry. Nothing is enforced yet.
  2. ``confirm_setup`` requires a first valid code (proves the app scanned it), promotes the
     secret, and returns ten recovery codes — shown exactly once, stored only as hashes.

Sign-in
  Password (or Google) succeeds → the route returns a 5-minute signed *challenge* instead of
  tokens → ``verify_second_factor`` with a 6-digit code or a recovery code → tokens.

Guarantees
  * The TOTP secret never touches the DB or backups in plaintext (app/core/crypto.py).
  * A code is accepted once: the accepted 30-second step is remembered (replay protection).
  * Five wrong codes lock the second step for 15 minutes; the lock and every change
    (enabled, disabled, recovery code used, admin reset) is audited and emailed.
  * Recovery codes are SHA-256 of 80 random bits, independent of the encryption key — if the
    key file is ever lost they are the way back in (plan/ASSISTANT_KEY_RECOVERY.md).

Failure counters are committed before the error is raised: the request session rolls back
on an exception, and a rolled-back counter would make the lockout useless.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid

import segno
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto, totp
from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import verify_password
from app.models import UserMfa, UserRecoveryCode
from app.models.identity import User
from app.services import notification_service

ISSUER = "Capimax PropShare"
RECOVERY_CODE_COUNT = 10
MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = dt.timedelta(minutes=15)
SETUP_TTL = dt.timedelta(minutes=30)
CHALLENGE_TTL_SECONDS = 300
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 symbols, no O/0/I/1 look-alikes


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --------------------------------------------------------------------------- #
# State helpers
# --------------------------------------------------------------------------- #
def available() -> bool:
    """2FA needs the platform encryption key to store secrets; without it we refuse to
    enrol anyone rather than store a secret in plaintext."""
    return crypto.is_configured()


def _require_available() -> None:
    if not available():
        raise AppError(
            "MFA_UNAVAILABLE",
            "Two-factor authentication is not available right now. Please try again later.",
            status_code=503,
        )


async def _state(
    session: AsyncSession, user_id: uuid.UUID, *, lock: bool = False
) -> UserMfa | None:
    stmt = select(UserMfa).where(UserMfa.user_id == user_id)
    if lock:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


def _enabled(state: UserMfa | None) -> bool:
    return bool(state and state.secret_enc and state.enabled_at)


async def is_enabled(session: AsyncSession, user_id: uuid.UUID) -> bool:
    return _enabled(await _state(session, user_id))


async def _remaining_codes(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(UserRecoveryCode)
            .where(UserRecoveryCode.user_id == user_id, UserRecoveryCode.used_at.is_(None))
        )
        or 0
    )


async def status(session: AsyncSession, user_id: uuid.UUID) -> dict:
    state = await _state(session, user_id)
    enabled = _enabled(state)
    has_password = bool(await session.scalar(select(User.password_hash).where(User.id == user_id)))
    return {
        # accounts created with Google have no password: turning 2FA off needs the code only
        "has_password": has_password,
        "enabled": enabled,
        "enabled_at": state.enabled_at if enabled and state else None,
        "recovery_codes_remaining": await _remaining_codes(session, user_id) if enabled else 0,
        "available": available(),
    }


def _decrypt(blob: bytes) -> str:
    try:
        return crypto.decrypt(blob).decode("ascii")
    except (crypto.CryptoNotConfigured, crypto.DecryptionFailed) as exc:
        raise AppError(
            "MFA_UNAVAILABLE",
            "Authenticator codes cannot be checked right now. Use one of your recovery codes.",
            status_code=503,
        ) from exc


# --------------------------------------------------------------------------- #
# Recovery codes
# --------------------------------------------------------------------------- #
def _normalize_recovery(code: str) -> str:
    return "".join(ch for ch in str(code).upper() if ch.isalnum())


def _hash_recovery(code: str) -> str:
    return hashlib.sha256(_normalize_recovery(code).encode("ascii")).hexdigest()


def _new_code() -> str:
    raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(16))  # 16 × 5 bits = 80
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


async def _replace_recovery_codes(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    await session.execute(delete(UserRecoveryCode).where(UserRecoveryCode.user_id == user_id))
    codes = [_new_code() for _ in range(RECOVERY_CODE_COUNT)]
    for c in codes:
        session.add(UserRecoveryCode(user_id=user_id, code_hash=_hash_recovery(c)))
    await session.flush()
    return codes


# --------------------------------------------------------------------------- #
# Enrolment
# --------------------------------------------------------------------------- #
async def begin_setup(session: AsyncSession, user: User) -> dict:
    _require_available()
    state = await _state(session, user.id, lock=True)
    if _enabled(state):
        raise AppError(
            "MFA_ALREADY_ENABLED",
            "Two-factor authentication is already on. Turn it off first to set up a new app.",
            status_code=409,
        )
    secret = totp.new_secret()
    if state is None:
        state = UserMfa(user_id=user.id)
        session.add(state)
    state.pending_secret_enc = crypto.encrypt(secret.encode("ascii"))
    state.pending_created_at = _utcnow()
    state.updated_at = _utcnow()
    await session.flush()
    uri = totp.provisioning_uri(secret, account=user.email, issuer=ISSUER)
    await write_audit(
        session,
        action="mfa.setup_started",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.id,
    )
    return {
        "secret": secret,  # for "can't scan? type this key" — shown to the user only
        "otpauth_uri": uri,
        "qr_svg_data_uri": segno.make(uri, error="m").svg_data_uri(scale=5, border=2),
        "expires_in": int(SETUP_TTL.total_seconds()),
    }


async def confirm_setup(session: AsyncSession, user: User, code: str) -> list[str]:
    _require_available()
    state = await _state(session, user.id, lock=True)
    if _enabled(state):
        raise AppError(
            "MFA_ALREADY_ENABLED", "Two-factor authentication is already on.", status_code=409
        )
    if (
        state is None
        or state.pending_secret_enc is None
        or state.pending_created_at is None
        or _utcnow() - state.pending_created_at > SETUP_TTL
    ):
        raise AppError(
            "MFA_SETUP_EXPIRED",
            "This setup has expired. Start again to get a new QR code.",
            status_code=409,
        )
    secret = _decrypt(state.pending_secret_enc)
    step = totp.matching_step(secret, code)
    if step is None:
        raise AppError(
            "MFA_INVALID_CODE",
            "That code did not match. Check the time on your phone and enter the newest code.",
            status_code=422,
        )
    now = _utcnow()
    state.secret_enc = state.pending_secret_enc
    state.pending_secret_enc = None
    state.pending_created_at = None
    state.enabled_at = now
    state.last_used_step = step
    state.failed_attempts = 0
    state.locked_until = None
    state.updated_at = now
    codes = await _replace_recovery_codes(session, user.id)
    await write_audit(
        session, action="mfa.enabled", entity_type="user", entity_id=str(user.id), actor_id=user.id
    )
    await notification_service.notify(
        session,
        user_id=user.id,
        type="security",
        title="Two-factor authentication turned on",
        message=(
            "Your account now asks for a code from your authenticator app at sign-in. If this "
            "was not you, contact support immediately."
        ),
        email_category="security",
        force_email=True,
    )
    return codes


# --------------------------------------------------------------------------- #
# Checking a second factor (sign-in, disable, regenerate)
# --------------------------------------------------------------------------- #
async def _register_failure(session: AsyncSession, user: User, state: UserMfa) -> AppError:
    state.failed_attempts = int(state.failed_attempts or 0) + 1
    state.updated_at = _utcnow()
    left = MAX_FAILED_ATTEMPTS - state.failed_attempts
    if left <= 0:
        state.locked_until = _utcnow() + LOCK_DURATION
        state.failed_attempts = 0
        await write_audit(
            session,
            action="mfa.locked",
            entity_type="user",
            entity_id=str(user.id),
            actor_id=user.id,
        )
        await notification_service.notify(
            session,
            user_id=user.id,
            type="security",
            title="Too many wrong sign-in codes",
            message=(
                "Someone entered your password correctly but failed the two-factor code "
                f"{MAX_FAILED_ATTEMPTS} times. Sign-in is paused for 15 minutes. If this was "
                "not you, change your password now."
            ),
            email_category="security",
            force_email=True,
        )
        err = AppError(
            "MFA_LOCKED",
            "Too many wrong codes. Try again in 15 minutes.",
            status_code=429,
            details={"retry_after": int(LOCK_DURATION.total_seconds())},
        )
    else:
        err = AppError(
            "MFA_INVALID_CODE",
            "That code is not valid.",
            status_code=401,
            details={"attempts_left": left},
        )
    # Persist the counter NOW: raising rolls the request session back.
    await session.commit()
    return err


async def verify_second_factor(session: AsyncSession, user: User, code: str) -> str:
    """Accept a current authenticator code or an unused recovery code. Returns which one."""
    state = await _state(session, user.id, lock=True)
    if not _enabled(state):
        raise AppError("MFA_NOT_ENABLED", "Two-factor authentication is off.", status_code=409)
    assert state is not None
    now = _utcnow()
    if state.locked_until and state.locked_until > now:
        raise AppError(
            "MFA_LOCKED",
            "Too many wrong codes. Try again later.",
            status_code=429,
            details={"retry_after": int((state.locked_until - now).total_seconds())},
        )

    digits = "".join(ch for ch in str(code) if ch.isdigit())
    is_totp = len(digits) == totp.DIGITS and len(_normalize_recovery(code)) == totp.DIGITS

    if is_totp:
        step = totp.matching_step(_decrypt(state.secret_enc), digits)
        if step is None or (state.last_used_step is not None and step <= state.last_used_step):
            raise await _register_failure(session, user, state)
        state.last_used_step = step
        state.failed_attempts = 0
        state.updated_at = now
        return "totp"

    row = (
        await session.execute(
            select(UserRecoveryCode)
            .where(
                UserRecoveryCode.user_id == user.id,
                UserRecoveryCode.code_hash == _hash_recovery(code),
                UserRecoveryCode.used_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise await _register_failure(session, user, state)
    row.used_at = now
    state.failed_attempts = 0
    state.updated_at = now
    remaining = await _remaining_codes(session, user.id)
    await write_audit(
        session,
        action="mfa.recovery_code_used",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.id,
        after={"remaining": remaining},
    )
    await notification_service.notify(
        session,
        user_id=user.id,
        type="security",
        title="A recovery code was used",
        message=(
            f"A recovery code was used to sign in. You have {remaining} left. If you lost your "
            "phone, turn two-factor off and on again in Account Settings to connect a new one."
        ),
        email_category="security",
        force_email=True,
    )
    return "recovery"


# --------------------------------------------------------------------------- #
# Managing an enabled factor
# --------------------------------------------------------------------------- #
async def disable(session: AsyncSession, user: User, *, password: str | None, code: str) -> None:
    # Accounts created with Google have no password; the second factor alone proves it's them.
    if user.password_hash and not verify_password(password or "", user.password_hash):
        raise AppError(
            "INVALID_CREDENTIALS", "Your current password is incorrect.", status_code=401
        )
    await verify_second_factor(session, user, code)
    await session.execute(delete(UserRecoveryCode).where(UserRecoveryCode.user_id == user.id))
    await session.execute(delete(UserMfa).where(UserMfa.user_id == user.id))
    await write_audit(
        session, action="mfa.disabled", entity_type="user", entity_id=str(user.id), actor_id=user.id
    )
    await notification_service.notify(
        session,
        user_id=user.id,
        type="security",
        title="Two-factor authentication turned off",
        message=(
            "Your account no longer asks for an authenticator code at sign-in. If this was not "
            "you, change your password and contact support immediately."
        ),
        email_category="security",
        force_email=True,
    )


async def regenerate_recovery_codes(session: AsyncSession, user: User, code: str) -> list[str]:
    await verify_second_factor(session, user, code)
    codes = await _replace_recovery_codes(session, user.id)
    await write_audit(
        session,
        action="mfa.recovery_codes_regenerated",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.id,
    )
    return codes


async def admin_reset(
    session: AsyncSession, *, user_id: uuid.UUID, actor_id: uuid.UUID | None
) -> bool:
    """Support path for a user who lost both the phone and the recovery codes. Identity must
    be re-verified by staff before this is used; it is audited and the user is emailed."""
    had = await is_enabled(session, user_id)
    await session.execute(delete(UserRecoveryCode).where(UserRecoveryCode.user_id == user_id))
    await session.execute(delete(UserMfa).where(UserMfa.user_id == user_id))
    await write_audit(
        session,
        action="mfa.admin_reset",
        entity_type="user",
        entity_id=str(user_id),
        actor_id=actor_id,
        after={"was_enabled": had},
    )
    if had:
        await notification_service.notify(
            session,
            user_id=user_id,
            type="security",
            title="Two-factor authentication was reset by support",
            message=(
                "At your request, our team turned off two-factor authentication on your account. "
                "Turn it back on in Account Settings. If you did not ask for this, contact "
                "support immediately."
            ),
            email_category="security",
            force_email=True,
        )
    return had


# --------------------------------------------------------------------------- #
# The sign-in challenge (between the password/Google step and the code step)
# --------------------------------------------------------------------------- #
def _challenge_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().jwt_secret, salt="mfa-login-challenge")


def issue_challenge(user_id: uuid.UUID, *, via: str) -> str:
    return _challenge_serializer().dumps({"uid": str(user_id), "via": via})


def read_challenge(token: str) -> tuple[uuid.UUID, str]:
    try:
        data = _challenge_serializer().loads(token, max_age=CHALLENGE_TTL_SECONDS)
        return uuid.UUID(str(data["uid"])), str(data.get("via") or "password")
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError) as exc:
        raise AppError(
            "MFA_CHALLENGE_EXPIRED",
            "Your sign-in took too long. Please sign in again.",
            status_code=401,
        ) from exc
