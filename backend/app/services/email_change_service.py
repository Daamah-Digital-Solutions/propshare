"""Changing the account's sign-in email address.

Client (meeting 2026-10-01): "I asked the assistant to change my email and it sent me to a
page; it knows it is me, it should change it." There was no way to change an email at all.

Two one-time links, in order, and only then does the address change:

  1. APPROVE, sent to the CURRENT address. A signed-in session alone is not enough to move an
     account: a session left open on someone else's device must not be able to take it over
     (after which "forgot password" would hand them the account).
  2. CONFIRM, sent to the NEW address once approved. This proves the user owns it and catches
     typos.

Neither link acts when it is opened: the page shows what the link is about (the new address
in full) and acts only when the person presses a button. Mail scanners open links on their
own, and must never approve or confirm anything. Both pages also offer "This wasn't me", which
stops the change; from the current address it also signs every device out.

Completing the change does four things:
  * it updates ``users.email`` and the ``profiles`` copy, and marks the address verified;
  * it ends every unused verification and password-reset link, because those were tied to the
    account, not to an address, and would otherwise outlive the change;
  * it tells the old address;
  * it is audited.

The same flow serves the Settings page and the assistant (a confirmed action).
Google and Apple sign-in keep working, because they match by the provider's own account id.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.core.security import hash_token, new_opaque_token
from app.models import Profile
from app.models.identity import EmailChangeRequest, EmailToken, User
from app.services import auth_service, notification_service
from app.services.integrations import email as email_provider

LINK_TTL = dt.timedelta(hours=24)
MAX_PER_DAY = 3
PENDING = ("awaiting_approval", "awaiting_confirmation")
CONFIRM_PATH = "/confirm-email-change"

_EMAIL = TypeAdapter(EmailStr)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def mask_email(email: str) -> str:
    """'sara.investor@gmail.com' -> 's***r@gmail.com': enough to recognise, not to read."""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def normalise(value: str) -> str:
    """Validate like sign-up does (the same EmailStr rules) and return the stored form."""
    try:
        return str(_EMAIL.validate_python(value.strip()))
    except ValidationError as exc:
        raise AppError(
            "INVALID_EMAIL", "That is not a valid email address.", status_code=422
        ) from exc


async def _send(to: str, *, subject: str, intro: str, cta: str, raw: str, footnote: str) -> None:
    link = email_provider.build_link(CONFIRM_PATH, raw)
    expiry = "This secure link expires in 24 hours."
    text = f"{intro}\n\n{cta}: {link}\n\n{expiry}\n\n{footnote}"
    html = email_provider.render_email_html(
        title=subject,
        paragraphs=[intro, expiry],
        cta_label=cta,
        cta_url=link,
        footnote=footnote,
        preheader=intro,
    )
    await email_provider.send_email(to=to, subject=subject, text=text, html=html)


async def pending_request(
    session: AsyncSession, *, user_id: uuid.UUID
) -> EmailChangeRequest | None:
    """The user's change still in progress (not expired), if any."""
    return (
        await session.execute(
            select(EmailChangeRequest)
            .where(
                EmailChangeRequest.user_id == user_id,
                EmailChangeRequest.status.in_(PENDING),
                EmailChangeRequest.expires_at > _utcnow(),
            )
            .order_by(EmailChangeRequest.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def request_change(
    session: AsyncSession, *, user_id: uuid.UUID, new_email: str, source: str = "settings"
) -> EmailChangeRequest:
    """Start a change: checks the new address, replaces any change in progress and sends the
    approval link to the current address. Nothing about the account changes yet."""
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("NOT_FOUND", "User not found", status_code=404)
    new = normalise(new_email)
    if new.lower() == user.email.lower():
        raise AppError(
            "SAME_EMAIL", "That is already the email address of your account.", status_code=409
        )
    if await auth_service.get_user_by_email(session, new) is not None:
        raise AppError(
            "EMAIL_EXISTS",
            "That email address is already used by another account.",
            status_code=409,
        )
    since = _utcnow() - dt.timedelta(days=1)
    recent = await session.scalar(
        select(func.count())
        .select_from(EmailChangeRequest)
        .where(EmailChangeRequest.user_id == user.id, EmailChangeRequest.created_at >= since)
    )
    if int(recent or 0) >= MAX_PER_DAY:
        raise AppError(
            "TOO_MANY_REQUESTS",
            "You asked to change your email several times today. Please try again tomorrow.",
            status_code=429,
        )
    # one change at a time: a new request replaces the one in progress
    await session.execute(
        update(EmailChangeRequest)
        .where(EmailChangeRequest.user_id == user.id, EmailChangeRequest.status.in_(PENDING))
        .values(status="cancelled", approve_token_hash=None, confirm_token_hash=None)
    )
    raw = new_opaque_token()
    req = EmailChangeRequest(
        user_id=user.id,
        old_email=user.email,
        new_email=new,
        status="awaiting_approval",
        approve_token_hash=hash_token(raw),
        source=source if source in ("settings", "assistant") else "settings",
        expires_at=_utcnow() + LINK_TTL,
    )
    session.add(req)
    await session.flush()
    await _send(
        user.email,
        subject="Approve the change of your Capimax PropShare email",
        # the new address in full: this goes to the account's owner, who must be able to tell
        # it from a look-alike before approving
        intro=(
            "We received a request to change the sign-in email of your Capimax PropShare "
            f"account to {new}. If that was you, open the link and approve it; we will then "
            "send a confirmation link to the new address."
        ),
        cta="Review the change",
        raw=raw,
        footnote=(
            "If you did not ask for this, nothing changes unless you approve it. To stop it "
            'and sign out every device, open the link and choose "This wasn\'t me", then '
            "change your password."
        ),
    )
    await write_audit(
        session,
        action="auth.email_change_requested",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.id,
        after={"new_email": mask_email(new), "source": req.source},
    )
    return req


async def cancel_request(session: AsyncSession, *, user_id: uuid.UUID) -> bool:
    """Stop the change in progress (its links stop working). False when there was none."""
    result = await session.execute(
        update(EmailChangeRequest)
        .where(EmailChangeRequest.user_id == user_id, EmailChangeRequest.status.in_(PENDING))
        .values(status="cancelled", approve_token_hash=None, confirm_token_hash=None)
    )
    return bool(result.rowcount)


async def _close(session: AsyncSession, req: EmailChangeRequest, status: str) -> None:
    """End a request for good (its links stop working). Committed at once: the error that
    follows rolls the request session back."""
    req.status, req.approve_token_hash, req.confirm_token_hash = status, None, None
    await session.commit()


async def _by_link(
    session: AsyncSession, raw: str, *, lock: bool
) -> tuple[EmailChangeRequest, str, User]:
    """(request, step, user) for a link from the emails; ``step`` is "approve" (the link sent
    to the current address) or "confirm" (the one sent to the new address). TOKEN_INVALID for
    anything else. With ``lock`` (the link is being used), a request found dead is closed."""
    digest = hash_token(raw)
    query = select(EmailChangeRequest).where(
        (EmailChangeRequest.approve_token_hash == digest)
        | (EmailChangeRequest.confirm_token_hash == digest)
    )
    req = (await session.execute(query.with_for_update() if lock else query)).scalar_one_or_none()
    invalid = AppError("TOKEN_INVALID", "This link is invalid or has expired.", status_code=400)
    if req is None:
        raise invalid
    if req.status == "awaiting_approval" and digest == req.approve_token_hash:
        step = "approve"
    elif req.status == "awaiting_confirmation" and digest == req.confirm_token_hash:
        step = "confirm"
    else:
        raise invalid
    user = await session.get(User, req.user_id)
    dead = None
    if req.expires_at <= _utcnow():
        dead = "expired"
    elif user is None or user.email.lower() != req.old_email.lower():
        dead = "cancelled"  # the address changed another way since the request: this one is moot
    if dead:
        if lock:
            await _close(session, req, dead)
        raise invalid
    return req, step, user


async def inspect_link(session: AsyncSession, *, raw: str) -> dict:
    """What a link is about, changing nothing: the page shows it and asks before it acts. The
    new address in full (the link went either to the account's owner or to that address
    itself); the account's current address masked."""
    req, step, _user = await _by_link(session, raw, lock=False)
    return {
        "step": step,
        "new_email": req.new_email,
        "account_email": mask_email(req.old_email),
        "expires_at": req.expires_at,
    }


async def follow_link(session: AsyncSession, *, raw: str) -> dict:
    """The person pressed the button on either link's page: the approval (from the current
    address) sends the confirmation link to the new one; the confirmation makes the change."""
    req, step, user = await _by_link(session, raw, lock=True)

    if step == "approve":
        raw_confirm = new_opaque_token()
        req.status = "awaiting_confirmation"
        req.approve_token_hash = None
        req.confirm_token_hash = hash_token(raw_confirm)
        req.approved_at = _utcnow()
        req.expires_at = _utcnow() + LINK_TTL
        await _send(
            req.new_email,
            subject="Confirm your new Capimax PropShare email",
            intro=(
                "Confirm that this address should become the sign-in email of your Capimax "
                "PropShare account. The change happens when you press the button on the page."
            ),
            cta="Review and confirm",
            raw=raw_confirm,
            footnote="If you did not ask for this, ignore this email: nothing changes.",
        )
        await write_audit(
            session,
            action="auth.email_change_approved",
            entity_type="user",
            entity_id=str(user.id),
            actor_id=user.id,
            after={"new_email": mask_email(req.new_email)},
        )
        return {"status": "awaiting_confirmation", "new_email": mask_email(req.new_email)}

    other = await auth_service.get_user_by_email(session, req.new_email)
    if other is not None and other.id != user.id:
        await _close(session, req, "cancelled")
        raise AppError(
            "EMAIL_EXISTS",
            "That email address is now used by another account.",
            status_code=409,
        )
    old = user.email
    user.email = req.new_email
    user.email_verified = True
    profile = await session.get(Profile, user.id)
    if profile is not None:
        profile.email = req.new_email
    # verification / reset links were tied to the account, not the address: end them
    await session.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user.id, EmailToken.used_at.is_(None))
        .values(used_at=_utcnow())
    )
    req.status, req.confirm_token_hash, req.completed_at = "completed", None, _utcnow()
    await write_audit(
        session,
        action="auth.email_changed",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.id,
        before={"email": mask_email(old)},
        after={"email": mask_email(req.new_email), "source": req.source},
    )
    await notification_service.notify(
        session,
        user_id=user.id,
        type="security",
        title="Your email address was changed",
        message=(
            f"Your sign-in email is now {mask_email(req.new_email)}. If you did not do "
            "this, contact support right away."
        ),
        email_category="security",
        force_email=True,
        email_to=old,
    )
    return {"status": "completed", "new_email": mask_email(req.new_email)}


async def reject_link(session: AsyncSession, *, raw: str) -> dict:
    """\"This wasn't me\" on either link's page: the change stops. From the current address
    (the account's owner did not ask for it, so someone else is using the account) every
    device is signed out too, and the owner is told to change the password."""
    req, step, user = await _by_link(session, raw, lock=True)
    req.status, req.approve_token_hash, req.confirm_token_hash = "cancelled", None, None
    signed_out = step == "approve"
    if signed_out:
        await auth_service.revoke_all_refresh(session, user_id=user.id)
        await notification_service.notify(
            session,
            user_id=user.id,
            type="security",
            title="Email change stopped",
            message=(
                "You stopped a request to change your sign-in email, and every device was "
                "signed out. Sign in again and change your password; turn on two-factor "
                "authentication too."
            ),
            email_category="security",
            force_email=True,
        )
    await write_audit(
        session,
        action="auth.email_change_rejected",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=None,
        after={"step": step, "new_email": mask_email(req.new_email), "signed_out": signed_out},
    )
    return {"status": "cancelled", "signed_out": signed_out}
