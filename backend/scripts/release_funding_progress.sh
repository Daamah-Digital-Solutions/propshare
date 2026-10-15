#!/usr/bin/env bash
# Capimax PropShare — release the funding progress fix (client, 2026-10-15): a listing's
# "Funding Progress" shows its decimals (0.03%, 0.2%, 2.5%) as the admin panel does. The
# site rounded the percentage to a whole number, so every opportunity under half a percent
# read 0% although investors had bought in.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_funding_progress.sh
#
# The site only: no database migration, no new package, and the API is not restarted. What it
# does, in order (running it again simply rebuilds and swaps):
#   1. preflight: layout, clean git tree, the new code on disk
#   2. site build, beside the live one (the live site keeps running)
#   3. new site live
#
# Rollback: the previous site stays in dist.old-<stamp>:
#   mv /opt/capimax/app/dist /opt/capimax/app/dist.bad && mv /opt/capimax/app/dist.old-<stamp> /opt/capimax/app/dist
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
[ -d "$APP/.git" ] && [ -f "$APP/package.json" ] || die "unexpected server layout"
[ -f "$APP/src/lib/funding.ts" ] || die "the new code is not here: run 'sudo -u deploy git pull' first"
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
grep -rqsF "<0.01%" "$APP"/dist.new/assets/ || die "the build does not carry the new funding display"
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
echo "   The marketplace cards and the property pages show the funding progress with its"
echo "   decimals, the same figure as the admin panel (0.03%, 0.2%, 2.5%)."
echo "   Open the marketplace in a private window, or reload once: a browser that had the site"
echo "   open picks the new version up on its next load."
echo "   Previous site: $APP/dist.old-$STAMP"
