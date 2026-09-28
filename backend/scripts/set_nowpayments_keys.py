"""Set or replace the NOWPayments (crypto) keys the API uses (run as root on the VPS).

Crypto payments go through NOWPayments with two values from its dashboard (Settings ->
Payments): the API key, and the IPN secret NOWPayments signs its "paid" notifications with.
This asks for them without showing them, checks the API key with NOWPayments itself —
production or sandbox, whichever accepts it, and how many coins the account has switched on —
writes exactly one line for each in .env (the previous .env kept beside it), restarts the API
and checks the crypto option is live on the property pages. Enter on a question keeps the
current value.

The secrets are never printed, logged, written anywhere but .env, or passed on a command line.
The .env handling is shared with fix_stripe_webhook_secret.py.

Usage, on the VPS as root (after ``sudo -u deploy git -C /opt/capimax/app pull``):
    /opt/capimax/venv/bin/python /opt/capimax/app/backend/scripts/set_nowpayments_keys.py
"""

from __future__ import annotations

import getpass
import hmac
import json
import os
import sys

import fix_stripe_webhook_secret as envtools

API_KEY = "NOWPAYMENTS_API_KEY"
IPN_SECRET = "NOWPAYMENTS_IPN_SECRET"
SANDBOX_FLAG = "NOWPAYMENTS_SANDBOX"
BASES = (
    ("production", "https://api.nowpayments.io/v1"),
    ("sandbox", "https://api-sandbox.nowpayments.io/v1"),
)
OPTIONS_PATH = "/api/v1/investments/payment-options"


def value_problem(value: str) -> str | None:
    """Why ``value`` cannot be a NOWPayments key or IPN secret, or None when it can."""
    if value.startswith(("sk_", "rk_", "pk_", "whsec_")):
        return "that is a Stripe value, not a NOWPayments one"
    if len(value) < 8 or any(ch.isspace() for ch in value):
        return "that does not look like a NOWPayments key: copy it whole, without spaces"
    return None


def check_key(api_key: str) -> tuple[str | None, str]:
    """Which NOWPayments accepts the key: ("production" | "sandbox" | None, detail). It asks
    for the account's own coins (/merchant/coins) because, unlike /currencies, that refuses a
    wrong key."""
    unreachable = []
    for mode, base in BASES:
        status, text = envtools._http(
            "GET", f"{base}/merchant/coins", headers={"x-api-key": api_key}
        )
        if status == 200:
            try:
                coins = json.loads(text).get("selectedCurrencies") or []
            except (ValueError, AttributeError):
                coins = []
            return mode, f"{len(coins)} coin(s) switched on in the account"
        if status is None:
            unreachable.append(f"{base} unreachable ({text[:80]})")
    if len(unreachable) == len(BASES):
        return None, "; ".join(unreachable)
    return None, "NOWPayments refused this API key (production and sandbox)"


def crypto_live() -> bool | None:
    """Whether the property pages offer crypto now (None: the API does not say — an API from
    before release_payment_methods.sh)."""
    status, text = envtools._http("GET", envtools.API_LOCAL + OPTIONS_PATH)
    if status != 200:
        return None
    try:
        return bool(json.loads(text).get("crypto"))
    except (ValueError, AttributeError):
        return None


def ask(prompt: str) -> str:
    for _ in range(3):
        try:
            value = envtools.clean_pasted(getpass.getpass(prompt))
        except (EOFError, KeyboardInterrupt):
            print()
            return ""
        if not value:
            return ""
        problem = value_problem(value)
        if problem is None:
            return value
        envtools.warn(problem)
    return ""


def _live_note(live: bool | None) -> str:
    return {True: "offered", False: "shown as not available", None: "unknown"}[live]


def main() -> int:
    say, ok, warn, info, stop = (
        envtools.say,
        envtools.ok,
        envtools.warn,
        envtools.info,
        envtools.stop,
    )
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return stop("run this as root: it edits the API's .env and restarts the API")
    if not envtools.ENV_FILE.is_file():
        return stop(f"{envtools.ENV_FILE} not found (set CAPIMAX_ENV_FILE)")

    say("1. What the API uses now")
    text, dotenv = envtools._read_env()
    proc = envtools.service_environment()
    for key in (API_KEY, IPN_SECRET):
        value, source = envtools.loaded_value(key, dotenv, proc)
        info(f"{key}: {envtools.fingerprint(value)} (from {source})")
    flag, _ = envtools.loaded_value(SANDBOX_FLAG, dotenv, proc)
    info(f"mode: {'sandbox' if str(flag).lower() in ('1', 'true', 'yes') else 'production'}")
    info(f"crypto on the property pages: {_live_note(crypto_live())}")

    say("2. The keys, from the NOWPayments dashboard (Settings -> Payments)")
    info("Paste each one here (nothing shows while you paste); Enter keeps the current one.")
    new_key = ask("   API key: ")
    mode = None
    if new_key:
        mode, detail = check_key(new_key)
        if mode is None:
            return stop(f"{detail}: nothing changed")
        ok(f"NOWPayments {mode} accepts the key: {detail}")
        if mode == "sandbox":
            warn("a SANDBOX key: test coins only, no real money")
    new_ipn = ask("   IPN secret: ")
    if not new_key and not new_ipn:
        ok("nothing entered: nothing changed")
        return 0
    if new_key and not new_ipn:
        warn("kept the current IPN secret: it must belong to the same NOWPayments account")

    say("3. Update the API")
    changes = [(k, v) for k, v in ((API_KEY, new_key), (IPN_SECRET, new_ipn)) if v]
    if mode is not None:
        changes.append((SANDBOX_FLAG, "true" if mode == "sandbox" else "false"))
    for key, _ in changes:
        places = envtools.unit_overrides(key)
        if places:
            return stop(
                f"{key} is also set in {', '.join(places)}, which wins over .env: remove it"
                f" there (systemctl cat {envtools.SERVICE}), then run this again"
            )
    new_text = text
    for key, value in changes:
        new_text = envtools.with_single_assignment(new_text, key, value)
    backup = envtools.write_env(new_text, tag="nowpayments")
    ok(f".env updated ({', '.join(k for k, _ in changes)}); the previous one: {backup}")
    if not envtools.restart_api():
        return stop(f"the API did not come back: journalctl -u {envtools.SERVICE} -n 80")
    ok("API restarted and healthy")
    text, dotenv = envtools._read_env()
    proc = envtools.service_environment()
    for key, value in changes:
        loaded, source = envtools.loaded_value(key, dotenv, proc)
        if not hmac.compare_digest((loaded or "").encode(), value.encode()):
            return stop(f"the API still loads another {key} (from {source})")
    ok("the API now loads the new keys")

    say("4. Crypto on the property pages")
    live = crypto_live()
    if live is True:
        ok("crypto is offered on every property")
    elif live is None:
        info("this API does not list its payment methods yet: run release_payment_methods.sh")
    else:
        warn("crypto still shows as not available: check both values and run this again")

    say("Done")
    print("   In the NOWPayments dashboard the account also needs a payout wallet (where the paid")
    print("   crypto goes). The IPN callback URL is sent with every invoice: nothing to set there.")
    print(f"   The .env before this change: {backup}")
    return 0 if live is not False else 1


if __name__ == "__main__":
    sys.exit(main())
