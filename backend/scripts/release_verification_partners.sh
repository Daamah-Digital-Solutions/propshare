#!/usr/bin/env bash
# Capimax PropShare — release "verify your documents" on the VPS: the Verification Center page
# and the investor's Verification tab list the five designated verification partners (CIM
# Global Financial, CoverTech Insurance, LexCrest Global, Proof Anchor), and the assistant
# sends each verification question to the matching partner with its link (client, 2026-10-01).
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_verification_partners.sh
#
# No database migration and no new package. What it does, in order (a re-run repeats nothing):
#   1. preflight: layout, clean git tree, database at 0032 (nothing to migrate)
#   2. site build, beside the live one (the live site keeps running)
#   3. API restarted on the new code (a few seconds), then checked
#   4. assistant knowledge base: the "verifying documents" article (EN + AR; only changed
#      articles get a new version, approved as the platform admin)
#   5. new site live, then checks: the page carries the partners' links
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl restart
# capimax and rebuild the site; the previous site stays in dist.old-<stamp> meanwhile.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
SERVICE=capimax
APP_USER=deploy
DB=capimaxpropshare
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
[ -f "$BE/app/services/verification_partners.py" ] || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0032 ] || die "unexpected database revision '$REV' (expected 0032: run release_payment_methods.sh first)"
ok "database revision $REV (nothing to migrate)"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqs "cimglobalfinancial.com/capimax-verify" "$APP"/dist.new/assets/ || die "the build does not carry the verification partners"
ok "site built (goes live in step 5)"

# ---------------------------------------------------------------------------------------------
say "3. API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "API restarted and answering"

# ---------------------------------------------------------------------------------------------
say "4. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
LIVE=$(psql_db -c "SELECT count(*) FROM kb_articles WHERE slug='developers-and-verification-center' AND status='approved' AND body_md LIKE '%proofanchor.io/verify%'")
[ "${LIVE:-0}" -ge 2 ] || die "the verification article is not approved in both languages (found ${LIVE:-0})"
ok "knowledge base up to date (approved as $ADMIN_EMAIL); the assistant knows the five partners"

# ---------------------------------------------------------------------------------------------
say "5. New site live"
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
echo "   https://capimaxpropshare.com/verification-center now lists the five verification partners"
echo "   (also in the investor dashboard's Verification tab), and the assistant answers"
echo "   'how do I verify ...' with the matching partner, what to enter there and its link."
echo "   Previous site: $APP/dist.old-$STAMP"
