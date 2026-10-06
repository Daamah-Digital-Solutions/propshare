#!/usr/bin/env bash
# Capimax PropShare — release the last two items of the client meeting of 2026-10-01:
#   * Under each certificate reference, the link to where it is verified (CIM Global
#     Financial's Capimax Verify): in the dashboard's Verification and Certificates tabs, and
#     printed under the reference on the certificate PDF, where it is a link too.
#   * The share of the property: the certificate now says it in its text ("representing
#     0.04762% of the property"), and the two tabs show the same figure (the Certificates tab
#     rounded it to two decimals, so a small holding read 0.00%).
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_certificate_verify.sh
#
# No database migration, no new package and nothing for the assistant's knowledge base. What it
# does, in order (running it again simply repeats the build, the restart and the swap):
#   1. preflight: layout, clean git tree, database at 0034 (nothing to migrate)
#   2. site build, beside the live one (the live site keeps running)
#   3. API restarted on the new code (a few seconds), then checked
#   4. new site live
#
# The link opens CIM's page; a certificate is found there by its reference only once it has
# been registered at CIM under that reference.
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
API_LOCAL=http://127.0.0.1:8000
VERIFY_URL=https://www.cimglobalfinancial.com/capimax-verify
STAMP=$(date -u +%Y%m%d-%H%M%S)

say()  { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'die "line $LINENO: $BASH_COMMAND"' ERR

as_app() { sudo -u "$APP_USER" -H "$@"; }

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] && [ -f "$ENVF" ] && [ -x "$VENV/bin/python" ] || die "unexpected server layout"
grep -qs "ownership_pct" "$BE/app/schemas/secondary.py" || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0034 ] || die "unexpected database revision '$REV' (expected 0034: run release_offplan_exit.sh first)"
ok "database revision $REV (nothing to migrate)"
# the certificate as the code on disk draws it: the share in its text, the link under its reference
RENDER_CHECK='
import sys
from app.services import certificate_service as c
pdf = c.render_certificate_pdf(
    holder="Release Check", property_title="Release Check", location="-", units=20,
    ownership=c.ownership_pct(20, 42000), value="-", spv="-", jurisdiction="-",
    cert_ref="CMX-00000000", issued="-",
)
assert b"representing 0.04762% of the property" in pdf, "the share is not in the text"
assert ("/URI (" + sys.argv[1] + ")").encode() in pdf, "the link is not in the file"
'
(cd "$BE" && as_app "$VENV/bin/python" -c "$RENDER_CHECK" "$VERIFY_URL") \
  || die "the certificate does not render with the share and the link (see the error above)"
ok "a certificate renders with the share in its text and the link under its reference"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqs "link under each reference" "$APP"/dist.new/assets/ || die "the build does not carry the link under each certificate reference"
ok "site built (goes live in step 4)"

# ---------------------------------------------------------------------------------------------
say "3. API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
grep -qF '"ownership_pct"' <<<"$SPEC" || die "the API does not give the share of the property with a holding (journalctl -u $SERVICE -n 80)"
ok "API restarted: holdings carry the share of the property"

# ---------------------------------------------------------------------------------------------
say "4. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   Dashboard -> Verification Center and Certificates: each certificate shows its share of"
echo "   the property and, under its reference, 'Verify at CIM Global Financial'."
echo "   The certificate PDF says the share in its text and prints the same link under the"
echo "   reference: $VERIFY_URL"
echo "   A certificate is found at CIM by its reference only once it is registered there."
echo "   Previous site: $APP/dist.old-$STAMP"
