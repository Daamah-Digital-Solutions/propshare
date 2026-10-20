#!/usr/bin/env bash
# Capimax PropShare — release the home page legal disclaimer (client, 2026-10-20): the home
# page had no legal / risk disclaimer. The client's text (operator, not a broker-dealer or
# adviser, investment risk, no guarantees, own assessment, User Agreement and Privacy Policy,
# copyright) now closes the home page in small print.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_home_disclaimer.sh
#
# Site only: no database change and no API restart. In order (safe to run again):
#   1. preflight: layout, clean git tree, the new code on disk
#   2. site build, beside the live one (the live site keeps running)
#   3. new site live
#
# Rollback: put the previous site back from dist.old-<stamp>.
set -Eeuo pipefail

APP=/opt/capimax/app
APP_USER=deploy
STAMP=$(date -u +%Y%m%d-%H%M%S)

say()  { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'die "line $LINENO: $BASH_COMMAND"' ERR

as_app() { sudo -u "$APP_USER" -H "$@"; }

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] || die "unexpected server layout"
[ -f "$APP/src/components/home/LegalDisclaimer.tsx" ] \
  || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqsF "not a registered broker-dealer or investment adviser" "$APP"/dist.new/assets/ \
  || die "the build does not carry the disclaimer"
ok "site built (goes live in step 3)"

# ---------------------------------------------------------------------------------------------
say "3. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   The home page ends with the Capimax PropShare Legal Disclaimer in small print."
echo "   Open it in a private window, or reload once: a browser that had the site open picks"
echo "   the new version up on its next load."
