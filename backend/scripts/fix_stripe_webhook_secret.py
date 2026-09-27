"""Check and fix the Stripe webhook signing secrets on the server (run as root).

Symptom: in Stripe -> Webhooks an endpoint shows every delivery failed with
``401 {"code": "WEBHOOK_SIGNATURE_INVALID"}``. Stripe signs each endpoint with its own secret
(``whsec_...``) and the API checks every delivery against STRIPE_WEBHOOK_SECRET (deposits and
purchases) or STRIPE_CONNECT_WEBHOOK_SECRET (investors' Stripe accounts). A test-mode
endpoint's secret, another endpoint's, or an older duplicate line in .env that wins over the
edited one: each of them fails every delivery this way.

No card payment is lost meanwhile (the reconcile job asks Stripe directly every 5 minutes);
a working webhook settles them within seconds instead.

What it does:
  1. shows what the API loads now: only a fingerprint (the first 12 hex digits of the
     SHA-256), how many .env lines set it, and how many deliveries the API refused lately;
  2. asks for each endpoint's signing secret without echoing it (Enter skips the Connect one);
  3. only if it differs: backs up .env, leaves exactly one line for the key, restarts the API
     and checks that the API now loads the new value;
  4. proves the API accepts a signature made with that secret, through the public URL Stripe
     uses, with a request that changes nothing (deposits: a replay of an event the API has
     already processed; Connect: an event type it ignores);
  5. runs the payment reconcile once and counts card/crypto payments still pending.

The secret is never printed, logged, written anywhere but .env, or passed on a command line.

Usage, on the VPS as root (after ``sudo -u deploy git -C /opt/capimax/app pull``):
    /opt/capimax/venv/bin/python /opt/capimax/app/backend/scripts/fix_stripe_webhook_secret.py
"""

from __future__ import annotations

import datetime
import getpass
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values  # what the API's own settings loader reads .env with

BACKEND = Path(__file__).resolve().parents[1]
ENV_FILE = Path(os.environ.get("CAPIMAX_ENV_FILE", str(BACKEND / ".env")))
SERVICE = os.environ.get("CAPIMAX_SERVICE", "capimax")
API_LOCAL = os.environ.get("CAPIMAX_API_LOCAL", "http://127.0.0.1:8000")
RECONCILE_PATH = "/api/v1/payments/maintenance/reconcile"


@dataclass(frozen=True)
class Endpoint:
    key: str  # the .env variable the API checks this endpoint's deliveries with
    label: str  # how the owner finds it in Stripe
    path: str  # the API route Stripe delivers to
    mark: str  # what the API logs for each delivery it refuses (stripe_gateway)
    required: bool
    replay: bool  # prove with a replay of a recorded event (else an ignored event type)
    expected: str  # the API's answer to that harmless signed request


DEPOSITS = Endpoint(
    key="STRIPE_WEBHOOK_SECRET",
    label="deposits endpoint",
    path="/api/v1/payments/webhooks/stripe",
    mark="signature rejected on the deposits endpoint",
    required=True,
    replay=True,
    expected="duplicate",
)
CONNECT = Endpoint(
    key="STRIPE_CONNECT_WEBHOOK_SECRET",
    label="Connect endpoint",
    path="/api/v1/payments/webhooks/stripe-payouts",
    mark="signature rejected on the Connect endpoint",
    required=False,
    replay=False,
    expected="ignored",
)
ENDPOINTS = (DEPOSITS, CONNECT)

_ASSIGNMENT = re.compile(r"""^\s*(?:export\s+)?['"]?([A-Za-z_][A-Za-z0-9_.]*)['"]?\s*=""")
_SIGNING_SECRET = re.compile(r"^whsec_[A-Za-z0-9+/=_-]{16,}$")
_PASTE_MARKERS = ("\x1b[200~", "\x1b[201~")  # a terminal's bracketed-paste wrapping


# --- pure helpers (unit-tested) ------------------------------------------------------------ #
def fingerprint(value: str | None) -> str:
    """Tells two secrets apart without helping anyone recover one."""
    if not value:
        return "(not set)"
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def clean_pasted(raw: str) -> str:
    for marker in _PASTE_MARKERS:
        raw = raw.replace(marker, "")
    return raw.strip().strip("\"'").strip()


def secret_problem(value: str) -> str | None:
    """Why ``value`` cannot be an endpoint's signing secret, or None when it can."""
    if value.startswith(("sk_", "rk_", "pk_")):
        return "that is an API key; the endpoint's signing secret starts with whsec_"
    if not _SIGNING_SECRET.match(value):
        return "a signing secret is whsec_ followed by letters and digits: copy it whole"
    return None


def assignments(text: str, key: str) -> list[int]:
    """Indexes of the lines that set ``key``, matched case-insensitively like the API's
    settings do (a commented-out line sets nothing)."""
    found = []
    for i, line in enumerate(text.splitlines()):
        m = _ASSIGNMENT.match(line)
        if m and m.group(1).lower() == key.lower():
            found.append(i)
    return found


def with_single_assignment(text: str, key: str, value: str) -> str:
    """``text`` where ``key`` is set exactly once, to ``value``: the first line that set it is
    replaced and every later one (the one that would win) is dropped; appended when never
    set. Every other line and the newline style are kept."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    found = assignments(text, key)
    line = f"{key}={value}"
    if found:
        lines[found[0]] = line
        for i in reversed(found[1:]):
            del lines[i]
    else:
        lines.append(line)
    return newline.join(lines) + newline


def lookup(values: dict[str, str | None], key: str) -> tuple[bool, str | None]:
    """(found, value) of ``key``, matched case-insensitively; the last match wins."""
    found, value = False, None
    for name, candidate in values.items():
        if name.lower() == key.lower():
            found, value = True, candidate
    return found, value


def loaded_value(
    key: str, dotenv: dict[str, str | None], process_env: dict[str, str]
) -> tuple[str | None, str]:
    """The value the API resolves for ``key``, and where from: its process environment wins
    over .env (pydantic-settings), e.g. when the service definition loads a file itself."""
    found, value = lookup(process_env, key)
    if found:
        return value, "the service environment"
    found, value = lookup(dotenv, key)
    return (value if found else None), ".env"


def public_api_base(dotenv: dict[str, str | None]) -> str | None:
    """The API's public origin, the one Stripe delivers to (Settings.admin_url's rule)."""
    _, base = lookup(dotenv, "ADMIN_BASE_URL")
    if base:
        return base.rstrip("/")
    _, site_url = lookup(dotenv, "APP_BASE_URL")
    site = urlparse(site_url or "")
    host = site.hostname or ""
    if "." not in host or host == "localhost":
        return None
    return f"{site.scheme or 'https'}://{host if host.startswith('api.') else 'api.' + host}"


def signed_request(
    secret: str, event_id: str, now: int | None = None
) -> tuple[bytes, dict[str, str]]:
    """A Stripe-shaped event the API acts on in no way, signed the way Stripe signs:
    HMAC-SHA256 of ``"<timestamp>.<body>"`` in the Stripe-Signature header."""
    body = json.dumps(
        {
            "id": event_id,
            "object": "event",
            "type": "capimax.signature_check",
            "data": {"object": {}},
        },
        separators=(",", ":"),
    ).encode()
    ts = int(time.time()) if now is None else now
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={ts},v1={sig}", "Content-Type": "application/json"}


def answer_of(status: int | None, text: str, ep: Endpoint) -> tuple[str, str]:
    """(verdict, detail) for the API's answer to the signed request."""
    if status is None:
        return "unreachable", text[:160]
    if status == 200:
        try:
            answer = str(json.loads(text).get("status"))
        except (ValueError, AttributeError):
            answer = text[:120]
        note = "nothing changed" if answer == ep.expected else f"unexpected answer {answer!r}"
        return "accepted", f"signature accepted ({note})"
    if status == 401:
        return "rejected", "401: the API still refuses this signature"
    if status == 503:
        return "rejected", f"503: the API has no {ep.key}"
    return "error", f"HTTP {status}: {text[:200]}"


# --- the server ---------------------------------------------------------------------------- #
def _run(cmd: list[str]) -> str | None:
    """A command's output, or None when it could not run or failed."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True, cwd="/")
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout


def _http(
    method: str, url: str, *, body: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int | None, str]:
    """(status, body); status None when the server could not be reached."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        return None, str(exc)


def service_environment() -> dict[str, str]:
    """The running API's environment variables (values are compared, never printed)."""
    pid = (_run(["systemctl", "show", "-p", "MainPID", "--value", SERVICE]) or "").strip()
    if not pid.isdigit() or pid == "0":
        return {}
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    env = {}
    for item in raw.split(b"\0"):
        name, sep, value = item.partition(b"=")
        if sep:
            env[name.decode(errors="replace")] = value.decode(errors="replace")
    return env


def unit_overrides(key: str) -> list[str]:
    """Where the service definition itself sets ``key``: editing .env then changes nothing."""
    found = []
    inline = _run(["systemctl", "show", "-p", "Environment", "--value", SERVICE]) or ""
    if re.search(rf"(?:^|\s){re.escape(key)}=", inline, re.IGNORECASE):
        found.append(f"an Environment= line of {SERVICE}.service")
    files = _run(["systemctl", "show", "-p", "EnvironmentFiles", "--value", SERVICE]) or ""
    for path in re.findall(r"(/\S+) \(ignore_errors=", files):
        other = Path(path)
        try:
            if other.resolve() == ENV_FILE.resolve():
                continue
            if assignments(other.read_text(encoding="utf-8", errors="replace"), key):
                found.append(f"the environment file {other}")
        except OSError:
            continue
    return found


def refusals_logged(mark: str, hours: int = 24) -> tuple[int, str | None] | None:
    """How many deliveries the API refused in the last ``hours``, and when the last was."""
    out = _run(
        ["journalctl", "-u", SERVICE, "--since", f"-{hours}h", "--no-pager", "-o", "short-iso"]
    )
    if out is None:
        return None
    hits = [line for line in out.splitlines() if mark in line]
    return len(hits), (hits[-1].split(" ", 1)[0] if hits else None)


def _psql(dotenv: dict[str, str | None], sql: str) -> str | None:
    _, url = lookup(dotenv, "DATABASE_URL")
    database = urlparse(url or "").path.lstrip("/") or "capimaxpropshare"
    out = _run(["sudo", "-u", "postgres", "psql", "-d", database, "-qtAX", "-c", sql])
    return out.strip() if out is not None else None


def write_env(text: str) -> Path:
    """Replace .env atomically with the same owner and mode; the previous one stays beside it."""
    st = ENV_FILE.stat()
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    backup = ENV_FILE.with_name(f"{ENV_FILE.name}.bak-stripe-{stamp}")
    shutil.copy2(ENV_FILE, backup)
    os.chmod(backup, 0o600)
    fd, tmp = tempfile.mkstemp(prefix=f"{ENV_FILE.name}.", dir=ENV_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        if hasattr(os, "chown"):
            os.chown(backup, st.st_uid, st.st_gid)
            os.chown(tmp, st.st_uid, st.st_gid)
        os.chmod(tmp, stat.S_IMODE(st.st_mode))
        os.replace(tmp, ENV_FILE)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return backup


def restart_api() -> bool:
    if _run(["systemctl", "restart", SERVICE]) is None:
        return False
    for _ in range(90):
        if _http("GET", f"{API_LOCAL}/healthz")[0] == 200:
            return True
        time.sleep(1)
    return False


def prove(ep: Endpoint, secret: str, dotenv: dict[str, str | None]) -> tuple[str, str]:
    """Send the harmless signed request the way Stripe does; (verdict, detail)."""
    if ep.replay:
        event_id = _psql(
            dotenv,
            "SELECT event_id FROM payment_events WHERE provider = 'stripe'"
            " ORDER BY created_at DESC LIMIT 1",
        )
        if not event_id:
            return "skipped", "no Stripe event recorded yet to replay: use Resend in Stripe"
    else:
        event_id = f"evt_capimax_signature_check_{int(time.time())}"
    body, headers = signed_request(secret, event_id)
    base = public_api_base(dotenv)
    tried = []
    for origin in ([base] if base else []) + [API_LOCAL]:
        status, text = _http("POST", origin + ep.path, body=body, headers=headers)
        verdict, detail = answer_of(status, text, ep)
        if verdict != "unreachable":
            return verdict, f"{origin}: {detail}"
        tried.append(f"{origin} unreachable ({detail})")
    return "error", "; ".join(tried)


# --- the run ------------------------------------------------------------------------------- #
def say(msg: str) -> None:
    print(f"\n\033[1;32m== {msg}\033[0m")


def ok(msg: str) -> None:
    print(f"   \033[32mok\033[0m  {msg}")


def warn(msg: str) -> None:
    print(f"   \033[33m!!\033[0m  {msg}")


def info(msg: str) -> None:
    print(f"       {msg}")


def stop(msg: str) -> int:
    print(f"\n\033[1;31mSTOPPED: {msg}\033[0m", file=sys.stderr)
    return 1


def ask_secret(ep: Endpoint) -> str:
    skip = "" if ep.required else " (Enter to skip)"
    for _ in range(3):
        try:
            value = clean_pasted(getpass.getpass(f"   Signing secret of the {ep.label}{skip}: "))
        except (EOFError, KeyboardInterrupt):
            print()
            return ""
        if not value:
            return ""
        problem = secret_problem(value)
        if problem is None:
            return value
        warn(problem)
    return ""


def _read_env() -> tuple[str, dict[str, str | None]]:
    return ENV_FILE.read_bytes().decode("utf-8"), dict(dotenv_values(ENV_FILE))


def main() -> int:
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return stop("run this as root: it edits the API's .env and restarts the API")
    if not ENV_FILE.is_file():
        return stop(f"{ENV_FILE} not found (set CAPIMAX_ENV_FILE)")

    say("1. What the API uses now")
    text, dotenv = _read_env()
    proc = service_environment()
    for ep in ENDPOINTS:
        value, source = loaded_value(ep.key, dotenv, proc)
        print(f"   {ep.label} -> {ep.key}")
        info(f"loaded: {fingerprint(value)} (from {source})")
        lines = len(assignments(text, ep.key))
        if lines > 1:
            warn(f".env sets it on {lines} lines and the LAST one wins: this run leaves one")
        for place in unit_overrides(ep.key):
            warn(f"also set in {place}")
        refused = refusals_logged(ep.mark)
        if refused and refused[0]:
            warn(f"deliveries refused in the last 24 h: {refused[0]} (last at {refused[1]})")
        elif refused is not None:
            info("deliveries refused in the last 24 h: 0")

    say("2. The endpoints' signing secrets, from Stripe")
    base = public_api_base(dotenv) or "https://api.<your domain>"
    info("In Stripe, in LIVE mode: Developers -> Webhooks, open the endpoint, then")
    info("'Signing secret' -> Reveal, copy it and paste it here (nothing shows while you paste).")
    info(f"Deposits endpoint URL: {base}{DEPOSITS.path}")
    info(f"Connect endpoint URL (only if you created one): {base}{CONNECT.path}")
    wanted: dict[Endpoint, str] = {}
    for ep in ENDPOINTS:
        secret = ask_secret(ep)
        if not secret:
            if ep.required:
                return stop("no signing secret entered for the deposits endpoint: nothing changed")
            info(f"{ep.label}: skipped")
            continue
        wanted[ep] = secret
        value, _ = loaded_value(ep.key, dotenv, proc)
        if hmac.compare_digest((value or "").encode(), secret.encode()):
            ok(f"{ep.label}: same secret as the API loads ({fingerprint(secret)})")
        else:
            warn(
                f"{ep.label}: the API loads {fingerprint(value)},"
                f" Stripe signs with {fingerprint(secret)}"
            )

    say("3. Update the API")
    for ep in wanted:
        places = unit_overrides(ep.key)
        if places:
            return stop(
                f"{ep.key} is also set in {', '.join(places)}, which wins over .env: remove it"
                f" there (systemctl cat {SERVICE}), run systemctl daemon-reload, then run this"
                " again"
            )
    to_write = [
        ep
        for ep, secret in wanted.items()
        if len(assignments(text, ep.key)) != 1 or lookup(dotenv, ep.key)[1] != secret
    ]
    must_restart = bool(to_write) or any(
        loaded_value(ep.key, dotenv, proc)[0] != secret for ep, secret in wanted.items()
    )
    backup = None
    if to_write:
        new_text = text
        for ep in to_write:
            new_text = with_single_assignment(new_text, ep.key, wanted[ep])
        backup = write_env(new_text)
        ok(f".env updated ({', '.join(ep.key for ep in to_write)}); the previous one: {backup}")
    restarted = False
    if must_restart:
        if not restart_api():
            return stop(f"the API did not come back: journalctl -u {SERVICE} -n 80")
        restarted = True
        ok("API restarted and healthy")
        text, dotenv = _read_env()
        proc = service_environment()
        for ep, secret in wanted.items():
            value, source = loaded_value(ep.key, dotenv, proc)
            if value != secret:
                return stop(
                    f"the API still loads another {ep.key} ({fingerprint(value)}, from {source})"
                )
        ok("the API now loads the secrets Stripe signs with")
    else:
        ok("nothing to change: the API already loads these secrets")

    say("4. Proof: a request signed with that secret, sent the way Stripe sends it")
    failed = False
    for ep, secret in wanted.items():
        verdict, detail = prove(ep, secret, dotenv)
        if verdict == "rejected" and not restarted and restart_api():
            # the running API may predate an edit of .env: restart it once and ask again
            restarted = True
            verdict, detail = prove(ep, secret, dotenv)
        if verdict == "accepted":
            ok(f"{ep.label}: {detail}")
        elif verdict == "skipped":
            warn(f"{ep.label}: {detail}")
        else:
            failed = True
            warn(f"{ep.label}: {detail}")

    say("5. Payments")
    _, cron = lookup(dotenv, "CRON_SECRET")
    if cron:
        status, answer = _http("POST", API_LOCAL + RECONCILE_PATH, headers={"X-Cron-Secret": cron})
        (ok if status == 200 else warn)(f"payment reconcile: {answer.strip()[:200]}")
    pending = _psql(
        dotenv,
        "SELECT count(*) FROM payments WHERE status = 'pending'"
        " AND provider IN ('stripe', 'nowpayments') AND created_at < now() - interval '10 minutes'",
    )
    if pending == "0":
        ok("no card/crypto payment left pending")
    else:
        warn(f"card/crypto payments still pending: {pending} (/admin -> Payments)")

    if failed:
        return stop(
            "the API does not accept this signature yet: check the lines above, and that the"
            " secret was copied from the endpoint whose URL is shown in step 2, in LIVE mode"
        )
    say("Done")
    print("   Last check, in Stripe: the endpoint -> Event deliveries -> a failed")
    print("   checkout.session.completed -> Resend. It now answers 200. For a payment the")
    print("   reconcile already settled, the answer says already_processed (or duplicate):")
    print("   nothing is credited twice. Stripe also retries every failed delivery by itself")
    print("   for up to 3 days.")
    if backup:
        print(f"   The .env before this change: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
