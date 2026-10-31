#!/usr/bin/env bash
# Capimax PropShare — release the client's Capimax BRX parity batch (2026-10-28):
#   * investment certificates carry a QR code; scanning it opens /verify/{code}, which shows
#     whether the certificate is authentic and current (migration 0038);
#   * the Verification Center verifies certificates by QR here (CIM Global Financial stays for
#     valuation and financial documents only), with a form for the code beside the QR;
#   * Admin -> Messages to users: write to one user or to every investor / owner & developer /
#     broker / liquidity provider / everyone, with templates, a review step and a record per
#     recipient; members read them in Messages (/messages) (migration 0039);
#   * Transfers: units or wallet balance to another person by email, TR- numbers, held at once,
#     30 days to be received, Admin -> Transfers desk; pending gifts can be cancelled and come
#     back after 30 days (migration 0040);
#   * the broker's commission is a percentage of the investment: a general rate (1.5%) and a
#     rate per property in the Listing Editor; on a plan it follows each payment (migration 0041);
#   * the site in English, Arabic (right-to-left) and French, from the language menu.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_brx_parity.sh
#
# In order (safe to run again):
#   1. preflight: layout, clean git tree, the new code on disk, database between 0037 and 0040,
#      the site address the QR codes will carry
#   2. site build, beside the live one (the live site keeps running)
#   3. database: migrations 0038-0041 (new tables, one new wallet movement type, a fee setting
#      at 0%, the broker rate); the only setting replaced is the old broker rate
#   4. the API restarts on the new code
#   5. checks: the verify page's API answers without an account, the inbox and transfer routes
#      are there, both new admin desks are staff-only, the scheduled jobs exist
#   6. assistant knowledge base: certificates by QR, transfers and messages (EN + AR, approved as
#      the platform admin)
#   7. new site live
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl
#   restart capimax, previous site back from dist.old-<stamp>. 0038-0041 only add tables,
#   columns, indexes and settings; they can stay, but with the old code the broker rate reads
#   its default (alembic downgrade 0040 restores the old row).
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
DB=capimaxpropshare
SERVICE=capimax
APP_USER=deploy
API_LOCAL=http://127.0.0.1:8000
SITE=${SITE:-https://capimaxpropshare.com}
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@capimaxpropshare.com}
STAMP=$(date -u +%Y%m%d-%H%M%S)

say()  { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
warn() { printf '   \033[33m!!\033[0m  %s\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'die "line $LINENO: $BASH_COMMAND"' ERR

as_app() { sudo -u "$APP_USER" -H "$@"; }
psql_db() { sudo -u postgres psql -d "$DB" -v ON_ERROR_STOP=1 -qtA "$@"; }
rev() { (cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1); }

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] && [ -f "$ENVF" ] && [ -x "$VENV/bin/python" ] || die "unexpected server layout"
for f in alembic/versions/0038_investment_certificates.py alembic/versions/0039_admin_messages.py \
         alembic/versions/0040_transfers.py alembic/versions/0041_broker_commission_per_property.py \
         app/admin_messages.py app/admin_transfers.py \
         app/api/routes/certificates.py; do
  [ -f "$BE/$f" ] || die "the new code is not here ($f): run 'sudo -u deploy git pull' first"
done
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(rev)
case "$REV" in
  0037|0038|0039|0040|0041) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0037 before this release)" ;;
esac
(cd "$BE" && as_app "$VENV/bin/python" -c "import segno") || die "segno is missing from the venv (it draws the QR codes): $VENV/bin/pip install segno"
BASE=$(cd "$BE" && as_app "$VENV/bin/python" -c "from app.core.config import get_settings; print(get_settings().app_base_url.rstrip('/'))")
[ "$BASE" = "$SITE" ] || die "APP_BASE_URL is '$BASE': every certificate's QR code would open that address. Set APP_BASE_URL=$SITE in $ENVF first"
ok "QR codes will open $BASE/verify/..."
PENDING=$(psql_db -c "SELECT count(*) FROM scheduled_gifts WHERE status='pending'")
ok "gifts waiting for their recipient now: $PENDING (from this release they can be cancelled, and come back 30 days after their date)"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
for s in "Verified on Capimax PropShare by QR code" "Messages from the Capimax PropShare team" "Confirm and send" "Commission by Property" "العربية"; do
  grep -rqsF "$s" "$APP"/dist.new/assets/ || die "the build does not carry the new screens ('$s' is missing)"
done
ok "site built (goes live in step 7)"

# ---------------------------------------------------------------------------------------------
say "3. Database"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head) \
  || die "the migrations did not run (see above)"
REV=$(rev)
[ "$REV" = 0041 ] || die "the database is at '$REV' after the upgrade (expected 0041)"
FEE=$(psql_db -c "SELECT value FROM platform_settings WHERE key='transfer_fee_pct'")
RATE=$(psql_db -c "SELECT value FROM platform_settings WHERE key='broker_commission_investment_pct'")
ok "database at 0041 (transfer fee ${FEE:-0}%, general broker commission ${RATE:-?}% of the investment: both in Admin -> Platform Settings)"

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
for r in '/api/v1/certificates/verify/{code}' '/api/v1/investments/certificates' '/api/v1/messages' \
         '/api/v1/transfers' '/api/v1/transfers/quote' '/api/v1/broker/commission-rates'; do
  grep -qF "\"$r\"" <<<"$SPEC" || die "the route $r is missing (journalctl -u $SERVICE -n 80)"
done
ok "verify, inbox and transfer routes are there"
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL/api/v1/certificates/verify/NotARealCode0000000000" || true)
[ "$CODE" = 404 ] && ok "an unknown certificate code is 'not found', without an account" \
  || die "the verify route answers $CODE for an unknown code (expected 404)"
for p in /admin/messages /admin/messages/new /admin/transfers-desk; do
  LOC=$(curl -s -m 10 -o /dev/null -w '%{http_code} %{redirect_url}' "$API_LOCAL$p" || true)
  case "$LOC" in
    30[27]\ *"/admin/login"*) ok "$p is there, for staff only" ;;
    *) die "$p answers '$LOC' without a session (expected a redirect to /admin/login)" ;;
  esac
done
JOBS=$( { crontab -l 2>/dev/null || true; crontab -u "$APP_USER" -l 2>/dev/null || true; } )
grep -q "admin/gifts/run-due" <<<"$JOBS" \
  && ok "the gifts job is scheduled (it also delivers due transfers and returns unclaimed ones)" \
  || warn "no scheduled job posts to /api/v1/admin/gifts/run-due: scheduled transfers would not go out and unclaimed ones would not come back (plan/VPS_DEPLOY_RUNBOOK.md, the cron section)"
grep -q "notifications/dispatch-emails" <<<"$JOBS" \
  && ok "the email job is scheduled (messages and transfer invitations go out by it)" \
  || warn "no scheduled job posts to /api/v1/admin/notifications/dispatch-emails: emails would wait"

# ---------------------------------------------------------------------------------------------
say "6. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
latest() {
  psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.slug='$1' AND a.status='approved' AND a.body_md LIKE '%$2%' AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)"
}
[ "$(latest transfers-and-messages TR-)" -ge 2 ] && ok "transfers and messages article approved, EN + AR" \
  || warn "the transfers and messages article is not approved in both languages; run this script again"
[ "$(latest developers-and-verification-center QR)" -ge 2 ] && ok "verification article explains the QR code, EN + AR" \
  || warn "the verification article does not explain the QR code yet in both languages; run this script again"

# ---------------------------------------------------------------------------------------------
say "7. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   Certificates: Dashboard -> Certificates -> PDF: the QR code opens $SITE/verify/<code>;"
echo "   the Verification Center takes the code for anyone who cannot scan it."
echo "   A certificate is issued when it is first downloaded or listed, and a new one when the"
echo "   units change (the old one then reads 'Superseded')."
echo "   Messages: Admin -> Messages to users -> New message -> Review before sending -> Send."
echo "   Transfers: Dashboard -> Transfers (or Wallet -> Transfer). Staff: Admin -> Transfers desk."
echo "   Broker commission: a property's rate in Admin -> Listing Editor; the general rate in"
echo "   Admin -> Platform Settings (broker_commission_investment_pct). Brokers see them in Commissions."
echo "   Languages: the Language menu at the foot of the side menu: EN, AR, FR."
echo "   Open it in a private window, or reload once: a browser that had the site open picks"
echo "   the new version up on its next load."
