"""0035 — a family transfer leaves a trace, and a beneficiary can prove and claim.

Client (2026-10-07):
  1. Adding a family member and transferring to one "do the whole job but leave no trace":
     no email, no notification, nothing on the investments page, nothing for the receiver.
  2. A beneficiary / heir must carry an identity document, be editable, and have a
     downloadable certificate the person can present later.
  3. A public page where that person reports the holder's death and claims, attaching the
     certificate and their own identity document. After staff review the assets move to the
     claimant's OWN account: nobody is ever given the holder's account.

  * ``ownership_ledger.ref_id`` — the family transfer or estate transfer a unit movement
    belongs to, so a movement can say who the other person was. Filled for the transfers
    already recorded (the ledger pair and its transfer row share a transaction, hence a
    timestamp; a transfer that became real later is matched by its ``materialized_at``).
  * ``family_members.pending_returns`` — what a member who cannot be paid yet is still owed.
    Until now the one counter ``allocated_returns`` was both "everything ever allocated to
    this member" and "what to move to them when they verify", so money already paid to a
    verified member was owed, and paid, a second time the next time their allocations were
    released. ``allocated_returns`` stays the running total the page shows; only
    ``pending_returns`` is released. Existing rows: a member who is not verified is owed what
    was recorded for them; a verified member is owed nothing.
  * ``estate_beneficiaries.certificate_no`` — the number printed on the beneficiary's
    certificate and typed into a claim (unique). ``version`` counts the changes to what the
    certificate prints, so a copy issued before a change can be told from the current one.
    ``id_documents`` — [{id, key, filename, content_type, size, uploaded_at}] in object
    storage: the copies of the person's identity document the holder uploaded (never public).
  * ``estate_claims`` — one claim: who claims, about which holder, why, the documents sent,
    what staff matched it to (holder, beneficiary record, the claimant's own account), the
    decision and the estate event it executed.
  * ``estate_events.claim_id`` / ``reason`` / ``date_of_death`` — the claim an execution came
    from and what it recorded.

Additive; raw SQL like 0029-0034.
"""

from __future__ import annotations

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute(
        """
        ALTER TABLE ownership_ledger ADD COLUMN IF NOT EXISTS ref_id UUID;

        UPDATE ownership_ledger l SET ref_id = t.id
          FROM family_transfers t
          JOIN family_members fm ON fm.id = t.from_member_id
          JOIN family_members tm ON tm.id = t.to_member_id
         WHERE l.ref_id IS NULL
           AND t.status = 'completed'
           AND l.property_id = t.property_id
           AND ((l.reason = 'family_transfer_out' AND l.user_id = fm.user_id
                 AND l.units = -t.units)
             OR (l.reason = 'family_transfer_in' AND l.user_id = tm.user_id
                 AND l.units = t.units))
           AND (l.created_at = t.created_at
                OR (t.materialized_at IS NOT NULL
                    AND l.created_at BETWEEN t.materialized_at - interval '2 minutes'
                                         AND t.materialized_at + interval '2 minutes'));

        UPDATE ownership_ledger l SET ref_id = et.id
          FROM estate_transfers et
          JOIN estate_events ev ON ev.id = et.estate_event_id
          JOIN estate_beneficiaries b ON b.id = et.beneficiary_id
         WHERE l.ref_id IS NULL
           AND et.status = 'completed'
           AND l.property_id = et.property_id
           AND ((l.reason = 'estate_transfer_out' AND l.user_id = ev.subject_user_id
                 AND l.units = -et.units)
             OR (l.reason = 'estate_transfer_in' AND l.user_id = b.beneficiary_user_id
                 AND l.units = et.units))
           AND (l.created_at = et.created_at
                OR (et.materialized_at IS NOT NULL
                    AND l.created_at BETWEEN et.materialized_at - interval '2 minutes'
                                         AND et.materialized_at + interval '2 minutes'));

        ALTER TABLE family_members
            ADD COLUMN IF NOT EXISTS pending_returns NUMERIC NOT NULL DEFAULT 0;
        UPDATE family_members SET pending_returns = allocated_returns
         WHERE is_verified = false AND allocated_returns > 0 AND pending_returns = 0;

        ALTER TABLE estate_beneficiaries
            ADD COLUMN IF NOT EXISTS certificate_no TEXT,
            ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,
            ADD COLUMN IF NOT EXISTS id_documents JSONB NOT NULL DEFAULT '[]'::jsonb;
        -- the records that exist get a number too (the service writes one for every new record)
        UPDATE estate_beneficiaries
           SET certificate_no = 'CPB-' || upper(substr(md5(id::text || random()::text), 1, 4))
                                || '-' || upper(substr(md5(random()::text || id::text), 1, 4))
         WHERE certificate_no IS NULL;
        -- a default too: a row written without a number (the code before this release, while
        -- it is still running or after a roll back of the code alone) gets one from the database
        ALTER TABLE estate_beneficiaries ALTER COLUMN certificate_no SET DEFAULT (
            'CPB-' || upper(substr(md5(gen_random_uuid()::text), 1, 4))
            || '-' || upper(substr(md5(gen_random_uuid()::text), 1, 4)));
        ALTER TABLE estate_beneficiaries ALTER COLUMN certificate_no SET NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS estate_beneficiaries_certificate_no_key
            ON estate_beneficiaries (certificate_no);

        CREATE TABLE IF NOT EXISTS estate_claims (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            reference TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitted'
                CHECK (status IN ('submitted', 'in_review', 'needs_info', 'approved', 'rejected')),
            reason TEXT NOT NULL CHECK (reason IN ('death', 'incapacity', 'other')),
            -- the person claiming
            claimant_name TEXT NOT NULL,
            claimant_email TEXT NOT NULL,
            claimant_phone TEXT,
            claimant_country TEXT NOT NULL,
            claimant_id_type TEXT,
            claimant_id_number TEXT,
            relationship TEXT,
            claimant_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            -- the account the claim is about, as the claimant wrote it
            holder_name TEXT NOT NULL,
            holder_email TEXT,
            certificate_no TEXT,
            date_of_death DATE,
            details TEXT,
            -- [{kind, key, filename, content_type, size, by}] in object storage (never public)
            documents JSONB NOT NULL DEFAULT '[]'::jsonb,
            -- what it was matched to
            subject_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            beneficiary_id UUID REFERENCES estate_beneficiaries(id) ON DELETE SET NULL,
            estate_event_id UUID REFERENCES estate_events(id) ON DELETE SET NULL,
            -- the last message staff sent the claimant, and the decision
            admin_note TEXT,
            decided_by UUID REFERENCES users(id) ON DELETE SET NULL,
            decided_at TIMESTAMPTZ,
            ip TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS estate_claims_reference_key
            ON estate_claims (reference);
        CREATE INDEX IF NOT EXISTS estate_claims_review_idx
            ON estate_claims (status, created_at DESC);
        CREATE INDEX IF NOT EXISTS estate_claims_claimant_email_idx
            ON estate_claims (lower(claimant_email), created_at DESC);
        CREATE INDEX IF NOT EXISTS estate_claims_claimant_user_idx
            ON estate_claims (claimant_user_id) WHERE claimant_user_id IS NOT NULL;

        ALTER TABLE estate_events
            ADD COLUMN IF NOT EXISTS claim_id UUID REFERENCES estate_claims(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS reason TEXT NOT NULL DEFAULT 'death',
            ADD COLUMN IF NOT EXISTS date_of_death DATE;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE estate_events
            DROP COLUMN IF EXISTS date_of_death,
            DROP COLUMN IF EXISTS reason,
            DROP COLUMN IF EXISTS claim_id;
        DROP TABLE IF EXISTS estate_claims;
        DROP INDEX IF EXISTS estate_beneficiaries_certificate_no_key;
        ALTER TABLE estate_beneficiaries
            DROP COLUMN IF EXISTS id_documents,
            DROP COLUMN IF EXISTS version,
            DROP COLUMN IF EXISTS certificate_no;
        ALTER TABLE family_members DROP COLUMN IF EXISTS pending_returns;
        ALTER TABLE ownership_ledger DROP COLUMN IF EXISTS ref_id;
        """
    )
