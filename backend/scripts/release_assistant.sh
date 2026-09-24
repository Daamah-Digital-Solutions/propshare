#!/usr/bin/env bash
# Capimax PropShare — release the AI assistant (and everything shipped with it) on the VPS.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_assistant.sh
#
# What it does, in order (each step checks first, so a re-run never repeats work):
#   1. preflight: layout, clean git tree, database revision, clock sync
#   2. database backup (pg_dump) before anything changes
#   3. new Python packages (pip install -e backend)
#   4. encryption key file /etc/capimax/keys/assistant.keys (shown ONCE for the password manager)
#   5. .env: assistant settings (asks for the OpenAI key on this screen; never echoed)
#   6. database migrations 0026-0029 (before the restart: the new code reads the new tables)
#   7. knowledge base + reference library, approved as the platform admin
#   8. assistant switched on for everyone, visitors included, English replies, gpt-5.6-luna
#   9. backup script v2 (refuses to back up key material), run once
#  10. scheduled jobs for the assistant (deploy's crontab)
#  11. site build with the new assistant widget
#  12. restart, then a real conversation through nginx to prove it works end to end
#
# Rollback: the schema changes only ADD tables and columns, so the previous code runs on it.
#   sudo -u deploy git -C /opt/capimax/app checkout <previous commit> && systemctl restart capimax
#   and rebuild the site. The pre-release dump from step 2 restores everything else.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
FE_ENV=$APP/.env.production
KEYDIR=/etc/capimax/keys
KEYF=$KEYDIR/assistant.keys
BACKUPS=/opt/capimax/backups
DB=capimaxpropshare
SERVICE=capimax
APP_USER=deploy
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@capimaxpropshare.com}
MODEL=gpt-5.6-luna
API_LOCAL=http://127.0.0.1:8000
API_PUBLIC=https://api.capimaxpropshare.com
# the end-to-end check goes through THIS server's nginx (not out and back in over the internet)
VIA_NGINX=(--resolve api.capimaxpropshare.com:443:127.0.0.1)
STAMP=$(date -u +%Y%m%d-%H%M%S)

say()  { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
warn() { printf '   \033[33m!!\033[0m  %s\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'die "line $LINENO: $BASH_COMMAND"' ERR

as_app() { sudo -u "$APP_USER" -H "$@"; }
env_get() { grep -E "^$1=" "$ENVF" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
env_add() {  # add KEY=VALUE only when KEY is absent or empty; never overwrites a set value
  local key=$1 value=$2
  if [ -n "$(env_get "$key" || true)" ]; then ok "$key already set"; return; fi
  sed -i "/^$key=/d" "$ENVF"
  chown --reference="$ENVF.bak-$STAMP" "$ENVF"; chmod --reference="$ENVF.bak-$STAMP" "$ENVF"  # sed -i makes a new file
  end_with_newline "$ENVF"
  printf '%s=%s\n' "$key" "$value" >> "$ENVF"
  ok "$key set"
}
psql_db() { sudo -u postgres psql -d "$DB" -v ON_ERROR_STOP=1 -qtA "$@"; }
end_with_newline() {  # so an append never glues onto a last line typed without Enter
  [ -s "$1" ] && [ -n "$(tail -c1 "$1")" ] && printf '\n' >> "$1"
  return 0
}
assistant_off_and_die() {  # a failed live check must not leave a broken assistant switched on
  psql_db -c "UPDATE platform_settings SET value='false' WHERE key='assistant_enabled';" >/dev/null || true
  die "$1 -- the assistant was switched OFF again (turn it back on in /admin -> Platform Settings -> assistant_enabled once fixed)"
}

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] && [ -f "$ENVF" ] && [ -x "$VENV/bin/python" ] || die "unexpected server layout"
[ -f "$BE/alembic/versions/0029_two_factor.py" ] || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
case "$REV" in
  0025|0026|0027|0028|0029) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0025)" ;;
esac
if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)" = yes ]; then
  ok "clock synchronised (two-factor codes need it)"
else
  warn "clock sync not confirmed: run 'timedatectl set-ntp true' if two-factor codes are refused"
fi

# ---------------------------------------------------------------------------------------------
say "2. Database backup"
mkdir -p "$BACKUPS"; chmod 700 "$BACKUPS"
DUMP=$BACKUPS/pre-assistant-$STAMP.dump
sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
chmod 600 "$DUMP"
TABLES=$(pg_restore -l "$DUMP" | grep -c ' TABLE ' || true)
[ "$TABLES" -gt 20 ] || die "the backup looks incomplete ($TABLES tables)"
ok "$DUMP ($TABLES tables, $(du -h "$DUMP" | cut -f1))"

# ---------------------------------------------------------------------------------------------
say "3. Python packages"
VENV_OWNER=$(stat -c %U "$VENV")
sudo -u "$VENV_OWNER" -H "$VENV/bin/pip" install -q -e "$BE"
# an editable install may leave metadata in the code folder: keep it the app user's
find "$BE" -maxdepth 1 -name '*.egg-info' -exec chown -R "$APP_USER": {} + 2>/dev/null || true
sudo -u "$VENV_OWNER" -H "$VENV/bin/python" -c "import openai, cryptography, pypdf, segno, openpyxl"
ok "openai $("$VENV/bin/python" -c 'import openai; print(openai.__version__)'), cryptography, pypdf, segno, openpyxl"

# ---------------------------------------------------------------------------------------------
say "4. Encryption key file"
install -d -o root -g "$APP_USER" -m 750 "$KEYDIR"
if [ ! -s "$KEYF" ]; then
  # the key only takes its real name once the owner has saved it: if the session drops before
  # SAVED, the re-run finds the pending key and shows it again
  if [ ! -s "$KEYF.pending" ]; then
    (umask 077; printf 'k1:%s\n' "$(openssl rand -base64 32)" > "$KEYF.pending")
  fi
  echo
  echo "   ONE-TIME: copy the line below into your password manager NOW."
  echo "   Without it, saved conversations and two-factor settings cannot be recovered"
  echo "   if this server is ever rebuilt. It is not in any backup."
  echo
  printf '   \033[1m%s\033[0m\n\n' "$(cat "$KEYF.pending")"
  while true; do
    read -rp "   Type SAVED once it is in the password manager: " answer
    [ "$answer" = SAVED ] && break
  done
  mv "$KEYF.pending" "$KEYF"
  chown root:"$APP_USER" "$KEYF"; chmod 640 "$KEYF"
  clear || true
else
  chown root:"$APP_USER" "$KEYF"; chmod 640 "$KEYF"
  ok "key file already exists (kept)"
fi
as_app test -r "$KEYF" || die "$APP_USER cannot read $KEYF"
ok "$KEYF readable by the app, not by anyone else"

# ---------------------------------------------------------------------------------------------
say "5. Settings file (.env)"
cp -p "$ENVF" "$ENVF.bak-$STAMP"   # same owner and mode as the original
ok "previous file kept as $ENVF.bak-$STAMP"
if [ -z "$(env_get OPENAI_API_KEY || true)" ]; then
  TRIES=0
  while true; do
    read -rsp "   Paste the OpenAI API key (hidden) and press Enter: " OKEY; echo
    OKEY=$(printf '%s' "$OKEY" | tr -d '[:space:]')
    [ -n "$OKEY" ] || continue
    # the same call the assistant makes: proves the key AND access to the model
    CODE=$(printf 'header = "Authorization: Bearer %s"\n' "$OKEY" \
      | curl -s -o /dev/null -w '%{http_code}' -m 60 -K - -H 'Content-Type: application/json' \
          -d "{\"model\":\"$MODEL\",\"input\":\"ping\",\"max_output_tokens\":16,\"store\":false}" \
          https://api.openai.com/v1/responses || true)
    [ "$CODE" = 200 ] && break
    TRIES=$((TRIES + 1))
    warn "OpenAI answered HTTP $CODE for $MODEL with this key (000 = no connection)"
    if [ "$TRIES" -ge 3 ]; then
      read -rp "   Type KEEP to use this key anyway, or press Enter to paste another: " keep
      [ "$keep" = KEEP ] && break
    fi
  done
  env_add OPENAI_API_KEY "$OKEY"
  unset OKEY
else
  ok "OPENAI_API_KEY already set"
fi
env_add ASSISTANT_ENABLED true
env_add ASSISTANT_ENCRYPTION_KEYS_FILE "$KEYF"
env_add ASSISTANT_ENCRYPTION_ACTIVE_KEY k1
env_add ASSISTANT_HMAC_SECRET "$(openssl rand -hex 32)"
if [ -z "$(env_get SUPPORT_INBOX_EMAIL || true)" ]; then
  read -rp "   Email that should receive support tickets [$ADMIN_EMAIL]: " SUPPORT
  env_add SUPPORT_INBOX_EMAIL "${SUPPORT:-$ADMIN_EMAIL}"
fi
chown --reference="$ENVF.bak-$STAMP" "$ENVF"; chmod --reference="$ENVF.bak-$STAMP" "$ENVF"
as_app test -r "$ENVF" || die "$APP_USER can no longer read $ENVF"

# ---------------------------------------------------------------------------------------------
say "6. Database migrations"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head)
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0029 ] || die "database is at '$REV' after the upgrade, expected 0029"
ok "database at 0029"

# ---------------------------------------------------------------------------------------------
say "7. Knowledge base and reference library"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_reference.py --approve-as "$ADMIN_EMAIL")
ok "approved as $ADMIN_EMAIL"

# ---------------------------------------------------------------------------------------------
say "8. Assistant switched on"
PRICING='{"gpt-5.6-luna":{"input":0.20,"cached_input":0.02,"output":1.20,"cache_write_multiplier":1.25}}'
psql_db <<SQL
INSERT INTO platform_settings (key, value) VALUES
  ('assistant_model', '$MODEL'),
  ('assistant_model_pricing', '$PRICING'),
  ('assistant_reply_language', 'en'),
  ('assistant_rollout', 'all'),
  ('assistant_visitor_enabled', 'true'),
  ('assistant_enabled', 'true')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
SQL
ok "$MODEL, everyone including visitors, English replies (change any time in /admin -> Platform Settings)"

# ---------------------------------------------------------------------------------------------
say "9. Backup script v2"
if ! cmp -s "$BE/scripts/capimax_backup.sh" /usr/local/bin/capimax_backup.sh; then
  [ -f /usr/local/bin/capimax_backup.sh ] && cp -p /usr/local/bin/capimax_backup.sh "/usr/local/bin/capimax_backup.sh.v1-$STAMP"
  install -o root -g root -m 750 "$BE/scripts/capimax_backup.sh" /usr/local/bin/capimax_backup.sh
fi
/usr/local/bin/capimax_backup.sh || die "backup v2 failed: see /var/log/capimax-backup.log"
ok "backup v2 installed and run: $(tail -1 /var/log/capimax-backup.log)"
crontab -l 2>/dev/null | grep -q capimax_backup.sh || warn "no nightly backup entry in root's crontab"

# ---------------------------------------------------------------------------------------------
say "10. Scheduled jobs"
CRON_SECRET=$(env_get CRON_SECRET || true)
[ -n "$CRON_SECRET" ] || die "CRON_SECRET is not set in .env"
CURRENT=$(crontab -u "$APP_USER" -l 2>/dev/null || true)
NEW=$CURRENT
add_job() {  # schedule path: only when the path is not scheduled yet
  local schedule=$1 path=$2
  if grep -q "$path" <<<"$CURRENT"; then ok "$path already scheduled"; return; fi
  NEW+=$'\n'"$schedule curl -fsS -m 300 -X POST -H 'X-Cron-Secret: $CRON_SECRET' $API_LOCAL$path >/dev/null 2>&1"
  ok "$path scheduled ($schedule)"
}
add_job "7 * * * *"  /api/v1/assistant/maintenance/nudges
add_job "17 * * * *" /api/v1/assistant/maintenance/index-documents
add_job "27 * * * *" /api/v1/assistant/maintenance/ops-cases
add_job "37 * * * *" /api/v1/assistant/maintenance/ticket-sla
add_job "0 6 * * *"  /api/v1/assistant/maintenance/daily-digest
add_job "45 3 * * *" /api/v1/assistant/maintenance/purge
if [ "$NEW" != "$CURRENT" ]; then
  printf '%s\n' "$NEW" | sed '/^$/d' | crontab -u "$APP_USER" -
fi

# ---------------------------------------------------------------------------------------------
say "11. Site build"
if grep -q '^VITE_ASSISTANT_V2=' "$FE_ENV" 2>/dev/null; then
  sed -i 's/^VITE_ASSISTANT_V2=.*/VITE_ASSISTANT_V2=true/' "$FE_ENV"
else
  end_with_newline "$FE_ENV"
  printf 'VITE_ASSISTANT_V2=true\n' >> "$FE_ENV"
fi
chown "$APP_USER":"$APP_USER" "$FE_ENV"
ok "VITE_ASSISTANT_V2=true in $FE_ENV"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
# built beside the live site and swapped in after the restart: the site never has a half-empty
# dist/, and the new pages only appear once the new API is up
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
ls "$APP"/dist.new/assets/*.js >/dev/null 2>&1 || die "the build produced no scripts"
ok "site built with the new assistant (goes live after the restart)"

# ---------------------------------------------------------------------------------------------
say "12. Restart and end-to-end check"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "API is up"

# swap the new site in; old hashed files stay available to tabs that were already open
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

VKEY=release-check-$(openssl rand -hex 12)
STATUS=$(curl -fsS -m 20 "${VIA_NGINX[@]}" -H "X-Visitor-Key: $VKEY" "$API_PUBLIC/api/v1/assistant/status" || true)
grep -q '"enabled":true' <<<"$STATUS" || assistant_off_and_die "assistant not enabled for visitors: $STATUS"
grep -q '"encryption":"ok"' <<<"$STATUS" || assistant_off_and_die "encryption not ok: $STATUS"
ok "status: enabled, encryption ok"

CONV=$(curl -fsS -m 20 "${VIA_NGINX[@]}" -X POST -H "X-Visitor-Key: $VKEY" "$API_PUBLIC/api/v1/assistant/conversations" \
  | sed -E 's/.*"id":"([^"]+)".*/\1/' || true)
[ -n "$CONV" ] || assistant_off_and_die "could not open a test conversation"
REPLY=$(curl -sS -N -m 150 "${VIA_NGINX[@]}" -X POST -H "X-Visitor-Key: $VKEY" -H 'Content-Type: application/json' \
  -d '{"text":"In one sentence, what is Capimax PropShare?","lang":"en"}' \
  "$API_PUBLIC/api/v1/assistant/conversations/$CONV/messages" || true)
psql_db -c "DELETE FROM assistant_conversations WHERE visitor_key = '$VKEY';" >/dev/null || true
grep -q '^event: done' <<<"$REPLY" || assistant_off_and_die "no answer came back through nginx: $(tail -c 400 <<<"$REPLY")"
grep -q '"safe_mode": null' <<<"$REPLY" || assistant_off_and_die "the assistant answered in safe mode: $(grep -A1 '^event: done' <<<"$REPLY" | tail -1)"
ok "a real question was answered through $API_PUBLIC (test conversation deleted)"

say "Done"
echo "   The assistant is live for everyone, visitors included. Settings: /admin -> Platform Settings"
echo "   (assistant_*). Conversations, tickets and the knowledge base: /admin -> Assistant."
echo "   Pre-release backup: $DUMP"
echo "   Now change the root password (passwd)."
