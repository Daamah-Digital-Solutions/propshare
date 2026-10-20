#!/usr/bin/env bash
# Capimax PropShare — release the unit statement (client, 2026-10-15): the wallet has a
# statement of its money, the units had none. Dashboard -> Active Investments -> Unit
# Movements -> "Download statement" gives, for a period the member chooses, every purchase,
# sale and transfer of units with the units held in that property after it, and per property
# the units held at the start and at the end, as a PDF or an Excel file.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_unit_statement.sh
#
# No database migration and no new package. What it does, in order (safe to run again):
#   1. preflight: layout, clean git tree, the new code on disk, database revision unchanged
#   2. site build, beside the live one (the live site keeps running)
#   3. the API restarts on the new code (a new route; nothing else changes)
#   4. checks: the route is there and answers 401 without a session
#   5. assistant knowledge base: the payments article says where the unit statement is
#      (EN + AR; only changed articles get a new version, approved as the platform admin)
#   6. new site live
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl
#   restart capimax, and put the previous site back from dist.old-<stamp>.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
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
[ -f "$BE/app/services/unit_statement_render.py" ] \
  || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0036 ] || die "unexpected database revision '$REV' (expected 0036: this release changes no table)"
ok "database revision $REV (unchanged by this release)"
# the statement is drawn with what this server already has (the wallet statement uses it)
DRAW_CHECK='
import datetime as dt
from app.services import unit_statement_render
from app.services.unit_movement_service import PropertyLine, UnitRow, UnitStatement
now = dt.datetime.now(dt.UTC)
stmt = UnitStatement(
    ref="UST-CHECK", holder="Release Check", email="check@example.invalid",
    start=now.date(), end=now.date(), generated_at=now, units_in=1, units_out=0,
    rows=[UnitRow(now, "Release Check Tower", "Purchase", "", 1, 1, "CHECK")],
    properties=[PropertyLine("Release Check Tower", 0, 1, 0, 1)],
)
pdf = unit_statement_render.render_pdf(stmt)
xlsx = unit_statement_render.render_xlsx(stmt)
assert pdf.startswith(b"%PDF") and b"Release Check Tower" in pdf, "the PDF was not drawn"
assert xlsx[:2] == b"PK", "the Excel file was not written"
print(len(pdf))
'
SIZE=$(cd "$BE" && as_app "$VENV/bin/python" -c "$DRAW_CHECK") \
  || die "the unit statement cannot be drawn on this server (see the error above; nothing was changed)"
ok "a unit statement is drawn ($SIZE bytes) and written as Excel"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqsF "capimax-unit-statement" "$APP"/dist.new/assets/ || die "the build does not carry the unit statement"
ok "site built (goes live in step 6)"

# ---------------------------------------------------------------------------------------------
say "3. The API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "the API is up on the new code"

# ---------------------------------------------------------------------------------------------
say "4. Checks"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
grep -qF '"/api/v1/investments/movements/statement"' <<<"$SPEC" || die "the unit statement route is missing (journalctl -u $SERVICE -n 80)"
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL/api/v1/investments/movements/statement?start=2026-01-01&end=2026-01-31" || true)
[ "$CODE" = 401 ] || die "the unit statement answers HTTP $CODE without a session (expected 401)"
ok "the unit statement is there, and a member's own (401 without a session)"

# ---------------------------------------------------------------------------------------------
say "5. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
KB=$(psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.slug='wallet-deposits-withdrawals' AND a.lang='en' AND a.status='approved' AND a.body_md LIKE '%Your units have their own%' AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)")
if [ "${KB:-0}" -ge 1 ]; then
  ok "knowledge base up to date (approved as $ADMIN_EMAIL)"
else
  warn "the approved payments article does not mention the unit statement yet (the assistant will not point to it); run this script again"
fi

# ---------------------------------------------------------------------------------------------
say "6. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   Members: Dashboard -> Active Investments -> Unit Movements -> Download statement:"
echo "   a period, then PDF or Excel. Every unit movement with the units held after it, and"
echo "   per property the units at the start and at the end."
echo "   Open it in a private window, or reload once: a browser that had the site open picks"
echo "   the new version up on its next load."
echo "   Previous site: $APP/dist.old-$STAMP"
