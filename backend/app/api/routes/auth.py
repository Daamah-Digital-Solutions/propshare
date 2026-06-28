"""Auth & identity routes (Phase 1).

Token model (owner-mandated): the access token is returned in the body (client
keeps it in memory); the refresh token is set as an httpOnly, Secure, SameSite
cookie and never exposed to JS.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.deps import PrincipalDep, SessionDep, current_principal
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ratelimit import FORGOT_LIMIT, LOGIN_LIMIT, REGISTER_LIMIT, limiter
from app.models import KycVerification, Wallet
from app.models.identity import User
from app.schemas.auth import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    MeOut,
    OAuthCallbackIn,
    RegisterIn,
    RequestRoleIn,
    ResetPasswordIn,
    SwitchRoleIn,
    TokenOut,
    VerifyEmailIn,
    WalletSummary,
)
from app.services import auth_service
from app.services.integrations import oauth

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# --------------------------------------------------------------------------- #
# Refresh-token cookie helpers
# --------------------------------------------------------------------------- #
def _set_refresh_cookie(response: Response, raw: str, max_age: int) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.refresh_cookie_name,
        value=raw,
        max_age=max_age,
        httponly=True,
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,  # type: ignore[arg-type]
        domain=s.cookie_domain or None,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        key=s.refresh_cookie_name, path="/api/v1/auth", domain=s.cookie_domain or None
    )


def _token_out(access: str) -> TokenOut:
    return TokenOut(access_token=access, expires_in=get_settings().access_token_ttl_seconds)


async def _build_me(session: SessionDep, user: User) -> MeOut:
    roles = await auth_service.get_roles(session, user.id)
    kyc = await session.execute(
        select(KycVerification.status).where(KycVerification.user_id == user.id)
    )
    wallet = await session.execute(select(Wallet).where(Wallet.user_id == user.id))
    w = wallet.scalar_one_or_none()
    wallet_summary = WalletSummary(
        balance=str(w.balance if w else 0),
        pending_balance=str(w.pending_balance if w else 0),
        total_invested=str(w.total_invested if w else 0),
        total_returns=str(w.total_returns if w else 0),
    )
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        email_verified=user.email_verified,
        roles=roles,
        active_role=str(user.active_role) if user.active_role is not None else None,
        kyc_status=str(kyc.scalar_one_or_none() or "pending"),
        wallet=wallet_summary,
    )


# --------------------------------------------------------------------------- #
# Register / login / logout / refresh
# --------------------------------------------------------------------------- #
@router.post("/register", response_model=TokenOut, status_code=201)
@limiter.limit(REGISTER_LIMIT)
async def register(body: RegisterIn, request: Request, response: Response, session: SessionDep):
    user = await auth_service.register(
        session,
        email=str(body.email),
        password=body.password,
        full_name=body.full_name,
        phone=body.phone,
        referral_code=body.referral_code,
    )
    access, raw_refresh, _exp = await auth_service.issue_tokens(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, raw_refresh, get_settings().refresh_token_ttl_seconds)
    return _token_out(access)


@router.post("/login", response_model=TokenOut)
@limiter.limit(LOGIN_LIMIT)
async def login(body: LoginIn, request: Request, response: Response, session: SessionDep):
    user = await auth_service.authenticate(session, email=str(body.email), password=body.password)
    access, raw_refresh, _exp = await auth_service.issue_tokens(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, raw_refresh, get_settings().refresh_token_ttl_seconds)
    return _token_out(access)


@router.post("/refresh", response_model=TokenOut)
async def refresh(request: Request, response: Response, session: SessionDep):
    raw = request.cookies.get(get_settings().refresh_cookie_name)
    if not raw:
        raise AppError("UNAUTHENTICATED", "Missing refresh cookie", status_code=401)
    _user, access, new_refresh, _exp = await auth_service.rotate_refresh(
        session,
        raw_refresh=raw,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, new_refresh, get_settings().refresh_token_ttl_seconds)
    return _token_out(access)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, session: SessionDep):
    raw = request.cookies.get(get_settings().refresh_cookie_name)
    if raw:
        await auth_service.revoke_refresh(session, raw_refresh=raw)
    _clear_refresh_cookie(response)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Me / roles
# --------------------------------------------------------------------------- #
@router.get("/me", response_model=MeOut)
async def me(principal: PrincipalDep, session: SessionDep):
    user = await session.get(User, principal.user_id)
    if user is None:
        raise AppError("NOT_FOUND", "User not found", status_code=404)
    return await _build_me(session, user)


@router.post("/switch-role", response_model=MeOut)
async def switch_role(body: SwitchRoleIn, principal: PrincipalDep, session: SessionDep):
    user = await session.get(User, principal.user_id)
    if user is None:
        raise AppError("NOT_FOUND", "User not found", status_code=404)
    await auth_service.switch_active_role(session, user=user, role=body.role)
    return await _build_me(session, user)


@router.post("/roles/request")
async def request_role(body: RequestRoleIn, principal: PrincipalDep, session: SessionDep) -> dict:
    user = await session.get(User, principal.user_id)
    if user is None:
        raise AppError("NOT_FOUND", "User not found", status_code=404)
    return await auth_service.request_role(session, user=user, role=body.role)


# --------------------------------------------------------------------------- #
# Email verification & password reset
# --------------------------------------------------------------------------- #
@router.post("/verify-email", status_code=204)
async def verify_email(body: VerifyEmailIn, session: SessionDep):
    await auth_service.verify_email(session, raw=body.token)
    return Response(status_code=204)


@router.post("/password/forgot", status_code=202)
@limiter.limit(FORGOT_LIMIT)
async def forgot_password(body: ForgotPasswordIn, request: Request, session: SessionDep):
    # Always 202 — never reveal whether the email exists.
    await auth_service.start_password_reset(session, email=str(body.email))
    return Response(status_code=202)


@router.post("/password/reset", status_code=204)
async def reset_password(body: ResetPasswordIn, session: SessionDep):
    await auth_service.reset_password(session, raw=body.token, new_password=body.new_password)
    return Response(status_code=204)


@router.post("/password/change", status_code=204)
async def change_password(body: ChangePasswordIn, principal: PrincipalDep, session: SessionDep):
    user = await session.get(User, principal.user_id)
    if user is None:
        raise AppError("NOT_FOUND", "User not found", status_code=404)
    await auth_service.change_password(
        session,
        user=user,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# OAuth (Google / Apple) — SPA posts the provider authorization code
# --------------------------------------------------------------------------- #
@router.post("/oauth/{provider}", response_model=TokenOut)
async def oauth_login(
    provider: str, body: OAuthCallbackIn, request: Request, response: Response, session: SessionDep
):
    profile = await oauth.exchange(provider, body.code, body.redirect_uri)
    user = await auth_service.oauth_upsert(
        session,
        provider=provider,
        subject=profile.subject,
        email=profile.email,
        full_name=profile.full_name,
    )
    access, raw_refresh, _exp = await auth_service.issue_tokens(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, raw_refresh, get_settings().refresh_token_ttl_seconds)
    return _token_out(access)


# expose for tests / other routers
__all__ = ["router", "current_principal"]
