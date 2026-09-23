# Assistant encryption key — provisioning, rotation, recovery

Conversations with the AI assistant are stored **encrypted (AES-256-GCM)** in
`assistant_messages` (`text_enc`, `content_enc`, `tool_calls_enc`, `cards_enc`). The key is
**never** in the database, never in `.env`, and never in a backup. A database dump or a
nightly backup is therefore ciphertext; **without the key file, transcripts are unrecoverable
by design** — tickets, audit rows and every other table stay readable.

This document is the only place that says where the key lives and how to get it back.

> **Since 2026-09-23 the same key file also protects two-factor authentication.** Each
> user's authenticator-app secret (`user_mfa.secret_enc`) is encrypted with it. Consequences:
> - **2FA cannot be switched on until this key file exists on the server.** Without it the
>   Account Settings panel says "Not available right now" and enrolment is refused (503) —
>   the platform never stores a 2FA secret in plaintext. The assistant does not need to be
>   enabled; only the key file (section 2) is required.
> - If the key is lost, users with 2FA on can still sign in with a **recovery code** (these are
>   hashed, not encrypted, so they do not depend on the key). A user who has neither phone nor
>   codes is helped by staff: `/admin → Users → (user) → Reset two-factor`, audited as
>   `mfa.admin_reset` — only after confirming the person's identity.

## 1. Where the key lives

| Item | Value |
|---|---|
| Key file (server) | `/etc/capimax/keys/assistant.keys` — owner `root:deploy`, mode `640` |
| Format | one line per key: `k1:<base64 of 32 random bytes>`; several lines allowed (rotation) |
| `.env` (only pointers, no material) | `ASSISTANT_ENCRYPTION_KEYS_FILE=/etc/capimax/keys/assistant.keys`<br>`ASSISTANT_ENCRYPTION_ACTIVE_KEY=k1` |
| Off-server copy | the **company password manager** (entry "Capimax PropShare — assistant encryption key kN"), optionally a sealed offline copy. Stored **at provisioning, before the first message is ever written**. |
| Backup job | `/usr/local/bin/capimax_backup.sh` (repo: `backend/scripts/capimax_backup.sh`) **refuses (exit 2) and deletes its run** if any key material lands in the backup set; it also refuses to run if `/etc/capimax/keys` is inside `/opt/capimax/backups`. Shell test: `backend/scripts/tests/test_backup_separation.sh`. |

The app refuses to start the assistant without a readable key file and an active key id
(`Settings.assistant_configured`). There is **no plaintext fallback**.

## 2. Provisioning (first time)

```bash
# on the VPS, as root
install -d -o root -g deploy -m 750 /etc/capimax/keys
umask 077
echo "k1:$(openssl rand -base64 32)" > /etc/capimax/keys/assistant.keys
chown root:deploy /etc/capimax/keys/assistant.keys
chmod 640 /etc/capimax/keys/assistant.keys
cat /etc/capimax/keys/assistant.keys   # -> copy this ONE line into the password manager NOW
```

Then in `/opt/capimax/app/backend/.env` (mode 600):

```
ASSISTANT_ENCRYPTION_KEYS_FILE=/etc/capimax/keys/assistant.keys
ASSISTANT_ENCRYPTION_ACTIVE_KEY=k1
ASSISTANT_HMAC_SECRET=<openssl rand -hex 32>      # separate secret; also in the password manager
```

Restart `capimax`, then verify: `GET https://api.capimaxpropshare.com/api/v1/assistant/status`
must report `"encryption": "ok"`, and `/admin/assistant-status` shows "Encryption key file: ok".
Run the backup once by hand and confirm exit 0 (`tail /var/log/capimax-backup.log`).

## 3. Rotation

1. Append a new line to the key file: `echo "k2:$(openssl rand -base64 32)" >> /etc/capimax/keys/assistant.keys`
   and store the new line in the password manager. **Keep `k1` in the file.**
2. Set `ASSISTANT_ENCRYPTION_ACTIVE_KEY=k2` in `.env`, restart `capimax`. New rows are written with `k2`; old rows still decrypt with `k1`.
3. Re-encrypt old rows in batches (admin session or cron secret):
   `POST /api/v1/assistant/maintenance/reencrypt` — repeat until the response says `"remaining": 0`.
4. Only then remove the `k1` line from the key file (and mark it retired in the password manager). Restart.

## 4. Recovery scenarios

| Scenario | What to do |
|---|---|
| Server rebuilt / key file lost, DB restored from dump | Recreate `/etc/capimax/keys/assistant.keys` from the password manager (every key id that was ever active, one line each), same ownership/mode, same `.env` pointers, restart. Transcripts read again. |
| Key file lost **and** password manager copy lost | Transcripts are gone. Tickets, audit, users, money are unaffected. Provision a fresh `k1` (section 2); old `assistant_messages` rows can be purged (`POST /api/v1/assistant/maintenance/purge` after setting `assistant_retention_days=0` temporarily, or `DELETE FROM assistant_conversations`). |
| Wrong key in the file (decrypt errors in the admin transcript view: "Could not decrypt") | The file does not contain the key id stored on the row (`assistant_messages.enc_key_id`). Restore the missing line from the password manager. |
| Key file lost, users have 2FA on | Authenticator codes answer "use a recovery code" (503 `MFA_UNAVAILABLE`); recovery codes keep working. Restore the key line from the password manager and restart — codes work again. Users with no codes left: staff reset (see the note at the top). |
| Suspected key exposure | Rotate immediately (section 3), then remove the exposed key line after re-encryption reaches 0 remaining. Review `audit_log` for `assistant.transcript_viewed`. |

## 5. Things that must stay true

- No key material in `.env`, the repo, CI, chat, tickets, or the backup tree. The backup job enforces this.
- `.env.pre-*.bak` snapshots are for env files only — never copy a key file that way.
- Opening a transcript in the admin panel is always audited (`assistant.transcript_viewed`).
- Retention purge (`assistant_retention_days`, default 180) runs from cron; the key does not change that.
