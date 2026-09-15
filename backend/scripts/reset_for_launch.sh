#!/usr/bin/env bash
# =============================================================================
# Capimax PropShare — LAUNCH RESET: wipe TEST-phase transactional data before real customers.
#
#   DRY RUN (default, read-only):   ./reset_for_launch.sh
#   EXECUTE (destructive):          CONFIRM=capimaxpropshare ./reset_for_launch.sh --execute
#   also drop the demo properties:  CONFIRM=capimaxpropshare ./reset_for_launch.sh --execute --drop-demo-properties
#   keep the audit trail:           ... --keep-audit
#
# What it does (one transaction — any failure rolls EVERYTHING back):
#   1. Runs a full backup first (/usr/local/bin/capimax_backup.sh) — always.
#   2. Deletes TEST users (email patterns below) and everything owned by them.
#   3. Truncates ALL money / ownership / activity tables (payments, investments, ledger,
#      installments, distributions, secondary market, gifts, LP, family transfers, broker
#      commissions, withdrawals, notifications, outbox, developer updates, estate events).
#   4. Zeroes every remaining wallet (test balances are NOT real money).
#   5. Resets every property's funding counters (funded 0, investors 0, all units available).
#   6. Optionally deletes the demo properties (slug 'demo-%') + their documents/milestones.
#
# FKs into users from properties.owner_id / property_milestones.created_by / users.referred_by
# are ON DELETE SET NULL, so deleting test users never blocks (verified against prod schema).
#
# What it KEEPS: real users + roles + KYC status + profiles + preferences, platform_settings,
# platform_bank_accounts, lp_pool_tiers, non-demo properties + their documents, saved payout
# methods of real users. Uploaded files of deleted rows stay on disk under /opt/capimax/storage.
#
# Run on the VPS as root. Never run against a DB you have not just backed up.
# =============================================================================
set -euo pipefail

DB="capimaxpropshare"
MODE="dry-run"; DROP_DEMO=0; KEEP_AUDIT=0
for a in "$@"; do
  case "$a" in
    --execute) MODE="execute" ;;
    --drop-demo-properties) DROP_DEMO=1 ;;
    --keep-audit) KEEP_AUDIT=1 ;;
    *) echo "unknown arg: $a"; exit 2 ;;
  esac
done

# Test accounts created during the build/QA phase (see prod-deployment notes).
TEST_USER_WHERE="email ~ '^(sec-|gift-|lp-|fam-|broker-|dist-|brk-|in-|noapp|methods@|livegate@)' OR email LIKE '%@x.com' OR email LIKE '%@dep.com'"
DEMO_WHERE="slug LIKE 'demo-%' OR title ILIKE 'Sample%'"

Q(){ sudo -u postgres psql -d "$DB" -v ON_ERROR_STOP=1 -tAc "$1"; }

echo "== Capimax launch reset — mode: $MODE  drop_demo=$DROP_DEMO  keep_audit=$KEEP_AUDIT =="
echo
echo "-- Test users that will be DELETED:"
Q "SELECT '   ' || email FROM users WHERE $TEST_USER_WHERE ORDER BY email"
echo "-- Demo properties $( [ $DROP_DEMO = 1 ] && echo 'that will be DELETED' || echo '(kept; counters reset — pass --drop-demo-properties to delete)'):"
Q "SELECT '   ' || coalesce(slug,'?') || '  ' || title FROM properties WHERE $DEMO_WHERE ORDER BY slug"
echo
echo "-- Rows to be wiped:"
for t in payments payment_events transactions investments ownership_ledger installment_plans \
         installment_payments distributions distribution_items secondary_listings secondary_trades \
         scheduled_gifts lp_exit_requests lp_positions family_transfers family_return_allocations \
         broker_referrals broker_commissions withdrawals payout_events notifications email_outbox \
         developer_updates developer_update_recipients estate_events estate_transfers kyc_webhook_events; do
  printf "   %-30s %s\n" "$t" "$(Q "SELECT count(*) FROM $t")"
done
[ $KEEP_AUDIT = 1 ] || printf "   %-30s %s\n" audit_log "$(Q "SELECT count(*) FROM audit_log")"
echo "   wallets to zero:               $(Q "SELECT count(*) FROM wallets WHERE balance<>0 OR pending_balance<>0 OR total_invested<>0 OR total_returns<>0")  (sum balance = \$$(Q "SELECT coalesce(sum(balance),0) FROM wallets"))"
echo

if [ "$MODE" != "execute" ]; then
  echo "DRY RUN — nothing changed. Re-run with:  CONFIRM=$DB $0 --execute [--drop-demo-properties] [--keep-audit]"
  exit 0
fi
if [ "${CONFIRM:-}" != "$DB" ]; then
  echo "REFUSED: set CONFIRM=$DB to execute."; exit 3
fi

echo "== 1) backup first =="
/usr/local/bin/capimax_backup.sh && tail -1 /var/log/capimax-backup.log

echo "== 2) reset (single transaction) =="
sudo -u postgres psql -d "$DB" -v ON_ERROR_STOP=1 <<SQL
BEGIN;

-- activity / money / ownership
TRUNCATE payments, payment_events, transactions, investments, ownership_ledger,
         installment_plans, installment_payments, distributions, distribution_items,
         secondary_listings, secondary_trades, scheduled_gifts, lp_exit_requests, lp_positions,
         family_transfers, family_return_allocations, broker_referrals, broker_commissions,
         withdrawals, payout_events, notifications, email_outbox, developer_updates,
         developer_update_recipients, estate_events, estate_transfers, kyc_webhook_events
  RESTART IDENTITY CASCADE;
$( [ $KEEP_AUDIT = 1 ] || echo "TRUNCATE audit_log RESTART IDENTITY;" )

-- test users (and everything hanging off them)
CREATE TEMP TABLE _tu AS SELECT id FROM users WHERE $TEST_USER_WHERE;
DELETE FROM saved_payment_methods   WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM payment_customers       WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM user_bank_accounts      WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM user_crypto_wallets     WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM connect_accounts        WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM broker_codes            WHERE broker_id IN (SELECT id FROM _tu);
DELETE FROM estate_beneficiaries    WHERE owner_id IN (SELECT id FROM _tu) OR beneficiary_user_id IN (SELECT id FROM _tu);
DELETE FROM family_member_bank_accounts WHERE member_id IN (SELECT id FROM family_members WHERE user_id IN (SELECT id FROM _tu) OR family_group_id IN (SELECT id FROM family_groups WHERE owner_id IN (SELECT id FROM _tu)));
DELETE FROM family_members          WHERE user_id IN (SELECT id FROM _tu) OR family_group_id IN (SELECT id FROM family_groups WHERE owner_id IN (SELECT id FROM _tu));
DELETE FROM family_groups           WHERE owner_id IN (SELECT id FROM _tu);
DELETE FROM role_grant_requests     WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM notification_preferences WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM kyc_verifications       WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM wallets                 WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM user_roles              WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM profiles                WHERE id IN (SELECT id FROM _tu);  -- profiles.id == users.id
DELETE FROM oauth_identities        WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM refresh_tokens          WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM email_tokens            WHERE user_id IN (SELECT id FROM _tu);
DELETE FROM users                   WHERE id IN (SELECT id FROM _tu);

-- every remaining wallet: test balances are not real money
UPDATE wallets SET balance = 0, pending_balance = 0, total_invested = 0, total_returns = 0;

-- property funding counters back to a fresh offering
UPDATE properties SET funded_amount = 0, investors_count = 0, available_units = total_units,
       status = CASE WHEN status = 'funded' THEN 'active' ELSE status END;

$( [ $DROP_DEMO = 1 ] && cat <<DEMO
-- demo properties
CREATE TEMP TABLE _dp AS SELECT id FROM properties WHERE $DEMO_WHERE;
DELETE FROM documents           WHERE property_id IN (SELECT id FROM _dp);
DELETE FROM property_milestones WHERE property_id IN (SELECT id FROM _dp);
DELETE FROM properties          WHERE id IN (SELECT id FROM _dp);
DEMO
)

COMMIT;
SQL

echo "== 3) after =="
echo "   users: $(Q "SELECT count(*) FROM users")   properties: $(Q "SELECT count(*) FROM properties")   investments: $(Q "SELECT count(*) FROM investments")   payments: $(Q "SELECT count(*) FROM payments")   wallet sum: \$$(Q "SELECT coalesce(sum(balance),0) FROM wallets")"
echo "DONE. Backup of the pre-reset state is in /opt/capimax/backups."
