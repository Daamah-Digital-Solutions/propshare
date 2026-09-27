"""The Stripe webhook secret fix (``scripts/fix_stripe_webhook_secret.py``) and the API
behaviour it relies on.

Every delivery to the live deposits endpoint failed with 401 WEBHOOK_SIGNATURE_INVALID: the
server's STRIPE_WEBHOOK_SECRET was not that endpoint's signing secret. The script puts the
right one in .env and proves the API accepts it. These tests pin:

* the .env rewrite leaves exactly one assignment, the one the API's own settings then load
  (a later duplicate line wins over an edited first one — one way to get this 401);
* what it reports as "loaded" follows the API's precedence (service environment over .env);
* its proof request is signed exactly like Stripe's (the API's verifier accepts it) and changes
  nothing on either endpoint: on deposits a replayed event id answers "duplicate" before any
  write, on Connect an unknown event type is ignored;
* a refused delivery is logged, without the secret, in the words the script counts.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.services.integrations.payments import stripe_gateway

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fix = _load("fix_stripe_webhook_secret")

KEY = "STRIPE_WEBHOOK_SECRET"
ENV_WITH_DUPLICATES = (
    "APP_BASE_URL=https://capimaxpropshare.com\n"
    "STRIPE_WEBHOOK_SECRET=whsec_EditedFirstLine000000\n"
    "CRON_SECRET=cron\n"
    "# STRIPE_WEBHOOK_SECRET=whsec_CommentedOut00000000\n"
    "export STRIPE_WEBHOOK_SECRET=whsec_OlderTestModeLine00\n"
)


def test_a_later_duplicate_wins_and_the_rewrite_leaves_the_line_the_api_loads(tmp_path):
    before = tmp_path / "before.env"
    before.write_text(ENV_WITH_DUPLICATES, encoding="utf-8")
    # the trap: the first line was edited, an older one further down still wins
    assert Settings(_env_file=before).stripe_webhook_secret == "whsec_OlderTestModeLine00"
    assert fix.assignments(ENV_WITH_DUPLICATES, KEY) == [1, 4]

    fixed = fix.with_single_assignment(ENV_WITH_DUPLICATES, KEY, "whsec_FromTheDashboard0000")
    assert fixed.splitlines() == [
        "APP_BASE_URL=https://capimaxpropshare.com",
        "STRIPE_WEBHOOK_SECRET=whsec_FromTheDashboard0000",
        "CRON_SECRET=cron",
        "# STRIPE_WEBHOOK_SECRET=whsec_CommentedOut00000000",
    ]
    after = tmp_path / "after.env"
    after.write_text(fixed, encoding="utf-8")
    assert Settings(_env_file=after).stripe_webhook_secret == "whsec_FromTheDashboard0000"


def test_the_rewrite_matches_keys_like_the_api_and_keeps_everything_else():
    # the API's settings ignore case, so a lower-case line counts; a longer name does not
    assert fix.assignments("stripe_webhook_secret=whsec_x\n", KEY) == [0]
    others = "STRIPE_WEBHOOK_SECRET_OLD=x\nSTRIPE_CONNECT_WEBHOOK_SECRET=y\n"
    assert fix.assignments(others, KEY) == []
    # never set: appended; the file's CRLF newlines are kept
    out = fix.with_single_assignment("A=1\r\nB=2\r\n", KEY, "whsec_Appended0000000000")
    assert out == "A=1\r\nB=2\r\nSTRIPE_WEBHOOK_SECRET=whsec_Appended0000000000\r\n"


def test_what_the_api_loads_follows_its_precedence():
    dotenv = {KEY: "whsec_file"}
    assert fix.loaded_value(KEY, dotenv, {}) == ("whsec_file", ".env")
    # a value the service definition puts in the process environment wins over .env
    unit = {"stripe_webhook_secret": "whsec_unit"}
    assert fix.loaded_value(KEY, dotenv, unit) == ("whsec_unit", "the service environment")
    assert fix.loaded_value("STRIPE_CONNECT_WEBHOOK_SECRET", dotenv, {}) == (None, ".env")


def test_a_pasted_secret_is_cleaned_and_checked():
    pasted = "\x1b[200~ whsec_AbCdEf0123456789xyz \x1b[201~\n"
    assert fix.clean_pasted(pasted) == "whsec_AbCdEf0123456789xyz"
    assert fix.clean_pasted('"whsec_AbCdEf0123456789xyz"') == "whsec_AbCdEf0123456789xyz"
    assert fix.secret_problem("whsec_AbCdEf0123456789xyz") is None
    assert "API key" in fix.secret_problem("rk_live_abc123")
    assert "API key" in fix.secret_problem("sk_live_abc123")
    assert fix.secret_problem("whsec_short") is not None
    assert fix.secret_problem("we_1UJD8ZLzE51wVKVXe2KrFtLv") is not None  # the endpoint's id


def test_only_a_fingerprint_is_ever_shown():
    a, b = fix.fingerprint("whsec_AbCdEf0123456789xyz"), fix.fingerprint("whsec_Other0123456789xyz")
    assert len(a) == 12 and a != b and "whsec" not in a
    assert fix.fingerprint(None) == fix.fingerprint("") == "(not set)"


def test_the_public_origin_is_where_stripe_delivers():
    site = {"APP_BASE_URL": "https://capimaxpropshare.com"}
    assert fix.public_api_base(site) == "https://api.capimaxpropshare.com"
    explicit = {**site, "ADMIN_BASE_URL": "https://panel.example.com/"}
    assert fix.public_api_base(explicit) == "https://panel.example.com"
    assert fix.public_api_base({"APP_BASE_URL": "http://localhost:5173"}) is None


def test_the_proof_is_signed_exactly_like_stripe_signs():
    body, headers = fix.signed_request("whsec_right", "evt_1", now=1_700_000_000)
    assert stripe_gateway._verify("whsec_right", body, headers["Stripe-Signature"])
    assert not stripe_gateway._verify("whsec_wrong", body, headers["Stripe-Signature"])


def test_answers_are_read_honestly():
    assert fix.answer_of(None, "Connection refused", fix.DEPOSITS)[0] == "unreachable"
    assert fix.answer_of(503, "{}", fix.DEPOSITS) == (
        "rejected",
        "503: the API has no STRIPE_WEBHOOK_SECRET",
    )
    assert fix.answer_of(200, '{"status":"processed"}', fix.DEPOSITS) == (
        "accepted",
        "signature accepted (unexpected answer 'processed')",
    )
    assert fix.answer_of(500, "boom", fix.DEPOSITS)[0] == "error"


def test_env_is_replaced_whole_and_the_previous_one_kept(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_bytes(b"A=1\nSTRIPE_WEBHOOK_SECRET=whsec_old000000000000\n")
    monkeypatch.setattr(fix, "ENV_FILE", env)
    backup = fix.write_env("A=1\nSTRIPE_WEBHOOK_SECRET=whsec_new000000000000\n")
    assert env.read_bytes() == b"A=1\nSTRIPE_WEBHOOK_SECRET=whsec_new000000000000\n"
    assert backup.read_bytes() == b"A=1\nSTRIPE_WEBHOOK_SECRET=whsec_old000000000000\n"
    assert backup.name.startswith(".env.bak-stripe-")
    leftovers = [p for p in tmp_path.iterdir() if p not in (env, backup)]
    assert leftovers == []  # no temporary file left behind


def test_it_refuses_to_run_without_root(capsys):
    if hasattr(fix.os, "geteuid") and fix.os.geteuid() == 0:
        pytest.skip("the suite itself runs as root here")
    assert fix.main() == 1
    assert "run this as root" in capsys.readouterr().err


def _counts(db) -> tuple:
    tables = ("payment_events", "payout_events", "audit_log", "transactions", "notifications")
    return tuple(db(f"SELECT count(*) FROM {t}")[0][0] for t in tables)


@pytest.mark.asyncio
async def test_the_deposits_proof_changes_nothing_and_a_refusal_is_logged(
    client, db, monkeypatch, caplog
):
    s = get_settings()
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_LiveEndpoint00000", raising=False)
    # what the script replays: the id of an event the API already recorded
    db(
        "INSERT INTO payment_events (provider, event_id, type)"
        " VALUES ('stripe', :e, 'checkout.session.lookup')",
        e="sync:cs_live_x:succeeded",
    )
    before = _counts(db)

    body, headers = fix.signed_request("whsec_LiveEndpoint00000", "sync:cs_live_x:succeeded")
    r = await client.post(fix.DEPOSITS.path, content=body, headers=headers)
    assert r.status_code == 200, r.text
    assert fix.answer_of(r.status_code, r.text, fix.DEPOSITS) == (
        "accepted",
        "signature accepted (nothing changed)",
    )
    assert _counts(db) == before

    # signed with another endpoint's secret: refused, logged in the words the script counts
    body, headers = fix.signed_request("whsec_OldTestEndpoint000", "sync:cs_live_x:succeeded")
    with caplog.at_level("WARNING"):
        r = await client.post(fix.DEPOSITS.path, content=body, headers=headers)
    assert r.status_code == 401 and "WEBHOOK_SIGNATURE_INVALID" in r.text
    assert fix.answer_of(r.status_code, r.text, fix.DEPOSITS)[0] == "rejected"
    assert fix.DEPOSITS.mark in caplog.text
    assert "whsec_" not in caplog.text
    assert _counts(db) == before


@pytest.mark.asyncio
async def test_the_connect_proof_changes_nothing_and_a_refusal_is_logged(
    client, db, monkeypatch, caplog
):
    s = get_settings()
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_LiveEndpoint00000", raising=False)
    monkeypatch.setattr(
        s, "stripe_connect_webhook_secret", "whsec_ConnectEndpoint000", raising=False
    )
    before = _counts(db)

    body, headers = fix.signed_request("whsec_ConnectEndpoint000", "evt_capimax_signature_check_1")
    r = await client.post(fix.CONNECT.path, content=body, headers=headers)
    assert r.status_code == 200, r.text
    assert fix.answer_of(r.status_code, r.text, fix.CONNECT) == (
        "accepted",
        "signature accepted (nothing changed)",
    )
    assert _counts(db) == before

    body, headers = fix.signed_request("whsec_SomeOtherEndpoint0", "evt_capimax_signature_check_2")
    with caplog.at_level("WARNING"):
        r = await client.post(fix.CONNECT.path, content=body, headers=headers)
    assert r.status_code == 401 and "WEBHOOK_SIGNATURE_INVALID" in r.text
    assert fix.CONNECT.mark in caplog.text
    assert "whsec_" not in caplog.text
    assert _counts(db) == before


# --- the whole run, on a simulated server ------------------------------------------------ #
RIGHT = "whsec_RightLiveEndpoint0000"
WRONG = "whsec_OldTestEndpoint00000"


class FakeServer:
    """The VPS as the script sees it: the API reads its secret when it (re)starts and checks
    each delivery with it, exactly as stripe_gateway does."""

    def __init__(self, env_file: Path, service_env: dict | None = None):
        self.env_file = env_file
        self.service_env = service_env or {}
        self.restarts = 0
        self.posts: list[str] = []
        self.loaded = self._load()

    def _load(self):
        found, value = fix.lookup(self.service_env, KEY)
        if found:
            return value
        return fix.lookup(dict(fix.dotenv_values(self.env_file)), KEY)[1]

    def restart(self) -> bool:
        self.restarts += 1
        self.loaded = self._load()
        return True

    def http(self, method, url, *, body=None, headers=None):
        if url.endswith(fix.RECONCILE_PATH):
            return 200, '{"checked":0,"settled":0,"failed":0,"pending":0,"errors":0}'
        self.posts.append(url)
        if stripe_gateway._verify(self.loaded or "", body, headers["Stripe-Signature"]):
            return 200, '{"status":"duplicate"}'
        return 401, '{"error":{"code":"WEBHOOK_SIGNATURE_INVALID"}}'


def _run_script(monkeypatch, tmp_path, env_text: str, *, typed: list[str], overrides=()):
    env = tmp_path / ".env"
    env.write_text(env_text, encoding="utf-8")
    server = FakeServer(env)
    answers = iter(typed)
    monkeypatch.setattr(fix.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(fix, "ENV_FILE", env)
    monkeypatch.setattr(fix, "service_environment", lambda: server.service_env)
    monkeypatch.setattr(fix, "unit_overrides", lambda key: list(overrides))
    monkeypatch.setattr(fix, "refusals_logged", lambda mark, hours=24: (52, "2026-09-27T21:28"))
    monkeypatch.setattr(
        fix, "_psql", lambda dotenv, sql: "sync:cs_live_x:succeeded" if "event_id" in sql else "0"
    )
    monkeypatch.setattr(fix, "restart_api", server.restart)
    monkeypatch.setattr(fix, "_http", server.http)
    monkeypatch.setattr(fix.getpass, "getpass", lambda prompt="": next(answers))
    return server, env, fix.main()


SITE = "APP_BASE_URL=https://capimaxpropshare.com\nCRON_SECRET=cron\n"


def test_a_run_replaces_a_wrong_secret_and_proves_it(monkeypatch, tmp_path, capsys):
    """The production case: every delivery refused because .env holds another endpoint's
    secret (here twice). One run: one line with the right secret, one restart, and the
    signed proof through the public URL is accepted. The secrets never reach the output."""
    env_text = f"{SITE}STRIPE_WEBHOOK_SECRET={RIGHT}\nSTRIPE_WEBHOOK_SECRET={WRONG}\n"
    server, env, code = _run_script(monkeypatch, tmp_path, env_text, typed=[RIGHT, ""])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert env.read_text(encoding="utf-8").count("STRIPE_WEBHOOK_SECRET=") == 1
    assert f"STRIPE_WEBHOOK_SECRET={RIGHT}" in env.read_text(encoding="utf-8")
    assert server.restarts == 1 and server.loaded == RIGHT
    assert server.posts == ["https://api.capimaxpropshare.com/api/v1/payments/webhooks/stripe"]
    assert "signature accepted (nothing changed)" in out.out
    assert "the LAST one wins" in out.out
    assert RIGHT not in out.out + out.err and WRONG not in out.out + out.err
    assert len(list(tmp_path.glob(".env.bak-stripe-*"))) == 1


def test_a_run_with_the_right_secret_changes_nothing(monkeypatch, tmp_path, capsys):
    server, env, code = _run_script(
        monkeypatch, tmp_path, f"{SITE}STRIPE_WEBHOOK_SECRET={RIGHT}\n", typed=[RIGHT, ""]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert server.restarts == 0 and not list(tmp_path.glob(".env.bak-stripe-*"))
    assert "nothing to change" in out and "signature accepted" in out


def test_an_api_started_before_the_edit_is_restarted_once(monkeypatch, tmp_path, capsys):
    """.env already right but the running API was started with the old value (edited without
    a restart): the proof is refused, the script restarts once and the proof passes."""
    env = tmp_path / ".env"
    env.write_text(f"{SITE}STRIPE_WEBHOOK_SECRET={WRONG}\n", encoding="utf-8")
    stale = FakeServer(env)  # started with the old value
    env.write_text(f"{SITE}STRIPE_WEBHOOK_SECRET={RIGHT}\n", encoding="utf-8")
    answers = iter([RIGHT, ""])
    monkeypatch.setattr(fix.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(fix, "ENV_FILE", env)
    monkeypatch.setattr(fix, "service_environment", lambda: {})
    monkeypatch.setattr(fix, "unit_overrides", lambda key: [])
    monkeypatch.setattr(fix, "refusals_logged", lambda mark, hours=24: None)
    monkeypatch.setattr(fix, "_psql", lambda dotenv, sql: "evt_1" if "event_id" in sql else "0")
    monkeypatch.setattr(fix, "restart_api", stale.restart)
    monkeypatch.setattr(fix, "_http", stale.http)
    monkeypatch.setattr(fix.getpass, "getpass", lambda prompt="": next(answers))
    assert fix.main() == 0, capsys.readouterr().err
    assert stale.restarts == 1 and len(stale.posts) == 2


def test_an_override_in_the_service_definition_stops_before_any_change(
    monkeypatch, tmp_path, capsys
):
    env_text = f"{SITE}STRIPE_WEBHOOK_SECRET={WRONG}\n"
    server, env, code = _run_script(
        monkeypatch,
        tmp_path,
        env_text,
        typed=[RIGHT, ""],
        overrides=["an Environment= line of capimax.service"],
    )
    assert code == 1
    assert "systemctl cat capimax" in capsys.readouterr().err
    assert env.read_text(encoding="utf-8") == env_text and server.restarts == 0


def test_an_api_key_pasted_by_mistake_is_refused(monkeypatch, tmp_path, capsys):
    env_text = f"{SITE}STRIPE_WEBHOOK_SECRET={WRONG}\n"
    typed = ["rk_live_NotTheSigningSecret", "sk_live_Nope", "pk_live_Nope"]
    server, env, code = _run_script(monkeypatch, tmp_path, env_text, typed=typed)
    out = capsys.readouterr()
    assert code == 1 and "that is an API key" in out.out
    assert env.read_text(encoding="utf-8") == env_text and server.restarts == 0
