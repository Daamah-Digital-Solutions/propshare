#!/usr/bin/env bash
# Capimax PropShare — release manual withdrawals beside the automatic ones (owner brief,
# 2026-10-20). A member asks for a withdrawal to a saved bank account or crypto wallet; the
# amount is held at once; the team pays it by hand and closes it on Admin -> Withdrawals desk
# (Mark as processing / PAID with the transfer number / FAILED with the reason, the amount
# back in the wallet once). A member linked to Stripe chooses Automatic (ticked first) or
# Manual; everyone else withdraws manually. Every wallet movement has a numbered PDF receipt.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_manual_withdrawals.sh
#
# In order (safe to run again):
#   1. preflight: layout, clean git tree, the new code on disk, database at 0036 or 0037
#   2. site build, beside the live one (the live site keeps running)
#   3. database: migration 0037 (withdrawal numbers, destination text, transfer number, one
#      refund per withdrawal). It stops by itself, changing nothing, if a withdrawal was ever
#      refunded twice.
#   4. the API restarts on the new code
#   5. checks: the receipt route, the desk is staff-only, the numbers were given
#   6. assistant knowledge base: the wallet article explains manual / automatic, the WD-
#      number and the receipts (EN + AR; approved as the platform admin)
#   7. new site live
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl
#   restart capimax, previous site back from dist.old-<stamp>. 0037 only adds columns and
#   indexes; it can stay.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
DB=capimaxpropshare
SERVICE=capimax
APP_USER=deploy
API_LOCAL=http://127.0.0.1:8000
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@capimaxpropshare.com}
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
[ -f "$BE/alembic/versions/0037_manual_withdrawals.py" ] && [ -f "$BE/app/admin_withdrawals.py" ] \
  || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
case "$REV" in
  0036|0037) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0036 before this release)" ;;
esac
WAITING=$(psql_db -c "SELECT count(*) FROM withdrawals WHERE status IN ('pending_review','approved','processing')")
ok "withdrawals in progress right now: $WAITING (they keep working; they get a WD- number too)"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqsF "Manual (saved bank account)" "$APP"/dist.new/assets/ || die "the build does not carry the new withdraw screen"
ok "site built (goes live in step 6)"

# ---------------------------------------------------------------------------------------------
say "3. Database"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head) \
  || die "migration 0037 did not run (see above; the database was not changed)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0037 ] || die "the database is at '$REV' after the upgrade (expected 0037)"
ok "database at 0037"

# ---------------------------------------------------------------------------------------------
say "4. The API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "the API is up on the new code"

# ---------------------------------------------------------------------------------------------
say "5. Checks"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
grep -qF '/api/v1/wallet/transactions/{transaction_id}/receipt' <<<"$SPEC" || die "the receipt route is missing (journalctl -u $SERVICE -n 80)"
ok "receipts are there"
LOC=$(curl -s -m 10 -o /dev/null -w '%{http_code} %{redirect_url}' "$API_LOCAL/admin/withdrawals-desk" || true)
case "$LOC" in
  30[27]\ *"/admin/login"*) ok "the Withdrawals desk is there, for staff only" ;;
  *) die "the desk answers '$LOC' without a session (expected a redirect to /admin/login)" ;;
esac
NONUM=$(psql_db -c "SELECT count(*) FROM withdrawals WHERE reference IS NULL")
[ "${NONUM:-1}" = 0 ] && ok "every withdrawal has its WD- number" || warn "$NONUM withdrawal(s) without a number"

# ---------------------------------------------------------------------------------------------
say "6. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
KB=$(psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.slug='wallet-deposits-withdrawals' AND a.status='approved' AND a.body_md LIKE '%WD-%' AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)")
if [ "${KB:-0}" -ge 2 ]; then
  ok "knowledge base up to date, EN + AR (approved as $ADMIN_EMAIL)"
else
  warn "the approved wallet article does not explain manual withdrawals yet (EN + AR found: ${KB:-0}); run this script again"
fi

# ---------------------------------------------------------------------------------------------
say "7. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   Members: Wallet -> Withdraw -> Bank or Crypto -> a saved account -> the amount is held"
echo "   and the team is told. Linked to Stripe: Automatic (ticked first) or Manual."
echo "   Staff: Admin -> Withdrawals desk -> the request -> Mark as processing / PAID / FAILED."
echo "   Every wallet movement: the download icon gives its numbered PDF receipt."
echo "   Open it in a private window, or reload once: a browser that had the site open picks"
echo "   the new version up on its next load."
