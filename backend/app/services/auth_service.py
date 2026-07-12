"""Authentication & identity service (Phase 1).

Owns: registration + provisioning, password & OAuth login, refresh-token
rotation, role switching (Scenario B), role-grant requests, and email
verify/reset. Routes call these; all DB writes happen here.

Cross-cutting rules honoured:
- Passwords never stored in plaintext (Argon2 via core.security).
- Refresh/email tokens stored only as SHA-256 hashes; raw values leave the
  server once (refresh in an httpOnly cookie; email token in a link).
- Active role must always be within the user's authorized role set.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import APPROVAL_ROLES, SELF_SERVE_ROLES, get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.models import KycVerification, Profile, UserRole, Wallet
from app.models.base import AppRole
from app.models.identity import EmailToken, OAuthIdentity, RefreshToken, RoleGrantRequest, User
from app.services import broker_service
from app.services.integrations import email as email_provider
from app.services.integrations import storage


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    res = await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    return res.scalar_one_or_none()


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_roles(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    res = await session.execute(select(UserRole.role).where(UserRole.user_id == user_id))
    return sorted(str(r) for r in res.scalars().all())


async def has_role(session: AsyncSession, user_id: uuid.UUID, role: str) -> bool:
    res = await session.execute(
        select(UserRole.id).where(UserRole.user_id == user_id, UserRole.role == AppRole(role))
    )
    return res.first() is not None


# --------------------------------------------------------------------------- #
# Registration & provisioning
# --------------------------------------------------------------------------- #
async def register(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None,
    phone: str | None,
    referral_code: str | None = None,
) -> User:
    if await get_user_by_email(session, email):
        raise AppError(
            "EMAIL_EXISTS", "An account with this email already exists.", status_code=409
        )

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        phone=phone,
        active_role=AppRole.investor,  # default role for a new account
    )
    session.add(user)
    await session.flush()  # assign user.id

    # Referral attribution (signup-only). A broker code creates the first-class,
    # commission-bearing broker_referrals link (Phase 11) AND sets referred_by to the
    # broker; anything else falls back to raw user→user attribution that earns no
    # commission. A client who signs up without a broker code can never be linked later.
    broker_id = await broker_service.resolve_signup_referral(
        session, new_user_id=user.id, referral_code=referral_code
    )
    user.referred_by = (
        broker_id if broker_id is not None else await _resolve_referral(session, referral_code)
    )

    await _provision_new_user(session, user)
    session.add(UserRole(user_id=user.id, role=AppRole.investor))

    await issue_email_token(session, user, kind="verify")
    return user


async def _provision_new_user(session: AsyncSession, user: User) -> None:
    """Create the profile/wallet/kyc rows (replaces the old handle_new_user trigger)."""
    session.add(Profile(id=user.id, email=user.email, full_name=user.full_name, phone=user.phone))
    session.add(Wallet(user_id=user.id))
    session.add(KycVerification(user_id=user.id, status="pending"))


async def _resolve_referral(session: AsyncSession, referral_code: str | None) -> uuid.UUID | None:
    """Phase 1 captures attribution only; broker validation + commissions are Phase 11."""
    if not referral_code:
        return None
    try:
        ref_id = uuid.UUID(referral_code)
    except ValueError:
        return None
    referrer = await session.get(User, ref_id)
    return referrer.id if referrer else None


# --------------------------------------------------------------------------- #
# Password login
# --------------------------------------------------------------------------- #
async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    user = await get_user_by_email(session, email)
    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Incorrect email or password.", status_code=401)
    return user


# --------------------------------------------------------------------------- #
# Tokens (access + refresh rotation)
# --------------------------------------------------------------------------- #
async def issue_tokens(
    session: AsyncSession,
    user: User,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[str, str, dt.datetime]:
    """Return (access_token, raw_refresh_token, refresh_expires_at)."""
    settings = get_settings()
    roles = await get_roles(session, user.id)
    active = str(user.active_role) if user.active_role is not None else None

    access = create_access_token(user_id=str(user.id), roles=roles, active_role=active)

    raw_refresh = new_opaque_token()
    expires_at = _utcnow() + dt.timedelta(seconds=settings.refresh_token_ttl_seconds)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
    )
    return access, raw_refresh, expires_at


async def rotate_refresh(
    session: AsyncSession,
    *,
    raw_refresh: str,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, str, str, dt.datetime]:
    """Validate a refresh token, revoke it, and issue a fresh pair (rotation).

    Returns (user, access_token, new_raw_refresh, refresh_expires_at).
    """
    row = await _load_active_refresh(session, raw_refresh)
    row.revoked_at = _utcnow()  # one-time use — rotate
    user = await session.get(User, row.user_id)
    if user is None:
        raise AppError("TOKEN_INVALID", "Invalid refresh token", status_code=401)
    access, new_refresh, exp = await issue_tokens(session, user, user_agent=user_agent, ip=ip)
    return user, access, new_refresh, exp


async def revoke_refresh(session: AsyncSession, *, raw_refresh: str) -> None:
    res = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    )
    row = res.scalar_one_or_none()
    if row and row.revoked_at is None:
        row.revoked_at = _utcnow()


async def revoke_all_refresh(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Revoke every active session for a user (used on role revoke / password reset)."""
    res = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    )
    for row in res.scalars().all():
        row.revoked_at = _utcnow()


async def _load_active_refresh(session: AsyncSession, raw_refresh: str) -> RefreshToken:
    res = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    )
    row = res.scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at <= _utcnow():
        raise AppError("TOKEN_INVALID", "Invalid or expired refresh token", status_code=401)
    return row


# --------------------------------------------------------------------------- #
# Roles (Scenario B): switch active role + request new role
# --------------------------------------------------------------------------- #
async def switch_active_role(session: AsyncSession, *, user: User, role: str) -> None:
    """Set the user's active role. Rejects any role not in the authorized set —
    server-enforced, regardless of what the client claims."""
    if not await has_role(session, user.id, role):
        raise AppError(
            "ROLE_NOT_AUTHORIZED",
            "You are not authorized for that role.",
            status_code=403,
        )
    user.active_role = AppRole(role)


async def request_role(session: AsyncSession, *, user: User, role: str) -> dict[str, str]:
    """Acquire a NEW role (D12):
    - self-serve (investor/owner) -> granted immediately.
    - approval (broker/liquidity_provider/admin) -> queued for an admin.
    `admin` is never self-serve and is granted only by an existing admin
    (admin requests are queued here but the seed admin is the first one).
    """
    if role not in SELF_SERVE_ROLES and role not in APPROVAL_ROLES:
        raise AppError("INVALID_ROLE", f"Unknown role {role!r}", status_code=422)

    if await has_role(session, user.id, role):
        return {"status": "granted", "role": role}

    if role in SELF_SERVE_ROLES:
        session.add(UserRole(user_id=user.id, role=AppRole(role)))
        if user.active_role is None:
            user.active_role = AppRole(role)
        return {"status": "granted", "role": role}

    # approval path — create a pending request (dedupe an existing pending one)
    existing = await session.execute(
        select(RoleGrantRequest).where(
            RoleGrantRequest.user_id == user.id,
            RoleGrantRequest.role == AppRole(role),
            RoleGrantRequest.status == "pending",
        )
    )
    if existing.scalar_one_or_none() is None:
        session.add(RoleGrantRequest(user_id=user.id, role=AppRole(role)))
    return {"status": "pending_approval", "role": role}


# Roles that go through a join-form application (fields + documents) before admin approval.
APPLICATION_ROLES = {"broker", "liquidity_provider"}


async def pending_role_names(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Roles the user has a still-pending approval request for (drives 'preview' access)."""
    res = await session.execute(
        select(RoleGrantRequest.role).where(
            RoleGrantRequest.user_id == user_id, RoleGrantRequest.status == "pending"
        )
    )
    return sorted(str(r) for r in res.scalars().all())


async def submit_role_application(
    session: AsyncSession,
    *,
    user: User,
    role: str,
    fields: dict,
    files: list[tuple[str, bytes, str | None]],
) -> RoleGrantRequest:
    """Submit (or resubmit) a Broker / Liquidity-Provider join application — the applicant's
    form fields + uploaded documents — attaching them to a pending approval request the admin
    reviews. Documents are saved to object storage; only their refs live on the request."""
    from app.services.document_service import _safe_filename, content_type_for  # lazy: no cycle

    if role not in APPLICATION_ROLES:
        raise AppError(
            "INVALID_ROLE", "This role does not require an application.", status_code=422
        )
    if await has_role(session, user.id, role):
        raise AppError("ALREADY_HAS_ROLE", "You already hold this role.", status_code=409)

    req = (
        await session.execute(
            select(RoleGrantRequest).where(
                RoleGrantRequest.user_id == user.id,
                RoleGrantRequest.role == AppRole(role),
                RoleGrantRequest.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if req is None:
        req = RoleGrantRequest(user_id=user.id, role=AppRole(role))
        session.add(req)
        await session.flush()  # need req.id to key the document storage paths

    documents: list[dict] = []
    for filename, data, content_type in files:
        safe = _safe_filename(filename)
        ct = content_type or content_type_for(safe)
        key = f"role-requests/{req.id}/{uuid.uuid4().hex}-{safe}"
        storage.save(key, data, ct)
        documents.append(
            {"label": filename, "key": key, "filename": safe, "content_type": ct}
        )

    req.application = {"fields": fields, "documents": documents, "submitted": True}
    return req


# --------------------------------------------------------------------------- #
# Email verification & password reset
# --------------------------------------------------------------------------- #
async def issue_email_token(session: AsyncSession, user: User, *, kind: str) -> str:
    settings = get_settings()
    ttl = (
        settings.email_verify_ttl_seconds
        if kind == "verify"
        else settings.password_reset_ttl_seconds
    )
    raw = new_opaque_token()
    session.add(
        EmailToken(
            user_id=user.id,
            kind=kind,
            token_hash=hash_token(raw),
            expires_at=_utcnow() + dt.timedelta(seconds=ttl),
        )
    )
    path = "/verify-email" if kind == "verify" else "/reset-password"
    link = email_provider.build_link(path, raw)
    if kind == "verify":
        subject = "Verify your CapiMax PropShare email"
        intro = (
            "Welcome to CapiMax PropShare! Please confirm your email address to activate your "
            "account and start exploring fractional property ownership."
        )
        cta_label = "Verify email address"
        expiry = "24 hours"
        footnote = (
            "If you didn't create a CapiMax PropShare account, "
            "you can safely ignore this email."
        )
    else:
        subject = "Reset your CapiMax PropShare password"
        intro = "We received a request to reset the password for your CapiMax PropShare account."
        cta_label = "Reset password"
        expiry = "1 hour"
        footnote = (
            "If you didn't request a password reset, you can safely ignore this email — "
            "your password won't change."
        )
    text = f"{intro}\n\n{cta_label}: {link}\n\nThis secure link expires in {expiry}.\n\n{footnote}"
    html = email_provider.render_email_html(
        title=subject,
        paragraphs=[intro, f"This secure link expires in {expiry}."],
        cta_label=cta_label,
        cta_url=link,
        footnote=footnote,
        preheader=intro,
    )
    await email_provider.send_email(to=user.email, subject=subject, text=text, html=html)
    return raw


async def _consume_email_token(session: AsyncSession, *, raw: str, kind: str) -> User:
    res = await session.execute(
        select(EmailToken).where(EmailToken.token_hash == hash_token(raw), EmailToken.kind == kind)
    )
    row = res.scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= _utcnow():
        raise AppError("TOKEN_INVALID", "Invalid or expired token", status_code=400)
    row.used_at = _utcnow()
    user = await session.get(User, row.user_id)
    if user is None:
        raise AppError("TOKEN_INVALID", "Invalid token", status_code=400)
    return user


async def verify_email(session: AsyncSession, *, raw: str) -> None:
    user = await _consume_email_token(session, raw=raw, kind="verify")
    user.email_verified = True


async def start_password_reset(session: AsyncSession, *, email: str) -> None:
    """Always succeeds from the caller's view (no account enumeration)."""
    user = await get_user_by_email(session, email)
    if user is not None:
        await issue_email_token(session, user, kind="reset")


async def reset_password(session: AsyncSession, *, raw: str, new_password: str) -> None:
    user = await _consume_email_token(session, raw=raw, kind="reset")
    user.password_hash = hash_password(new_password)
    await revoke_all_refresh(session, user_id=user.id)  # force re-login everywhere


async def change_password(
    session: AsyncSession, *, user: User, current_password: str, new_password: str
) -> None:
    """Authenticated password change — requires the current password."""
    if not user.password_hash or not verify_password(current_password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Current password is incorrect.", status_code=400)
    user.password_hash = hash_password(new_password)


# --------------------------------------------------------------------------- #
# OAuth (Google / Apple)
# --------------------------------------------------------------------------- #
async def oauth_upsert(
    session: AsyncSession,
    *,
    provider: str,
    subject: str,
    email: str,
    full_name: str | None,
) -> User:
    """Find or create the user for a verified OAuth identity."""
    res = await session.execute(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider, OAuthIdentity.provider_subject == subject
        )
    )
    identity = res.scalar_one_or_none()
    if identity is not None:
        user = await session.get(User, identity.user_id)
        assert user is not None
        return user

    user = await get_user_by_email(session, email)
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            email_verified=True,  # provider already verified the email
            active_role=AppRole.investor,
        )
        session.add(user)
        await session.flush()
        await _provision_new_user(session, user)
        session.add(UserRole(user_id=user.id, role=AppRole.investor))

    session.add(OAuthIdentity(user_id=user.id, provider=provider, provider_subject=subject))
    return user


# --------------------------------------------------------------------------- #
# Admin role management (admin-only; routes enforce the admin gate)
# --------------------------------------------------------------------------- #
async def admin_grant_role(session: AsyncSession, *, target_user_id: uuid.UUID, role: str) -> None:
    if role not in SELF_SERVE_ROLES and role not in APPROVAL_ROLES:
        raise AppError("INVALID_ROLE", f"Unknown role {role!r}", status_code=422)
    user = await session.get(User, target_user_id)
    if user is None:
        raise AppError("NOT_FOUND", "User not found", status_code=404)
    if not await has_role(session, target_user_id, role):
        session.add(UserRole(user_id=target_user_id, role=AppRole(role)))
        if user.active_role is None:
            user.active_role = AppRole(role)


async def admin_revoke_role(session: AsyncSession, *, target_user_id: uuid.UUID, role: str) -> None:
    res = await session.execute(
        select(UserRole).where(UserRole.user_id == target_user_id, UserRole.role == AppRole(role))
    )
    row = res.scalar_one_or_none()
    if row is None:
        return
    await session.delete(row)
    user = await session.get(User, target_user_id)
    if user is not None and user.active_role is not None and str(user.active_role) == role:
        remaining = [r for r in await get_roles(session, target_user_id) if r != role]
        user.active_role = AppRole(remaining[0]) if remaining else None
    # Force re-auth so the revoked role cannot continue within a live token TTL
    # (works with the action-time DB re-check in api/deps.require_active_role_db).
    await revoke_all_refresh(session, user_id=target_user_id)


async def decide_role_request(
    session: AsyncSession, *, request_id: uuid.UUID, approve: bool, actor_id: uuid.UUID
) -> RoleGrantRequest:
    req = await session.get(RoleGrantRequest, request_id)
    if req is None:
        raise AppError("NOT_FOUND", "Role request not found", status_code=404)
    if req.status != "pending":
        raise AppError("ALREADY_DECIDED", "Request already decided", status_code=409)
    req.status = "approved" if approve else "rejected"
    req.decided_by = actor_id
    req.decided_at = _utcnow()
    if approve:
        await admin_grant_role(session, target_user_id=req.user_id, role=str(req.role))
    return req
