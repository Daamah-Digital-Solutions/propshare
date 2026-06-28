"""OAuth code-exchange for Google + Apple (Phase 1).

Each function turns an authorization ``code`` (+ the ``redirect_uri`` the SPA
used) into a verified identity ``(subject, email, full_name)``. If the provider
is not configured (no client id/secret), a clear 503 ``OAUTH_NOT_CONFIGURED`` is
raised so the feature degrades honestly rather than faking success.

NOTE: requires the owner-provisioned credentials to test live (see
plan/phase-01-identity-access.md → "OAuth config the owner must provide").
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import httpx
import jwt

from app.core.config import get_settings
from app.core.errors import AppError

_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
_APPLE_TOKEN = "https://appleid.apple.com/auth/token"
_APPLE_JWKS = "https://appleid.apple.com/auth/keys"
_APPLE_ISS = "https://appleid.apple.com"


@dataclass(frozen=True)
class OAuthProfile:
    subject: str
    email: str
    full_name: str | None


def _not_configured(provider: str) -> AppError:
    return AppError(
        "OAUTH_NOT_CONFIGURED",
        f"{provider} sign-in is not configured.",
        status_code=503,
    )


async def exchange_google(code: str, redirect_uri: str) -> OAuthProfile:
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        raise _not_configured("Google")
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            _GOOGLE_TOKEN,
            data={
                "code": code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]
        info_resp = await client.get(
            _GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access_token}"}
        )
        info_resp.raise_for_status()
        info = info_resp.json()
    email = info.get("email")
    if not email:
        raise AppError("OAUTH_NO_EMAIL", "Google account did not return an email", status_code=400)
    return OAuthProfile(subject=str(info["sub"]), email=email, full_name=info.get("name"))


def _apple_client_secret() -> str:
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    headers = {"kid": s.apple_key_id}
    payload = {
        "iss": s.apple_team_id,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=5)).timestamp()),
        "aud": _APPLE_ISS,
        "sub": s.apple_client_id,
    }
    return jwt.encode(payload, s.apple_private_key, algorithm="ES256", headers=headers)


async def exchange_apple(code: str, redirect_uri: str) -> OAuthProfile:
    s = get_settings()
    if not (s.apple_client_id and s.apple_team_id and s.apple_key_id and s.apple_private_key):
        raise _not_configured("Apple")
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            _APPLE_TOKEN,
            data={
                "code": code,
                "client_id": s.apple_client_id,
                "client_secret": _apple_client_secret(),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        id_token = token_resp.json()["id_token"]
        # Verify the id_token signature against Apple's JWKS.
        jwk_client = jwt.PyJWKClient(_APPLE_JWKS)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=s.apple_client_id,
            issuer=_APPLE_ISS,
        )
    email = claims.get("email")
    if not email:
        raise AppError("OAUTH_NO_EMAIL", "Apple account did not return an email", status_code=400)
    return OAuthProfile(subject=str(claims["sub"]), email=email, full_name=None)


async def exchange(provider: str, code: str, redirect_uri: str) -> OAuthProfile:
    if provider == "google":
        return await exchange_google(code, redirect_uri)
    if provider == "apple":
        return await exchange_apple(code, redirect_uri)
    raise AppError("OAUTH_UNKNOWN_PROVIDER", f"Unknown provider {provider!r}", status_code=404)
