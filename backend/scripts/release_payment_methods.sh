#!/usr/bin/env bash
# Capimax PropShare — release "the same payment methods on every property" on the VPS: wallet,
# card / Apple Pay / Google Pay, crypto, Pronova and Nova Sukuk, for a purchase and for an
# installment plan's down payment (client feedback 2026-09-27, the Capimax BRX concept).
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_payment_methods.sh
#
# What it does, in order (each step checks first, so a re-run never repeats work):
#   1. preflight: layout, clean git tree, database revision
#   2. Python packages (no new ones; kept so a skipped earlier release is caught up)
#   3. site build, beside the live one (while the current API still serves)
#   4. database backup (pg_dump) before anything changes
#   5. API stopped for the migration (under a minute): 0032 adds columns and one table, and
#      counts card / crypto / Pronova purchases in the buyers' invested totals — with the old
#      API stopped, no purchase confirmed meanwhile can be missed — then started on the new code
#   6. assistant knowledge base: the payment methods in "Getting started" and "Installment
#      plans" (EN + AR; only changed articles get a new version, approved as the platform admin)
#   7. scheduled job: the reservation sweep (it now also releases unpaid down payments)
#   8. new site live, then checks: API up, and the payment methods every property offers
#
# Rollback, only while no plan waits for a down payment or a Nova review and no Nova certificate
# is pending or pledged (the 0032 downgrade refuses otherwise — the previous code knows neither):
#   cd /opt/capimax/app/backend && sudo -u deploy /opt/capimax/venv/bin/alembic downgrade 0031
#   sudo -u deploy git -C /opt/capimax/app checkout <previous commit> && systemctl restart capimax
#   and rebuild the site. The pre-release dump from step 4 restores everything else.
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
[ -f "$BE/alembic/versions/0032_payment_methods.py" ] || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
case "$REV" in
  0031|0032) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0031: run release_client_feedback.sh first)" ;;
esac
CRON_SECRET=$(env_get CRON_SECRET || true)
[ -n "$CRON_SECRET" ] || die "CRON_SECRET is not set in $ENVF"
if [ -z "$(env_get SUPPORT_INBOX_EMAIL || true)" ]; then
  warn "SUPPORT_INBOX_EMAIL is empty: new Nova Sukuk certificates reach admins in-app only"
fi

# ---------------------------------------------------------------------------------------------
say "2. Python packages"
VENV_OWNER=$(stat -c %U "$VENV")
sudo -u "$VENV_OWNER" -H "$VENV/bin/pip" install -q -e "$BE"
find "$BE" -maxdepth 1 -name '*.egg-info' -exec chown -R "$APP_USER": {} + 2>/dev/null || true
ok "packages up to date"

# ---------------------------------------------------------------------------------------------
say "3. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
# built beside the live site and swapped in once the new API is up: the site never has a
# half-empty dist/, and the new pages only appear with the API that serves them
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
ls "$APP"/dist.new/assets/*.js >/dev/null 2>&1 || die "the build produced no scripts"
ok "site built (goes live after the migration)"

# ---------------------------------------------------------------------------------------------
say "4. Database backup"
mkdir -p "$BACKUPS"; chmod 700 "$BACKUPS"
DUMP=$BACKUPS/pre-payment-methods-$STAMP.dump
sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
chmod 600 "$DUMP"
TABLES=$(pg_restore -l "$DUMP" | grep -c ' TABLE ' || true)
[ "$TABLES" -gt 20 ] || die "the backup looks incomplete ($TABLES tables)"
ok "$DUMP ($TABLES tables, $(du -h "$DUMP" | cut -f1))"

# ---------------------------------------------------------------------------------------------
say "5. Database migration (API stopped for it)"
# stopped: a purchase the old code confirmed after the migration counted the invested totals
# would be counted by neither it nor the new code. Payment webhooks meanwhile get a 502 and
# the provider retries them; the reconcile job settles the rest.
systemctl stop "$SERVICE"
if ! (cd "$BE" && as_app "$VENV/bin/alembic" upgrade head); then
  systemctl start "$SERVICE" || true
  die "the migration failed (the API was started again on the old code)"
fi
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
systemctl start "$SERVICE"
[ "$REV" = 0032 ] || die "database is at '$REV' after the upgrade, expected 0032"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "database at 0032 and the API is up on the new code"

# ---------------------------------------------------------------------------------------------
say "6. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
ok "knowledge base up to date (approved as $ADMIN_EMAIL)"

# ---------------------------------------------------------------------------------------------
say "7. Scheduled job: release reservations nobody paid"
CURRENT=$(crontab -u "$APP_USER" -l 2>/dev/null || true)
JOB_PATH=/api/v1/investments/maintenance/expire-reservations
if grep -q "$JOB_PATH" <<<"$CURRENT"; then
  ok "$JOB_PATH already scheduled (it now also releases unpaid installment down payments)"
else
  NEW=$CURRENT$'\n'"*/5 * * * * curl -fsS -m 120 -X POST -H 'X-Cron-Secret: $CRON_SECRET' $API_LOCAL$JOB_PATH >/dev/null 2>&1"
  printf '%s\n' "$NEW" | sed '/^$/d' | crontab -u "$APP_USER" -
  ok "$JOB_PATH scheduled every 5 minutes"
fi

# ---------------------------------------------------------------------------------------------
say "8. New site live, and checks"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

OPTIONS=$(curl -fsS -m 10 "$API_LOCAL/api/v1/investments/payment-options" || true)
grep -q '"sukuk"' <<<"$OPTIONS" || die "the payment methods did not answer: $OPTIONS (journalctl -u $SERVICE -n 80)"
ok "payment methods on every property: $OPTIONS"
for rail in card crypto; do
  if ! grep -q "\"$rail\":true" <<<"$OPTIONS"; then
    warn "$rail shows as 'not available' on the property pages: its provider keys are not set"
  fi
done

say "Done"
echo "   Every property now offers: wallet, card, Apple Pay, Google Pay, crypto, Pronova, Nova Sukuk"
echo "   — for a purchase and for an installment plan's down payment."
echo "   New in the admin panel: Nova Sukuk (review certificates: approve, reject with a reason,"
echo "   release the Nova Finance pledge)."
echo "   Pre-release backup: $DUMP"
