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
        # id, created, status, purpose, amount, captured, invoice, member, events, np ids, age,
        # the coin chosen on the platform, what the platform kept per NOWPayments payment
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
            "",
            "{}",
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
            "usdtbsc",
            "{}",
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
            "btc",
            '{"4900": {"status": "finished", "credited": "50.00"}}',
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
        found = PAYMENTS.get(url.rsplit("/", 1)[-1])
        return (200, found) if found else (404, '{"message":"Payment not found"}')
    if "/min-amount?currency_from=" in url:
        coin = url.split("currency_from=")[1].split("&")[0]
        return 200, f'{{"min_amount":1,"fiat_equivalent":{MINIMUMS[coin]}}}'
    return None, "unexpected"


def _setup(monkeypatch, tmp_path, env_text: str, unmatched: str = ""):
    env = tmp_path / ".env"
    env.write_text(env_text, encoding="utf-8")
    (tmp_path / "access.log").write_text(LOG, encoding="utf-8")
    monkeypatch.setattr(check.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(check.sys, "argv", ["check_crypto_deposits.py"])
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
    assert check.verdict({**row, "status": "failed"}, None) == (
        "ok",
        "closed as failed: nothing was credited",
    )
    # a purchase paid short: not completed, what arrived is in the member's wallet
    kind, why = check.verdict({**row, "status": "failed", "captured": "500.00"}, None)
    assert kind == "ok" and "500.00 USD arrived another way than asked" in why
    # an under-payment still pending was never settled: its notification is sent again
    kind, why = check.verdict(chosen, {"payment_status": "partially_paid"})
    assert kind == "act" and "Send it again" in why and "do not change its status" in why
    # the platform WAS notified of the money and could not value it: said as that, not as a
    # notification refused or lost (2026-10-06: the summary sent staff to press IPN again)
    partial = {"payment_id": 7, "payment_status": "partially_paid", "actually_paid": 13}
    partial["pay_currency"] = "usdtbsc"
    kind, why = check.verdict(chosen, partial, {"7": {"status": "partially_paid", "review": True}})
    assert kind == "act" and "could not tell what it is worth" in why and "13 usdtbsc" in why
    assert "refused or lost" not in why
    kind, why = check.verdict(chosen, partial, {"7": {"status": "partially_paid"}})
    assert kind == "act" and "settled nothing" in why
    # noted only as waiting: the notification of the money itself never arrived
    kind, why = check.verdict(chosen, partial, {"7": {"status": "waiting"}})
    assert "refused or lost" in why
    assert "refused or lost" in check.verdict(chosen, partial, {"8": {"review": True}})[1]
    # what the platform did with each NOWPayments payment under an invoice
    kept = check.kept_records(
        '{"1": {"status": "partially_paid", "credited": "12.99"},'
        ' "2": {"status": "finished", "credited": "25.00", "valued_by": "rate"},'
        ' "3": {"status": "partially_paid", "review": true}, "4": {"status": "waiting"}}'
    )
    assert check.done_with(kept["1"]) == "the platform settled it at 12.99"
    assert check.done_with(kept["2"]) == "the platform settled it at 25.00 (valued at its rate)"
    assert "a staff case is open, nothing credited" in check.done_with(kept["3"])
    assert check.done_with(kept["4"]) == "the platform saw it as 'waiting': nothing to settle"
    assert "has no note of it" in check.done_with(kept.get("5"))
    assert check.kept_records("not json") == {} and check.kept_records("[1]") == {}
    assert "received 13 (worth 12.98513924 in fiat)" in check.describe(
        {"payment_id": 9, "actually_paid": 13, "actually_paid_at_fiat": 12.98513924}
    )
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
    assert check.main(["--minimums"]) == 0
    out = capsys.readouterr()
    text = out.out
    assert "mode: production" in text and "3 coin(s) switched on" in text
    assert "NOWPayments 5001: partially_paid; coin usdtbsc; asked 13.02, received 12.4" in text
    assert "matched no payment" not in text
    assert (
        "paid LESS than the invoice (asked 13.02, received 12.4) and nothing was credited" in text
    )
    assert "NOWPayments never notified the platform about it" in text
    assert "settled: 50.00 USD" in text
    # the coin the member chose here, and what the platform did with each NOWPayments payment
    assert "platform payment p-silent | coin chosen on the platform: usdtbsc" in text
    assert "platform payment p-under | coin chosen on the platform: none" in text
    assert "the platform settled it at 50.00" in text
    assert "the platform has no note of it" in text  # 5001: recorded, never settled
    assert "asked for by id" not in text
    assert "3 in 1 log file(s): HTTP 200 x2, HTTP 401 x1" in text
    # others passed, so the secret is right: that one notification was refused
    assert "not accepted: 06/Oct/2026:10:20:00 +0000 -> 401" in text
    assert "401 on some only" in text and "is not the IPN secret" not in text
    assert "an invoice of 5 USD: 0 of 3 coin(s) take it" in text
    assert "an invoice of 13 USD: 2 of 3 coin(s) take it" in text
    assert "no coin takes less than 6.00 USD now" in text
    summary = text.split("== Summary")[1]
    assert "13.00 USD (cl***@x.com)" in summary and "5.00 USD (ot***@x.com)" in summary
    assert "some notifications were refused: send them again" in summary
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
    assert check.main(["--minimums"]) == 0
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


def test_a_payment_the_platform_never_heard_of_is_shown_by_its_id(monkeypatch, tmp_path, capsys):
    """Its notification was refused, so the platform knows no id to ask by: staff copy it from
    the NOWPayments dashboard and read the record here before sending the notification again."""
    _setup(monkeypatch, tmp_path, ENV)
    assert check.main(["7770", "5001", "404404", "--help"]) == 0
    text = capsys.readouterr().out
    assert "NOWPayments payment 7770, asked for by id" in text
    assert "order (the platform's payment): none on the record" in text
    assert '"parent_payment_id":5001' in text
    assert "payment 5001, asked for by id" not in text  # already shown under its invoice
    assert "NOWPayments payment 404404: not found with this key" in text


def test_the_coins_minimums_are_asked_only_on_request(monkeypatch, tmp_path, capsys):
    """Seen on the server, 2026-10-06: NOWPayments answers 429 to whoever asks it a few times
    in a second, the site's own requests included. A routine check asks about the payments
    only, each question paced, and one refused for that reason is asked once more."""
    _setup(monkeypatch, tmp_path, ENV)
    asked: list[str] = []
    waits: list[float] = []

    def counting(method, url, *, body=None, headers=None):
        asked.append(url)
        if url.endswith("/payment/5001") and asked.count(url) == 1:
            return 429, ""
        return _http(method, url, body=body, headers=headers)

    monkeypatch.setattr(envtools, "_http", counting)
    monkeypatch.setattr(check.time, "sleep", waits.append)
    assert check.main() == 0
    text = capsys.readouterr().out
    assert "not asked: add --minimums" in text and "an invoice of" not in text
    assert not [url for url in asked if "/min-amount" in url]
    # the payment refused once was asked again after a longer wait, and its record read
    assert len([url for url in asked if url.endswith("/payment/5001")]) == 2
    assert "NOWPayments 5001: partially_paid" in text
    assert check.BUSY_PAUSE in waits and waits.count(check.PAUSE) >= 3


def test_every_notification_refused_means_a_wrong_ipn_secret(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path, ENV)
    refused = "\n".join(line.replace('" 200 ', '" 401 ') for line in LOG.splitlines())
    (tmp_path / "access.log").write_text(refused + "\n", encoding="utf-8")
    assert check.main() == 0
    text = capsys.readouterr().out
    assert "NOWPAYMENTS_IPN_SECRET is not the IPN secret of this NOWPayments account" in text
    assert "notifications are refused (wrong IPN secret)" in text.split("== Summary")[1]


def test_the_minimum_is_asked_again_with_the_pair_spelled_out(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path, ENV)

    def wants_the_pair(method, url, *, body=None, headers=None):
        if "/min-amount?" in url and "currency_to=" not in url:
            return 400, '{"message":"currency_to is required"}'
        return _http(method, url, body=body, headers=headers)

    monkeypatch.setattr(envtools, "_http", wants_the_pair)
    assert check.main(["--minimums"]) == 0
    assert "an invoice of 13 USD: 2 of 3 coin(s) take it" in capsys.readouterr().out
