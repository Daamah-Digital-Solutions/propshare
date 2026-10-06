"""Crypto deposits: what the platform and NOWPayments each know about them (read only).

A member says "I paid in crypto and nothing arrived", or the NOWPayments page offered no coin
to pay with. Run this on the VPS as root: it changes nothing and prints no key.

  1. the NOWPayments account the API uses: mode, whether the key is accepted, the coins
     switched on;
  2. the latest crypto payments of the platform, each with the notifications (IPN) received
     for it and what NOWPayments says about it now (coin, amount asked and received), and
     the notifications that matched no payment (a deposit recovered from another network);
  3. how the API answered NOWPayments' notifications lately, from the nginx access log (a 401
     means the IPN secret is not this account's: nothing can be credited);
  4. the smallest payment each coin takes right now, and how many coins an invoice of a given
     amount can be paid with.

A crypto payment is settled by NOWPayments' "finished" notification only. The platform keeps
the INVOICE id; the payment under it is known once a notification arrived, so a payment that
was never notified can only be looked up in the NOWPayments dashboard (Payments).

Usage, on the VPS as root (after ``sudo -u deploy git -C /opt/capimax/app pull``):
    /opt/capimax/venv/bin/python /opt/capimax/app/backend/scripts/check_crypto_deposits.py
"""

from __future__ import annotations

import datetime
import glob
import gzip
import json
import os
import re
import sys
import time
from collections import Counter
from urllib.parse import quote, urlparse

import fix_stripe_webhook_secret as envtools

API_KEY = "NOWPAYMENTS_API_KEY"
IPN_SECRET = "NOWPAYMENTS_IPN_SECRET"
SANDBOX_FLAG = "NOWPAYMENTS_SANDBOX"
BASES = {False: "https://api.nowpayments.io/v1", True: "https://api-sandbox.nowpayments.io/v1"}
WEBHOOK_PATH = "/api/v1/payments/webhooks/nowpayments"
ACCESS_LOGS = os.environ.get("CAPIMAX_ACCESS_LOGS", "/var/log/nginx/*access*log*")
LATEST = 12  # payments shown
MAX_COINS = 150  # minimums asked for, one request each
PAUSE = 0.12  # seconds between those requests
AMOUNTS = (5, 10, 13, 20, 25, 50, 100)  # invoice sizes checked against the minimums
FRESH_MINUTES = 20  # an invoice younger than this may simply not be paid yet

_ROW = (
    "id",
    "created",
    "status",
    "purpose",
    "amount",
    "captured",
    "invoice",
    "member",
    "events",
    "np_ids",
    "age_min",
)
# One row per payment, newest first. The member's email is cut to its first two letters; a
# NOWPayments payment id is the part of an event id before the colon (payment_service).
PAYMENTS_SQL = rf"""
SELECT p.id,
       to_char(p.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI'),
       p.status, p.purpose, p.amount,
       coalesce(p.amount_captured::text, ''),
       coalesce(p.provider_payment_id, ''),
       regexp_replace(u.email, '^(.{{2}})[^@]*', '\1***'),
       coalesce((SELECT string_agg(coalesce(e.type, '?') || ' '
                                   || to_char(e.created_at AT TIME ZONE 'UTC', 'HH24:MI'),
                                   ', ' ORDER BY e.created_at)
                   FROM payment_events e WHERE e.payment_id = p.id), ''),
       coalesce((SELECT string_agg(DISTINCT split_part(e.event_id, ':', 1), ',')
                   FROM payment_events e WHERE e.payment_id = p.id), ''),
       round(extract(epoch FROM now() - p.created_at) / 60)
  FROM payments p JOIN users u ON u.id = p.user_id
 WHERE p.provider = 'nowpayments'
 ORDER BY p.created_at DESC
 LIMIT {LATEST}
"""
# Notifications that matched no payment of the platform (payment_service audits each): a
# NOWPayments payment id is all digits, a Stripe one is not.
UNMATCHED_SQL = (
    "SELECT entity_id, coalesce(after->>'type', '?'),"
    " to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI')"
    " FROM audit_log WHERE action = 'payment.webhook.unmatched' AND entity_id ~ '^[0-9]+$'"
    " AND created_at > now() - interval '14 days' ORDER BY created_at DESC LIMIT 8"
)
_LOG_LINE = re.compile(r'\[([^\]]+)\] "POST (\S+)[^"]*" (\d{3}) ')
_PROCESSING = ("confirming", "confirmed", "sending")
_CLOSED = ("expired", "failed", "refunded")
_RANK = {"finished": 0, "partially_paid": 1, "sending": 2, "confirmed": 3, "confirming": 4}


# --- pure helpers (unit-tested) ------------------------------------------------------------ #
def sandbox(flag: str | None) -> bool:
    """The API's own rule: NOWPAYMENTS_SANDBOX is true unless set otherwise (Settings)."""
    return str("true" if flag is None else flag).strip().lower() in ("1", "true", "yes", "on")


def parse_rows(out: str) -> list[dict]:
    rows = []
    for line in out.splitlines():
        cells = line.split("\t")
        if len(cells) == len(_ROW):
            rows.append(dict(zip(_ROW, cells, strict=True)))
    return rows


def webhook_answers(lines) -> list[tuple[str, int]]:
    """(time, HTTP status) of every NOWPayments payment notification in nginx log lines."""
    found = []
    for line in lines:
        if WEBHOOK_PATH not in line:
            continue
        m = _LOG_LINE.search(line)
        if m and m.group(2).split("?")[0].rstrip("/") == WEBHOOK_PATH:
            found.append((m.group(1), int(m.group(3))))
    return found


def _log_time(stamp: str) -> datetime.datetime:
    try:
        return datetime.datetime.strptime(stamp, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return datetime.datetime.min.replace(tzinfo=datetime.UTC)


def payable(minimums: dict[str, float], amount: float) -> list[str]:
    """The coins whose smallest payment is not above ``amount`` (both in USD)."""
    return sorted(coin for coin, usd in minimums.items() if usd <= amount)


def describe(payment: dict) -> str:
    """NOWPayments' own record of a payment, on one line."""
    line = (
        f"{payment.get('payment_id')}: {payment.get('payment_status')}; coin"
        f" {payment.get('pay_currency')}; asked {payment.get('pay_amount')}, received"
        f" {payment.get('actually_paid')}"
    )
    if payment.get("outcome_amount") is not None:
        line += f"; settles {payment.get('outcome_amount')} {payment.get('outcome_currency')}"
    if payment.get("parent_payment_id"):
        # a second deposit on the same address, or one recovered from another coin or network
        line += f"; an extra deposit on payment {payment.get('parent_payment_id')}"
    return f"{line}; updated {payment.get('updated_at')}"


def unusual(payment: dict) -> bool:
    """An under-paid payment or an extra deposit: the ones whose whole record is worth reading."""
    return payment.get("payment_status") == "partially_paid" or bool(
        payment.get("parent_payment_id")
    )


def whole(payment: dict) -> str:
    """Everything NOWPayments holds on a payment, on one line, without the payer's email."""
    kept = {name: value for name, value in payment.items() if "email" not in name.lower()}
    return json.dumps(kept, separators=(",", ":"), sort_keys=True)


def leading(records: list[dict]) -> dict | None:
    """The record that decides a payment: a finished one, else an under-paid one, else the
    one furthest on (an invoice can hold several: extra and recovered deposits)."""
    if not records:
        return None
    return min(records, key=lambda r: _RANK.get(str(r.get("payment_status")), len(_RANK)))


def verdict(row: dict, latest: dict | None) -> tuple[str, str]:
    """What one crypto payment needs: ("ok" | "wait" | "act", why). ``latest`` is NOWPayments'
    own record that decides it (``leading``), None when it could not be asked."""
    status = row["status"]
    age = int(float(row["age_min"] or 0))
    if status == "succeeded":
        return "ok", f"settled: {row['captured'] or row['amount']} USD"
    if status != "pending":
        return "ok", f"closed as {status}: nothing was credited"
    state = (latest or {}).get("payment_status")
    if state is None and row["events"]:
        state = row["events"].rsplit(", ", 1)[-1].split(" ")[0]  # the last notification
    if state is None:
        if age < FRESH_MINUTES:
            return "wait", "open: NOWPayments has reported nothing yet"
        return "act", (
            "NOWPayments never notified the platform about it: not paid, paid on another coin"
            " or network than the one chosen on the invoice, or its notifications are refused"
            " (step 3). Find the invoice in the NOWPayments dashboard -> Payments"
        )
    if state == "waiting":
        if age < FRESH_MINUTES:
            return "wait", "a coin was chosen; no funds seen on its address yet"
        return "act", (
            "a coin was chosen but NOWPayments saw no funds on that coin and network: not"
            " sent, or sent on another network or coin (dashboard -> Payments, label"
            " 'Wrong Asset')"
        )
    if state in _PROCESSING:
        return "wait", f"funds seen; NOWPayments is at '{state}': settled when it says finished"
    if state == "partially_paid":
        got = (latest or {}).get("actually_paid", "less")
        asked = (latest or {}).get("pay_amount", "the amount")
        return "act", (
            f"paid LESS than the invoice (asked {asked}, received {got}): the platform does"
            " not settle an under-payment by itself. If the gap is small, set the payment to"
            " Finished in the NOWPayments dashboard: its 'finished' notification settles it"
        )
    if state == "finished":
        return "act", (
            "NOWPayments finished it but the platform has not settled it: the 'finished'"
            " notification was refused or lost (step 3). Send it again from the payment's"
            " page in the NOWPayments dashboard"
        )
    if state in _CLOSED:
        return "act", f"NOWPayments closed it as '{state}'; the platform still shows it pending"
    return "wait", f"NOWPayments says '{state}'"


# --- the server ---------------------------------------------------------------------------- #
def np_get(base: str, path: str, key: str) -> tuple[int | None, dict | None]:
    status, text = envtools._http("GET", base + path, headers={"x-api-key": key})
    if status != 200:
        return status, None
    try:
        data = json.loads(text)
    except ValueError:
        return status, None
    return status, data if isinstance(data, dict) else None


def _psql(dotenv: dict[str, str | None], sql: str) -> str | None:
    _, url = envtools.lookup(dotenv, "DATABASE_URL")
    database = urlparse(url or "").path.lstrip("/") or "capimaxpropshare"
    return envtools._run(
        ["sudo", "-u", "postgres", "psql", "-d", database, "-qtAX", "-F", "\t", "-c", sql]
    )


def read_access_logs() -> tuple[list[tuple[str, int]], int] | None:
    """Every notification the kept nginx logs hold, oldest first, and how many files."""
    files = sorted(glob.glob(ACCESS_LOGS))
    if not files:
        return None
    found: list[tuple[str, int]] = []
    for path in files:
        opener = gzip.open if path.endswith(".gz") else open
        try:
            with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
                found.extend(webhook_answers(fh))
        except OSError:
            continue
    return sorted(found, key=lambda hit: _log_time(hit[0])), len(files)


def main() -> int:
    say, ok, warn, info, stop = (
        envtools.say,
        envtools.ok,
        envtools.warn,
        envtools.info,
        envtools.stop,
    )
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return stop("run this as root: it reads the API's .env, the database and the nginx log")
    if not envtools.ENV_FILE.is_file():
        return stop(f"{envtools.ENV_FILE} not found (set CAPIMAX_ENV_FILE)")
    _, dotenv = envtools._read_env()
    proc = envtools.service_environment()
    key, _ = envtools.loaded_value(API_KEY, dotenv, proc)
    ipn, _ = envtools.loaded_value(IPN_SECRET, dotenv, proc)
    flag, _ = envtools.loaded_value(SANDBOX_FLAG, dotenv, proc)
    test_mode = sandbox(flag)
    base = BASES[test_mode]
    attention: list[str] = []

    say("1. The NOWPayments account the API uses")
    info(f"mode: {'SANDBOX (test coins, no real money)' if test_mode else 'production'}")
    info(f"API key: {'set' if key else 'NOT SET'}; IPN secret: {'set' if ipn else 'NOT SET'}")
    if not key or not ipn:
        return stop("crypto is off on the site until both are set (set_nowpayments_keys.py)")
    status, _text = envtools._http("GET", base + "/status")
    (ok if status == 200 else warn)(
        "NOWPayments API is up" if status == 200 else f"NOWPayments API answers {status}"
    )
    status, data = np_get(base, "/merchant/coins", key)
    coins = [str(c).lower() for c in (data or {}).get("selectedCurrencies") or []]
    coins = coins or [str(c).lower() for c in (data or {}).get("currencies") or []]
    if status != 200:
        warn(f"NOWPayments refuses the API key here (HTTP {status}): no invoice can be made")
        attention.append("the API key is refused by NOWPayments")
    elif not coins:
        warn("the key is accepted but NO coin is switched on: every invoice page is empty")
        info("NOWPayments dashboard -> Settings -> Payments -> Payment details: switch coins on")
        attention.append("no coin is switched on in the NOWPayments account")
    else:
        ok(f"key accepted; {len(coins)} coin(s) switched on")
        info(", ".join(coins[:60]) + (" ..." if len(coins) > 60 else ""))

    say(f"2. The latest {LATEST} crypto payments (times in UTC)")
    out = _psql(dotenv, PAYMENTS_SQL)
    rows = parse_rows(out or "")
    if out is None:
        warn("could not read the database (sudo -u postgres psql)")
    elif not rows:
        info("no crypto payment was ever started")
    for row in rows:
        records = []
        for np_id in filter(None, row["np_ids"].split(",")):
            _status, found = np_get(base, f"/payment/{quote(np_id, safe='')}", key)
            if found:
                records.append(found)
        kind, why = verdict(row, leading(records))
        print(
            f"   {row['created']}  {row['amount']:>10} USD  {row['purpose']:<11}"
            f" {row['status']:<9} {row['member']}"
        )
        info(f"invoice {row['invoice'] or '(none)'} | platform payment {row['id']}")
        info(f"notifications received: {row['events'] or 'none'}")
        for record in records:
            info(f"NOWPayments {describe(record)}")
            if unusual(record):
                info(f"   whole record: {whole(record)}")
        {"ok": ok, "wait": info, "act": warn}[kind](why)
        if kind == "act":
            attention.append(f"{row['created']} {row['amount']} USD ({row['member']}): {why}")
    unmatched = [line.split("\t") for line in (_psql(dotenv, UNMATCHED_SQL) or "").splitlines()]
    unmatched = [cells for cells in unmatched if len(cells) == 3]
    if unmatched:
        warn(f"{len(unmatched)} notification(s) in 14 days matched no payment of the platform:")
        for np_id, state, when in unmatched:
            _status, found = np_get(base, f"/payment/{quote(np_id, safe='')}", key)
            info(f"{when}  '{state}'  NOWPayments {describe(found) if found else np_id}")
            if found:
                info(f"   whole record: {whole(found)}")
        attention.append("NOWPayments reported payment(s) the platform could not match (step 2)")

    say("3. How the API answered NOWPayments' notifications")
    logs = read_access_logs()
    if logs is None:
        info(f"no nginx access log found ({ACCESS_LOGS})")
    else:
        answers, files = logs
        if not answers:
            info(f"none in the {files} log file(s) kept: NOWPayments did not call the API")
        else:
            counts = Counter(code for _when, code in answers)
            info(
                f"{len(answers)} in {files} log file(s): "
                + ", ".join(f"HTTP {code} x{n}" for code, n in sorted(counts.items()))
            )
            for when, code in answers[-6:]:
                info(f"{when}  ->  {code}")
            if counts.get(401):
                warn(
                    "401 = the signature did not match: NOWPAYMENTS_IPN_SECRET is not the IPN"
                    " secret of this NOWPayments account, so nothing it reports is settled."
                    " Set it with scripts/set_nowpayments_keys.py"
                )
                attention.append("notifications are refused (wrong IPN secret)")
            if any(code >= 500 or code == 429 for code in counts):
                warn("some notifications were not taken (429 or 5xx): journalctl -u capimax")
            if set(counts) == {200}:
                ok("every notification was accepted")

    say("4. The smallest payment each coin takes now (USD)")
    asked = coins[:MAX_COINS]
    if len(coins) > MAX_COINS:
        info(f"asking for the first {MAX_COINS} of the {len(coins)} coins")
    minimums: dict[str, float] = {}
    for coin in asked:
        # towards the account's own outcome currency; if NOWPayments wants the pair spelled
        # out, the coin kept as it is
        path = f"/min-amount?currency_from={quote(coin, safe='')}&fiat_equivalent=usd"
        for query in (path, f"{path}&currency_to={quote(coin, safe='')}"):
            _status, found = np_get(base, query, key)
            usd = (found or {}).get("fiat_equivalent")
            time.sleep(PAUSE)
            if isinstance(usd, int | float):
                minimums[coin] = float(usd)
                break
    if not minimums:
        info("NOWPayments gave no minimum" if asked else "no coin to ask about")
    else:
        ranked = sorted(minimums.items(), key=lambda item: item[1])
        info("lowest:  " + ", ".join(f"{c} {usd:.2f}" for c, usd in ranked[:8]))
        info("highest: " + ", ".join(f"{c} {usd:.2f}" for c, usd in ranked[-4:]))
        if len(minimums) < len(asked):
            info(f"{len(asked) - len(minimums)} coin(s) gave no minimum and are not counted")
        for amount in AMOUNTS:
            count = len(payable(minimums, amount))
            line = f"an invoice of {amount} USD: {count} of {len(minimums)} coin(s) take it"
            (warn if count == 0 else info)(line)
        floor = ranked[0][1]
        info(f"no coin takes less than {floor:.2f} USD now; these minimums move with network fees")
        info("the platform itself accepts a crypto deposit of any amount above 0")

    say("Summary")
    if attention:
        for line in attention:
            warn(line)
    else:
        ok("nothing here needs a person")
    return 0


if __name__ == "__main__":
    sys.exit(main())
