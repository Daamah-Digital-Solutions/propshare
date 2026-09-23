"""Guard rails around the model (plan §2/§4): who may call which tool, which links the model
may hand out, one-time confirmation tokens for proposed actions, and the sanitising of
everything that flows in or out of the model.

Principles:
  * the model proposes, the user confirms, the platform executes: a proposal row holds only
    the HASH of a one-time token that the user's own confirmation call must present;
  * tool results are data, never instructions: free text is wrapped under
    ``untrusted_text`` with control characters stripped and a hard size cap;
  * the model can only link to an allow-list of routes, never to arbitrary URLs;
  * the provider's safety identifier is a keyed hash of the user id with a dedicated
    secret (an unkeyed hash of a UUID could be reversed against our own database).
"""

from __future__ import annotations

import contextvars
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AssistantActionProposal
from app.services.assistant.context import AgentContext

if TYPE_CHECKING:  # the tools package imports this module; keep the dependency one-way
    from app.services.assistant.tools.base import ToolSpec

# --------------------------------------------------------------------------- #
# Authorisation
# --------------------------------------------------------------------------- #
VISITOR_TIERS = frozenset({"informational"})


def authorize(spec: ToolSpec, ctx: AgentContext) -> None:
    """Raise AppError when this caller may not use this tool."""
    if ctx.is_visitor and spec.tier not in VISITOR_TIERS:
        raise AppError(
            "SIGN_IN_REQUIRED",
            "Please sign in to use this. I can only look at account details for a signed-in user.",
            status_code=401,
        )
    if spec.roles and not (set(spec.roles) & set(ctx.roles)):
        raise AppError(
            "ROLE_REQUIRED",
            f"This is available to {', '.join(spec.roles)} accounts only.",
            status_code=403,
        )


# --------------------------------------------------------------------------- #
# Deep links: the ONLY URLs the model may hand out
# --------------------------------------------------------------------------- #
# Every path here MUST be a real route of the SPA (src/App.tsx) and every ``?tab=`` a tab the
# page actually opens from the URL — test_assistant_deep_links.py enforces both.
DEEP_LINKS: dict[str, tuple[str, str]] = {
    "marketplace": ("/marketplace", "Browse properties"),
    "property": ("/property/{slug}", "Open the property page"),
    "developer": ("/developers/{slug}", "Open the developer's profile"),
    "dashboard": ("/dashboard", "Open your dashboard"),
    "wallet": ("/dashboard?tab=wallet", "Open your wallet"),
    "deposit": ("/dashboard?tab=wallet", "Add funds from your wallet"),
    "withdraw": ("/dashboard?tab=wallet", "Request a withdrawal from your wallet"),
    "portfolio": ("/dashboard?tab=investments", "Open your investments"),
    "installments": ("/dashboard?tab=installments", "Your installment plans"),
    "returns": ("/dashboard?tab=returns", "Your returns and distributions"),
    "certificates": ("/dashboard?tab=certificates", "Your investment certificates"),
    "documents": ("/dashboard?tab=documents", "Your documents"),
    "verification_center": ("/dashboard?tab=verification", "Verification Center"),
    "my_exits": ("/dashboard?tab=exits", "Your exit requests"),
    "family": ("/dashboard?tab=family", "Family investment group"),
    "kyc": ("/kyc", "Start or continue identity verification"),
    "account": ("/settings", "Open your account settings"),
    "security": ("/settings?tab=security", "Password and two-factor authentication"),
    "roles": ("/settings", "Request another role (Account settings)"),
    "reports": ("/reports", "Reports"),
    "secondary_market": ("/secondary-market", "Secondary market"),
    "liquidity_market": ("/liquidity-market", "Liquidity provider market"),
    "exit": ("/exit-mechanisms", "How to exit an investment"),
    "notifications": ("/notifications", "Your notifications"),
    "support": ("/support", "Contact support"),
    "tickets": ("/support/tickets", "Your support tickets"),
    "fees": ("/fees", "Fees"),
    "how_it_works": ("/how-it-works", "How it works"),
    "faq": ("/faq", "Frequently asked questions"),
    "broker": ("/broker-dashboard", "Broker dashboard"),
    "owner": ("/owner-dashboard", "Owner dashboard"),
    "liquidity_dashboard": ("/liquidity-dashboard", "Liquidity provider dashboard"),
}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")
# developer slugs keep non-Latin letters (an Arabic company name stays Arabic)
_DEV_SLUG_RE = re.compile(r"^[^\W_][\w-]{0,120}$")


def _slug_ok(route_id: str, slug: str) -> bool:
    pattern = _DEV_SLUG_RE if route_id == "developer" else _SLUG_RE
    return bool(pattern.match(slug))


def make_link(route_id: str, slug: str | None = None) -> dict[str, str]:
    if route_id not in DEEP_LINKS:
        raise AppError("UNKNOWN_ROUTE", f"No link for {route_id!r}.", status_code=422)
    path, label = DEEP_LINKS[route_id]
    if "{slug}" in path:
        if not slug or not _slug_ok(route_id, slug):
            raise AppError("BAD_SLUG", "A valid slug is required.", status_code=422)
        path = path.replace("{slug}", slug)
    return {"route_id": route_id, "path": path, "label": label}


_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)


def url_allowed(url: str) -> bool:
    base = get_settings().app_base_url.rstrip("/")
    return url.startswith(base + "/") or url == base


# --------------------------------------------------------------------------- #
# Safety identifier for the provider (keyed hash, never the id)
# --------------------------------------------------------------------------- #
def safety_identifier(subject: str) -> str:
    secret = get_settings().assistant_hmac_secret
    if not secret:
        raise AppError("ASSISTANT_NOT_CONFIGURED", "HMAC secret missing.", status_code=503)
    return hmac.new(secret.encode(), subject.encode(), hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------- #
# Confirmation tokens for proposed actions
# --------------------------------------------------------------------------- #
PROPOSAL_TTL = dt.timedelta(minutes=15)

# Side channel from ``issue_confirmation`` to the agent loop: the raw token must reach the
# user's confirmation card but must NEVER be part of a tool result (which the model reads).
# The agent installs a fresh list before running a tool and drains it afterwards.
issued_tokens: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "assistant_issued_tokens", default=None
)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_confirmation(
    session: AsyncSession,
    *,
    ctx: AgentContext,
    action: str,
    params: dict[str, Any],
    summary: str,
    message_id: uuid.UUID | None = None,
) -> tuple[AssistantActionProposal, str]:
    """Create a proposal and return it with the ONE-TIME token. The token goes to the user's
    browser card only; the model never sees it (the tool output omits it)."""
    if ctx.user_id is None or ctx.conversation_id is None:
        raise AppError("SIGN_IN_REQUIRED", "Sign in to confirm actions.", status_code=401)
    token = secrets.token_urlsafe(32)
    proposal = AssistantActionProposal(
        conversation_id=ctx.conversation_id,
        message_id=message_id,
        user_id=ctx.user_id,
        action=action,
        params=params,
        summary=summary,
        token_hash=_hash_token(token),
        expires_at=dt.datetime.now(dt.UTC) + PROPOSAL_TTL,
    )
    session.add(proposal)
    await session.flush()
    sink = issued_tokens.get()
    if sink is not None:
        sink.append(
            {
                "proposal_id": str(proposal.id),
                "token": token,
                "expires_at": proposal.expires_at.isoformat(),
            }
        )
    return proposal, token


async def verify_confirmation(
    session: AsyncSession, *, user_id: uuid.UUID, proposal_id: uuid.UUID, token: str
) -> AssistantActionProposal:
    """The user's own, unexpired, still-pending proposal with a matching token. Marks it
    ``confirmed`` so the same token can never be replayed."""
    proposal = await session.get(AssistantActionProposal, proposal_id)
    if proposal is None or proposal.user_id != user_id:
        raise AppError("NOT_FOUND", "Proposal not found.", status_code=404)
    if proposal.status != "awaiting_user_confirmation":
        raise AppError("PROPOSAL_USED", "This action was already decided.", status_code=409)
    if proposal.expires_at < dt.datetime.now(dt.UTC):
        proposal.status = "expired"
        raise AppError("PROPOSAL_EXPIRED", "This confirmation has expired.", status_code=410)
    if not hmac.compare_digest(proposal.token_hash, _hash_token(token)):
        raise AppError("BAD_TOKEN", "Confirmation token does not match.", status_code=403)
    proposal.status = "confirmed"
    proposal.decided_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return proposal


# --------------------------------------------------------------------------- #
# Sanitising what goes to / comes from the model
# --------------------------------------------------------------------------- #
MAX_RESULT_BYTES = 8 * 1024
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PLATFORM_CTX_RE = re.compile(r"</?platform_context>", re.I)


def strip_platform_context_tags(text: str) -> str:
    """The <platform_context> block is server-generated; a user typing the tags is an
    attempt to spoof it."""
    return _PLATFORM_CTX_RE.sub("", text)


def _clean_strings(value: Any) -> Any:
    if isinstance(value, str):
        return _CONTROL_RE.sub("", value)
    if isinstance(value, list):
        return [_clean_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean_strings(v) for k, v in value.items()}
    return value


def sanitize_result(name: str, result: dict[str, Any], *, is_error: bool = False) -> str:
    """Tool result -> JSON text for the model: control characters stripped, free text marked
    untrusted, size capped. Truncation shrinks lists and strings until the payload fits, so
    the model always receives VALID JSON (never a cut-off document)."""
    data = _clean_strings(result)
    caps = ((40, 20, 500), (20, 10, 300), (10, 5, 200), (5, 3, 100), (0, 0, 0))
    for i, (keys, items, chars) in enumerate(caps):
        payload: dict[str, Any] = {"tool": name, "ok": not is_error}
        if i:
            payload["truncated"] = True
        payload["data"] = data if i == 0 else _truncate(data, keys, items, chars)
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(text.encode("utf-8")) <= MAX_RESULT_BYTES:
            return text
    return json.dumps(
        {"tool": name, "ok": not is_error, "truncated": True, "data": {}}, separators=(",", ":")
    )


def _truncate(data: Any, keys: int, items: int, chars: int) -> Any:
    if isinstance(data, dict):
        return {k: _truncate(v, keys, items, chars) for k, v in list(data.items())[:keys]}
    if isinstance(data, list):
        return [_truncate(v, keys, items, chars) for v in data[:items]]
    if isinstance(data, str) and len(data) > chars:
        return data[:chars] + "…"
    return data


def wrap_untrusted(text: str | None) -> dict[str, str] | None:
    """Free text that came from users or third parties is data for the model, not orders."""
    if text is None:
        return None
    return {"untrusted_text": _CONTROL_RE.sub("", text)[:2000]}


# Output flags: wording the platform must never use (legal/marketing decisions).
FORBIDDEN_TERMS = (
    re.compile(r"\btoken(s|ized|ization)?\b", re.I),
    re.compile(r"smart[- ]contract", re.I),
    re.compile(r"blockchain", re.I),
    re.compile(r"guarantee[ds]?\s+(return|profit|yield|income)", re.I),
    re.compile(r"risk[- ]free", re.I),
)


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(\s*(/[^)\s]*)\s*\)")
_BARE_PATH_RE = re.compile(
    r"(?<![\w/.])(/[a-z][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*(?:\?[a-z_]+=[a-z_]+)?)(?![\w/])"
)


def allowed_route_for(path: str) -> str | None:
    """The deep-link id whose path equals this relative path (property pages by prefix)."""
    for route_id, (pattern, _label) in DEEP_LINKS.items():
        if "{slug}" in pattern:
            prefix = pattern.split("{slug}")[0]
            if path.startswith(prefix) and _slug_ok(route_id, path[len(prefix) :]):
                return route_id
        elif path == pattern:
            return route_id
    return None


def postprocess_output(text: str) -> tuple[str, list[str], list[dict[str, str]]]:
    """Strip links that are not ours, flag forbidden wording, and collect the platform
    routes the text refers to. Returns (text, flags, links).

    The model is told to hand out pages only through ``prepare_deep_link``, but it still
    types relative markdown links it has seen. An allow-listed path becomes a real link card
    (``links``); anything else is reduced to its label so no unknown route reaches the user."""
    flags: list[str] = []
    links: list[dict[str, str]] = []

    def _link(m: re.Match) -> str:
        url = m.group(0)
        if url_allowed(url):
            return url
        flags.append("external_link_removed")
        return "[link removed]"

    def _md(m: re.Match) -> str:
        label, path = m.group(1), m.group(2)
        route_id = allowed_route_for(path)
        if route_id is None:
            flags.append("unknown_route_removed")
            return label
        if not any(link["path"] == path for link in links):
            links.append({"route_id": route_id, "path": path, "label": DEEP_LINKS[route_id][1]})
        return label

    cleaned = _URL_RE.sub(_link, text)
    cleaned = _MD_LINK_RE.sub(_md, cleaned)
    for m in _BARE_PATH_RE.finditer(cleaned):
        path = m.group(1)
        route_id = allowed_route_for(path)
        if route_id is not None and not any(link["path"] == path for link in links):
            links.append({"route_id": route_id, "path": path, "label": DEEP_LINKS[route_id][1]})
    for pattern in FORBIDDEN_TERMS:
        if pattern.search(cleaned):
            flags.append(f"forbidden_term:{pattern.pattern[:30]}")
    return cleaned, sorted(set(flags)), links
