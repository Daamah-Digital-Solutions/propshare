#!/usr/bin/env bash
# Capimax PropShare — release "part of an installment plan changes hands" (client, 2026-11-08):
#   * an investor on a running installment plan can sell or send PART of it (one unit, two, any
#     number), and the rest stays theirs: on the secondary market (a buyer can also take part of
#     a listing), to a liquidity provider, or by transfer to another member;
#   * selling 3 units of 10 gives the new holder 30% of everything, as a plan of their own with
#     the same dates: 30% of what was paid (what they pay the seller for, plus or minus the price
#     change) and 30% of every installment still to come; the seller's plan keeps 70% of each;
#     the last payment of each kind takes the rounding, so the two plans add up to the original;
#   * a part changes hands only when no installment of the plan is overdue; selling the whole
#     plan on the secondary market works as before;
#   * the buyer sees the units, what is paid now and the installments taken over before buying;
#     both sides are told; the new plan, its schedule and its PDF are in the new holder's name;
#   * also: every centred dialog sat half off-screen with the site in Arabic (now centred), and
#     the phone menu no longer opens as icons only after the side menu was narrowed.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_plan_parts.sh
#
# In order (safe to run again):
#   1. preflight: layout, clean git tree, the new code on disk, database at 0041 (or 0042)
#   2. database backup (pg_dump) before anything changes
#   3. site build, beside the live one (the live site keeps running)
#   4. database: migration 0042 (columns only: a plan's parent, holder and entry price; the plan
#      of a liquidity request, of a provider's position and of a transfer)
#   5. the API restarts on the new code; checks
#   6. assistant knowledge base: exits, installment plans, trading rules (EN + AR, approved as
#      the platform admin)
#   7. new site live
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl restart
#   capimax, previous site back from dist.old-<stamp>. 0042 only adds columns and widens the
#   transfers checks; it can stay with the old code (plans split meanwhile stay valid plans).
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
BACKUPS=/opt/capimax/backups
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
for f in alembic/versions/0042_plan_parts.py app/tests/test_plan_parts_db.py; do
  [ -f "$BE/$f" ] || die "the new code is not here ($f): run 'sudo -u deploy git pull' first"
done
grep -q "def split_plan" "$BE/app/services/installment_service.py" \
  || die "the new code is not here (split_plan): run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(rev)
case "$REV" in
  0041|0042) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0041 before this release)" ;;
esac
RUNNING=$(psql_db -c "SELECT count(*) FROM installment_plans WHERE status='active'")
ok "running installment plans now: $RUNNING (each can be sold or sent in part from this release)"

# ---------------------------------------------------------------------------------------------
say "2. Database backup"
mkdir -p "$BACKUPS"; chmod 700 "$BACKUPS"
DUMP=$BACKUPS/pre-plan-parts-$STAMP.dump
sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
chmod 600 "$DUMP"
TABLES=$(pg_restore -l "$DUMP" | grep -c ' TABLE ' || true)
[ "$TABLES" -gt 20 ] || die "the backup looks incomplete ($TABLES tables)"
ok "$DUMP ($TABLES tables, $(du -h "$DUMP" | cut -f1))"

# ---------------------------------------------------------------------------------------------
say "3. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
for s in "Units to sell (1–" "Plan units" "Units to fund (1–" "plan-part-schedule"; do
  grep -rqsF "$s" "$APP"/dist.new/assets/ || die "the build does not carry the new screens ('$s' is missing)"
done
ok "site built (goes live in step 7)"

# ---------------------------------------------------------------------------------------------
say "4. Database"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head) \
  || die "the migration did not run (see above)"
REV=$(rev)
[ "$REV" = 0042 ] || die "the database is at '$REV' after the upgrade (expected 0042)"
COLS=$(psql_db -c "SELECT count(*) FROM information_schema.columns WHERE table_name='installment_plans' AND column_name IN ('parent_plan_id','holder_since','entry_price')")
[ "$COLS" = 3 ] || die "installment_plans lacks the new columns ($COLS of 3)"
ok "database at 0042"

# ---------------------------------------------------------------------------------------------
say "5. The API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "the API is up on the new code"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
for r in '/api/v1/secondary/listings/{listing_id}/quote' '/api/v1/liquidity/exit-requests/{request_id}/quote'; do
  grep -qF "\"$r\"" <<<"$SPEC" || die "the route $r is missing (journalctl -u $SERVICE -n 80)"
done
ok "the quote routes (what a part comes to, before buying or funding) are there"
grep -qF '"plan"' <<<"$SPEC" && ok "transfers accept units of a plan" \
  || die "the transfer schema does not know units of a plan (journalctl -u $SERVICE -n 80)"
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL/api/v1/secondary/listings/00000000-0000-0000-0000-000000000000/quote?units=1" || true)
[ "$CODE" = 401 ] && ok "a quote needs an account" \
  || die "the quote route answers $CODE without an account (expected 401)"

# ---------------------------------------------------------------------------------------------
say "6. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
latest() {
  psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.slug='$1' AND a.status='approved' AND (a.body_md LIKE '%$2%' OR a.body_md LIKE '%$3%') AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)"
}
[ "$(latest exit-options 'three tenths' 'ثلاثة أعشار')" -ge 2 ] && ok "the exits article explains selling part of a plan, EN + AR" \
  || warn "the exits article does not explain parts yet in both languages; run this script again"
[ "$(latest installment-plans 'some of its units' 'بعض وحداتها')" -ge 2 ] && ok "the installment plans article too, EN + AR" \
  || warn "the installment plans article does not explain parts yet in both languages; run this script again"

# ---------------------------------------------------------------------------------------------
say "7. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   Selling part: Secondary Market -> Sell -> an installment position -> Units to sell."
echo "   Buying part: View & Buy on a listed position -> How many units (the schedule shows first)."
echo "   To a liquidity provider: Exit -> Liquidity Provider Exit -> Units on an installment plan."
echo "   To another person: Dashboard -> Transfers -> Transfer units -> Plan units."
echo "   Pre-release backup: $DUMP"
