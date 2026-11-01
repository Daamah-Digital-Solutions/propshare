#!/usr/bin/env bash
# Capimax PropShare — release documents in the site's language (client, 2026-11-01):
#   certificates, receipts, statements, installment schedules and the beneficiary certificate
#   (PDF and Excel) download in the language the person has the site in: English, Arabic or
#   French. Arabic documents read from the right. English documents are unchanged.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_doc_language.sh
#
# In order (safe to run again):
#   1. preflight: layout, clean git tree, the new code and fonts on disk
#   2. the two Python libraries that join Arabic letters and order them for drawing
#   3. a sample of each language rendered on the server, before anything goes live
#   4. site build, beside the live one (the live site keeps running)
#   5. the API restarts on the new code; checks
#   6. assistant knowledge base: documents come in the site's language (EN + AR, approved)
#   7. new site live
#
# No database change. Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>,
#   systemctl restart capimax, previous site back from dist.old-<stamp>.
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
DB=capimaxpropshare
SERVICE=capimax
APP_USER=deploy
API_LOCAL=http://127.0.0.1:8000
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@capimaxpropshare.com}
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
for f in app/services/doc_lang.py app/services/doc_strings.py \
         app/assets/DejaVuSans.ttf app/assets/DejaVuSans-Bold.ttf; do
  [ -f "$BE/$f" ] || die "the new code is not here ($f): run 'sudo -u deploy git pull' first"
done
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"

# ---------------------------------------------------------------------------------------------
say "2. Libraries for Arabic"
"$VENV/bin/pip" install --quiet "arabic-reshaper>=3.0" "python-bidi>=0.4" \
  || die "the two libraries did not install (see above)"
ok "arabic-reshaper and python-bidi installed"

# ---------------------------------------------------------------------------------------------
say "3. A sample in each language, on this server"
(cd "$BE" && as_app "$VENV/bin/python" - <<'PY') || die "a document did not render (see above); nothing has gone live"
import datetime as dt

from app.services import certificate_service as cs
from app.services.doc_lang import doc_language

now = dt.datetime.now(dt.UTC)


def sample() -> bytes:
    return cs.render_certificate_pdf(
        holder="Sample Holder",
        property_title="Sample Property",
        location="Dubai",
        units=1,
        ownership="1%",
        value="$100.00",
        spv="Sample SPV",
        jurisdiction="Dubai",
        cert_ref="PSC-SAMPLE",
        issued=now.strftime("%b %d, %Y"),
        verification_code="SampleSampleSample",
        verify_url="https://capimaxpropshare.com/verify/SampleSampleSample",
    )


english = sample()
assert b"Certificate of Ownership" in english and b"DejaVuSans" not in english
with doc_language("ar"):
    assert b"DejaVuSans" in sample()
with doc_language("fr"):
    assert b"Certificat de propri" in sample()
print("   ok  English, Arabic and French render")
PY

# ---------------------------------------------------------------------------------------------
say "4. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqsF "lang=" "$APP"/dist.new/assets/ || die "the build does not ask for documents in the site's language"
ok "site built (goes live in step 7)"

# ---------------------------------------------------------------------------------------------
say "5. The API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
ok "the API is up on the new code"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
[ "$(grep -o '"name":"lang"' <<<"$SPEC" | wc -l)" -ge 9 ] \
  && ok "every document download takes the language" \
  || die "the document routes do not take the language (journalctl -u $SERVICE -n 80)"
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$API_LOCAL/api/v1/investments/certificates.zip?lang=ar" || true)
[ "$CODE" = 401 ] && ok "a certificate still needs an account" \
  || die "certificates.zip answers $CODE without an account (expected 401)"

# ---------------------------------------------------------------------------------------------
say "6. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
NEW=$(psql_db -c "SELECT count(*) FROM kb_articles a WHERE a.status='approved' AND (a.body_md LIKE '%Every document you download%' OR a.body_md LIKE '%كل مستند تنزّله%') AND a.version = (SELECT max(b.version) FROM kb_articles b WHERE b.slug=a.slug AND b.lang=a.lang)")
[ "$NEW" -ge 2 ] && ok "the assistant knows documents come in the site's language, EN + AR" \
  || warn "the article about documents is not approved in both languages; run this script again"

# ---------------------------------------------------------------------------------------------
say "7. New site live"
if [ -d "$APP/dist" ]; then
  cp -rn "$APP/dist/assets/." "$APP/dist.new/assets/" 2>/dev/null || true
  mv "$APP/dist" "$APP/dist.old-$STAMP"
fi
mv "$APP/dist.new" "$APP/dist"
ok "new site live (previous one kept as dist.old-$STAMP)"

say "Done"
echo "   Choose العربية or Français in the Language menu, then download a certificate, a receipt or"
echo "   a statement: it comes in that language. Reload once in a browser that had the site open."
