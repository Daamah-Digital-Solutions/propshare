#!/usr/bin/env bash
# Capimax PropShare — release Arabic and French versions of a listing's written text (client,
# 2026-11-01): Admin -> Listing Editor -> "Arabic & French versions" has a box for each text the
# listing has (description, developer, SPV, terms, risks, milestones, document titles, price
# notes...), with the English under it. The property page, the marketplace cards and the developer
# profile show them when the site is in that language, and the English where a box is blank.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_listing_translations.sh
#
# In order (safe to run again):
#   1. preflight: layout, clean git tree, the new code on disk
#   2. site build, beside the live one (the live site keeps running)
#   3. the API restarts on the new code; checks
#   4. new site live
#
# No database change: the versions are kept in the listing's existing content. A listing reads as
# before until someone fills its boxes. Rollback: sudo -u deploy git -C /opt/capimax/app checkout
#   <previous commit>, systemctl restart capimax, previous site back from dist.old-<stamp>.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
SERVICE=capimax
APP_USER=deploy
API_LOCAL=http://127.0.0.1:8000
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
for f in app/services/listing_translation.py app/services/listing_translation_form.py; do
  [ -f "$BE/$f" ] || die "the new code is not here ($f): run 'sudo -u deploy git pull' first"
done
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
(cd "$BE" && as_app "$VENV/bin/python" -c "import arabic_reshaper, bidi") \
  || die "documents in Arabic are not released yet: run backend/scripts/release_doc_language.sh first"
ok "code at $(as_app git -C "$APP" log --oneline -1)"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
ok "site built (goes live in step 4)"

# ---------------------------------------------------------------------------------------------
say "3. The API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "the API is up on the new code"
curl -fsS -m 10 "$API_LOCAL/api/v1/properties?limit=1&lang=ar" >/dev/null \
  && ok "the marketplace answers in a language" \
  || die "the marketplace does not answer with a language (journalctl -u $SERVICE -n 80)"
curl -fsS -m 10 "$API_LOCAL/api/v1/properties?limit=5" | grep -q '"translations"' \
  && die "a listing's stored versions reach the public answer" \
  || ok "stored versions stay out of the public answer"
LOC=$(curl -s -m 10 -o /dev/null -w '%{http_code} %{redirect_url}' "$API_LOCAL/admin/listing/" || true)
case "$LOC" in
  30[27]\ *"/admin/login"*) ok "the Listing Editor is there, for staff only" ;;
  *) die "/admin/listing/ answers '$LOC' without a session (expected a redirect to /admin/login)" ;;
esac

# ---------------------------------------------------------------------------------------------
say "4. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   Admin -> Listing Editor -> a listing -> Arabic & French versions: fill the boxes and save."
echo "   Then open that property with the site in Arabic or French. Blank boxes show the English."
