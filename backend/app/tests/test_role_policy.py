"""Phase 1 — DB-free checks of the Scenario-B role-acquisition policy (D12).

Locks the owner's sub-decision: investor/owner are self-serve; broker/
liquidity_provider/admin require admin approval.
"""

from __future__ import annotations

from app.core.config import APPROVAL_ROLES, SELF_SERVE_ROLES
from app.models.base import AppRole


def test_self_serve_roles() -> None:
    assert SELF_SERVE_ROLES == {"investor", "owner"}


def test_approval_roles() -> None:
    assert APPROVAL_ROLES == {"broker", "liquidity_provider", "admin"}


def test_every_app_role_has_a_policy_and_no_overlap() -> None:
    all_roles = {r.value for r in AppRole}
    assert all_roles == SELF_SERVE_ROLES | APPROVAL_ROLES
    assert not (SELF_SERVE_ROLES & APPROVAL_ROLES)


def test_admin_is_never_self_serve() -> None:
    assert "admin" not in SELF_SERVE_ROLES
