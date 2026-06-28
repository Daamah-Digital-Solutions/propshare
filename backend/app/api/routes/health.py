"""Health endpoints.

GET /healthz  -> 200 when the DATABASE is reachable (Redis is OPTIONAL — money paths
use Postgres FOR UPDATE, not Redis — so Redis being down is reported but does not fail
health). 503 only when the database is down. Still valid JSON either way.
GET /         -> tiny liveness probe (always 200 if the process is up).
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app import __version__
from app.core.config import get_settings
from app.core.db import ping_db
from app.core.redis import ping_redis

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, str]:
    return {"service": "capimax-backend", "version": __version__, "status": "ok"}


@router.get("/healthz")
async def healthz(response: Response) -> dict[str, object]:
    db_ok = await ping_db()
    redis_ok = await ping_redis()
    # Redis is optional — only the database gates health.
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if db_ok else "down",
        "version": __version__,
        "environment": get_settings().environment,
        "dependencies": {
            "database": "up" if db_ok else "down",
            "redis": "up" if redis_ok else "down",
        },
    }
