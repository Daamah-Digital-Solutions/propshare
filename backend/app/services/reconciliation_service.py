"""System-wide reconciliation (Phase 13) — a READ-ONLY drift detector.

Every money invariant is enforced at write time (DB CHECKs + ``FOR UPDATE``) and asserted
per-operation in tests. This adds a DB-wide pass that scans the whole database and reports
any row that violates an invariant — ideally zero. It NEVER mutates anything (no repair);
it is a detector for a launch-readiness pass and a cron-able health signal.

Invariants checked:
  1. wallet_balance        wallets.balance == Σ transactions.amount (per user)
  2. pending_balance       wallets.pending_balance == Σ non-terminal withdrawals
  3. property_units        total_units == available + Σ pending-reservation + Σ issued(ledger)
  4. ownership_nonneg      no (user, property) holds negative net units
  5. family_pending        Σ pending family transfers ≤ holder's net holding (per property)
  6. distribution_split    Σ(item.net + item.management_fee) == distribution.gross_pool
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SAMPLE_CAP = 20

# Each check: a SELECT that returns ONLY drifting rows (empty result == healthy).
_CHECKS: dict[str, str] = {
    "wallet_balance": """
        SELECT w.user_id::text AS user_id, w.balance::text AS balance,
               COALESCE(SUM(t.amount), 0)::text AS ledger
        FROM wallets w
        LEFT JOIN transactions t ON t.user_id = w.user_id
        GROUP BY w.user_id, w.balance
        HAVING w.balance <> COALESCE(SUM(t.amount), 0)
    """,
    "pending_balance": """
        SELECT w.user_id::text AS user_id, w.pending_balance::text AS pending_balance,
               COALESCE(SUM(wd.amount) FILTER (
                   WHERE wd.status IN ('pending_review', 'approved', 'processing')), 0)::text
                   AS in_flight
        FROM wallets w
        LEFT JOIN withdrawals wd ON wd.user_id = w.user_id
        GROUP BY w.user_id, w.pending_balance
        HAVING w.pending_balance <> COALESCE(SUM(wd.amount) FILTER (
                   WHERE wd.status IN ('pending_review', 'approved', 'processing')), 0)
    """,
    "property_units": """
        SELECT p.id::text AS property_id, p.total_units, p.available_units,
               COALESCE((SELECT SUM(o.units) FROM ownership_ledger o
                         WHERE o.property_id = p.id), 0) AS issued,
               COALESCE((SELECT SUM(i.units) FROM investments i
                         WHERE i.property_id = p.id AND i.status = 'pending'), 0) AS reserved
        FROM properties p
        WHERE p.total_units <> p.available_units
              + COALESCE((SELECT SUM(o.units) FROM ownership_ledger o
                          WHERE o.property_id = p.id), 0)
              + COALESCE((SELECT SUM(i.units) FROM investments i
                          WHERE i.property_id = p.id AND i.status = 'pending'), 0)
    """,
    "ownership_nonneg": """
        SELECT user_id::text AS user_id, property_id::text AS property_id,
               SUM(units) AS net_units
        FROM ownership_ledger
        GROUP BY user_id, property_id
        HAVING SUM(units) < 0
    """,
    "family_pending": """
        SELECT fm.user_id::text AS holder_id, ft.property_id::text AS property_id,
               SUM(ft.units) AS pending_units,
               COALESCE((SELECT SUM(o.units) FROM ownership_ledger o
                         WHERE o.user_id = fm.user_id AND o.property_id = ft.property_id), 0)
                   AS net_held
        FROM family_transfers ft
        JOIN family_members fm ON ft.from_member_id = fm.id
        WHERE ft.status = 'pending' AND fm.user_id IS NOT NULL AND ft.property_id IS NOT NULL
        GROUP BY fm.user_id, ft.property_id
        HAVING SUM(ft.units) > COALESCE((SELECT SUM(o.units) FROM ownership_ledger o
                         WHERE o.user_id = fm.user_id AND o.property_id = ft.property_id), 0)
    """,
    "distribution_split": """
        SELECT d.id::text AS distribution_id, d.gross_pool::text AS gross_pool,
               COALESCE(SUM(di.net_amount + di.management_fee), 0)::text AS split_total
        FROM distributions d
        LEFT JOIN distribution_items di ON di.distribution_id = d.id
        GROUP BY d.id, d.gross_pool
        HAVING d.gross_pool <> COALESCE(SUM(di.net_amount + di.management_fee), 0)
    """,
}


async def run(session: AsyncSession) -> dict:
    """Run all checks. Returns {ok, checks:[{name, drift_count, samples}]}; ok == no drift."""
    checks: list[dict] = []
    overall_ok = True
    for name, sql in _CHECKS.items():
        rows = (await session.execute(text(sql))).mappings().all()
        if rows:
            overall_ok = False
        checks.append(
            {
                "name": name,
                "drift_count": len(rows),
                "samples": [dict(r) for r in rows[:_SAMPLE_CAP]],
            }
        )
    return {"ok": overall_ok, "checks": checks}
