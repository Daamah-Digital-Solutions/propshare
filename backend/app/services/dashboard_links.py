"""Where the SPA shows a member's wallet, by active role.

The wallet is one per user and shared across roles, but each role has its own dashboard
and the investor dashboard is closed to a token whose active role is another one. A
provider's return URL (hosted checkout, Stripe Connect onboarding) must therefore send the
member back to the dashboard of the role they were using, or they land on a page they
cannot open and never see the outcome.
"""

from __future__ import annotations

_HOME_BY_ROLE = {
    "investor": "/dashboard",
    "owner": "/owner-dashboard",
    "broker": "/broker-dashboard",
    "liquidity_provider": "/liquidity-dashboard",
}


def home_path(active_role: str | None) -> str:
    return _HOME_BY_ROLE.get(active_role or "", "/dashboard")


def wallet_url(app_base: str, active_role: str | None, **params: str) -> str:
    """``{app_base}{role home}?tab=wallet&<params>`` — the wallet tab of the role's dashboard."""
    query = "&".join(["tab=wallet", *(f"{k}={v}" for k, v in params.items())])
    return f"{app_base.rstrip('/')}{home_path(active_role)}?{query}"
