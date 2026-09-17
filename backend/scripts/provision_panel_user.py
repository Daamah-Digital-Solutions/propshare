"""Provision an admin-panel account with a ONE-TIME password (run on the server).

Creates the user if needed, grants the role (e.g. ``content_editor``), sets
``must_change_password`` and prints the generated password ONCE to stdout. The password is
never written to a file, a log, the audit trail or the environment — only its hash is
stored. The holder must replace it at the first admin-panel login.

Refuses to touch an account that holds the ``admin`` role.

Usage:
    python scripts/provision_panel_user.py <email> <role> ["Full Name"]
"""

from __future__ import annotations

import asyncio
import sys

from app.core.db import session_scope
from app.core.errors import AppError
from app.services import auth_service


async def _run(email: str, role: str, full_name: str | None) -> int:
    try:
        async with session_scope() as session:
            password = await auth_service.provision_panel_user(
                session, email=email, role=role, full_name=full_name
            )
    except (AppError, ValueError) as exc:
        print(f"FAIL: {getattr(exc, 'message', None) or exc}")
        return 1
    print(f"OK: {email} provisioned with role {role}; password change forced at first login.")
    print(f"ONE-TIME PASSWORD: {password}")
    return 0


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print('usage: python scripts/provision_panel_user.py <email> <role> ["Full Name"]')
        return 2
    return asyncio.run(_run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None))


if __name__ == "__main__":
    sys.exit(main())
