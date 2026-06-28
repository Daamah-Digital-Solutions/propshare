"""FastAPI application entrypoint.

Phase 0 wiring: settings, CORS, error envelope, request-id logging, the health
router, and OpenAPI at /docs + /openapi.json. Domain routers are registered
from Phase 1 onward.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import (
    auth,
    broker,
    developer_updates,
    documents,
    family,
    health,
    investments,
    kyc,
    liquidity,
    milestones,
    notifications,
    owner_stats,
    payment_methods,
    payments,
    profiles,
    properties,
    secondary,
    wallet,
    withdrawals,
)
from app.api.routes.admin import distributions as admin_distributions
from app.api.routes.admin import kyc as admin_kyc
from app.api.routes.admin import liquidity as admin_liquidity
from app.api.routes.admin import properties as admin_properties
from app.api.routes.admin import reconciliation as admin_reconciliation
from app.api.routes.admin import users as admin_users
from app.api.routes.admin import withdrawals as admin_withdrawals
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.errors import register_exception_handlers
from app.core.ratelimit import limiter
from app.core.redis import close_redis

logger = logging.getLogger("capimax")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logger.info("starting capimax-backend v%s (env=%s)", __version__, settings.environment)
    yield
    await dispose_engine()
    await close_redis()
    logger.info("shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CapiMax PropShare API",
        version=__version__,
        description="CapiMax PropShare backend. Phase 0 — foundation & schema adoption.",
        lifespan=lifespan,
    )

    # Rate limiting (Phase 13): IP-keyed limiter; over-limit -> 429 in the error envelope.
    from slowapi.errors import RateLimitExceeded

    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(_: Request, exc: RateLimitExceeded) -> Response:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": f"Too many requests ({exc.detail}). Please slow down.",
                    "details": {},
                }
            },
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_mw(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(profiles.router)
    app.include_router(kyc.router)
    app.include_router(properties.router)
    app.include_router(wallet.router)
    app.include_router(payments.router)
    app.include_router(investments.router)
    app.include_router(withdrawals.router)
    app.include_router(secondary.router)
    app.include_router(liquidity.router)
    app.include_router(family.router)
    app.include_router(broker.router)
    app.include_router(notifications.router)
    app.include_router(owner_stats.router)
    app.include_router(milestones.router)
    app.include_router(developer_updates.router)
    app.include_router(documents.router)
    app.include_router(payment_methods.router)
    app.include_router(admin_users.router)
    app.include_router(admin_kyc.router)
    app.include_router(admin_properties.router)
    app.include_router(admin_distributions.router)
    app.include_router(admin_withdrawals.router)
    app.include_router(admin_liquidity.router)
    app.include_router(admin_reconciliation.router)

    # Server-rendered, admin-gated management panel at /admin.
    from app.admin import setup_admin

    setup_admin(app)
    return app


app = create_app()
