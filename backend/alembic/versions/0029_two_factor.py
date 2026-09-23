"""0029 — two-factor authentication (authenticator app + recovery codes).

Replaces the disabled "Two-Factor Authentication — Not available yet" row in Account
Settings with the real thing.

  * ``user_mfa`` — one row per user who started or finished enrolment.
      - ``secret_enc`` / ``pending_secret_enc``: the TOTP secret, AES-GCM encrypted with the
        platform key file (app/core/crypto.py) — never plaintext in the DB or in backups.
        ``pending`` holds a secret shown in a QR code but not yet confirmed by a first code.
      - ``last_used_step``: the 30-second step of the last accepted code, so the same code
        cannot be used twice (replay).
      - ``failed_attempts`` / ``locked_until``: repeated wrong codes lock the second step.
  * ``user_recovery_codes`` — ten one-time codes shown once at enrolment. Stored as SHA-256
    of an 80-bit random code (brute force is infeasible even if the table leaked), so they
    keep working if the encryption key is ever lost — the documented way back in.

Additive and idempotent, raw SQL like 0023/0026/0027/0028.
"""

from __future__ import annotations

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_mfa (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            secret_enc BYTEA,
            pending_secret_enc BYTEA,
            pending_created_at TIMESTAMPTZ,
            enabled_at TIMESTAMPTZ,
            last_used_step BIGINT,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_recovery_codes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS user_recovery_codes_hash_key
            ON user_recovery_codes (user_id, code_hash);
        CREATE INDEX IF NOT EXISTS user_recovery_codes_user_idx
            ON user_recovery_codes (user_id) WHERE used_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_recovery_codes;")
    op.execute("DROP TABLE IF EXISTS user_mfa;")
