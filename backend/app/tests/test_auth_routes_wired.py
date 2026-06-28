"""Phase 1 — the auth/profile/admin routers are wired and appear in OpenAPI,
and protected endpoints reject unauthenticated callers (no DB needed).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

EXPECTED_PATHS = {
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/auth/switch-role",
    "/api/v1/auth/roles/request",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/password/forgot",
    "/api/v1/auth/password/reset",
    "/api/v1/auth/oauth/{provider}",
    "/api/v1/profiles/me",
    "/api/v1/admin/users",
}


def test_auth_paths_in_openapi() -> None:
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
    missing = EXPECTED_PATHS - set(spec["paths"].keys())
    assert not missing, f"missing OpenAPI paths: {sorted(missing)}"


def test_me_requires_authentication() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


def test_switch_role_requires_authentication() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/v1/auth/switch-role", json={"role": "admin"})
    assert resp.status_code == 401


def test_admin_route_requires_authentication() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/admin/users")
    assert resp.status_code == 401
