"""Phase 3 — property routes are wired and protected. No DB needed: the auth
checks on protected routes fire before any DB access, and the public routes are
asserted via the OpenAPI schema only (their data path needs Postgres)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

EXPECTED_PATHS = {
    "/api/v1/properties",
    "/api/v1/properties/{id_or_slug}",
    "/api/v1/properties/{prop_id}",
    "/api/v1/properties/{prop_id}/submit",
    "/api/v1/properties/{prop_id}/images",
    "/api/v1/owner/properties",
    "/api/v1/admin/properties",
    "/api/v1/admin/properties/{prop_id}/approve",
    "/api/v1/admin/properties/{prop_id}/reject",
    "/api/v1/admin/properties/{prop_id}/close",
}

_VALID_CREATE = {
    "title": "Test Tower",
    "property_type": "apartment",
    "location": "Dubai, UAE",
    "total_value": 1000000,
    "unit_price": 100,
}


def test_property_paths_in_openapi() -> None:
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
    missing = EXPECTED_PATHS - set(spec["paths"].keys())
    assert not missing, f"missing OpenAPI paths: {sorted(missing)}"


def test_create_requires_auth() -> None:
    with TestClient(app) as client:
        # Valid body so it's the auth gate (not validation) that rejects.
        assert client.post("/api/v1/properties", json=_VALID_CREATE).status_code == 401


def test_owner_list_requires_auth() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/owner/properties").status_code == 401


def test_submit_requires_auth() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/v1/properties/00000000-0000-0000-0000-000000000000/submit")
    assert resp.status_code == 401


def test_admin_moderation_requires_auth() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/properties").status_code == 401
        resp = client.post("/api/v1/admin/properties/00000000-0000-0000-0000-000000000000/approve")
    assert resp.status_code == 401
