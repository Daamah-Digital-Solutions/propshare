#!/usr/bin/env bash
# Capimax PropShare — release the client's letter of 2026-11-18, the market fees sheet and the
# technical updates of 2026-11-19 (PropShare part):
#   * property page: number of units, Investment Model, Investment Strategy, Due Diligence tab
#     (valuation, insurance, legal review and their documents), documents by category, Arabic
#     that reads from the right, "(5yr)" gone from Est. Total Return;
#   * dashboard: change since purchase, Transfer on each holding; cards "Coming soon · Join the
#     Waitlist" (migration 0048);
#   * certificates: share of the named SPV, issued at purchase, FINAL / PROVISIONAL (0047);
#   * admin: Listing Editor (due diligence cards, row tables, BRX-like uploads with names in three
#     languages, a valuation that can set the unit price, a full-screen description box), saved
#     developers in every language (0044, 0046), document issuer and date (0043), the quarterly
#     valuation reminder, Developers and Card waitlist pages;
#   * market fees (0045): seller 0.5% / buyer 1.5% on secondary sales; liquidity market seller
#     1.5% with a 0.5% share to the provider; the liquidity discount at 0;
#   * the verification page no longer lists blockchain records.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_client_letter.sh
#
# In order (safe to run again):
#   1. preflight: layout, clean tree, the new code on disk, database between 0042 and 0048
#   2. database backup (pg_dump) before anything changes
#   3. site build, beside the live one (the live site keeps running)
#   4. database: migrations 0043-0048 (only additions; the fee rates move only where they still
#      hold the old defaults)
#   5. the API restarts on the new code
#   6. checks: new routes, staff-only admin pages, the fee rates, the hourly job that also sends
#      the valuation reminders
#   7. assistant knowledge base: the fees article (EN + AR), approved as the platform admin
#   8. new site live
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout 9343f6e, systemctl restart capimax,
#   previous site back from dist.old-<stamp>; the database from the backup of step 2 if needed
#   (0043-0048 only add tables, columns and settings).
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
DB=capimaxpropshare
SERVICE=capimax
APP_USER=deploy
API_LOCAL=http://127.0.0.1:8000
BACKUPS=/opt/capimax/backups
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
setting() { psql_db -c "SELECT value FROM platform_settings WHERE key='$1'"; }

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] && [ -f "$ENVF" ] && [ -x "$VENV/bin/python" ] || die "unexpected server layout"
for f in alembic/versions/0043_document_issuer_date.py alembic/versions/0044_saved_developers.py \
         alembic/versions/0045_market_fees.py alembic/versions/0046_saved_developer_versions.py \
         alembic/versions/0047_certificate_payment_status.py alembic/versions/0048_card_waitlist.py \
         app/admin_developers.py app/admin_cards.py app/services/market_fees.py \
         app/services/valuation_service.py app/services/certificate_auto.py app/api/routes/cards.py; do
  [ -f "$BE/$f" ] || die "the new code is not here ($f): run 'sudo -u deploy git pull' first"
done
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(rev)
case "$REV" in
  0042|0043|0044|0045|0046|0047|0048) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0042 before this release)" ;;
esac

# ---------------------------------------------------------------------------------------------
say "2. Database backup"
mkdir -p "$BACKUPS" && chmod 700 "$BACKUPS"
DUMP="$BACKUPS/pre-client-letter-$STAMP.dump"
sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
[ -s "$DUMP" ] || die "the backup is empty"
ok "backup $DUMP ($(du -h "$DUMP" | cut -f1))"

# ---------------------------------------------------------------------------------------------
say "3. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
for s in "Investment Strategy" "Coming soon · Join the Waitlist" "FINAL · FULLY PAID" \
         "Due Diligence" "Est. Total Return" "استراتيجية الاستثمار"; do
  grep -rqsF "$s" "$APP"/dist.new/assets/ || die "the build does not carry the new screens ('$s' is missing)"
done
ok "site built (goes live in step 8)"

# ---------------------------------------------------------------------------------------------
say "4. Database"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head) || die "the migrations did not run (see above)"
REV=$(rev)
[ "$REV" = 0048 ] || die "the database is at '$REV' after the upgrade (expected 0048)"
ok "database at 0048"
ok "secondary sale: buyer $(setting secondary_resale_fee_pct)%, seller $(setting secondary_seller_fee_pct)%"
ok "liquidity market: seller $(setting liquidity_fee_pct)%, provider's share $(setting lp_fee_share_pct)%, discount $(setting liquidity_discount_pct)%"
ok "saved developers: $(psql_db -c "SELECT count(*) FROM saved_developers") (from the listings), $(psql_db -c "SELECT count(*) FROM saved_developers WHERE versions <> '{}'::jsonb") with Arabic or French text"
[ "$(setting secondary_resale_fee_pct)" = 1.5 ] || warn "the buyer's fee is not 1.5%: it had been changed by hand before, so it was left as it was (Admin -> Platform Settings)"
[ "$(setting liquidity_discount_pct)" = 0 ] || warn "the liquidity discount is not 0: it had been changed by hand before, so it was left as it was (Admin -> Platform Settings)"

# ---------------------------------------------------------------------------------------------
say "5. The API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "the API is up on the new code"

# ---------------------------------------------------------------------------------------------
say "6. Checks"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
for r in '/api/v1/cards/waitlist' '/api/v1/certificates/verify/{code}' '/api/v1/secondary/settings'; do
  grep -qF "\"$r\"" <<<"$SPEC" || die "the route $r is missing (journalctl -u $SERVICE -n 80)"
done
ok "the new routes are there"
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL/api/v1/cards/waitlist" || true)
[ "$CODE" = 401 ] && ok "the card waitlist needs an account" || die "the card waitlist answers $CODE without an account (expected 401)"
for p in /admin/developers /admin/card-waitlist; do
  LOC=$(curl -s -m 10 -o /dev/null -w '%{http_code} %{redirect_url}' "$API_LOCAL$p" || true)
  case "$LOC" in
    30[27]\ *"/admin/login"*) ok "$p is there, for staff only" ;;
    *) die "$p answers '$LOC' without a session (expected a redirect to /admin/login)" ;;
  esac
done
JOBS=$( { crontab -l 2>/dev/null || true; crontab -u "$APP_USER" -l 2>/dev/null || true; } )
grep -q "admin/installments/run-due" <<<"$JOBS" \
  && ok "the hourly installments job is scheduled (it also reminds the admins of quarterly valuations)" \
  || warn "no scheduled job posts to /api/v1/admin/installments/run-due: installments and the valuation reminders would not run"
grep -q "notifications/dispatch-emails" <<<"$JOBS" \
  && ok "the email job is scheduled" || warn "no scheduled job posts to /api/v1/admin/notifications/dispatch-emails: emails would wait"
DUE=$(cd "$BE" && as_app "$VENV/bin/python" -c "
import asyncio
from app.core.db import session_scope
from app.services import valuation_service
async def main():
    async with session_scope() as s:
        print(len(await valuation_service.due_listings(s)))
asyncio.run(main())")
ok "under-construction listings due a quarterly valuation now: $DUE (Admin -> Listings shows them)"

# ---------------------------------------------------------------------------------------------
say "7. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
latest() {
  psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.slug='fees-overview' AND a.lang='$1' AND a.status='approved' AND a.body_md LIKE '%$2%' AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)"
}
[ "$(latest en 'share of the fee the other side pays')" -ge 1 ] && ok "fees article approved (EN)" \
  || warn "the English fees article is not the approved latest one; run this script again"
[ "$(latest ar 'حصة من الرسوم التي يدفعها الطرف الآخر')" -ge 1 ] && ok "fees article approved (AR)" \
  || warn "the Arabic fees article is not the approved latest one; run this script again"

# ---------------------------------------------------------------------------------------------
say "8. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   Property page: Investment Strategy beside the status, the Due Diligence tab, the units field."
echo "   Admin -> Listing Editor: valuation (with the new unit price), insurance, legal review,"
echo "   documents dropped several at once (names in three languages), Expand on the description."
echo "   Admin -> Developers and Admin -> Card waitlist are new."
echo "   Certificates now read FINAL or PROVISIONAL; a new purchase gets its certificate at once."
echo "   Open the site in a private window, or reload once: a browser that had the site open"
echo "   picks the new version up on its next load."
