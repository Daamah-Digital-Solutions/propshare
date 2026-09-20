#!/usr/bin/env bash
# Shell test for capimax_backup.sh v2 (plan rev 3): the backup must FAIL (exit 2) and leave
# nothing behind when the produced set would contain the conversation-encryption key, and
# must refuse to run when the key directory sits inside the backup directory.
#
# Runs anywhere with bash + tar (no postgres, no sudo): PGDUMP_CMD is stubbed.
#   bash backend/scripts/tests/test_backup_separation.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../capimax_backup.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fake_pgdump() { echo "fake dump"; }
export -f fake_pgdump

run_backup() {  # $1 = env file, $2 = dest, $3 = key dir
  DB=testdb STORAGE="$TMP/storage" ENV_FILE="$1" DEST="$2" KEY_DIR="$3" \
  LOG="$TMP/backup.log" PGDUMP_CMD="fake_pgdump" RETENTION_DAYS=14 \
  bash "$SCRIPT"
}

pass=0; fail=0
check() { if "$@"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $*"; fi; }

mkdir -p "$TMP/storage" "$TMP/keys"
echo "hello" > "$TMP/storage/file.txt"
echo "k1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=" > "$TMP/keys/assistant.keys"

# 1) A clean env (path only, no key material) -> exit 0, three files.
printf 'DATABASE_URL=postgres://x\nASSISTANT_ENCRYPTION_KEYS_FILE=/etc/capimax/keys/assistant.keys\nASSISTANT_ENCRYPTION_ACTIVE_KEY=k1\n' > "$TMP/env.clean"
set +e; run_backup "$TMP/env.clean" "$TMP/dest1" "$TMP/keys"; rc=$?; set -e
check test "$rc" -eq 0
check test "$(ls "$TMP/dest1" | wc -l)" -eq 3
check grep -q "backup done" "$TMP/backup.log"

# 2) A planted inline key variable -> exit 2, run files deleted, logged.
printf 'DATABASE_URL=postgres://x\nASSISTANT_ENCRYPTION_KEYS=k1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n' > "$TMP/env.bad"
set +e; run_backup "$TMP/env.bad" "$TMP/dest2" "$TMP/keys"; rc=$?; set -e
check test "$rc" -eq 2
check test "$(ls "$TMP/dest2" 2>/dev/null | wc -l)" -eq 0
check grep -q "ABORT: encryption key material found" "$TMP/backup.log"

# 3) A pasted key line (key-file format) in the env -> exit 2.
printf 'DATABASE_URL=postgres://x\nk1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n' > "$TMP/env.bad2"
set +e; run_backup "$TMP/env.bad2" "$TMP/dest3" "$TMP/keys"; rc=$?; set -e
check test "$rc" -eq 2
check test "$(ls "$TMP/dest3" 2>/dev/null | wc -l)" -eq 0

# 4) A .keys file inside the storage tree -> exit 2.
mkdir -p "$TMP/storage2"; cp "$TMP/keys/assistant.keys" "$TMP/storage2/oops.keys"
set +e; STORAGE="$TMP/storage2" DB=testdb ENV_FILE="$TMP/env.clean" DEST="$TMP/dest4" KEY_DIR="$TMP/keys" \
  LOG="$TMP/backup.log" PGDUMP_CMD="fake_pgdump" bash "$SCRIPT"; rc=$?; set -e
check test "$rc" -eq 2
check test "$(ls "$TMP/dest4" 2>/dev/null | wc -l)" -eq 0

# 5) Key directory inside the backup directory -> refused before writing anything.
mkdir -p "$TMP/dest5/keys"
set +e; run_backup "$TMP/env.clean" "$TMP/dest5" "$TMP/dest5/keys"; rc=$?; set -e
check test "$rc" -eq 2
check grep -q "inside the backup directory" "$TMP/backup.log"
check test "$(find "$TMP/dest5" -type f | wc -l)" -eq 0

echo "backup separation: $pass passed, $fail failed"
test "$fail" -eq 0
