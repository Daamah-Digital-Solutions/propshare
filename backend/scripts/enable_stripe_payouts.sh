#!/usr/bin/env bash
# Capimax PropShare — switch bank withdrawals to automatic payouts through Stripe Connect
# (owner, 2026-10-20: "the Stripe side is set up"). From then on an investor links their bank
# once through Stripe (Wallet -> Withdraw -> "Link bank account"); a bank withdrawal up to the
# auto-approve limit is sent to their Stripe account at once, a larger one waits for an admin's
# Approve. Crypto withdrawals stay manual. Nothing else changes.
#
# Run as root, AFTER pulling the code:
#   cd /opt/capimax/app && sudo -u deploy git pull && bash backend/scripts/enable_stripe_payouts.sh
#
# Undo (back to manual bank withdrawals):  bash backend/scripts/enable_stripe_payouts.sh --off
#
# In order (safe to run again):
#   1. preflight: layout, live Stripe keys in .env, the Connect webhook secret
#   2. Stripe: the key can reach Connect, and the platform's available balance
#   3. the withdrawal jobs are scheduled (execute every 2 min, reconcile every 15)
#   4. the switch: payout_auto_methods = bank (audited), and what it means now
set -Eeuo pipefail

APP=/opt/capimax/app
BE=$APP/backend
VENV=/opt/capimax/venv
ENVF=$BE/.env
DB=capimaxpropshare
APP_USER=deploy
MODE=on
[ "${1:-}" = "--off" ] && MODE=off

say()  { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
warn() { printf '   \033[33m!!\033[0m  %s\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'die "line $LINENO: $BASH_COMMAND"' ERR

as_app() { sudo -u "$APP_USER" -H "$@"; }
psql_db() { sudo -u postgres psql -d "$DB" -v ON_ERROR_STOP=1 -qtA "$@"; }
envval() { grep -E "^$1=" "$ENVF" | tail -1 | cut -d= -f2- | tr -d "\"'" || true; }
py() { (cd "$BE" && as_app "$VENV/bin/python" -c "$1"); }

# ---------------------------------------------------------------------------------------------
say "1. Preflight"
[ "$(id -u)" = 0 ] || die "run this as root"
[ -d "$APP/.git" ] && [ -f "$ENVF" ] && [ -x "$VENV/bin/python" ] || die "unexpected server layout"
KEY=$(envval STRIPE_SECRET_KEY)
case "$KEY" in
  sk_live_*|rk_live_*) ok "Stripe key is a LIVE key" ;;
  "") die "STRIPE_SECRET_KEY is empty in $ENVF" ;;
  *) [ "$MODE" = off ] || die "STRIPE_SECRET_KEY is not a live key (sk_live_ / rk_live_): real payouts need the live one" ;;
esac
[ -n "$(envval STRIPE_WEBHOOK_SECRET)" ] || die "STRIPE_WEBHOOK_SECRET is empty: Stripe is not fully set up on this server"
if [ -n "$(envval STRIPE_CONNECT_WEBHOOK_SECRET)" ]; then
  ok "Connect webhook secret is set (investors are told when their bank refuses a payout)"
else
  warn "STRIPE_CONNECT_WEBHOOK_SECRET is empty: payouts still work, but nobody is told when an investor's bank refuses one."
  warn "  Stripe -> Developers -> Webhooks -> endpoint https://api.capimaxpropshare.com/api/v1/payments/webhooks/stripe-payouts"
  warn "  ('Events on Connected accounts': account.updated, payout.paid, payout.failed) -> its signing secret into .env, then systemctl restart capimax"
fi

if [ "$MODE" = on ]; then
# ---------------------------------------------------------------------------------------------
say "2. Stripe"
STRIPE_CHECK='
import asyncio, httpx
from app.core.config import get_settings

async def main():
    key = get_settings().stripe_secret_key
    async with httpx.AsyncClient(base_url="https://api.stripe.com", auth=(key, ""), timeout=20) as c:
        acc = await c.get("/v1/accounts", params={"limit": 1})
        bal = await c.get("/v1/balance")
    print("CONNECT", acc.status_code, (acc.json().get("error") or {}).get("message", "") if acc.status_code != 200 else "")
    if bal.status_code == 200:
        usd = [b for b in bal.json().get("available", []) if b.get("currency") == "usd"]
        print("BALANCE", "%.2f" % ((usd[0]["amount"] if usd else 0) / 100))
    else:
        print("BALANCE ?", (bal.json().get("error") or {}).get("message", ""))

asyncio.run(main())
'
OUT=$(py "$STRIPE_CHECK") || die "could not reach Stripe from this server (see above)"
CONNECT=$(grep '^CONNECT' <<<"$OUT")
case "$CONNECT" in
  "CONNECT 200"*) ok "the key can use Stripe Connect" ;;
  *) die "the Stripe key cannot use Connect: ${CONNECT#CONNECT } (a restricted key needs Connect permissions: Accounts and Transfers: Write, Payouts: Read)" ;;
esac
BAL=$(grep '^BALANCE' <<<"$OUT" | cut -d' ' -f2-)
ok "platform's available Stripe balance: \$$BAL USD"
warn "payouts are paid from this balance; when it is short, a withdrawal waits for an admin with the money still held"

# ---------------------------------------------------------------------------------------------
say "3. Withdrawal jobs"
CRON=$(crontab -u "$APP_USER" -l 2>/dev/null || true)
grep -q 'withdrawals/execute' <<<"$CRON" && ok "the payout job is scheduled" \
  || warn "no 'withdrawals/execute' job in $APP_USER's crontab: an approved withdrawal over the limit is only sent when someone runs it (small ones still go at once)"
grep -q 'withdrawals/reconcile' <<<"$CRON" && ok "the reconcile job is scheduled" \
  || warn "no 'withdrawals/reconcile' job in $APP_USER's crontab"
fi

# ---------------------------------------------------------------------------------------------
say "4. The switch"
NEW=$([ "$MODE" = on ] && echo bank || echo "")
SWITCH="
import asyncio
from app.core.audit import write_audit
from app.core.db import session_scope
from app.models.investments import PlatformSetting
from app.services import settings_service, withdrawal_service

async def main():
    settings_service.validate_setting('payout_auto_methods', '$NEW')
    async with session_scope() as s:
        row = await s.get(PlatformSetting, 'payout_auto_methods')
        before = row.value if row else None
        if row is None:
            s.add(PlatformSetting(key='payout_auto_methods', value='$NEW',
                                  description='Withdrawal methods paid by their provider (bank = Stripe Connect)'))
        else:
            row.value = '$NEW'
        await write_audit(s, action='payments.settings_changed', entity_type='platform_setting',
                          entity_id='payout_auto_methods', before={'value': before}, after={'value': '$NEW'})
    async with session_scope() as s:
        print('BANK', 'manual' if await withdrawal_service.is_manual_for(s, 'bank') else 'automatic')
        print('CRYPTO', 'manual' if await withdrawal_service.is_manual_for(s, 'crypto') else 'automatic')
        print('LIMIT', await settings_service.get_setting(s, 'withdrawal_auto_approve_limit'))
        print('INSTANT', await settings_service.get_setting(s, 'payout_instant_enabled'))

asyncio.run(main())
"
OUT=$(py "$SWITCH") || die "the setting was not changed (see above)"
BANK=$(grep '^BANK' <<<"$OUT" | cut -d' ' -f2)
if [ "$MODE" = on ]; then
  [ "$BANK" = automatic ] || die "bank withdrawals are still manual after the switch: Stripe is not seen as configured by the app"
  ok "bank withdrawals: AUTOMATIC through Stripe Connect"
else
  ok "bank withdrawals: manual again (an admin pays them and presses Mark paid)"
fi
ok "crypto withdrawals: $(grep '^CRYPTO' <<<"$OUT" | cut -d' ' -f2)"
ok "auto-approve limit: \$$(grep '^LIMIT' <<<"$OUT" | cut -d' ' -f2) (above it, an admin presses Approve and Stripe pays)"
ok "instant payouts: $(grep '^INSTANT' <<<"$OUT" | cut -d' ' -f2)"

if [ "$MODE" = on ]; then
  WAITING=$(psql_db -c "SELECT count(*) || ' ($' || COALESCE(sum(amount), 0) || ')' FROM withdrawals WHERE method = 'bank' AND status IN ('pending_review', 'approved')")
  [ "${WAITING%% *}" != 0 ] && warn "bank withdrawals already waiting from before: $WAITING. Pay those by hand as before and press Mark paid (or Reject): they were asked for with a saved bank account, not through Stripe." \
    || ok "no bank withdrawal waiting from before"
  LINKED=$(psql_db -c "SELECT count(*) FILTER (WHERE payouts_enabled) || ' ready, ' || count(*) || ' started' FROM connect_accounts")
  ok "investors linked to Stripe so far: $LINKED"
fi

say "Done"
if [ "$MODE" = on ]; then
  echo "   Investors: Wallet -> Withdraw -> Bank -> 'Link bank account' (once, on Stripe), then"
  echo "   withdraw; up to the limit the money is sent at once. Stripe Connect reaches banks in"
  echo "   the US, UK, EEA, Canada and Switzerland only: an investor elsewhere cannot link a bank."
  echo "   Back to manual: bash backend/scripts/enable_stripe_payouts.sh --off"
fi
