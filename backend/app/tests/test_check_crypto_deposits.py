"""scripts/check_crypto_deposits.py — reading a crypto deposit's state on the server.

* a payment's verdict follows what NOWPayments reports: paid less than the invoice, never
  notified, still processing, finished there but not settled here;
* only the payment notifications are read from the nginx log (not the payout ones), and a 401
  among them is called out as a wrong IPN secret;
* an invoice below every coin's minimum is shown as payable with no coin;
* nothing is written, and no key reaches the output.
"""

# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


envtools = _load("fix_stripe_webhook_secret")
check = _load("check_crypto_deposits")

KEY = "NP0ProdKey000000000000000"
IPN = "IpnSecret0000000000000000"
ROWS = "\n".join(
    "\t".join(cells)
    for cells in (
        # id, created, status, purpose, amount, captured, invoice, member, events, np ids, age
        (
            "p-under",
            "2026-10-06 10:00",
            "pending",
            "deposit",
            "13.00",
            "",
            "4455",
            "cl***@x.com",
            "waiting 10:01, partially_paid 10:09",
            "5001",
            "300",
        ),
        (
            "p-silent",
            "2026-10-06 11:00",
            "pending",
            "deposit",
            "5.00",
            "",
            "4456",
            "ot***@x.com",
            "",
            "",
            "200",
        ),
        (
            "p-paid",
            "2026-10-03 09:00",
            "succeeded",
            "deposit",
            "50.00",
            "50.00",
            "4400",
            "cl***@x.com",
            "waiting 09:00, confirming 09:02, finished 09:10",
            "4900",
            "5000",
        ),
    )
)
MINIMUMS = {"btc": 18.4, "usdttrc20": 9.2, "bnbbsc": 6.0}
PAYMENTS = {
    "5001": '{"payment_id":5001,"payment_status":"partially_paid","pay_currency":"usdtbsc",'
    '"pay_amount":13.02,"actually_paid":12.4,"outcome_amount":12.1,'
    '"outcome_currency":"usdttrc20","updated_at":"2026-10-06T10:09:00.000Z"}',
    "4900": '{"payment_id":4900,"payment_status":"finished","pay_currency":"btc",'
    '"pay_amount":0.0005,"actually_paid":0.0005,"updated_at":"2026-10-03T09:10:00.000Z"}',
    # a deposit recovered from another network: its own payment, tied to the first by its parent
    "7770": '{"payment_id":7770,"parent_payment_id":5001,"payment_status":"finished",'
    '"pay_currency":"usdterc20","pay_amount":13.02,"actually_paid":12.98,"order_id":null,'
    '"invoice_id":4455,"updated_at":"2026-10-06T10:30:00.000Z"}',
}
UNMATCHED = "7770\tfinished\t2026-10-06 10:30\n"
LOG = (
    '1.2.3.4 - - [03/Oct/2026:09:10:01 +0000] "POST /api/v1/payments/webhooks/nowpayments HTTP/1.1" 200 31 "-" "np"\n'
    '1.2.3.4 - - [06/Oct/2026:10:09:02 +0000] "POST /api/v1/payments/webhooks/nowpayments HTTP/1.1" 200 31 "-" "np"\n'
    '1.2.3.4 - - [06/Oct/2026:10:20:00 +0000] "POST /api/v1/payments/webhooks/nowpayments HTTP/1.1" 401 60 "-" "np"\n'
    '1.2.3.4 - - [06/Oct/2026:10:21:00 +0000] "POST /api/v1/payments/webhooks/nowpayments-payouts HTTP/1.1" 401 60 "-" "np"\n'
    '1.2.3.4 - - [06/Oct/2026:10:22:00 +0000] "GET /api/v1/properties HTTP/1.1" 200 900 "-" "x"\n'
)


def _http(method, url, *, body=None, headers=None):
    if url.endswith("/status"):
        return 200, '{"message":"OK"}'
    if (headers or {}).get("x-api-key") != KEY:
        return 403, '{"code":"INVALID_API_KEY"}'
    if url.endswith("/merchant/coins"):
        return 200, '{"selectedCurrencies":["BTC","USDTTRC20","BNBBSC"]}'
    if "/payment/" in url:
        return 200, PAYMENTS[url.rsplit("/", 1)[-1]]
    if "/min-amount?currency_from=" in url:
        coin = url.split("currency_from=")[1].split("&")[0]
        return 200, f'{{"min_amount":1,"fiat_equivalent":{MINIMUMS[coin]}}}'
    return None, "unexpected"


def _setup(monkeypatch, tmp_path, env_text: str, unmatched: str = ""):
    env = tmp_path / ".env"
    env.write_text(env_text, encoding="utf-8")
    (tmp_path / "access.log").write_text(LOG, encoding="utf-8")
    monkeypatch.setattr(check.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(check, "ACCESS_LOGS", str(tmp_path / "access.log*"))
    monkeypatch.setattr(check.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(envtools, "ENV_FILE", env)
    monkeypatch.setattr(envtools, "service_environment", lambda: {})
    monkeypatch.setattr(envtools, "_http", _http)
    monkeypatch.setattr(
        envtools, "_run", lambda cmd: unmatched if "audit_log" in cmd[-1] else ROWS + "\n"
    )
    return env


def test_only_payment_notifications_are_read_from_the_log():
    assert check.webhook_answers(LOG.splitlines()) == [
        ("03/Oct/2026:09:10:01 +0000", 200),
        ("06/Oct/2026:10:09:02 +0000", 200),
        ("06/Oct/2026:10:20:00 +0000", 401),
    ]


def test_a_payment_is_judged_by_what_nowpayments_reports():
    row = check.parse_rows(ROWS)[1]  # pending, never notified
    assert check.verdict(row, None)[0] == "act"
    assert check.verdict({**row, "age_min": "3"}, None) == (
        "wait",
        "open: NOWPayments has reported nothing yet",
    )
    chosen = {**row, "events": "waiting 11:01"}
    assert "another network or coin" in check.verdict(chosen, None)[1]
    assert check.verdict({**chosen, "age_min": "5"}, None)[0] == "wait"
    assert check.verdict(chosen, {"payment_status": "confirming"})[0] == "wait"
    kind, why = check.verdict(chosen, {"payment_status": "finished"})
    assert kind == "act" and "has not settled it" in why
    assert check.verdict(chosen, {"payment_status": "expired"})[0] == "act"
    assert check.verdict({**row, "status": "failed"}, None)[0] == "ok"
    # several records under one invoice: the finished one decides, then the under-paid one
    waiting, partial, done = (
        {"payment_id": 1, "payment_status": "waiting"},
        {"payment_id": 2, "payment_status": "partially_paid"},
        {"payment_id": 3, "payment_status": "finished", "parent_payment_id": 1},
    )
    assert check.leading([waiting, partial, done]) is done
    assert check.leading([waiting, partial]) is partial and check.leading([]) is None
    assert "an extra deposit on payment 1" in check.describe(done)
    # the whole record is shown for the unusual ones only, never with the payer's email
    assert check.unusual(partial) and check.unusual(done) and not check.unusual(waiting)
    assert check.whole({"payment_id": 2, "customer_email": "a@b.c"}) == '{"payment_id":2}'
    # sandbox is the API's default until the flag says otherwise
    assert check.sandbox(None) and check.sandbox("true") and not check.sandbox("false")
    assert (
        check.payable(MINIMUMS, 10) == ["bnbbsc", "usdttrc20"] and check.payable(MINIMUMS, 5) == []
    )


def test_the_report_names_what_needs_a_person_and_shows_no_key(monkeypatch, tmp_path, capsys):
    env_text = (
        "DATABASE_URL=postgresql+asyncpg://u:p@localhost/capimaxpropshare\n"
        f"NOWPAYMENTS_API_KEY={KEY}\nNOWPAYMENTS_IPN_SECRET={IPN}\nNOWPAYMENTS_SANDBOX=false\n"
    )
    env = _setup(monkeypatch, tmp_path, env_text)
    assert check.main() == 0
    out = capsys.readouterr()
    text = out.out
    assert "mode: production" in text and "3 coin(s) switched on" in text
    assert "NOWPayments 5001: partially_paid; coin usdtbsc; asked 13.02, received 12.4" in text
    assert "matched no payment" not in text
    assert "paid LESS than the invoice (asked 13.02, received 12.4)" in text
    assert "NOWPayments never notified the platform about it" in text
    assert "settled: 50.00 USD" in text
    assert "3 in 1 log file(s): HTTP 200 x2, HTTP 401 x1" in text
    assert "NOWPAYMENTS_IPN_SECRET is not the IPN secret of this NOWPayments account" in text
    assert "an invoice of 5 USD: 0 of 3 coin(s) take it" in text
    assert "an invoice of 13 USD: 2 of 3 coin(s) take it" in text
    assert "no coin takes less than 6.00 USD now" in text
    summary = text.split("== Summary")[1]
    assert "13.00 USD (cl***@x.com)" in summary and "5.00 USD (ot***@x.com)" in summary
    assert "notifications are refused (wrong IPN secret)" in summary
    for secret in (KEY, IPN):
        assert secret not in text + out.err
    assert env.read_text(encoding="utf-8") == env_text  # read only


def test_without_keys_it_says_crypto_is_off(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path, "NOWPAYMENTS_API_KEY=\n")
    assert check.main() == 1
    assert "crypto is off on the site" in capsys.readouterr().err


def test_an_account_with_no_coin_switched_on_is_called_out(monkeypatch, tmp_path, capsys):
    env_text = (
        f"NOWPAYMENTS_API_KEY={KEY}\nNOWPAYMENTS_IPN_SECRET={IPN}\nNOWPAYMENTS_SANDBOX=false\n"
    )
    _setup(monkeypatch, tmp_path, env_text)

    def no_coins(method, url, *, body=None, headers=None):
        if url.endswith("/merchant/coins"):
            return 200, '{"selectedCurrencies":[]}'
        return _http(method, url, body=body, headers=headers)

    monkeypatch.setattr(envtools, "_http", no_coins)
    assert check.main() == 0
    text = capsys.readouterr().out
    assert "NO coin is switched on: every invoice page is empty" in text
    assert "no coin to ask about" in text


ENV = f"NOWPAYMENTS_API_KEY={KEY}\nNOWPAYMENTS_IPN_SECRET={IPN}\nNOWPAYMENTS_SANDBOX=false\n"


def test_a_notification_that_matched_no_payment_is_looked_up(monkeypatch, tmp_path, capsys):
    """A deposit recovered from another coin or network is its own NOWPayments payment: when
    its notification carries no order of ours the platform cannot place it, and says so."""
    _setup(monkeypatch, tmp_path, ENV, unmatched=UNMATCHED)
    assert check.main() == 0
    text = capsys.readouterr().out
    assert "1 notification(s) in 14 days matched no payment of the platform" in text
    assert "2026-10-06 10:30  'finished'  NOWPayments 7770: finished; coin usdterc20" in text
    assert "received 12.98; an extra deposit on payment 5001" in text
    assert '"invoice_id":4455,"order_id":null,"parent_payment_id":5001' in text
    assert "could not match" in text.split("== Summary")[1]


def test_the_minimum_is_asked_again_with_the_pair_spelled_out(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path, ENV)

    def wants_the_pair(method, url, *, body=None, headers=None):
        if "/min-amount?" in url and "currency_to=" not in url:
            return 400, '{"message":"currency_to is required"}'
        return _http(method, url, body=body, headers=headers)

    monkeypatch.setattr(envtools, "_http", wants_the_pair)
    assert check.main() == 0
    assert "an invoice of 13 USD: 2 of 3 coin(s) take it" in capsys.readouterr().out
