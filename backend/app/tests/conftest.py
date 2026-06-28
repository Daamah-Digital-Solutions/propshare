"""DB-backed integration test harness (pre-Phase-4 hardening).

Builds a throwaway ``<db>_test`` database from the REAL Alembic migrations,
points the FastAPI app's ``get_session`` at it, and hands tests an httpx
``AsyncClient`` plus a synchronous SQL helper (``db``) for arrange/assert.

If Postgres is unreachable (e.g. CI without a DB), the whole integration layer
is SKIPPED — the DB-free unit tests still run everywhere. The test DB is derived
from the app's configured ``DATABASE_URL`` (so it follows your local .env, port
and credentials), with ``_test`` appended to the database name.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from collections.abc import AsyncIterator, Callable, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.db import get_session
from app.main import app

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]


def _render(url) -> str:
    # SQLAlchemy's str(URL) masks the password as "***" — render the real one.
    return url.render_as_string(hide_password=False)


def _derive_urls() -> tuple[str, str, str, str]:
    base = make_url(get_settings().database_url)
    test_db = f"{base.database}_test"
    async_url = base.set(database=test_db)
    sync_url = async_url.set(drivername="postgresql+psycopg")
    maint_url = base.set(drivername="postgresql+psycopg", database="postgres")
    return _render(async_url), _render(sync_url), _render(maint_url), test_db


@pytest.fixture(scope="session")
def _test_db() -> Iterator[tuple[str, str]]:
    async_url, sync_url, maint_url, test_db = _derive_urls()
    try:
        eng = create_engine(maint_url, isolation_level="AUTOCOMMIT")
        with eng.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{test_db}"'))
        eng.dispose()
    except Exception as exc:  # Postgres unreachable -> skip the whole integration layer
        pytest.skip(f"integration DB unavailable: {exc}")

    alembic_exe = pathlib.Path(sys.prefix) / (
        "Scripts/alembic.exe" if os.name == "nt" else "bin/alembic"
    )
    res = subprocess.run(
        [str(alembic_exe), "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env={**os.environ, "ALEMBIC_DATABASE_URL": sync_url},
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        pytest.skip(f"alembic upgrade failed on test DB: {res.stderr[-400:]}")

    yield async_url, sync_url

    eng = create_engine(maint_url, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
    eng.dispose()


@pytest.fixture(scope="session")
def _sync_engine(_test_db):
    _async_url, sync_url = _test_db
    eng = create_engine(sync_url)
    yield eng
    eng.dispose()


# NOTE: these are NOT autouse — they only run for tests that request `client`/`db`,
# so the DB-free unit tests never touch Postgres (and never skip when it's absent).
@pytest.fixture(scope="session")
def _override_session(_test_db):
    async_url, _sync = _test_db
    engine = create_async_engine(async_url, poolclass=NullPool)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_session() -> AsyncIterator:
        async with sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = _get_session
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def _clean(_sync_engine):
    """Truncate all data tables before each integration test for isolation."""
    with _sync_engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename <> 'alembic_version'"
            )
        ).all()
        names = ", ".join(f'"{r[0]}"' for r in rows)
        if names:
            c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
            c.commit()
    yield


@pytest.fixture(autouse=True)
def _clear_provider_secrets(monkeypatch):
    """Make the test env deterministic regardless of the developer's local .env:
    all external providers start UNconfigured. Tests that need a provider
    configured monkeypatch its secret explicitly (and that wins for that test)."""
    # Rate limiting OFF by default so the register/login-heavy suites aren't throttled;
    # the dedicated rate-limit test flips it on for its own assertions.
    from app.core.ratelimit import limiter

    limiter.enabled = False
    settings = get_settings()
    for attr in (
        "stripe_secret_key",
        "stripe_webhook_secret",
        "nowpayments_api_key",
        "nowpayments_ipn_secret",
        "nowpayments_email",
        "nowpayments_password",
        "sumsub_app_token",
        "sumsub_secret_key",
        "sumsub_webhook_secret",
    ):
        monkeypatch.setattr(settings, attr, "", raising=False)
    yield


@pytest_asyncio.fixture
async def client(_override_session, _clean) -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False -> an unhandled app error becomes a 500 response
    # (as a real HTTP client sees it) instead of propagating into the test.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def asession(_test_db, _clean) -> AsyncIterator:
    """A raw AsyncSession on the test DB — for exercising service functions (e.g. the
    reservation-expiry sweep) directly, without going through an HTTP route."""
    async_url, _sync = _test_db
    engine = create_async_engine(async_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def db(_sync_engine) -> Callable[..., list]:
    """Run raw SQL against the test DB for arrange/assert (commits each call)."""

    def run(sql: str, **params) -> list:
        with _sync_engine.connect() as c:
            res = c.execute(text(sql), params)
            rows = res.fetchall() if res.returns_rows else []
            c.commit()
            return rows

    return run
