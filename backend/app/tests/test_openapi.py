"""OpenAPI / docs are served (the frontend's integration contract)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_json() -> None:
    with TestClient(app) as client:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        assert spec["openapi"].startswith("3.")
        assert spec["info"]["title"] == "CapiMax PropShare API"
        assert "/healthz" in spec["paths"]


def test_swagger_docs() -> None:
    with TestClient(app) as client:
        resp = client.get("/docs")
        assert resp.status_code == 200
