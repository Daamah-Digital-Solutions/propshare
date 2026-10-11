#!/usr/bin/env bash
# Capimax PropShare — release what was decided for the open points of the family and estate
# release (2026-10-11, migration 0036):
#   * A confirmed email address. What is sent to a person by email address (a family
#     allocation and its returns, a gift, a beneficiary's share) reaches the account
#     registered with that address only once the account confirmed it. Until now an account
#     opened by anyone with that address received it as soon as its identity was verified.
#     The confirmation link works from inside the account (sign in, then open it); a password
#     reset through the emailed link confirms the address too.
#   * A beneficiary's share covers the holder's wallet balance when the holder ticked Wallet
#     Balance or Full Portfolio for them: the same percentage, moved with the units when the
#     claim is approved.
#   * The holder's account closes when a claim for a death, or for a holder who can no longer
#     manage the account, is approved. Staff close and reopen accounts under Admin -> Users.
#   * The beneficiary form says what its choices do: what the wallet tick adds, and that
#     nothing is ever transferred by itself.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_estate_decisions.sh
#
# What it does, in order:
#   1. preflight: layout, clean git tree, database revision, who is affected
#   2. site build, beside the live one (the live site keeps running)
#   3. database backup (pg_dump) before anything changes
#   4. database migration 0036: three nullable columns on users, one on estate_transfers, one
#      on estate_events and one new transaction kind, so the API keeps running; then the API
#      restarts on the new code
#   5. checks
#   6. assistant knowledge base: the family article and the one on beneficiaries and claims
#      (EN + AR; only changed articles get a new version, approved as the platform admin)
#   7. new site live
# Safe to run again after a stop: the migration and the knowledge base repeat nothing, and the
# backup is taken only while the database is still at 0035.
#
# No new package. What changes for members at once: a confirmation link opened without being
# signed in now asks to sign in first, and an account whose address is not confirmed no
# longer receives what was sent to that address until it confirms it (step 1 says how many).
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl
#   restart capimax and rebuild the site (the previous one stays in dist.old-<stamp>). The
#   database can stay at 0036: the earlier code runs on it, but it does not know a closed
#   account (reopen any closed account first: Admin -> Users) nor a wallet share (prefer
#   restoring the backup of step 3 if a claim with a wallet share was approved in between).
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
BACKUPS=/opt/capimax/backups
DB=capimaxpropshare
SERVICE=capimax
APP_USER=deploy
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@capimaxpropshare.com}
API_LOCAL=http://127.0.0.1:8000
STAMP=$(date -u +%Y%m%d-%H%M%S)

say()  { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
warn() { printf '   \033[33m!!\033[0m  %s\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'die "line $LINENO: $BASH_COMMAND"' ERR

as_app() { sudo -u "$APP_USER" -H "$@"; }
psql_db() { sudo -u postgres psql -d "$DB" -v ON_ERROR_STOP=1 -qtA "$@"; }

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] && [ -f "$ENVF" ] && [ -x "$VENV/bin/python" ] || die "unexpected server layout"
[ -f "$BE/alembic/versions/0036_account_closing_estate_wallet.py" ] \
  && [ -f "$BE/app/services/account_service.py" ] \
  && [ -f "$APP/src/components/account/ConfirmAddressNotice.tsx" ] \
  || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
case "$REV" in
  0035|0036) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0035: run release_family_estate.sh first)" ;;
esac
# who the confirmed-address rule concerns today: accounts that never confirmed their address,
# and how many of them have something waiting that was sent to that address
UNCONFIRMED=$(psql_db -c "SELECT count(*) FROM users WHERE email_verified = false")
WAITING=$(psql_db -c "SELECT count(DISTINCT u.id) FROM users u WHERE u.email_verified = false AND (EXISTS (SELECT 1 FROM family_members m WHERE lower(m.email) = lower(u.email) AND m.user_id IS NULL) OR EXISTS (SELECT 1 FROM scheduled_gifts g WHERE lower(g.recipient_email) = lower(u.email) AND g.recipient_user_id IS NULL AND g.status IN ('scheduled', 'pending')) OR EXISTS (SELECT 1 FROM estate_beneficiaries b WHERE lower(b.email) = lower(u.email) AND b.beneficiary_user_id IS NULL))")
ok "accounts whose email address is not confirmed: ${UNCONFIRMED:-0}; of them, with something sent to that address and not yet tied to the account: ${WAITING:-0}"
if [ "${WAITING:-0}" -gt 0 ]; then
  warn "those ${WAITING} account(s) receive it once they confirm their address (Account Settings sends the link again); the page tells them"
fi

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqs "Sign in to confirm your email address" "$APP"/dist.new/assets/ || die "the build does not carry the new confirmation page"
grep -rqs "Send me the confirmation link" "$APP"/dist.new/assets/ || die "the build does not carry the confirmation link button"
grep -rqs "Nothing is transferred by itself" "$APP"/dist.new/assets/ || die "the build does not carry the beneficiary form's new help"
grep -rqs "Beneficiary transfer" "$APP"/dist.new/assets/ || die "the build does not carry the wallet's new transaction name"
ok "site built (goes live in step 7)"

# ---------------------------------------------------------------------------------------------
say "3. Database backup"
mkdir -p "$BACKUPS"; chmod 700 "$BACKUPS"
if [ "$REV" = 0036 ]; then
  # a second run: the database is already migrated, a dump now would not be "before"
  LAST=$(ls -1t "$BACKUPS"/pre-estate-decisions-*.dump 2>/dev/null | head -1 || true)
  DUMP=${LAST:-"(none found in $BACKUPS)"}
  ok "already migrated: the backup from before this release is $DUMP"
else
  DUMP=$BACKUPS/pre-estate-decisions-$STAMP.dump
  sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
  chmod 600 "$DUMP"
  TABLES=$(pg_restore -l "$DUMP" | grep -c ' TABLE ' || true)
  [ "$TABLES" -gt 20 ] || die "the backup looks incomplete ($TABLES tables)"
  ok "$DUMP ($TABLES tables, $(du -h "$DUMP" | cut -f1))"
fi

# ---------------------------------------------------------------------------------------------
say "4. Database migration, then the API on the new code"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head) || die "the migration failed (nothing changed: the API still runs the old code). If it says 'lock timeout', a long task was using the database: run this script again in a minute"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0036 ] || die "database is at '$REV' after the upgrade, expected 0036"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "database at 0036 and the API is up on the new code"

# ---------------------------------------------------------------------------------------------
say "5. Checks"
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"token":"release-check"}' "$API_LOCAL/api/v1/auth/verify-email" || true)
[ "$CODE" = 401 ] || die "the confirmation link answers HTTP $CODE to a visitor (expected 401: it works from inside the account only)"
ok "a confirmation link does nothing for a visitor (401 without a session)"
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL/admin/user/list" || true)
case "$CODE" in
  200|302|303|307) ok "Admin -> Users is there (HTTP $CODE without a session)" ;;
  *) die "the admin page /admin/user/list answers HTTP $CODE (journalctl -u $SERVICE -n 80)" ;;
esac
KIND=$(psql_db -c "SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'transaction_type' AND e.enumlabel = 'estate_transfer'")
[ "${KIND:-0}" = 1 ] || die "the transaction kind 'estate_transfer' is missing"
COLS=$(psql_db -c "SELECT count(*) FROM information_schema.columns WHERE (table_name = 'users' AND column_name IN ('closed_at', 'closed_reason', 'closed_by')) OR (table_name = 'estate_transfers' AND column_name = 'amount') OR (table_name = 'estate_events' AND column_name = 'wallet_base')")
[ "${COLS:-0}" = 5 ] || die "expected 5 new columns, found ${COLS:-0}"
CLOSED=$(psql_db -c "SELECT count(*) FROM users WHERE closed_at IS NOT NULL")
ok "the new columns and the new transaction kind are there; closed accounts: ${CLOSED:-0}"
# the gate itself, on this server's code and database: a closed account is refused
GATE_CHECK='
from app.core.errors import AppError
from app.models.identity import User
from app.services import account_service
import datetime as dt
closed = User(email="release-check@example.invalid", closed_at=dt.datetime.now(dt.UTC))
try:
    account_service.ensure_open(closed)
except AppError as exc:
    assert exc.code == "ACCOUNT_CLOSED", exc.code
else:
    raise SystemExit("a closed account was let through")
account_service.ensure_open(User(email="release-check@example.invalid"))
print("ok")
'
(cd "$BE" && as_app "$VENV/bin/python" -c "$GATE_CHECK" >/dev/null) \
  || die "the closed-account gate does not answer as expected (see the error above)"
ok "a closed account is refused, an open one is not"
STUCK=$(psql_db -c "SELECT count(*) FROM email_outbox WHERE status='pending' AND created_at < now() - interval '15 minutes'")
if [ "${STUCK:-0}" -gt 0 ]; then
  warn "$STUCK email(s) have been waiting to be sent for more than 15 minutes: the job that sends them is not running"
else
  ok "no email is stuck waiting to be sent"
fi

# ---------------------------------------------------------------------------------------------
say "6. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
SHARE=$(psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.slug='beneficiaries-and-claims' AND a.lang='en' AND a.status='approved' AND a.body_md LIKE '%What a share covers%' AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)")
[ "${SHARE:-0}" -ge 1 ] || die "the approved article on beneficiaries and claims does not say what a share covers; the API is live, the site is not swapped yet: run this script again"
FAMILY=$(psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.slug='family-and-brokers' AND a.lang='en' AND a.status='approved' AND a.body_md LIKE '%Confirming the address matters%' AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)")
[ "${FAMILY:-0}" -ge 1 ] || die "the approved family article does not say that the address must be confirmed"
ok "knowledge base up to date (approved as $ADMIN_EMAIL)"

# ---------------------------------------------------------------------------------------------
say "7. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"
STATUS=$(curl -fsS -m 10 "$API_LOCAL/api/v1/assistant/status" || true)
if grep -q '"model_configured":true' <<<"$STATUS" && grep -q '"encryption":"ok"' <<<"$STATUS"; then
  ok "assistant configured"
else
  warn "the assistant does not report itself ready: $STATUS"
fi

say "Done"
echo "   A confirmed address: units, returns or a gift sent to a person by email address reach"
echo "   the account under that address only once it confirmed the address. The link works"
echo "   from inside the account (sign in, then open it); Account Settings, the Family"
echo "   Investment tab and the claim page send a new one; \"Forgot password\" confirms it too."
echo "   A beneficiary's share: the units, plus the same percentage of the holder's wallet"
echo "   balance when the holder ticked Wallet Balance or Full Portfolio. The claim's page"
echo "   lists what an approval moves, money included."
echo "   The holder's account closes when a claim for a death (or for a holder who can no"
echo "   longer manage the account) is approved. Staff: Admin -> Users -> open the user ->"
echo "   Close account / Reopen account."
echo "   Backup from before this release: $DUMP"
echo "   Previous site: $APP/dist.old-$STAMP"
