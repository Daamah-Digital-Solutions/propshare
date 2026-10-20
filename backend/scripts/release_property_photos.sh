#!/usr/bin/env bash
# Capimax PropShare — release the property photo fixes (client, 2026-10-20):
#   * the home page's property cards showed a broken photo: they asked the website itself for
#     a file the API serves (the marketplace and the property pages already asked the API);
#     the owner and developer dashboards and the installment plans had the same fault;
#   * an off-plan property's page showed its photos as one fixed collage (the first four,
#     no way to see the others); it now has the same gallery as a ready property: every
#     photo, arrows, thumbnails and full screen.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_property_photos.sh
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
grep -qF "assetUrl(s.image" "$APP/src/components/home/FeaturedProperties.tsx" \
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
grep -rqsF "Chat with PropShare AI" "$APP"/dist.new/assets/ || die "the build is not the latest code"
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
echo "   Home page cards show their photos; an off-plan property's page has the full gallery."
echo "   Open it in a private window, or reload once: a browser that had the site open picks"
echo "   the new version up on its next load."
