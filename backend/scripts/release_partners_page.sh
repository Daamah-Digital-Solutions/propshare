#!/usr/bin/env bash
# Capimax PropShare — release the Partners page (client's partner register, 2026-10-07): the
# page at /partners lists the register's partners in its seven sections, each with its own
# logo, its role, what it does, its market and a link to its own site. It replaces the
# placeholder companies shown over stock photographs.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_partners_page.sh
#
# The site only: no database migration, no new package, and the API is not restarted. What it
# does, in order (running it again simply rebuilds and swaps):
#   1. preflight: layout, clean git tree, the new page on disk
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
[ -f "$APP/src/lib/partners.ts" ] && [ -f "$APP/src/assets/partners/stripe.webp" ] \
  || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
LOGOS=$(find "$APP/src/assets/partners" -name '*.webp' | wc -l)
[ "$LOGOS" -ge 23 ] || die "only $LOGOS partner logos on disk (expected 23)"
ok "$LOGOS partner logos on disk"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
PAGE=$(find "$APP/dist.new/assets" -name 'Partners-*.js' | head -1)
[ -n "$PAGE" ] || die "the build has no Partners page"
grep -qs "Payments and Digital Asset Payments" "$PAGE" || die "the built Partners page does not carry the register"
grep -qs "Hospitality, Property and Facility Management" "$PAGE" || die "the built Partners page is missing its last section"
if grep -qs "TDH Development" "$PAGE"; then die "the built Partners page still lists the placeholder companies"; fi
# the small logos travel inside the page itself; the others are files beside it
BUILT=$(find "$APP/dist.new/assets" -name '*.webp' | wc -l)
[ "$BUILT" -ge 15 ] || die "the build carries only $BUILT partner logo files"
ok "site built: $(basename "$PAGE"), $BUILT logo files (goes live in step 3)"

# ---------------------------------------------------------------------------------------------
say "3. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
[ -f "$APP/dist/assets/$(basename "$PAGE")" ] || die "the live folder does not hold the new Partners page"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   https://capimaxpropshare.com/partners now lists the register's partners in seven sections,"
echo "   each with its logo, its role, its market and a link to its own site."
echo "   Open it in a private window, or reload once, to see it: a browser that had the site open"
echo "   picks the new version up on its next load."
echo "   Previous site: $APP/dist.old-$STAMP"
