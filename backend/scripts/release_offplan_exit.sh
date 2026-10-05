#!/usr/bin/env bash
# Capimax PropShare — release the exit from under-construction properties (client meeting
# 2026-10-01): a property under construction earns by its unit price going up, and its holder
# can exit at any time.
#   * Unit prices: Admin -> Unit prices records a listing's new price (a monthly revaluation or
#     a new sales phase). New buyers pay it, holdings are valued at it, holders are told, and
#     every price a listing has had is kept. Investors see it on the dashboard, on the property
#     page and as a chart in Reports.
#   * How an under-construction listing is bought: by the installment plan (as today), paid in
#     full (a project sold in phases, each at its own price), or either. Set per listing in the
#     Listing editor ("How investors pay"); every existing listing stays on installments.
#   * Selling a running installment plan: the whole plan is listed on the secondary market as
#     one position. The buyer pays the seller what was paid plus the price change on all the
#     plan's units, and takes over the remaining installments on their dates.
#   * A checkout paid after its 30-minute hold ran out is honoured only at the price it was
#     made at: once the unit price has changed, the money goes back to the wallet instead.
#   * The API now saves a request's work BEFORE it answers (it used to answer first): a
#     success always means saved. This needs FastAPI 0.121 or newer; step 2 installs it.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_offplan_exit.sh
#
# What it does, in order:
#   1. preflight: layout, clean git tree, database revision
#   2. Python packages (a FastAPI older than 0.121 is replaced by 0.136.3, the tested version)
#   3. site build, beside the live one (the live site keeps running)
#   4. database backup (pg_dump) before anything changes
#   5. database migration 0034: one new table (price history) and new columns that all have a
#      default, so the API keeps running; then the API restarts on the new code
#   6. checks: the new routes and the admin page answer
#   7. new site live
#   8. assistant knowledge base: the articles on exits, installments, fees and ownership models
#      (EN + AR; only changed articles get a new version, approved as the platform admin)
# Safe to run again after a stop: the migration and the knowledge base repeat nothing, and the
# backup is taken only while the database is still at 0033 (so it is always the state from
# before this release); the build, the restart and the site swap are simply done again.
#
# Nothing changes for investors until staff use it: no price is recorded and no listing is
# switched to full payment by this release. A running plan can be listed by its holder at once.
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, then
#   cd /opt/capimax/app/backend && sudo -u deploy /opt/capimax/venv/bin/alembic downgrade 0033
#   systemctl restart capimax and rebuild the site (the previous one stays in dist.old-<stamp>).
#   The downgrade closes any position still listed for sale, then drops the price history and
#   the record of which sales were positions: prefer restoring the backup of step 4 if a price
#   was recorded or a position was sold in between.
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
[ -f "$BE/alembic/versions/0034_offplan_exit.py" ] || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
case "$REV" in
  0033|0034) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0033, the release of the assistant's meeting feedback)" ;;
esac

# ---------------------------------------------------------------------------------------------
say "2. Python packages"
VENV_OWNER=$(stat -c %U "$VENV")
HAS_SCOPE="from fastapi import Depends; Depends(lambda: None, scope='function')"
# the API commits before it answers through Depends(scope="function") (FastAPI 0.121+). If the
# server's FastAPI is older, install the versions this release was tested with, not whatever is
# newest today
if ! "$VENV/bin/python" -c "$HAS_SCOPE" 2>/dev/null; then
  warn "FastAPI $("$VENV/bin/python" -c 'import fastapi; print(fastapi.__version__)') is older than 0.121: installing 0.136.3, the version this release was tested with"
  sudo -u "$VENV_OWNER" -H "$VENV/bin/pip" install -q "fastapi==0.136.3" "starlette==1.2.1"
fi
sudo -u "$VENV_OWNER" -H "$VENV/bin/pip" install -q -e "$BE"
find "$BE" -maxdepth 1 -name '*.egg-info' -exec chown -R "$APP_USER": {} + 2>/dev/null || true
# an older FastAPI would not even start the new code, so make sure before anything is touched
"$VENV/bin/python" -c "$HAS_SCOPE" \
  || die "FastAPI in $VENV is older than 0.121: run '$VENV/bin/pip install \"fastapi==0.136.3\" \"starlette==1.2.1\"' as $VENV_OWNER and start again"
ok "packages up to date (FastAPI $("$VENV/bin/python" -c 'import fastapi; print(fastapi.__version__)'))"

# ---------------------------------------------------------------------------------------------
say "3. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqs "Sell this position" "$APP"/dist.new/assets/ || die "the build does not carry the sale of an installment position"
grep -rqs "Unit Price of Your Properties" "$APP"/dist.new/assets/ || die "the build does not carry the unit price report"
ok "site built (goes live in step 7)"

# ---------------------------------------------------------------------------------------------
say "4. Database backup"
mkdir -p "$BACKUPS"; chmod 700 "$BACKUPS"
if [ "$REV" = 0034 ]; then
  # a second run: the database is already migrated, a dump now would not be "before"
  LAST=$(ls -1t "$BACKUPS"/pre-offplan-exit-*.dump 2>/dev/null | head -1 || true)
  DUMP=${LAST:-"(none found in $BACKUPS)"}
  ok "already migrated: the backup from before this release is $DUMP"
else
  DUMP=$BACKUPS/pre-offplan-exit-$STAMP.dump
  sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
  chmod 600 "$DUMP"
  TABLES=$(pg_restore -l "$DUMP" | grep -c ' TABLE ' || true)
  [ "$TABLES" -gt 20 ] || die "the backup looks incomplete ($TABLES tables)"
  ok "$DUMP ($TABLES tables, $(du -h "$DUMP" | cut -f1))"
fi

# ---------------------------------------------------------------------------------------------
say "5. Database migration, then the API on the new code"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head) || die "the migration failed (nothing changed: the API still runs the old code). If it says 'lock timeout', a long task was using the database: run this script again in a minute"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0034 ] || die "database is at '$REV' after the upgrade, expected 0034"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "database at 0034 and the API is up on the new code"

# ---------------------------------------------------------------------------------------------
say "6. Checks"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
for route in \
  "/api/v1/properties/{id_or_slug}/prices" \
  "/api/v1/secondary/positions"; do
  grep -qF "\"$route\"" <<<"$SPEC" || die "route $route is missing (journalctl -u $SERVICE -n 80)"
done
# the price history really answers, for a listing investors can see
LISTING=$(psql_db -c "SELECT id FROM properties WHERE status IN ('active','funded') ORDER BY created_at LIMIT 1")
if [ -n "$LISTING" ]; then
  curl -fsS -m 10 "$API_LOCAL/api/v1/properties/$LISTING/prices" | grep -q '"current_price"' \
    || die "the price history of listing $LISTING does not answer (journalctl -u $SERVICE -n 80)"
  ok "the price history answers"
else
  warn "no published listing to read a price history from"
fi
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL/api/v1/secondary/positions" || true)
case "$CODE" in
  401|403) ok "installment positions are there (HTTP $CODE without a session)" ;;
  *) die "/api/v1/secondary/positions answers HTTP $CODE without a session (expected 401)" ;;
esac
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL/admin/unit-prices" || true)
case "$CODE" in
  200|302|303|307) ok "Admin -> Unit prices is there (HTTP $CODE without a session)" ;;
  *) die "the admin page /admin/unit-prices answers HTTP $CODE (journalctl -u $SERVICE -n 80)" ;;
esac
# every listing keeps the way it was bought until staff change it
OTHER=$(psql_db -c "SELECT count(*) FROM properties WHERE offplan_payment <> 'installments'")
PRICES=$(psql_db -c "SELECT count(*) FROM property_prices")
ok "listings on another way to pay than installments: ${OTHER:-0}; prices recorded so far: ${PRICES:-0}"

# ---------------------------------------------------------------------------------------------
say "7. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

# ---------------------------------------------------------------------------------------------
say "8. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
LIVE=$(psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.slug='exit-options' AND a.status='approved' AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)")
[ "${LIVE:-0}" -ge 2 ] || die "the exit article is not approved in both languages (found ${LIVE:-0}); the site and the API are live, only the assistant's articles are the old ones"
EN=$(psql_db -c "SELECT count(*) FROM kb_articles WHERE slug='exit-options' AND lang='en' AND status='approved' AND body_md LIKE '%as one position%'")
[ "${EN:-0}" -ge 1 ] || die "the approved exit article does not describe the sale of a position"
ok "knowledge base up to date (approved as $ADMIN_EMAIL)"

say "Done"
echo "   Admin -> Unit prices: record a listing's new price (each month, or when a sales phase"
echo "   opens). Holders are told, and the price shows on their dashboard, the property page"
echo "   and in Reports."
echo "   Admin -> Listings -> a listing -> 'How investors pay': installments, full payment or"
echo "   either, for an under-construction listing."
echo "   Investors: Dashboard -> Installments -> 'Sell this position' lists a running plan on"
echo "   the secondary market; a buyer pays what was paid plus the price change and takes"
echo "   over the remaining installments."
echo "   Backup from before this release: $DUMP"
