"""Seed the FIRST admin (run once, on the server).

Grants the ``admin`` role to an existing user (by email) and sets it active.
This is the ONLY way the first admin is created; thereafter an existing admin
grants ``admin`` to others via the admin API. Admin is never self-serve.

Usage:
    python scripts/seed_admin.py admin@example.com
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.db import session_scope
from app.models import UserRole
from app.models.base import AppRole
from app.models.identity import User


async def _seed(email: str) -> int:
    async with session_scope() as session:
        res = await session.execute(select(User).where(User.email == email))
        user = res.scalar_one_or_none()
        if user is None:
            print(f"FAIL: no user with email {email!r}. Register them first.")
            return 1
        exists = await session.execute(
            select(UserRole.id).where(UserRole.user_id == user.id, UserRole.role == AppRole.admin)
        )
        if exists.first() is None:
            session.add(UserRole(user_id=user.id, role=AppRole.admin))
        user.active_role = AppRole.admin
        print(f"OK: {email} is now admin (active_role=admin).")
        return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/seed_admin.py <email>")
        return 2
    return asyncio.run(_seed(sys.argv[1]))


if __name__ == "__main__":
    sys.exit(main())
