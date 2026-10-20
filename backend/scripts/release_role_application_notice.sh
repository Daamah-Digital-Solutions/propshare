#!/usr/bin/env bash
# Capimax PropShare — release the role application notice (client, 2026-10-20): a Broker or
# Liquidity Provider application sat in Admin -> Role Applications until someone opened the
# page. Now every admin gets an in-app notice and an email, and the support inbox an email,
# each with the link to the request, when one is submitted or resubmitted.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_role_application_notice.sh
#
# No database migration, no new package and no site change. In order (safe to run again):
#   1. preflight: layout, clean git tree, the new code on disk, database revision unchanged
#   2. the API restarts on the new code
#   3. checks: the API answers, and who will receive the emails
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl
#   restart capimax.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
DB=capimaxpropshare
SERVICE=capimax
APP_USER=deploy
API_LOCAL=http://127.0.0.1:8000

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
grep -qF "_notify_staff_of_application" "$BE/app/services/auth_service.py" \
  || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0036 ] || die "unexpected database revision '$REV' (expected 0036: this release changes no table)"
ok "database revision $REV (unchanged by this release)"

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
say "3. Who is told about a new application"
ADMINS=$(psql_db -c "SELECT string_agg(u.email, ', ' ORDER BY u.email) FROM users u JOIN user_roles r ON r.user_id = u.id WHERE r.role = 'admin' AND u.closed_at IS NULL")
[ -n "$ADMINS" ] && ok "admins (in-app + email): $ADMINS" || warn "no open admin account: nobody would be told"
INBOX=$(grep -E '^SUPPORT_INBOX_EMAIL=' "$ENVF" | tail -1 | cut -d= -f2- | tr -d '"'"'" || true)
if [ -n "$INBOX" ]; then ok "support inbox (email): $INBOX"; else warn "SUPPORT_INBOX_EMAIL is not set: only the admins are emailed"; fi
WAITING=$(psql_db -c "SELECT count(*) FROM role_grant_requests WHERE status = 'pending'")
[ "${WAITING:-0}" -gt 0 ] && warn "$WAITING application(s) already waiting in Role Applications (sent before this release, so nobody was told)" \
  || ok "no application waiting"

say "Done"
echo "   From now on a Broker or Liquidity Provider application (or a resubmission) sends every"
echo "   admin a notice and an email with the link to it in Admin -> Role Applications."
