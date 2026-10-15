#!/usr/bin/env bash
# Capimax PropShare — release the Distribute returns page (client, 2026-10-15): the old form
# asked for a property's id, a "kind" and a "period key", and failed with 'property_id' on
# every save. Admin -> Distributions -> + New (or "Distribute returns" in the menu) now picks
# the property by name, fills the period from a month, takes a gross yield in % a year (or a
# total amount), and shows each investor's units, share, management fee and what reaches their
# wallet before anything is paid; "Distribute now" runs the same audited distribution as
# before. A period now counts both its dates (1 to 30 September = 30 days).
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_distribution_page.sh
#
# No database migration, no new package and no site change (admin panel only). In order (safe
# to run again):
#   1. preflight: layout, clean git tree, the new code on disk, database revision unchanged
#   2. the API restarts on the new code
#   3. checks: the page is there and staff-only (sends to the login without a session), and
#      the old create form sends to it
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl
#   restart capimax.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
SERVICE=capimax
APP_USER=deploy
API_LOCAL=http://127.0.0.1:8000

say()  { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'die "line $LINENO: $BASH_COMMAND"' ERR

as_app() { sudo -u "$APP_USER" -H "$@"; }

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] && [ -f "$ENVF" ] && [ -x "$VENV/bin/python" ] || die "unexpected server layout"
[ -f "$BE/app/admin_distribution.py" ] \
  || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0036 ] || die "unexpected database revision '$REV' (expected 0036: this release changes no table)"
ok "database revision $REV (unchanged by this release)"
(cd "$BE" && as_app "$VENV/bin/python" -c "import app.admin_distribution") \
  || die "the new page does not load on this server (see the error above; nothing was changed)"
ok "the new page loads"

# ---------------------------------------------------------------------------------------------
say "2. The API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "the API is up on the new code"

# ---------------------------------------------------------------------------------------------
say "3. Checks"
LOC=$(curl -s -m 10 -o /dev/null -w '%{http_code} %{redirect_url}' "$API_LOCAL/admin/distribution/new" || true)
case "$LOC" in
  30[27]\ *"/admin/login"*) ok "Distribute returns is there, for staff only (no session -> login)" ;;
  *) die "the page answers '$LOC' without a session (expected a redirect to /admin/login)" ;;
esac
grep -qF 'LEGACY_DISTRIBUTION_CREATE = "/distribution/create"' "$BE/app/admin.py" \
  || die "the old create form does not send to the new page"
ok "the old create form sends to the new page"

say "Done"
echo "   Admin -> Distributions -> + New (or Distribute returns in the menu): choose the"
echo "   property by name, the type of return, the month and the gross yield (% a year) or a"
echo "   total; Preview shows every investor's share, management fee and net; Distribute now"
echo "   pays it."
