"""Phase 0 health checks (Phase 13: Redis is optional).

The DATABASE gates health: 200 when the DB is up (regardless of Redis), 503 only when
the DB is down — both valid JSON with the dependency breakdown. Redis being down is
reported but does not fail health (money paths use Postgres FOR UPDATE, not Redis).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_root_liveness() -> None:
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "capimax-backend"
        assert body["status"] == "ok"


def test_healthz_shape_and_status() -> None:
    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert body["status"] in ("ok", "down")
        assert body["dependencies"]["database"] in ("up", "down")
        assert body["dependencies"]["redis"] in ("up", "down")
        # Phase 13: the DATABASE gates health (Redis is optional). 200 iff DB up.
        db_up = body["dependencies"]["database"] == "up"
        assert (resp.status_code == 200) == db_up


def test_request_id_header_present() -> None:
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.headers.get("X-Request-ID")
