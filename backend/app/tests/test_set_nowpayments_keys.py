"""scripts/set_nowpayments_keys.py — replacing the crypto (NOWPayments) keys on the server.

* the API key is checked with NOWPayments itself on /merchant/coins (production /currencies
  answers 200 even for a wrong key), and the mode follows whichever accepts it;
* one line per key is written (the sandbox flag set to match), the API restarted, and the
  crypto option checked on the property pages;
* a refused key changes nothing; the secrets never reach the output.
"""

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
nowp = _load("set_nowpayments_keys")

GOOD = "NP0ProdKey000000000000000"
SANDBOX_KEY = "NP0SandboxKey00000000000"
IPN = "IpnSecret0000000000000000"
OLD = "OldKey000000000000000000"


class FakeNow:
    """NOWPayments and the API as the script sees them."""

    def __init__(self, env_file: Path):
        self.env_file = env_file
        self.restarts = 0

    def loaded(self, key: str):
        return envtools.lookup(dict(envtools.dotenv_values(self.env_file)), key)[1]

    def http(self, method, url, *, body=None, headers=None):
        if url.endswith("/merchant/coins"):
            key = (headers or {}).get("x-api-key")
            if "api-sandbox" in url:
                ok = key == SANDBOX_KEY
            else:
                ok = key == GOOD
            if ok:
                return 200, '{"selectedCurrencies":["btc","usdttrc20"]}'
            return 403, '{"code":"INVALID_API_KEY"}'
        if url.endswith(nowp.OPTIONS_PATH):
            live = bool(self.loaded("NOWPAYMENTS_API_KEY")) and self.loaded(
                "NOWPAYMENTS_IPN_SECRET"
            ) not in (None, "")
            return 200, '{"crypto":%s}' % ("true" if live else "false")
        return None, "unexpected"

    def restart(self) -> bool:
        self.restarts += 1
        return True


def _setup(monkeypatch, tmp_path, env_text: str, typed: list[str]):
    env = tmp_path / ".env"
    env.write_text(env_text, encoding="utf-8")
    fake = FakeNow(env)
    answers = iter(typed)
    monkeypatch.setattr(nowp.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(envtools, "ENV_FILE", env)
    monkeypatch.setattr(envtools, "service_environment", lambda: {})
    monkeypatch.setattr(envtools, "unit_overrides", lambda key: [])
    monkeypatch.setattr(envtools, "_http", fake.http)
    monkeypatch.setattr(envtools, "restart_api", fake.restart)
    monkeypatch.setattr(nowp.getpass, "getpass", lambda prompt="": next(answers))
    return env, fake


def test_the_key_is_checked_where_a_wrong_one_is_refused(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, "", [])
    assert nowp.check_key(GOOD) == ("production", "2 coin(s) switched on in the account")
    assert nowp.check_key(SANDBOX_KEY)[0] == "sandbox"
    assert nowp.check_key("WrongKey0000000000")[0] is None
    assert nowp.value_problem("rk_live_abc123") is not None
    assert nowp.value_problem("short") is not None
    assert nowp.value_problem(GOOD) is None


def test_new_keys_are_written_once_and_crypto_goes_live(monkeypatch, tmp_path, capsys):
    env_text = (
        "APP_BASE_URL=https://capimaxpropshare.com\n"
        f"NOWPAYMENTS_API_KEY={OLD}\n"
        "NOWPAYMENTS_SANDBOX=true\n"
        f"NOWPAYMENTS_API_KEY={OLD}\n"
    )
    env, fake = _setup(monkeypatch, tmp_path, env_text, [GOOD, IPN])
    assert nowp.main() == 0
    out = capsys.readouterr()
    text = env.read_text(encoding="utf-8")
    assert text.count("NOWPAYMENTS_API_KEY=") == 1 and f"NOWPAYMENTS_API_KEY={GOOD}" in text
    assert f"NOWPAYMENTS_IPN_SECRET={IPN}" in text
    assert "NOWPAYMENTS_SANDBOX=false" in text  # the key is a production one
    assert fake.restarts == 1
    assert "crypto is offered on every property" in out.out
    for secret in (GOOD, IPN, OLD):
        assert secret not in out.out + out.err
    assert len(list(tmp_path.glob(".env.bak-nowpayments-*"))) == 1


def test_a_refused_key_changes_nothing(monkeypatch, tmp_path, capsys):
    env_text = f"NOWPAYMENTS_API_KEY={OLD}\nNOWPAYMENTS_IPN_SECRET={IPN}\n"
    env, fake = _setup(monkeypatch, tmp_path, env_text, ["WrongKey0000000000"])
    assert nowp.main() == 1
    assert "refused this API key" in capsys.readouterr().err
    assert env.read_text(encoding="utf-8") == env_text and fake.restarts == 0


def test_enter_on_both_questions_changes_nothing(monkeypatch, tmp_path):
    env_text = f"NOWPAYMENTS_API_KEY={OLD}\n"
    env, fake = _setup(monkeypatch, tmp_path, env_text, ["", ""])
    assert nowp.main() == 0
    assert env.read_text(encoding="utf-8") == env_text and fake.restarts == 0
