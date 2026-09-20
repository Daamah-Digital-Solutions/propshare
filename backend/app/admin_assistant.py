"""Admin panel for the assistant (plan §4): conversations with an AUDITED transcript view,
proposed actions, support tickets with a reply form, the knowledge base with explicit
approval, and a status dashboard.

Every view is full-admin only (``AdminOnlyModelView`` + the path gate in ``AdminAuth``).
Message text is ciphertext in the database; opening a conversation's details page decrypts
it on demand and writes ``assistant.transcript_viewed`` to the audit log (who, which
conversation, which ticket) — staff can read, but never silently.
"""

# ruff: noqa: E501  (inline HTML templates)
from __future__ import annotations

import datetime as dt
import html as _html
import json
import uuid

from markupsafe import Markup
from sqladmin import BaseView, ModelView, action, expose
from sqlalchemy import Integer, cast, func, select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.admin_listing import is_full_admin
from app.core import crypto
from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.errors import AppError
from app.models import (
    AssistantActionProposal,
    AssistantConversation,
    AssistantMessage,
    KbArticle,
    SupportTicket,
    SupportTicketMessage,
)
from app.services import kb_service, ticket_service
from app.services.assistant import agent


def _actor(request: Request) -> uuid.UUID | None:
    raw = request.session.get("admin_id")
    return uuid.UUID(raw) if raw else None


def _admin_only(request: Request) -> bool:
    return bool(request.session.get("admin_id")) and is_full_admin(request)


class _AdminOnly(ModelView):
    def is_accessible(self, request: Request) -> bool:
        return _admin_only(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)


# --------------------------------------------------------------------------- #
# Conversations (audited transcript)
# --------------------------------------------------------------------------- #
def _fmt_cost(m: AssistantConversation, _a) -> str:
    return f"${m.est_cost_usd:.4f}" if m.est_cost_usd is not None else "-"


class AssistantConversationAdmin(_AdminOnly, model=AssistantConversation):
    name = "Assistant Conversation"
    name_plural = "Assistant Conversations"
    icon = "fa-solid fa-comments"
    category = "Assistant"
    column_list = [
        AssistantConversation.created_at,
        AssistantConversation.user_id,
        AssistantConversation.visitor_key,
        AssistantConversation.lang,
        AssistantConversation.status,
        AssistantConversation.message_count,
        AssistantConversation.est_cost_usd,
        AssistantConversation.model,
        AssistantConversation.ticket_id,
        AssistantConversation.last_message_at,
    ]
    column_default_sort = [(AssistantConversation.last_message_at, True)]
    column_searchable_list = [AssistantConversation.visitor_key, AssistantConversation.title]
    column_formatters = {AssistantConversation.est_cost_usd: _fmt_cost}
    column_formatters_detail = {AssistantConversation.est_cost_usd: _fmt_cost}
    details_template = "admin/assistant_conversation_details.html"
    can_create = False
    can_edit = False
    can_delete = True  # retention is the cron's job; manual delete stays possible
    page_size = 50

    async def get_object_for_details(self, request: Request):
        """Decrypt the transcript for this page AND write the audit row. The decrypted rows
        are attached to the model object for the template only; nothing is cached."""
        # SQLAdmin calls this twice per page (permission check, then render): decrypt and
        # audit once per request, not once per call.
        cached = getattr(request.state, "transcript_conv", None)
        if cached is not None and str(cached.id) == str(request.path_params.get("pk")):
            return cached
        conv = await super().get_object_for_details(request)
        if conv is None:
            return None
        actor = _actor(request)
        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        select(AssistantMessage)
                        .where(AssistantMessage.conversation_id == conv.id)
                        .order_by(AssistantMessage.created_at)
                    )
                )
                .scalars()
                .all()
            )
            transcript = []
            decrypt_error = None
            for m in rows:
                try:
                    transcript.append(
                        {
                            "id": str(m.id),
                            "role": m.role,
                            "text": m.text or "",
                            "tool_calls": m.tool_calls if isinstance(m.tool_calls, list) else [],
                            "cards": m.cards if isinstance(m.cards, list) else [],
                            "confidence": m.confidence,
                            "flags": m.guardrail_flags or [],
                            "feedback": m.feedback,
                            "usage": m.usage or {},
                            "latency_ms": m.latency_ms,
                            "created_at": m.created_at,
                            "key": m.enc_key_id,
                        }
                    )
                except crypto.DecryptionFailed as exc:  # pragma: no cover - key mismatch
                    decrypt_error = str(exc)
                    break
            ticket_no = None
            if conv.ticket_id is not None:
                ticket_no = await session.scalar(
                    select(SupportTicket.ticket_no).where(SupportTicket.id == conv.ticket_id)
                )
            await write_audit(
                session,
                action="assistant.transcript_viewed",
                entity_type="assistant_conversation",
                entity_id=str(conv.id),
                actor_id=actor,
                after={"messages": len(transcript), "ticket_no": ticket_no},
                ip=request.client.host if request.client else None,
            )
        conv._transcript = transcript  # type: ignore[attr-defined]
        conv._decrypt_error = decrypt_error  # type: ignore[attr-defined]
        conv._ticket_no = ticket_no  # type: ignore[attr-defined]
        request.state.transcript_conv = conv
        return conv


class AssistantActionProposalAdmin(_AdminOnly, model=AssistantActionProposal):
    name = "Assistant Action"
    name_plural = "Assistant Actions"
    icon = "fa-solid fa-hand-pointer"
    category = "Assistant"
    column_list = [
        AssistantActionProposal.created_at,
        AssistantActionProposal.user_id,
        AssistantActionProposal.action,
        AssistantActionProposal.status,
        AssistantActionProposal.summary,
        AssistantActionProposal.decided_at,
    ]
    column_default_sort = [(AssistantActionProposal.created_at, True)]
    column_details_exclude_list = [AssistantActionProposal.token_hash]
    can_create = False
    can_edit = False
    can_delete = False


# --------------------------------------------------------------------------- #
# Support tickets
# --------------------------------------------------------------------------- #
def _fmt_ticket_no(m: SupportTicket, _a) -> Markup:
    return Markup(f"<strong>{_html.escape(m.ticket_no or '')}</strong>")


class SupportTicketAdmin(_AdminOnly, model=SupportTicket):
    name = "Support Ticket"
    name_plural = "Support Tickets"
    icon = "fa-solid fa-life-ring"
    category = "Assistant"
    column_list = [
        SupportTicket.ticket_no,
        SupportTicket.created_at,
        SupportTicket.kind,
        SupportTicket.category,
        SupportTicket.priority,
        SupportTicket.status,
        SupportTicket.subject,
        SupportTicket.source,
        SupportTicket.user_id,
        SupportTicket.contact_email,
    ]
    column_default_sort = [(SupportTicket.created_at, True)]
    column_searchable_list = [
        SupportTicket.ticket_no,
        SupportTicket.subject,
        SupportTicket.contact_email,
    ]
    column_formatters = {SupportTicket.ticket_no: _fmt_ticket_no}
    column_details_exclude_list = [SupportTicket.context]
    details_template = "admin/support_ticket_details.html"
    can_create = False
    can_edit = False  # status changes go through the audited service (actions below)
    can_delete = False
    page_size = 50

    async def get_object_for_details(self, request: Request):
        ticket = await super().get_object_for_details(request)
        if ticket is None:
            return None
        async with session_scope() as session:
            msgs = await ticket_service.list_messages(
                session, ticket_id=ticket.id, include_internal=True
            )
            thread = [
                {
                    "author_type": m.author_type,
                    "body": m.body,
                    "internal": m.internal,
                    "created_at": m.created_at,
                }
                for m in msgs
            ]
        ticket._thread = thread  # type: ignore[attr-defined]
        ticket._transcript_url = (  # type: ignore[attr-defined]
            f"/admin/assistant-conversation/details/{ticket.conversation_id}"
            if ticket.conversation_id
            else None
        )
        return ticket

    async def _set_status(self, request: Request, status: str) -> RedirectResponse:
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        actor = _actor(request)
        async with session_scope() as session:
            for pk in pks:
                try:
                    await ticket_service.set_status(
                        session, actor_id=actor, ticket_id=uuid.UUID(pk), status=status
                    )
                except AppError:
                    continue
        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity), 302
        )

    @action(
        name="ticket_in_progress", label="Mark in progress", add_in_detail=True, add_in_list=True
    )
    async def ticket_in_progress(self, request: Request) -> RedirectResponse:
        return await self._set_status(request, "in_progress")

    @action(
        name="ticket_resolve",
        label="Resolve",
        confirmation_message="Mark the selected ticket(s) as resolved?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def ticket_resolve(self, request: Request) -> RedirectResponse:
        return await self._set_status(request, "resolved")

    @action(
        name="ticket_close",
        label="Close",
        confirmation_message="Close the selected ticket(s)? The owner can no longer reply.",
        add_in_detail=True,
        add_in_list=True,
    )
    async def ticket_close(self, request: Request) -> RedirectResponse:
        return await self._set_status(request, "closed")


class SupportTicketMessageAdmin(_AdminOnly, model=SupportTicketMessage):
    name = "Ticket Message"
    name_plural = "Ticket Messages"
    icon = "fa-solid fa-message"
    category = "Assistant"
    column_list = [
        SupportTicketMessage.created_at,
        SupportTicketMessage.ticket_id,
        SupportTicketMessage.author_type,
        SupportTicketMessage.internal,
        SupportTicketMessage.body,
    ]
    column_default_sort = [(SupportTicketMessage.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


_REPLY_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Reply to {ticket_no}</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f4f5f3;margin:0;padding:24px;color:#23302a}}
.wrap{{max-width:760px;margin:0 auto}} .card{{background:#fff;border:1px solid #e8e6e1;border-radius:14px;padding:20px 22px;margin-bottom:18px}}
h1{{font-size:20px;margin:0 0 12px}} label{{display:block;font-weight:600;margin:12px 0 4px}} textarea,select{{width:100%;box-sizing:border-box;padding:8px;border:1px solid #d9dcd8;border-radius:8px;font:inherit}}
button{{padding:8px 14px;border-radius:8px;border:1px solid #198653;background:#198653;color:#fff;font-weight:600;cursor:pointer;margin-top:12px}}
.err{{color:#b00;margin-bottom:8px}} .hint{{color:#6b726c;font-size:13px}} a{{color:#0f6e4e}}</style></head><body><div class="wrap">
<div class="card"><h1>Reply to {ticket_no}</h1><p class="hint">{subject}</p>{error}
<form method="post"><label>Message</label><textarea name="body" rows="8" required></textarea>
<label><input type="checkbox" name="internal" value="1"> Internal note (staff only; the owner never sees it and is not notified)</label>
<label>Status after sending</label><select name="status"><option value="">Keep as is (public replies become "waiting for user")</option>
<option value="in_progress">In progress</option><option value="waiting_user">Waiting for user</option><option value="resolved">Resolved</option><option value="closed">Closed</option></select>
<button type="submit">Send</button> <a href="/admin/support-ticket/details/{ticket_id}">Back to ticket</a></form></div></div></body></html>"""


class TicketReplyView(BaseView):
    """Staff reply / internal note form. Public replies notify (and email) the ticket owner."""

    name = "Ticket reply"
    icon = "fa-solid fa-reply"

    def is_visible(self, request: Request) -> bool:
        return False  # reached from the ticket details page, not the sidebar

    def is_accessible(self, request: Request) -> bool:
        return _admin_only(request)

    @expose("/support-ticket/reply/{ticket_id}", methods=["GET", "POST"])
    async def reply(self, request: Request):
        if not request.session.get("admin_id"):
            return RedirectResponse("/admin/login", status_code=302)
        if not is_full_admin(request):
            return HTMLResponse("Forbidden", status_code=403)
        try:
            ticket_id = uuid.UUID(str(request.path_params["ticket_id"]))
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        error = ""
        async with session_scope() as session:
            ticket = await session.get(SupportTicket, ticket_id)
            if ticket is None:
                return HTMLResponse("Not found", status_code=404)
            ticket_no, subject = ticket.ticket_no, ticket.subject or ""
            if request.method == "POST":
                form = await request.form()
                try:
                    await ticket_service.staff_reply(
                        session,
                        actor_id=_actor(request),
                        ticket_id=ticket_id,
                        body=str(form.get("body") or ""),
                        internal=bool(form.get("internal")),
                        new_status=str(form.get("status") or "") or None,
                    )
                    return RedirectResponse(
                        f"/admin/support-ticket/details/{ticket_id}", status_code=303
                    )
                except AppError as exc:
                    error = exc.message
        html = _REPLY_PAGE.format(
            ticket_no=_html.escape(ticket_no),
            subject=_html.escape(subject),
            ticket_id=ticket_id,
            error=f'<p class="err">{_html.escape(error)}</p>' if error else "",
        )
        return HTMLResponse(html, status_code=400 if error else 200)


# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #
class KbArticleAdmin(_AdminOnly, model=KbArticle):
    name = "Knowledge Article"
    name_plural = "Knowledge Base"
    icon = "fa-solid fa-book"
    category = "Assistant"
    column_list = [
        KbArticle.slug,
        KbArticle.lang,
        KbArticle.version,
        KbArticle.status,
        KbArticle.title,
        KbArticle.category,
        KbArticle.priority,
        KbArticle.approved_at,
        KbArticle.updated_at,
    ]
    column_default_sort = [(KbArticle.slug, False), (KbArticle.version, True)]
    column_searchable_list = [KbArticle.slug, KbArticle.title, KbArticle.body_md]
    form_columns = [
        KbArticle.slug,
        KbArticle.lang,
        KbArticle.title,
        KbArticle.body_md,
        KbArticle.category,
        KbArticle.audience,
        KbArticle.priority,
        KbArticle.source_ref,
    ]
    column_labels = {KbArticle.body_md: "Body (Markdown)", KbArticle.source_ref: "Source page"}
    can_create = True  # a new DRAFT version
    can_edit = True  # drafts only (see on_model_change)
    can_delete = True  # drafts only

    async def on_model_change(self, data, model, is_created, request) -> None:
        """Every save is a draft. An approved or retired version is immutable: create a new
        version instead, then approve it (the old one retires automatically)."""
        if not is_created and getattr(model, "status", "draft") != "draft":
            raise ValueError(
                "Approved and retired versions cannot be edited. Create a new version "
                "(same slug + language) and approve it."
            )
        data["status"] = "draft"
        if is_created:
            async with session_scope() as session:
                latest = await session.scalar(
                    select(func.max(KbArticle.version)).where(
                        KbArticle.slug == data.get("slug"), KbArticle.lang == data.get("lang")
                    )
                )
            data["version"] = int(latest or 0) + 1
        data["updated_at"] = dt.datetime.now(dt.UTC)

    async def on_model_delete(self, model, request) -> None:
        if getattr(model, "status", "draft") != "draft":
            raise ValueError("Only drafts can be deleted; retire an approved version instead.")

    @action(
        name="kb_approve",
        label="Approve (goes live for the assistant)",
        confirmation_message=(
            "Approve the selected version(s)? The assistant starts using the text immediately "
            "and any previously approved version of the same article is retired."
        ),
        add_in_detail=True,
        add_in_list=True,
    )
    async def kb_approve(self, request: Request) -> RedirectResponse:
        return await self._kb(request, kb_service.approve)

    @action(
        name="kb_retire",
        label="Retire (assistant stops using it)",
        confirmation_message="Retire the selected version(s)?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def kb_retire(self, request: Request) -> RedirectResponse:
        return await self._kb(request, kb_service.retire)

    async def _kb(self, request: Request, fn) -> RedirectResponse:
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        actor = _actor(request)
        async with session_scope() as session:
            for pk in pks:
                try:
                    await fn(session, article_id=uuid.UUID(pk), actor_id=actor)
                except (AppError, ValueError):
                    continue
        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity), 302
        )


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
_DASH_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Assistant status</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f4f5f3;margin:0;padding:24px;color:#23302a}
.wrap{max-width:960px;margin:0 auto} .card{background:#fff;border:1px solid #e8e6e1;border-radius:14px;padding:20px 22px;margin-bottom:18px}
h1{font-size:22px;margin:0 0 6px} h2{font-size:15px;margin:0 0 10px;color:#0f6e4e;text-transform:uppercase;letter-spacing:.04em}
table{border-collapse:collapse;width:100%} td,th{padding:6px 8px;border-bottom:1px solid #eee;text-align:left;font-size:14px}
.ok{color:#0f6e4e;font-weight:600} .bad{color:#b00;font-weight:600} .hint{color:#6b726c;font-size:13px} a{color:#0f6e4e}</style></head>
<body><div class="wrap"><h1>AI assistant</h1><p class="hint">Everything here is read from the live settings and today's usage. Change switches under <a href="/admin/platform-setting/list">Platform Settings</a> (keys starting with <code>assistant_</code>).</p>
<div class="card"><h2>Readiness</h2><table>{{ rows }}</table></div>
<div class="card"><h2>Today (UTC)</h2><table>{{ today }}</table></div>
<div class="card"><h2>Where to go</h2><p><a href="/admin/assistant-conversation/list">Conversations</a> · <a href="/admin/support-ticket/list">Support tickets</a> · <a href="/admin/kb-article/list">Knowledge base</a> · <a href="/admin/assistant-action-proposal/list">Proposed actions</a></p>
<p class="hint">Opening a conversation decrypts its transcript and is written to the audit log.</p></div></div></body></html>"""


class AssistantDashboardView(BaseView):
    name = "Assistant status"
    icon = "fa-solid fa-robot"
    category = "Assistant"

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    def is_accessible(self, request: Request) -> bool:
        return _admin_only(request)

    @expose("/assistant-status", methods=["GET"])
    async def status(self, request: Request):
        if not request.session.get("admin_id"):
            return RedirectResponse("/admin/login", status_code=302)
        if not is_full_admin(request):
            return HTMLResponse("Forbidden", status_code=403)
        env = get_settings()
        async with session_scope() as session:
            s = await agent.load_settings(session)
            start = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            msgs = await session.scalar(
                select(func.count())
                .select_from(AssistantMessage)
                .where(AssistantMessage.role == "user", AssistantMessage.created_at >= start)
            )
            usage = AssistantMessage.usage
            tokens = await session.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            cast(usage["input_tokens"].astext, Integer)
                            + cast(usage["output_tokens"].astext, Integer)
                        ),
                        0,
                    )
                ).where(AssistantMessage.role == "assistant", AssistantMessage.created_at >= start)
            )
            cost = await session.scalar(
                select(func.coalesce(func.sum(AssistantConversation.est_cost_usd), 0)).where(
                    AssistantConversation.last_message_at >= start
                )
            )
            safe = await session.scalar(
                select(func.count())
                .select_from(AssistantMessage)
                .where(
                    AssistantMessage.role == "assistant",
                    AssistantMessage.confidence == "safe_mode",
                    AssistantMessage.created_at >= start,
                )
            )
            open_tickets = await session.scalar(
                select(func.count())
                .select_from(SupportTicket)
                .where(SupportTicket.status.in_(("open", "in_progress")))
            )

        def row(label, ok, value):
            cls = "ok" if ok else "bad"
            return f"<tr><th>{_html.escape(label)}</th><td class='{cls}'>{_html.escape(str(value))}</td></tr>"

        rows = "".join(
            [
                row(
                    "Deploy switch (ASSISTANT_ENABLED)",
                    env.assistant_enabled,
                    env.assistant_enabled,
                ),
                row("Provider key present", bool(env.openai_api_key), bool(env.openai_api_key)),
                row(
                    "Encryption key file",
                    crypto.is_configured(),
                    "ok" if crypto.is_configured() else "missing",
                ),
                row(
                    "HMAC secret present",
                    bool(env.assistant_hmac_secret),
                    bool(env.assistant_hmac_secret),
                ),
                row("DB switch (assistant_enabled)", s.enabled, s.enabled),
                row(
                    "Model (assistant_model)",
                    bool(s.model),
                    s.model or "(not set — assistant unavailable)",
                ),
                row("Provider", True, s.provider),
                row("Rollout", True, s.rollout),
                row("Visitor mode", True, s.visitor_enabled),
                row("Reasoning effort / max output", True, f"{s.effort} / {s.max_output_tokens}"),
                row("Disabled tools", True, ", ".join(sorted(s.disabled_tools)) or "none"),
                row("Retention (days)", True, s.retention_days),
                row("Policy version", True, env.assistant_policy_version),
                row(
                    "Pricing table",
                    bool(s.pricing),
                    json.dumps(s.pricing) if s.pricing else "(empty — costs show as $0)",
                ),
            ]
        )
        today = "".join(
            [
                row("User messages", True, f"{msgs} (cap per user: {s.daily_message_cap})"),
                row("Tokens (in + out)", True, f"{tokens} (budget: {s.daily_token_budget})"),
                row("Estimated cost", True, f"${cost:.4f}"),
                row("Safe-mode answers", int(safe or 0) == 0, safe),
                row("Open tickets (all time)", True, open_tickets),
            ]
        )
        return HTMLResponse(_DASH_PAGE.replace("{{ rows }}", rows).replace("{{ today }}", today))


ASSISTANT_VIEWS = (
    AssistantDashboardView,
    AssistantConversationAdmin,
    AssistantActionProposalAdmin,
    SupportTicketAdmin,
    SupportTicketMessageAdmin,
    TicketReplyView,
    KbArticleAdmin,
)
