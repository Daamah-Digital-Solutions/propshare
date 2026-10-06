#!/usr/bin/env bash
# Capimax PropShare — release the crypto payment fixes (client, 2026-10-06):
#   * NOWPayments' notifications that carry a very small number (the network fee of a paid BNB,
#     BTC or ETH payment) were refused with 401, so such a payment could never settle. They are
#     accepted now.
#   * Money that arrives another way than the invoice asked (less than asked, a second
#     transfer, another coin or network that NOWPayments could process) is credited to the
#     member's wallet at what it is worth, once, with a notification. A purchase paid short is
#     not completed: its units are released and the money is in the wallet.
#   * The member chooses the coin and its network on PropShare; the payment page is then made
#     for that one coin. An amount under the coin's minimum is refused before any invoice.
#   * A crypto payment still on its way shows at the top of the wallet.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/release_crypto_payments.sh
#
# No database migration and no new package. What it does, in order (running it again simply
# repeats the build, the restart and the swap; unchanged knowledge-base articles are left alone):
#   1. preflight: layout, clean git tree, database at 0034, the notification check on disk
#   2. site build, beside the live one (the live site keeps running)
#   3. API restarted on the new code (a few seconds), then checked; the coins a member will be
#      offered are read from the NOWPayments account
#   4. assistant knowledge base: how crypto works now (EN + AR, approved as the platform admin)
#   5. new site live
#
# AFTER it, for the 13 USD deposit of 2026-10-06 (NOWPayments payment 4870885867):
#   a. look at it:   /opt/capimax/venv/bin/python backend/scripts/check_crypto_deposits.py 4870885867
#   b. NOWPayments dashboard -> Payments -> open 4870885867 -> press "IPN" (send it again).
#      Do NOT change its status. The platform credits what arrived (12.99 USD) and tells the member.
#   c. run the check again: the payment reads "settled" and "the platform settled it at 12.99".
#   If step 3 of the check shows a NEW 401 instead, the notification was refused again; what it
#   carried is now in the log, for the developer:
#      journalctl -u capimax --since "30 min ago" | grep "notification refused"
#
# Rollback: sudo -u deploy git -C /opt/capimax/app checkout <previous commit>, systemctl restart
# capimax and rebuild the site; the previous site stays in dist.old-<stamp> meanwhile. Payments
# settled meanwhile stay settled (what was done is kept on each payment).
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
SERVICE=capimax
APP_USER=deploy
DB=capimaxpropshare
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
grep -qs "def value_now" "$BE/app/services/integrations/payments/nowpayments_gateway.py" \
  || die "the new code is not here: run 'sudo -u deploy git pull' first"
if [ -n "$(as_app git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  as_app git -C "$APP" status --short --untracked-files=no
  die "the code folder has local changes (listed above); send them to the developer before continuing"
fi
ok "code at $(as_app git -C "$APP" log --oneline -1)"
REV=$(cd "$BE" && as_app "$VENV/bin/alembic" current 2>/dev/null | awk '{print $1}' | tail -1)
[ "$REV" = 0034 ] || die "unexpected database revision '$REV' (expected 0034: run release_offplan_exit.sh first)"
ok "database revision $REV (nothing to migrate)"
# the check on disk accepts a notification written the way NOWPayments writes it: a fee of
# 0.000083 signed as that text (the old check re-wrote it as 8.3e-05 and refused it)
SIGN_CHECK='
import hashlib, hmac
from app.services.integrations.payments import nowpayments_gateway as n
body = b"{\"payment_id\":1,\"payment_status\":\"partially_paid\",\"fee\":{\"depositFee\":0.000083}}"
signed = "{\"fee\":{\"depositFee\":0.000083},\"payment_id\":1,\"payment_status\":\"partially_paid\"}"
theirs = hmac.new(b"check", signed.encode(), hashlib.sha512).hexdigest()
assert theirs in n.signatures("check", body), "a small number is still re-written"
'
(cd "$BE" && as_app "$VENV/bin/python" -c "$SIGN_CHECK") \
  || die "the notification check on disk still refuses a small number (see the error above)"
ok "a notification carrying a small fee passes the signature check"

# ---------------------------------------------------------------------------------------------
say "2. Site build (the live site keeps running)"
(cd "$APP" && as_app npm ci --no-audit --no-fund --loglevel=error)
rm -rf "$APP/dist.new"
(cd "$APP" && as_app npx vite build --outDir dist.new --emptyOutDir --logLevel error)
grep -rqs "Choose the coin you will send" "$APP"/dist.new/assets/ || die "the build does not carry the coin choice"
grep -rqs "Crypto payments on their way" "$APP"/dist.new/assets/ || die "the build does not carry the payments on their way"
ok "site built (goes live in step 5)"

# ---------------------------------------------------------------------------------------------
say "3. API on the new code"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS -m 5 "$API_LOCAL/api/v1/properties?limit=1" >/dev/null || die "the API did not come back: journalctl -u $SERVICE -n 80"
SPEC=$(curl -fsS -m 10 "$API_LOCAL/openapi.json" || true)
grep -qF '/api/v1/payments/crypto/coins' <<<"$SPEC" || die "the API does not list the coins (journalctl -u $SERVICE -n 80)"
grep -qF '/api/v1/payments/crypto/open' <<<"$SPEC" || die "the API does not list the crypto payments on their way"
grep -qF '"pay_currency"' <<<"$SPEC" || die "the API does not take the coin chosen with a payment"
ok "API restarted: coins, payments on their way, and the coin with a deposit or a purchase"
# what a member will be offered, read from the NOWPayments account with the API's own key
# (read only; prints no key)
COINS_CHECK='
import asyncio
from app.services.integrations.payments import nowpayments_gateway as n

async def main():
    if not n.is_configured():
        print("   NOWPayments is not configured: crypto stays off on the site")
        return
    coins = await n.list_coins()
    listed = [c for c in coins if c["stable"] or c["popular"]]
    print("   %d coin(s) offered; %d listed up front (stablecoins and popular), the rest by search" % (len(coins), len(listed)))
    for c in listed[:12]:
        memo = ", needs a memo/tag" if c["memo"] else ""
        print("     %s - %s  [code %s, network %s%s]" % (c["ticker"], c["name"], c["code"], c["network"], memo))
    for code in ("usdttrc20", "usdtbsc", "btc"):
        if any(c["code"] == code for c in coins):
            floor = await n.minimum_usd(code)
            print("     smallest %s payment now: %s USD" % (code, floor))

asyncio.run(main())
'
(cd "$BE" && as_app "$VENV/bin/python" -c "$COINS_CHECK") \
  || warn "the coins could not be read from NOWPayments just now (the site says so and offers to try again)"

# ---------------------------------------------------------------------------------------------
say "4. Assistant knowledge base"
(cd "$BE" && as_app "$VENV/bin/python" scripts/seed_kb.py --approve-as "$ADMIN_EMAIL")
# both languages name the memo / tag a coin can need, a word the earlier article did not have
LIVE=$(psql_db -c "SELECT count(*) FROM kb_articles WHERE slug='wallet-deposits-withdrawals' AND status='approved' AND body_md LIKE '%memo%'")
[ "${LIVE:-0}" -ge 2 ] || die "the wallet article is not approved in both languages (found ${LIVE:-0})"
ok "knowledge base up to date (approved as $ADMIN_EMAIL); the assistant explains crypto as it works now"

# ---------------------------------------------------------------------------------------------
say "5. New site live"
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
echo "   Wallet -> Add Funds -> Cryptocurrency, and a property's payment methods: the member chooses"
echo "   the coin and its network here; the payment page then asks for that coin only."
echo "   A crypto payment still on its way shows at the top of the wallet."
echo "   Money that arrives short or in another coin is credited to the wallet at what arrived."
echo
echo "   NEXT, for the 13 USD deposit of 2026-10-06:"
echo "     1) $VENV/bin/python $BE/scripts/check_crypto_deposits.py 4870885867"
echo "     2) NOWPayments dashboard -> Payments -> 4870885867 -> press IPN (do not change its status)"
echo "     3) run 1) again: it reads 'settled' and 'the platform settled it at 12.99'"
echo "        (a NEW 401 in its step 3 instead? send the developer:"
echo "         journalctl -u $SERVICE --since '30 min ago' | grep 'notification refused')"
echo "   Previous site: $APP/dist.old-$STAMP"
