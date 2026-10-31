"""0040 — Transfers: property units or wallet balance to another person, as on Capimax BRX.

Client (2026-10-28): an investor transfers units of a property they hold, or an amount from
their wallet, to anyone by email, from the dashboard's Transfers tab or the wallet.

``transfers``, one row per transfer, numbered ``TR-`` and ten characters:

  * what is sent is held at once: units are reserved against the sender's holding (the shared
    reserved-units rule counts open transfers), an amount leaves the wallet (with any fee);
  * ``scheduled`` until its delivery date (today by default, up to a year ahead);
  * ``delivered`` when the recipient's email is confirmed and identity verified: units move on
    the ownership ledger (``transfer_out`` / ``transfer_in``), an amount is credited;
  * ``waiting`` otherwise: the recipient is invited and has ``expires_at`` (30 days) to sign up
    and verify; it is handed over the moment they do;
  * ``cancelled`` (by the sender, before delivery, or by the team), ``expired`` (not received
    in time) or ``failed`` (it could not be delivered): everything held goes back, once.

``transaction_type`` gains ``transfer`` (committed on its own, as a new enum value must be
before it is used). ``transactions_transfer_paid_out_once``: at most one money-in row per
transfer, so an amount is either delivered to the recipient or returned to the sender, never
both and never twice. ``platform_settings.transfer_fee_pct`` (default 0).

Gifts: ``scheduled_gifts.claim_expires_at`` — a gift waiting for its recipient (``pending``) now
goes back to the giver after 30 days. A gift already waiting when this runs gets its 30 days
from now, not from its old date (nobody was told of a deadline before).

Additive; raw SQL like 0029-0039.
"""

from __future__ import annotations

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE public.transaction_type ADD VALUE IF NOT EXISTS 'transfer'")
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            reference TEXT NOT NULL,
            sender_id UUID NOT NULL REFERENCES users(id),
            recipient_id UUID REFERENCES users(id) ON DELETE SET NULL,
            recipient_email TEXT NOT NULL,
            recipient_name TEXT,
            asset TEXT NOT NULL CHECK (asset IN ('units', 'balance')),
            property_id UUID REFERENCES properties(id),
            property_title TEXT,
            units INTEGER,
            unit_price NUMERIC(15, 2),
            amount NUMERIC(15, 2) NOT NULL CHECK (amount >= 0),
            fee NUMERIC(15, 2) NOT NULL DEFAULT 0 CHECK (fee >= 0),
            fee_pct NUMERIC(6, 3) NOT NULL DEFAULT 0,
            message TEXT,
            occasion TEXT,
            deliver_on DATE NOT NULL,
            reminder_sent_at TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN
                ('scheduled', 'waiting', 'delivered', 'cancelled', 'expired', 'failed')),
            invited_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            delivered_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ,
            closed_reason TEXT,
            closed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            idempotency_key TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT transfers_what_check CHECK (
                (asset = 'units' AND property_id IS NOT NULL AND units > 0)
                OR (asset = 'balance' AND units IS NULL AND amount > 0)
            )
        )
        """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS transfers_reference_key ON transfers (reference)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS transfers_idempotency_key "
        "ON transfers (sender_id, idempotency_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS transfers_sender ON transfers (sender_id, created_at DESC)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS transfers_recipient ON transfers (recipient_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS transfers_waiting_email "
        "ON transfers (lower(recipient_email)) WHERE status = 'waiting'"
    )
    op.execute("CREATE INDEX IF NOT EXISTS transfers_open ON transfers (status, deliver_on)")
    # held units: the reserved-units rule sums open transfers per holder and property
    op.execute(
        "CREATE INDEX IF NOT EXISTS transfers_held_units ON transfers (sender_id, property_id) "
        "WHERE status IN ('scheduled', 'waiting')"
    )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS transactions_transfer_paid_out_once
            ON transactions (reference_id)
         WHERE type = 'transfer' AND amount > 0
        """)
    op.execute("ALTER TABLE scheduled_gifts ADD COLUMN IF NOT EXISTS claim_expires_at TIMESTAMPTZ")
    op.execute(
        "UPDATE scheduled_gifts SET claim_expires_at = now() + interval '30 days' "
        "WHERE status = 'pending' AND claim_expires_at IS NULL"
    )
    op.execute(
        "INSERT INTO platform_settings (key, value, description) VALUES ('transfer_fee_pct', '0', "
        "'Transfer fee, percent of what is transferred, paid by the sender (default 0)') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS transactions_transfer_paid_out_once")
    op.execute("DROP TABLE IF EXISTS transfers")
    op.execute("ALTER TABLE scheduled_gifts DROP COLUMN IF EXISTS claim_expires_at")
    op.execute("DELETE FROM platform_settings WHERE key = 'transfer_fee_pct'")
    # a value cannot be removed from a Postgres enum; 'transfer' stays, unused
