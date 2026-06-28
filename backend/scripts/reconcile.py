"""Reconciliation CLI (Phase 13) — run the DB-wide invariant drift report.

Prints each check's drift count (and a few sample rows on drift), then exits:
  * exit 0 — clean (no drift anywhere).
  * exit 1 — drift found (suitable for a cron that should alert on non-zero).

This is the same read-only detector as GET /api/v1/admin/reconciliation; it NEVER
mutates. Cron-able nightly on the VPS.

Usage (from backend/, with the venv):
    .venv\\Scripts\\python.exe scripts/reconcile.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from app.core.db import session_scope
from app.services import reconciliation_service


async def _main() -> int:
    async with session_scope() as session:
        report = await reconciliation_service.run(session)
    print(f"reconciliation: {'OK (no drift)' if report['ok'] else 'DRIFT DETECTED'}")
    for check in report["checks"]:
        flag = "ok" if check["drift_count"] == 0 else f"DRIFT x{check['drift_count']}"
        print(f"  - {check['name']}: {flag}")
        for sample in check["samples"]:
            print(f"      {json.dumps(sample, default=str)}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
