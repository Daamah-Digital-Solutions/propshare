#!/usr/bin/env bash
# Capimax PropShare — release the client-feedback fixes on the VPS (payments reflect in the
# platform, owner listing submissions, liquidity-provider wallet and cycle, broker
# "Listings & Referrals").
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_client_feedback.sh
#
# What it does, in order (each step checks first, so a re-run never repeats work):
#   1. preflight: layout, clean git tree, database revision
#   2. database backup (pg_dump) before anything changes
#   3. Python packages (no new ones; kept so a skipped earlier release is caught up)
#   4. database migrations 0030 (owner submission review trail) and 0031 (broker leads)
#   5. assistant knowledge base: the broker article now explains "Listings & Referrals"
#      (only changed articles get a new version, approved as the platform admin)
#   6. scheduled job: settle card payments whose webhook never arrived (every 5 minutes)
#   7. site build
#   8. restart, then checks: API up, the new reconcile endpoint answers, and one run of it
#      settles the payments already stuck (the client's test payments of the last 7 days)
#
# Rollback: the schema changes only ADD a table and columns, so the previous code runs on it.
#   sudo -u deploy git -C /opt/capimax/app checkout <previous commit> && systemctl restart capimax
#   and rebuild the site. The pre-release dump from step 2 restores everything else.
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
env_get() { grep -E "^$1=" "$ENVF" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
psql_db() { sudo -u postgres psql -d "$DB" -v ON_ERROR_STOP=1 -qtA "$@"; }

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] && [ -f "$ENVF" ] && [ -x "$VENV/bin/python" ] || die "unexpected server layout"
[ -f "$BE/alembic/versions/0031_broker_leads.py" ] || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
case "$REV" in
  0029|0030|0031) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0029: run release_assistant.sh first)" ;;
esac
CRON_SECRET=$(env_get CRON_SECRET || true)
[ -n "$CRON_SECRET" ] || die "CRON_SECRET is not set in $ENVF"
if [ -z "$(env_get SUPPORT_INBOX_EMAIL || true)" ]; then
  warn "SUPPORT_INBOX_EMAIL is empty: owner submissions and broker leads will reach admins in-app only"
fi

# ---------------------------------------------------------------------------------------------
say "2. Database backup"
mkdir -p "$BACKUPS"; chmod 700 "$BACKUPS"
DUMP=$BACKUPS/pre-client-feedback-$STAMP.dump
sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
chmod 600 "$DUMP"
TABLES=$(pg_restore -l "$DUMP" | grep -c ' TABLE ' || true)
[ "$TABLES" -gt 20 ] || die "the backup looks incomplete ($TABLES tables)"
ok "$DUMP ($TABLES tables, $(du -h "$DUMP" | cut -f1))"

# ---------------------------------------------------------------------------------------------
say "3. Python packages"
VENV_OWNER=$(stat -c %U "$VENV")
sudo -u "$VENV_OWNER" -H "$VENV/bin/pip" install -q -e "$BE"
find "$BE" -maxdepth 1 -name '*.egg-info' -exec chown -R "$APP_USER": {} + 2>/dev/null || true
ok "packages up to date"

# ---------------------------------------------------------------------------------------------
say "4. Database migrations"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head)
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0031 ] || die "database is at '$REV' after the upgrade, expected 0031"
ok "database at 0031 (owner submission review trail, broker leads)"

# ---------------------------------------------------------------------------------------------
say "5. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
ok "knowledge base up to date (approved as $ADMIN_EMAIL)"

# ---------------------------------------------------------------------------------------------
say "6. Scheduled job: settle card payments whose webhook never arrived"
CURRENT=$(crontab -u "$APP_USER" -l 2>/dev/null || true)
JOB_PATH=/api/v1/payments/maintenance/reconcile
if grep -q "$JOB_PATH" <<<"$CURRENT"; then
  ok "$JOB_PATH already scheduled"
else
  NEW=$CURRENT$'\n'"*/5 * * * * curl -fsS -m 300 -X POST -H 'X-Cron-Secret: $CRON_SECRET' $API_LOCAL$JOB_PATH >/dev/null 2>&1"
  printf '%s\n' "$NEW" | sed '/^$/d' | crontab -u "$APP_USER" -
  ok "$JOB_PATH scheduled every 5 minutes"
fi

# ---------------------------------------------------------------------------------------------
say "7. Site build"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
# built beside the live site and swapped in after the restart: the site never has a half-empty
# dist/, and the new pages only appear once the new API is up
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
ls "$APP"/dist.new/assets/*.js >/dev/null 2>&1 || die "the build produced no scripts"
ok "site built (goes live after the restart)"

# ---------------------------------------------------------------------------------------------
say "8. Restart and checks"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "API is up"

if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

# one run now: settles card payments that were paid but never credited (last 7 days)
RESULT=$(curl -fsS -m 300 -X POST -H "X-Cron-Secret: $CRON_SECRET" "$API_LOCAL$JOB_PATH" || true)
grep -q '"checked"' <<<"$RESULT" || die "the payment reconcile did not answer: $RESULT (journalctl -u $SERVICE -n 80)"
ok "payment reconcile ran: $RESULT"
STUCK=$(psql_db -c "SELECT count(*) FROM payments WHERE status='pending' AND provider IN ('stripe','nowpayments') AND created_at < now() - interval '10 minutes';" || echo "?")
if [ "$STUCK" != "0" ]; then
  warn "$STUCK card/crypto payment(s) still pending (never paid, card ones older than 7 days, or"
  warn "crypto): open /admin -> Payments, sort by Status; for a card payment the member paid use"
  warn "'Check with provider'; for crypto check the payment in the NOWPayments dashboard."
else
  ok "no card/crypto payment left pending"
fi

say "Done"
echo "   New in the admin panel: Owner Submissions, Property Owners, Broker Leads, and Payments"
echo "   (every deposit and purchase, with 'Check with provider')."
echo "   In Stripe -> Developers -> Webhooks -> your deposits endpoint, also tick the event"
echo "   checkout.session.async_payment_succeeded (needed only for delayed payment methods)."
echo "   Pre-release backup: $DUMP"
