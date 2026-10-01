#!/usr/bin/env bash
# Capimax PropShare — release the client's assistant feedback (meeting 2026-10-01): the
# assistant does the job in the chat instead of sending people to pages.
#   * certificates and installment schedules download from the chat (PDF, ZIP, Excel), with the
#     share of the property written precisely (the certificate PDF too) and where to verify it;
#   * "I have $900": what it can enter and the units it buys; why units cannot be sold yet;
#   * a ticket carries the problem the user told it (they confirm it on the card) + View ticket;
#   * the phone number changes from the chat; the sign-in email changes from the chat or from
#     Account settings, approved from the current inbox and confirmed from the new one (each
#     link acts only on a button, so mail scanners approve nothing; "This wasn't me" stops it);
#   * pictures and files (PDF, Word, Excel, PowerPoint, CSV, text) in the chat, checked by their
#     content and stored encrypted, signed-in users only; staff open them from the transcript.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_assistant_meeting.sh
#
# What it does, in order (each step checks first, so a re-run never repeats work):
#   1. preflight: layout, clean git tree, database revision, upload size limit in nginx
#   2. Python packages (no new ones: Pillow, pypdf and openpyxl are already there)
#   3. site build, beside the live one (the live site keeps running)
#   4. database backup (pg_dump) before anything changes
#   5. database migration 0033: two new tables only (chat attachments, email changes), so the
#      API keeps running; then the API restarts on the new code
#   6. checks: the new routes answer
#   7. scheduled job: the nightly assistant purge (it now also removes attachments never sent)
#   8. new site live
#
# Turning attachments off later: Admin -> Platform Settings -> assistant_attachments_enabled =
# false (limits: assistant_attachments_per_message, assistant_attachment_max_mb,
# assistant_attachments_daily_cap, assistant_file_max_pages). One member's share of the daily
# token budget: assistant_user_daily_token_cap (default 2,000,000; 0 = no cap).
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, then
#   cd /opt/capimax/app/backend && sudo -u deploy /opt/capimax/venv/bin/alembic downgrade 0032
#   (drops the two new tables: pending email changes and chat attachments), systemctl restart
#   capimax and rebuild the site; the previous site stays in dist.old-<stamp> meanwhile.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
BACKUPS=/opt/capimax/backups
DB=capimaxpropshare
SERVICE=capimax
APP_USER=deploy
API_LOCAL=http://127.0.0.1:8000
STAMP=$(date -u +%Y%m%d-%H%M%S)

say()  { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
warn() { printf '   \033[33m!!\033[0m  %s\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'die "line $LINENO: $BASH_COMMAND"' ERR

as_app() { sudo -u "$APP_USER" -H "$@"; }
env_get() { grep -E "^$1=" "$ENVF" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] && [ -f "$ENVF" ] && [ -x "$VENV/bin/python" ] || die "unexpected server layout"
[ -f "$BE/alembic/versions/0033_assistant_images_email_change.py" ] || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
case "$REV" in
  0032|0033) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0032: run release_payment_methods.sh first)" ;;
esac
CRON_SECRET=$(env_get CRON_SECRET || true)
[ -n "$CRON_SECRET" ] || die "CRON_SECRET is not set in $ENVF"
# a chat attachment can be up to 10 MB: nginx refuses bodies over 1 MB unless told otherwise
BODY=$(nginx -T 2>/dev/null | grep -Eo 'client_max_body_size[[:space:]]+[0-9]+[mMkK]?' | head -1 | awk '{print $2}' || true)
case "$BODY" in
  "") warn "nginx sets no client_max_body_size (default 1 MB): files over 1 MB will be refused" ;;
  *[mM]) if [ "${BODY%[mM]}" -ge 11 ]; then ok "nginx accepts uploads up to $BODY"; else warn "nginx accepts only $BODY: files up to 10 MB need at least 11M"; fi ;;
  *) warn "nginx client_max_body_size is $BODY: files up to 10 MB need at least 11M" ;;
esac

# ---------------------------------------------------------------------------------------------
say "2. Python packages"
VENV_OWNER=$(stat -c %U "$VENV")
sudo -u "$VENV_OWNER" -H "$VENV/bin/pip" install -q -e "$BE"
find "$BE" -maxdepth 1 -name '*.egg-info' -exec chown -R "$APP_USER": {} + 2>/dev/null || true
"$VENV/bin/python" -c "import PIL, openpyxl, pypdf" || die "Pillow / openpyxl / pypdf missing from $VENV"
ok "packages up to date"

# ---------------------------------------------------------------------------------------------
say "3. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqs "confirm-email-change" "$APP"/dist.new/assets/ || die "the build does not carry the email change page"
grep -rqs "Attach a file or picture" "$APP"/dist.new/assets/ || die "the build does not carry the chat attachments"
ok "site built (goes live in step 8)"

# ---------------------------------------------------------------------------------------------
say "4. Database backup"
mkdir -p "$BACKUPS"; chmod 700 "$BACKUPS"
DUMP=$BACKUPS/pre-assistant-meeting-$STAMP.dump
sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
chmod 600 "$DUMP"
TABLES=$(pg_restore -l "$DUMP" | grep -c ' TABLE ' || true)
[ "$TABLES" -gt 20 ] || die "the backup looks incomplete ($TABLES tables)"
ok "$DUMP ($TABLES tables, $(du -h "$DUMP" | cut -f1))"

# ---------------------------------------------------------------------------------------------
say "5. Database migration, then the API on the new code"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head) || die "the migration failed (nothing changed: the API still runs the old code)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0033 ] || die "database is at '$REV' after the upgrade, expected 0033"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "database at 0033 and the API is up on the new code"

# ---------------------------------------------------------------------------------------------
say "6. Checks"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
for route in \
  "/api/v1/assistant/conversations/{conversation_id}/attachments" \
  "/api/v1/assistant/attachments/{attachment_id}" \
  "/api/v1/auth/email-change" \
  "/api/v1/auth/email-change/inspect" \
  "/api/v1/auth/email-change/confirm" \
  "/api/v1/auth/email-change/reject" \
  "/api/v1/installments/{plan_id}/schedule.xlsx"; do
  grep -qF "\"$route\"" <<<"$SPEC" || die "route $route is missing (journalctl -u $SERVICE -n 80)"
done
ok "chat attachments, email change and the Excel schedule answer"
STATUS=$(curl -fsS -m 10 "$API_LOCAL/api/v1/assistant/status" || true)
if grep -q '"model_configured":true' <<<"$STATUS" && grep -q '"encryption":"ok"' <<<"$STATUS"; then
  ok "assistant configured"
else
  warn "the assistant does not report itself ready: $STATUS"
fi

# ---------------------------------------------------------------------------------------------
say "7. Scheduled job: the nightly assistant purge"
CURRENT=$(crontab -u "$APP_USER" -l 2>/dev/null || true)
JOB_PATH=/api/v1/assistant/maintenance/purge
if grep -q "$JOB_PATH" <<<"$CURRENT"; then
  ok "$JOB_PATH already scheduled (it now also removes attachments that were never sent)"
else
  NEW=$CURRENT$'\n'"30 3 * * * curl -fsS -m 300 -X POST -H 'X-Cron-Secret: $CRON_SECRET' $API_LOCAL$JOB_PATH >/dev/null 2>&1"
  printf '%s\n' "$NEW" | sed '/^$/d' | crontab -u "$APP_USER" -
  ok "$JOB_PATH scheduled nightly at 03:30 UTC"
fi

# ---------------------------------------------------------------------------------------------
say "8. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   In the chat: certificates and installment schedules download straight from it; budgets,"
echo "   exits, tickets with the problem written in, phone and email changes, and pictures and"
echo "   files (PDF, Word, Excel, PowerPoint, CSV, text)."
echo "   In Account settings: 'Change email' (approval link to the current inbox, then a"
echo "   confirmation link to the new one)."
echo "   Pre-release backup: $DUMP"
