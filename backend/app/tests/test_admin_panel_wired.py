"""The SQLAdmin panel is mounted and admin-gated. No DB needed: the auth gate is
session-based and fires before any data access, so an anonymous visitor is
redirected to the login page rather than seeing any data."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_admin_index_redirects_anonymous_to_login() -> None:
    with TestClient(app) as client:
        # follow the mount's trailing-slash hop, but stop before the login page
        resp = client.get("/admin/", follow_redirects=False)
    # SQLAdmin redirects unauthenticated users to its login page.
    assert resp.status_code in (302, 307)
    assert "/admin/login" in resp.headers.get("location", "")


def test_admin_login_page_renders() -> None:
    with TestClient(app) as client:
        resp = client.get("/admin/login")
    assert resp.status_code == 200
    assert "password" in resp.text.lower()


def test_admin_property_list_requires_auth() -> None:
    with TestClient(app) as client:
        resp = client.get("/admin/property/list", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/admin/login" in resp.headers.get("location", "")
