#!/usr/bin/env bash
# Capimax PropShare — release the family traces and the beneficiary's certificate and claim
# (client, recordings relayed 2026-10-07):
#   * A family action leaves a trace. Adding a relative, transferring units or allocating
#     returns to one, cancelling an allocation: both sides get a notification and an email.
#     The Family Investment tab lists the activity of each member on either side (a relative
#     who only received sees it there too), the transfer history says who, what and when, and
#     the Active Investments tab lists every unit movement with the other person named.
#   * The beneficiary register: Edit beside Delete, copies of the person's identity document
#     kept with their record, and a certificate to download for each person.
#   * A public page (/estate-claim, in the menu under Help) where the person a holder named reports
#     the holder's death and claims, with the certificate and their own identity document.
#     Staff review it under Admin -> Estate Claims; an approved claim moves the claimant's
#     share to the claimant's OWN verified account. Nobody is given the holder's account.
#   * Fixed on the way: a family transfer moves the sender's own units only; returns already
#     paid to a verified relative are not paid a second time; a group's page shows a relative
#     what reached them through the group, not their whole portfolio.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_family_estate.sh
#
# What it does, in order:
#   1. preflight: layout, clean git tree, database revision, the certificate can be drawn
#   2. site build, beside the live one (the live site keeps running)
#   3. database backup (pg_dump) before anything changes
#   4. database migration 0035: one new table (claims) and new columns that all have a
#      default, so the API keeps running; then the API restarts on the new code
#   5. checks: the new routes and the admin page answer, uploaded documents can be stored,
#      and how email leaves this server
#   6. assistant knowledge base: the family article and a new one on beneficiaries and claims
#      (EN + AR; only changed articles get a new version, approved as the platform admin)
#   7. new site live
# Safe to run again after a stop: the migration and the knowledge base repeat nothing, and the
# backup is taken only while the database is still at 0034 (so it is always the state from
# before this release); the build, the restart and the site swap are simply done again.
#
# No new package. Nothing changes for a member until they use it: no claim exists, no
# certificate is issued and no email is sent by this release itself.
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl
#   restart capimax and rebuild the site (the previous one stays in dist.old-<stamp>). The
#   database can stay at 0035: the earlier code runs on it. Going back to 0034
#   (alembic downgrade 0034) DROPS the claims and the certificate numbers already printed on
#   certificates: prefer restoring the backup of step 3 if a claim was sent in between.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
BACKUPS=/opt/capimax/backups
DB=capimaxpropshare
SERVICE=capimax
APP_USER=deploy
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@capimaxpropshare.com}
API_LOCAL=http://127.0.0.1:8000
STAMP=$(date -u +%Y%m%d-%H%M%S)

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
[ -f "$BE/alembic/versions/0035_family_traces_estate_claims.py" ] \
  && grep -qs "async def claim_approve" "$BE/app/services/estate_service.py" \
  && [ -f "$APP/src/pages/EstateClaim.tsx" ] \
  || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
case "$REV" in
  0034|0035) ok "database revision $REV" ;;
  *) die "unexpected database revision '$REV' (expected 0034: run release_offplan_exit.sh first)" ;;
esac
# the certificate is drawn with packages this server already has (the ownership certificate and
# the two-factor QR code use them): draw one before anything is touched
CERT_CHECK='
from app.services import estate_certificate
pdf = estate_certificate.render(
    beneficiary="Release Check", holder="Capimax PropShare", role="Heir",
    designation="as heir, with an allocation of 40%,", relationship="-", id_type="Passport",
    id_number="CHECK-0000", allocation="40%", coverage="Ownership Rights",
    condition="On verified death", email="-", certificate_no="CPB-0000-0000",
    issued="Oct 11, 2026", version=1, claim_url="https://capimaxpropshare.com/estate-claim",
)
assert pdf.startswith(b"%PDF") and b"CPB-0000-0000" in pdf, "the certificate was not drawn"
print(len(pdf))
'
SIZE=$(cd "$BE" && as_app "$VENV/bin/python" -c "$CERT_CHECK") \
  || die "the certificate cannot be drawn on this server (see the error above; nothing was changed)"
ok "a beneficiary certificate is drawn ($SIZE bytes)"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqs "Report a Death or Make a Claim" "$APP"/dist.new/assets/ || die "the build does not carry the claim page"
grep -rqs "Unit Movements" "$APP"/dist.new/assets/ || die "the build does not carry the unit movements"
grep -rqs "Family Activity" "$APP"/dist.new/assets/ || die "the build does not carry the family activity"
grep -rqs "Copy of their identity document" "$APP"/dist.new/assets/ || die "the build does not carry the identity document upload"
ok "site built (goes live in step 7)"

# ---------------------------------------------------------------------------------------------
say "3. Database backup"
mkdir -p "$BACKUPS"; chmod 700 "$BACKUPS"
if [ "$REV" = 0035 ]; then
  # a second run: the database is already migrated, a dump now would not be "before"
  LAST=$(ls -1t "$BACKUPS"/pre-family-estate-*.dump 2>/dev/null | head -1 || true)
  DUMP=${LAST:-"(none found in $BACKUPS)"}
  ok "already migrated: the backup from before this release is $DUMP"
else
  DUMP=$BACKUPS/pre-family-estate-$STAMP.dump
  sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
  chmod 600 "$DUMP"
  TABLES=$(pg_restore -l "$DUMP" | grep -c ' TABLE ' || true)
  [ "$TABLES" -gt 20 ] || die "the backup looks incomplete ($TABLES tables)"
  ok "$DUMP ($TABLES tables, $(du -h "$DUMP" | cut -f1))"
fi

# ---------------------------------------------------------------------------------------------
say "4. Database migration, then the API on the new code"
(cd "$BE" && as_app "$VENV/bin/alembic" upgrade head) || die "the migration failed (nothing changed: the API still runs the old code). If it says 'lock timeout', a long task was using the database: run this script again in a minute"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0035 ] || die "database is at '$REV' after the upgrade, expected 0035"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "database at 0035 and the API is up on the new code"

# ---------------------------------------------------------------------------------------------
say "5. Checks"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
for route in \
  "/api/v1/family/activity" \
  "/api/v1/investments/movements" \
  "/api/v1/estate/claims" \
  "/api/v1/estate/claims/mine" \
  "/api/v1/estate/beneficiaries/{beneficiary_id}/certificate" \
  "/api/v1/estate/beneficiaries/{beneficiary_id}/documents"; do
  grep -qF "\"$route\"" <<<"$SPEC" || die "route $route is missing (journalctl -u $SERVICE -n 80)"
done
ok "the new routes are there"
for path in /api/v1/family/activity /api/v1/investments/movements /api/v1/estate/claims/mine; do
  CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL$path" || true)
  [ "$CODE" = 401 ] || die "$path answers HTTP $CODE without a session (expected 401)"
done
ok "a member's activity, movements and claims are theirs alone (401 without a session)"
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL/admin/estate-claims" || true)
case "$CODE" in
  200|302|303|307) ok "Admin -> Estate Claims is there (HTTP $CODE without a session)" ;;
  *) die "the admin page /admin/estate-claims answers HTTP $CODE (journalctl -u $SERVICE -n 80)" ;;
esac
# every record that existed has its certificate number, and nobody is owed anything twice
NO_NUMBER=$(psql_db -c "SELECT count(*) FROM estate_beneficiaries WHERE certificate_no IS NULL OR certificate_no = ''")
[ "${NO_NUMBER:-0}" = 0 ] || die "$NO_NUMBER beneficiary record(s) have no certificate number"
RECORDS=$(psql_db -c "SELECT count(*) FROM estate_beneficiaries")
OWED=$(psql_db -c "SELECT count(*) FROM family_members WHERE pending_returns > 0")
NAMED=$(psql_db -c "SELECT count(*) FROM ownership_ledger WHERE ref_id IS NOT NULL")
ok "beneficiary records with a certificate number: ${RECORDS:-0}; relatives still owed returns: ${OWED:-0}; earlier transfers that now name the other person: ${NAMED:-0} ledger rows"
# a document sent with a claim, or a copy of an identity document, can be stored and read back
STORE_CHECK='
from app.services.integrations import storage
key = "estate-claims/_release-check/probe.txt"
storage.save(key, b"release check", "text/plain")
assert storage.load(key) == b"release check"
storage.delete(key)
'
(cd "$BE" && as_app "$VENV/bin/python" -c "$STORE_CHECK") \
  || die "uploaded documents cannot be stored (see the error above): the claim form and the identity copies need the storage to be writable"
ok "uploaded documents are stored and read back"
# the client said no email arrived: say how email leaves this server (no secret is printed)
MAIL=$(cd "$BE" && as_app "$VENV/bin/python" -c "from app.core.config import get_settings as g; s = g(); print(s.email_provider.lower(), 'inbox' if s.support_inbox_email else 'no-inbox')" 2>/dev/null || echo "unknown unknown")
PROVIDER=${MAIL%% *}
case "$PROVIDER" in
  console) warn "EMAIL_PROVIDER is 'console': emails are only written to the log, none is sent. Set a real provider in $ENVF" ;;
  unknown) warn "the email provider could not be read" ;;
  *) ok "emails leave through '$PROVIDER'" ;;
esac
[ "${MAIL##* }" = inbox ] || warn "SUPPORT_INBOX_EMAIL is empty: staff are told about a new claim in the admin panel only, not by email"
JOBS=$( { crontab -l 2>/dev/null || true; crontab -u "$APP_USER" -l 2>/dev/null || true; } )
if grep -q "notifications/dispatch-emails" <<<"$JOBS"; then
  ok "the job that sends queued emails is scheduled"
else
  warn "no scheduled job posts to /api/v1/admin/notifications/dispatch-emails: queued emails are never sent (plan/VPS_DEPLOY_RUNBOOK.md, the cron section)"
fi
STUCK=$(psql_db -c "SELECT count(*) FROM email_outbox WHERE status='pending' AND created_at < now() - interval '15 minutes'")
if [ "${STUCK:-0}" -gt 0 ]; then
  warn "$STUCK email(s) have been waiting to be sent for more than 15 minutes: the job that sends them is not running"
else
  ok "no email is stuck waiting to be sent"
fi
FAILED=$(psql_db -c "SELECT count(*) FROM email_outbox WHERE status='failed' AND created_at > now() - interval '7 days'")
[ "${FAILED:-0}" = 0 ] || warn "$FAILED email(s) failed in the last 7 days: Admin -> Email Outbox shows why (last_error)"
# a claim carries documents, up to 25 MB together: say what the web server lets through
BODY=$(nginx -T 2>/dev/null | grep -Eo 'client_max_body_size[[:space:]]+[0-9]+[mMkK]?' | head -1 | awk '{print $2}' || true)
case "$BODY" in
  "") warn "nginx sets no client_max_body_size (default 1 MB): a claim with photos would be refused. Set 'client_max_body_size 30M;' for the API" ;;
  *[mM]) if [ "${BODY%[mM]}" -ge 26 ]; then ok "nginx accepts uploads up to $BODY (a claim carries up to 25 MB of documents)"; else warn "nginx accepts only $BODY: a claim carries up to 25 MB of documents and needs at least 26M ('client_max_body_size 30M;')"; fi ;;
  *) warn "nginx client_max_body_size is $BODY: a claim carries up to 25 MB of documents and needs at least 26M" ;;
esac

# ---------------------------------------------------------------------------------------------
say "6. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
LIVE=$(psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.slug='beneficiaries-and-claims' AND a.status='approved' AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)")
[ "${LIVE:-0}" -ge 2 ] || die "the article on beneficiaries and claims is not approved in both languages (found ${LIVE:-0}); the API is live, the site is not swapped yet: run this script again"
FAMILY=$(psql_db -c "SELECT count(*) FROM kb_articles WHERE slug='family-and-brokers' AND lang='en' AND status='approved' AND body_md LIKE '%Both sides are told%'")
[ "${FAMILY:-0}" -ge 1 ] || die "the approved family article does not say that both sides are told"
ok "knowledge base up to date (approved as $ADMIN_EMAIL)"

# ---------------------------------------------------------------------------------------------
say "7. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"
STATUS=$(curl -fsS -m 10 "$API_LOCAL/api/v1/assistant/status" || true)
if grep -q '"model_configured":true' <<<"$STATUS" && grep -q '"encryption":"ok"' <<<"$STATUS"; then
  ok "assistant configured"
else
  warn "the assistant does not report itself ready: $STATUS"
fi

say "Done"
echo "   Members: Dashboard -> Family Investment. Adding a relative or transferring to one tells"
echo "   both sides (notification + email); the Activity tab and the transfer history show it,"
echo "   and Dashboard -> Active Investments lists every unit movement."
echo "   Beneficiaries & Inheritance: Edit, a copy of the person's identity document, and a"
echo "   Certificate to download for each person."
echo "   The public claim page: https://capimaxpropshare.com/estate-claim (menu -> Help, and"
echo "   on the Support page)."
echo "   Staff: Admin -> Estate Claims. Open a claim, compare what was sent with the record,"
echo "   then ask for more, reject with a message, or approve: the claimant's share moves to"
echo "   the claimant's own verified account. An approval needs the official supporting"
echo "   document on file (attach it on the claim's page if it came another way)."
echo "   Backup from before this release: $DUMP"
echo "   Previous site: $APP/dist.old-$STAMP"
