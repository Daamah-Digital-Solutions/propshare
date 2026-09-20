#!/usr/bin/env bash
# Capimax PropShare — nightly backup v2 (DB + uploaded files + env). Idempotent; safe to re-run.
# Installed at /usr/local/bin/capimax_backup.sh, run by root cron nightly (15 3 * * *).
# Keeps RETENTION_DAYS of local backups in $DEST (chmod 700).
#
# v2 (AI assistant, plan rev 3): the conversation-encryption key must NEVER be part of the
# backup set. Backups are ciphertext without it (by design); a backup that contained the key
# would be plaintext-equivalent. This script therefore
#   (a) refuses to run if the key directory lives under $DEST,
#   (b) after writing, scans the produced files for key material and, on any hit, deletes
#       this run's files and exits 2 (logged). The nightly cron then shows a failure.
# The key is backed up through a SEPARATE channel (company password manager) — see
# plan/ASSISTANT_KEY_RECOVERY.md.
#
# NOTE: this is the ON-BOX copy. Push $DEST off-server (S3/rclone/Hostinger backups) for
# disaster recovery — a box-level failure would take these with it.
set -euo pipefail

DB="${DB:-capimaxpropshare}"
STORAGE="${STORAGE:-/opt/capimax/storage}"
ENV_FILE="${ENV_FILE:-/opt/capimax/app/backend/.env}"
DEST="${DEST:-/opt/capimax/backups}"
KEY_DIR="${KEY_DIR:-/etc/capimax/keys}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
LOG="${LOG:-/var/log/capimax-backup.log}"
# Overridable for the shell test (no postgres / sudo on a dev box).
PGDUMP_CMD="${PGDUMP_CMD:-sudo -u postgres pg_dump -Fc}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"

mkdir -p "$DEST"; chmod 700 "$DEST"
exec >>"$LOG" 2>&1
echo "[$STAMP] backup start"

# (a) Pre-flight: the key directory must not be inside the backup tree.
case "$(readlink -f "$KEY_DIR" 2>/dev/null || echo "$KEY_DIR")/" in
  "$(readlink -f "$DEST")/"*)
    echo "[$STAMP] ABORT: key directory $KEY_DIR is inside the backup directory $DEST"
    exit 2 ;;
esac

RUN_FILES=()
cleanup_run() { for f in "${RUN_FILES[@]:-}"; do [ -n "$f" ] && rm -f -- "$f"; done; }

# 1) Database — custom format (pg_restore-able, compressed).
RUN_FILES+=("$DEST/db-$STAMP.dump")
$PGDUMP_CMD "$DB" > "$DEST/db-$STAMP.dump"

# 2) Uploaded files (documents, role-application docs, property images).
RUN_FILES+=("$DEST/storage-$STAMP.tgz")
tar -czf "$DEST/storage-$STAMP.tgz" -C "$(dirname "$STORAGE")" "$(basename "$STORAGE")"

# 3) Secrets/config snapshot (chmod 600 — same protection as the source).
RUN_FILES+=("$DEST/env-$STAMP.bak")
cp "$ENV_FILE" "$DEST/env-$STAMP.bak"; chmod 600 "$DEST/env-$STAMP.bak"

# (b) Separation check: no key material anywhere in the backup set.
#   - ASSISTANT_ENCRYPTION_KEYS= (inline key material; the app only accepts *_KEYS_FILE=)
#   - a key line of the key-file format (kN:<base64 32 bytes>)
#   - any *.keys file copied into the tree
HIT=""
if grep -lE '^ASSISTANT_ENCRYPTION_KEYS=' "$DEST"/env-*.bak >/dev/null 2>&1; then HIT="inline key variable in env backup"; fi
if grep -lE '^k[0-9]+:[A-Za-z0-9+/=]{40,}$' "$DEST"/env-*.bak >/dev/null 2>&1; then HIT="key line in env backup"; fi
if [ -n "$(find "$DEST" -name '*.keys' -print -quit 2>/dev/null)" ]; then HIT="key file inside backup directory"; fi
if tar -tzf "$DEST/storage-$STAMP.tgz" 2>/dev/null | grep -qE '\.keys$'; then HIT="key file inside storage archive"; fi
if [ -n "$HIT" ]; then
  echo "[$STAMP] ABORT: encryption key material found in the backup set ($HIT); deleting this run's files"
  cleanup_run
  exit 2
fi

# 4) Retention.
find "$DEST" -type f -mtime +"$RETENTION_DAYS" -delete

echo "[$STAMP] backup done: $(du -sh "$DEST" | cut -f1) total, $(ls "$DEST" | wc -l) files"
