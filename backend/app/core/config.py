"""Application settings, loaded from environment / .env (pydantic-settings).

Phase 0 established DB + Redis + app basics. Phase 1 adds identity/auth config
(JWT, refresh-cookie, email, OAuth). Provider secrets for later phases (Stripe,
OnePayments, KYC) remain placeholders. NEVER hardcode real secrets.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Scenario-B role policy (D12): how a user acquires a NEW role.
#   self-serve -> granted immediately on request
#   approval   -> creates a role_grant_request an admin must approve
SELF_SERVE_ROLES: frozenset[str] = frozenset({"investor", "owner"})
APPROVAL_ROLES: frozenset[str] = frozenset({"broker", "liquidity_provider", "admin"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    environment: str = "local"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:5173"
    # Shared secret for system-cron to call the idempotent admin job endpoints via the
    # X-Cron-Secret header (no embedded admin password). Empty => header auth disabled
    # (only an authenticated admin can call those endpoints). Set on the VPS.
    cron_secret: str = ""
    # Public URL of the SPA (used to build email verify/reset links).
    app_base_url: str = "http://localhost:5173"

    # Datastores. Defaults point at the local docker-compose services so the app
    # boots without a .env; /healthz will report "down" if they are unreachable.
    database_url: str = "postgresql+asyncpg://capimax:capimax@localhost:5432/capimax"
    redis_url: str = "redis://localhost:6379/0"

    # Sync URL for Alembic (psycopg). If blank, env.py derives it from database_url.
    alembic_database_url: str = ""

    # --- Auth / JWT (Phase 1) ---
    # JWT_SECRET MUST be overridden in staging/production. The default is a clearly
    # non-production value used only for local boot/tests.
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900  # 15 min — short, per owner mandate
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days

    # Refresh token cookie (httpOnly; access token stays in memory client-side).
    refresh_cookie_name: str = "capimax_refresh"
    cookie_secure: bool = False  # True in staging/production (HTTPS)
    cookie_samesite: str = "lax"
    cookie_domain: str = ""  # set in prod if API/SPA share a parent domain

    # Email-token lifetimes
    email_verify_ttl_seconds: int = 60 * 60 * 24  # 24h
    password_reset_ttl_seconds: int = 60 * 60  # 1h

    # --- Email (Phase 1: verification + password reset ONLY) ---
    # provider: "console" (dev — logs the link), "resend", or "smtp"
    email_provider: str = "console"
    email_from: str = "CapiMax <no-reply@capimax.local>"
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # --- KYC / Sumsub (Phase 2). Empty app token/secret => provider disabled (503). ---
    sumsub_base_url: str = "https://api.sumsub.com"
    sumsub_app_token: str = ""  # X-App-Token for the Sumsub REST API
    sumsub_secret_key: str = ""  # signs outbound API requests (HMAC)
    sumsub_webhook_secret: str = ""  # verifies inbound webhook X-Payload-Digest
    sumsub_level_name: str = "basic-kyc-level"

    @property
    def sumsub_configured(self) -> bool:
        return bool(self.sumsub_app_token and self.sumsub_secret_key)

    # --- Payments / deposits (Phase 4). Empty creds => provider disabled (503). ---
    # Wallet currency (USD). Crypto deposits are credited as the USD-equivalent the
    # provider settles; the original asset/amount is kept in payments.raw_payload.
    wallet_currency: str = "USD"

    # Stripe (cards / Apple Pay / Google Pay) — D2.
    stripe_secret_key: str = ""  # sk_... (server-side API calls)
    stripe_webhook_secret: str = ""  # whsec_... (verifies Stripe-Signature)
    stripe_publishable_key: str = ""  # pk_... (exposed to the SPA)

    # NOWPayments (crypto) — D4. IPN signed HMAC-SHA512 in the x-nowpayments-sig header.
    nowpayments_api_key: str = ""
    nowpayments_ipn_secret: str = ""  # signs/verifies inbound IPN callbacks
    nowpayments_sandbox: bool = True  # api-sandbox.nowpayments.io vs api.nowpayments.io

    # NOWPayments PAYOUTS (Phase 7, crypto withdrawals). The payout API needs a JWT
    # (auth with the account email+password) + 2FA + an IP-whitelisted server.
    nowpayments_email: str = ""
    nowpayments_password: str = ""

    # Stripe Connect (Phase 7, bank withdrawals): payouts to investors' connected
    # accounts. Reuses stripe_secret_key; webhook reuses stripe_webhook_secret.

    @property
    def stripe_configured(self) -> bool:
        return bool(self.stripe_secret_key and self.stripe_webhook_secret)

    @property
    def nowpayments_configured(self) -> bool:
        return bool(self.nowpayments_api_key and self.nowpayments_ipn_secret)

    @property
    def nowpayments_payout_configured(self) -> bool:
        # Crypto withdrawals: payout API (JWT) + IPN verification.
        return bool(
            self.nowpayments_api_key
            and self.nowpayments_email
            and self.nowpayments_password
            and self.nowpayments_ipn_secret
        )

    @property
    def stripe_connect_configured(self) -> bool:
        # Bank withdrawals via Connect reuse the Stripe secret + webhook secret.
        return self.stripe_configured

    @property
    def nowpayments_base_url(self) -> str:
        return (
            "https://api-sandbox.nowpayments.io/v1"
            if self.nowpayments_sandbox
            else "https://api.nowpayments.io/v1"
        )

    # --- OAuth (Phase 1: Google + Apple). Empty => provider disabled (clear 503). ---
    google_client_id: str = ""
    google_client_secret: str = ""
    apple_client_id: str = ""  # Services ID
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""  # contents of the .p8

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
