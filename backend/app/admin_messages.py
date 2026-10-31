"""Messages to users, in the admin panel (client, 2026-10-28, as on Capimax BRX).

The team writes to one user (by email) or to everyone holding a role: investors, property
owners and developers, brokers, liquidity providers, or everyone. Writing a message is three
steps: compose (from scratch or from a saved template), review (how many people it reaches, a
few of them, how many turned announcement emails off, and the email exactly as it will read),
then Send. Each recipient gets it in their inbox (/messages), as a notification and, unless
"Also email it" is off, by email. The page of a sent message lists every recipient with whether
they read it and whether their email was sent, is waiting, failed, or was not sent (opted out).
Sent messages cannot be edited. Templates (name, subject, body) are kept on their own page.
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import secrets
import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.admin_listing import _STYLE, is_full_admin
from app.core.audit import write_audit
from app.core.db import session_scope
from app.core.errors import AppError
from app.models.identity import User
from app.models.messages import MessageBroadcast, MessageTemplate
from app.services import message_service
from app.services.message_service import AUDIENCES, BODY_MAX, SUBJECT_MAX

_env = Environment(autoescape=True)

MAIL_LABELS = {
    "sent": "Email sent",
    "queued": "Email waiting",
    "failed": "Email failed",
    "opted_out": "Not emailed (opted out)",
    "no_email": "Not emailed",
}
MAIL_BADGE = {"sent": "active", "queued": "draft", "failed": "closed"}
REPORT_FILTERS = (
    ("", "Everyone"),
    ("read", "Read"),
    ("unread", "Not read yet"),
    ("sent", "Email sent"),
    ("queued", "Email waiting"),
    ("failed", "Email failed"),
    ("opted_out", "Opted out of emails"),
    ("no_email", "Not emailed"),
)

_CSS = _STYLE + """ .num{text-align:right;white-space:nowrap} table td{font-size:13px}
 .kv{display:grid;grid-template-columns:180px 1fr;gap:6px 14px;font-size:14px} .kv div:nth-child(odd){color:#6b726c}
 .scroll{overflow-x:auto} .mono{font-family:ui-monospace,Consolas,monospace;font-size:13px}
 input[type=email],input[type=search]{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #d9dcd8;border-radius:8px;font-size:14px}
 textarea{min-height:220px;font-family:inherit;line-height:1.5} .body{white-space:pre-wrap;line-height:1.55;font-size:14px}
 .mail{border:1px solid #e8e6e1;border-radius:10px;background:#fafaf8;padding:14px 16px}
 .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
 .stat{border:1px solid #e8e6e1;border-radius:10px;padding:10px 12px;background:#fafaf8}
 .stat b{display:block;font-size:20px} .stat span{color:#6b726c;font-size:12px}
 .check{display:flex;gap:8px;align-items:center;font-weight:400} .check input{width:auto}
 .filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
"""

_HEAD = """<!doctype html><html><head><meta charset="utf-8"><title>{{ title }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{{ css|safe }}</style></head><body><div class="wrap">"""

_LIST = _env.from_string(
    _HEAD
    + """<div class="top"><div><div class="muted"><a href="/admin/">&larr; Admin</a> · <a href="/admin/messages/templates">Templates</a></div>
<h1>Messages to users</h1>
<p class="lead">Write to one user or to everyone holding a role. Each person gets it in their inbox on the platform, as a notification and by email.</p></div>
<div class="actions"><a class="btn primary" href="/admin/messages/new">New message</a></div></div>
<div class="card scroll"><table>
<tr><th>Subject</th><th>To</th><th class="num">Recipients</th><th class="num">Emails</th><th class="num">Read</th><th>Sent by</th><th>Sent</th></tr>
{% for r in rows %}<tr>
<td><a href="/admin/messages/sent/{{ r.b.id }}">{{ r.b.subject }}</a></td><td>{{ r.to or '—' }}</td>
<td class="num">{{ r.b.recipients }}</td><td class="num">{{ r.b.emails_queued if r.b.send_email else 'off' }}</td><td class="num">{{ r.read }}</td>
<td class="muted">{{ r.sender or '—' }}</td><td class="muted">{{ r.b.created_at.strftime('%d %b %Y %H:%M') }}</td></tr>
{% else %}<tr><td colspan="7" class="muted">No message sent yet.</td></tr>{% endfor %}
</table></div></div></body></html>"""
)

_FORM = _env.from_string(
    _HEAD
    + """<div class="top"><div><div class="muted"><a href="/admin/messages">&larr; Messages to users</a></div>
<h1>New message</h1><p class="lead">Nothing is sent from this page: the next step shows who it reaches and the email as it will read.</p></div></div>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
{% if templates %}<form class="card" method="get" action="/admin/messages/new"><label for="template">Start from a template</label>
<div class="actions"><select id="template" name="template" style="max-width:420px"><option value="">— None —</option>{% for t in templates %}<option value="{{ t.id }}" {{ 'selected' if f.template_id == t.id|string }}>{{ t.name }}</option>{% endfor %}</select>
<input type="hidden" name="to" value="{{ f.user_email }}"><button type="submit">Use it</button></div>
<p class="help">Fills in the subject and the message below; you can still change them. <a href="/admin/messages/templates">Manage templates</a></p></form>{% endif %}
<form class="card" method="post" action="/admin/messages/new">
<input type="hidden" name="token" value="{{ f.token }}"><input type="hidden" name="template_id" value="{{ f.template_id }}">
<label for="audience">Send to <span class="req">*</span></label>
<select id="audience" name="audience" onchange="document.getElementById('one').style.display=this.value==='user'?'block':'none'">{% for k, v in audiences.items() %}<option value="{{ k }}" {{ 'selected' if f.audience == k }}>{{ v[0] }}</option>{% endfor %}</select>
<p class="help">A group means every open account holding that role. A user who holds several roles gets the message once.</p>
<div id="one" style="display:{{ 'block' if f.audience == 'user' else 'none' }}"><label for="user_email">The user's email <span class="req">*</span></label>
<input id="user_email" type="email" name="user_email" value="{{ f.user_email }}" maxlength="320" placeholder="name@example.com"></div>
<label for="subject">Subject <span class="req">*</span></label><input id="subject" type="text" name="subject" value="{{ f.subject }}" maxlength="{{ subject_max }}" required>
<label for="body">Message <span class="req">*</span></label><textarea id="body" name="body" maxlength="{{ body_max }}" required dir="auto">{{ f.body }}</textarea>
<p class="help">Plain text; line breaks are kept. Links you type stay plain text in the inbox.</p>
<label class="check"><input type="checkbox" name="send_email" value="1" {{ 'checked' if f.send_email }}> Also email it</label>
<p class="help">For a group, people who turned off "Announcements" in their settings are not emailed (they still get it in their inbox). A message to one user is always emailed.</p>
<input type="hidden" name="action" value="review"><div class="actions" style="margin-top:14px"><button class="primary" type="submit">Review before sending</button></div>
</form></div></body></html>"""
)

_REVIEW = _env.from_string(
    _HEAD
    + """<div class="top"><div><div class="muted"><a href="/admin/messages">&larr; Messages to users</a></div>
<h1>Review and send</h1><p class="lead">Check who it reaches and how it reads. Nothing has been sent yet.</p></div></div>
<div class="card"><div class="stats">
<div class="stat"><b>{{ p.count }}</b><span>{{ 'person' if p.count == 1 else 'people' }} will get it in their inbox</span></div>
<div class="stat"><b>{{ (p.count - p.opted_out) if f.send_email else 0 }}</b><span>will be emailed</span></div>
{% if f.audience != 'user' %}<div class="stat"><b>{{ p.opted_out }}</b><span>turned announcement emails off</span></div>{% endif %}
</div>
<div class="kv" style="margin-top:14px"><div>To</div><div>{{ to }}</div>
{% if p.sample %}<div>{{ 'Recipient' if p.count == 1 else 'Among them' }}</div><div class="mono">{{ p.sample|join(', ') }}{% if p.count > p.sample|length %} and {{ p.count - p.sample|length }} more{% endif %}</div>{% endif %}
<div>Subject</div><div><b>{{ f.subject }}</b></div></div></div>
<div class="card"><h2>In the inbox</h2><div class="body" dir="auto">{{ f.body }}</div></div>
{% if f.send_email %}<div class="card"><h2>The email</h2><div class="mail"><div class="muted">Subject: {{ f.subject }}</div><div class="body" dir="auto" style="margin-top:8px">{{ email_body }}</div></div></div>{% endif %}
{% if p.count == 0 %}<div class="err">Nobody holds that role yet: there is nobody to send it to.</div>{% endif %}
<form method="post" action="/admin/messages/new" class="actions" onsubmit="setTimeout(()=>this.querySelectorAll('button').forEach(b=>b.disabled=true),0)">
{% for k in ('token', 'template_id', 'audience', 'user_email', 'subject', 'body') %}<input type="hidden" name="{{ k }}" value="{{ f[k] }}">{% endfor %}
{% if f.send_email %}<input type="hidden" name="send_email" value="1">{% endif %}
<button type="submit" name="action" value="edit">&larr; Change it</button>
{% if p.count %}<button class="primary" type="submit" name="action" value="send">Send to {{ p.count }} {{ 'person' if p.count == 1 else 'people' }}</button>{% endif %}
</form></div></body></html>"""
)

_DETAIL = _env.from_string(
    _HEAD
    + """<div class="top"><div><div class="muted"><a href="/admin/messages">&larr; Messages to users</a></div>
<h1>{{ b.subject }}</h1><p class="lead">To {{ to }} · sent {{ b.created_at.strftime('%d %b %Y %H:%M') }} UTC by {{ sender or '—' }}</p></div>
<div class="actions"><a class="btn" href="/admin/messages/new?resend={{ b.id }}">Write a similar one</a></div></div>
{% if done %}<div class="ok">{{ done }}</div>{% endif %}
<div class="card"><div class="stats">
<div class="stat"><b>{{ b.recipients }}</b><span>recipients</span></div>
<div class="stat"><b>{{ t.read }}</b><span>read it</span></div>
<div class="stat"><b>{{ t.sent }}</b><span>emails sent</span></div>
<div class="stat"><b>{{ t.queued }}</b><span>emails waiting</span></div>
<div class="stat"><b>{{ t.failed }}</b><span>emails failed</span></div>
<div class="stat"><b>{{ t.opted_out + t.no_email }}</b><span>not emailed</span></div>
</div>{% if not b.send_email %}<p class="help">Sent without email: inbox and notification only.</p>{% endif %}
{% if t.queued %}<p class="help">Waiting emails go out in batches, about 50 a minute.</p>{% endif %}</div>
<div class="card"><h2>Message</h2><div class="body" dir="auto">{{ b.body }}</div></div>
<div class="card"><h2>Recipients</h2>
<div class="filters">{% for k, label in filters %}<a class="btn {{ 'primary' if k == status }}" href="?status={{ k }}">{{ label }}</a>{% endfor %}</div>
<div class="scroll"><table><tr><th>Member</th><th>Read</th><th>Email</th></tr>
{% for r in rows %}<tr><td>{{ r.email }}{% if r.name %} <span class="muted">· {{ r.name }}</span>{% endif %}</td>
<td>{{ r.read_at.strftime('%d %b %Y %H:%M') if r.read_at else '—' }}</td>
<td><span class="badge {{ badge.get(r.mail, '') }}">{{ mail[r.mail] }}</span>{% if r.error %} <span class="muted">{{ r.error|truncate(120) }}</span>{% endif %}</td></tr>
{% else %}<tr><td colspan="3" class="muted">Nobody matches.</td></tr>{% endfor %}
</table></div></div></div></body></html>"""
)

_TEMPLATES = _env.from_string(
    _HEAD
    + """<div class="top"><div><div class="muted"><a href="/admin/messages">&larr; Messages to users</a></div>
<h1>Message templates</h1><p class="lead">Subjects and messages the team reuses. Choose one when writing a message; it can still be changed before sending.</p></div></div>
{% if error %}<div class="err">{{ error }}</div>{% endif %}{% if done %}<div class="ok">{{ done }}</div>{% endif %}
<div class="card scroll"><table><tr><th>Name</th><th>Subject</th><th>Changed</th><th></th></tr>
{% for t in templates %}<tr><td><b>{{ t.name }}</b></td><td>{{ t.subject }}</td><td class="muted">{{ t.updated_at.strftime('%d %b %Y') if t.updated_at }}</td>
<td class="actions"><a class="btn mini" href="/admin/messages/new?template={{ t.id }}">Use</a><a class="btn mini" href="/admin/messages/templates?edit={{ t.id }}">Edit</a>
<form class="inline" method="post" onsubmit="return confirm('Delete this template? Messages already sent keep their text.')"><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="{{ t.id }}"><button class="mini danger" type="submit">Delete</button></form></td></tr>
{% else %}<tr><td colspan="4" class="muted">No template yet.</td></tr>{% endfor %}</table></div>
<form class="card" method="post"><h2>{{ 'Edit ' ~ e.name if e.id else 'New template' }}</h2>
<input type="hidden" name="action" value="save"><input type="hidden" name="id" value="{{ e.id or '' }}">
<label for="name">Name <span class="req">*</span></label><input id="name" type="text" name="name" value="{{ e.name or '' }}" maxlength="80" required placeholder="e.g. Monthly update">
<label for="subject">Subject <span class="req">*</span></label><input id="subject" type="text" name="subject" value="{{ e.subject or '' }}" maxlength="{{ subject_max }}" required>
<label for="body">Message <span class="req">*</span></label><textarea id="body" name="body" maxlength="{{ body_max }}" required dir="auto">{{ e.body or '' }}</textarea>
<div class="actions" style="margin-top:12px"><button class="primary" type="submit">Save template</button>{% if e.id %}<a class="btn" href="/admin/messages/templates">Cancel</a>{% endif %}</div>
</form></div></body></html>"""
)


def _gate(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse("/admin/login", status_code=302)
    if not is_full_admin(request):
        return HTMLResponse("Forbidden", status_code=403)
    return None


def _actor(request: Request) -> uuid.UUID | None:
    raw = request.session.get("admin_id")
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


def _uuid(raw: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


def _to_label(audience: str, user_email: str | None) -> str:
    if audience == "user":
        return user_email or "—"
    return AUDIENCES[audience][0]


async def _templates(session) -> list[MessageTemplate]:
    return list(
        (await session.execute(select(MessageTemplate).order_by(func.lower(MessageTemplate.name))))
        .scalars()
        .all()
    )


class MessagesView(BaseView):
    name = "Messages to users"
    icon = "fa-solid fa-envelope"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    @expose("/messages", methods=["GET"], identity="messages")
    async def sent(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        async with session_scope() as session:
            rows = await message_service.list_broadcasts(session)
        return HTMLResponse(_LIST.render(css=_CSS, title="Messages to users", rows=rows))

    @expose("/messages/new", methods=["GET", "POST"], identity="messages-new")
    async def compose(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        f = {
            "token": secrets.token_urlsafe(24),
            "template_id": "",
            "audience": "user",
            "user_email": "",
            "subject": "",
            "body": "",
            "send_email": True,
        }
        if request.method == "GET":
            q = request.query_params
            f["user_email"] = (q.get("to") or "").strip()[:320]
            async with session_scope() as session:
                templates = await _templates(session)
                tid = _uuid(q.get("template"))
                like = _uuid(q.get("resend"))
                if tid and (t := await session.get(MessageTemplate, tid)) is not None:
                    f.update(template_id=str(t.id), subject=t.subject, body=t.body)
                elif like and (b := await session.get(MessageBroadcast, like)) is not None:
                    f.update(audience=b.audience, subject=b.subject, body=b.body)
                    f["send_email"] = b.send_email
                    if b.user_id and (u := await session.get(User, b.user_id)) is not None:
                        f["user_email"] = u.email
            return HTMLResponse(self._form(f, templates))

        form = await request.form()
        for k in ("token", "template_id", "audience", "user_email", "subject", "body"):
            f[k] = str(form.get(k) or "")
        f["send_email"] = form.get("send_email") == "1"
        action = str(form.get("action") or "")
        async with session_scope() as session:
            templates = await _templates(session)
            if action == "edit":
                return HTMLResponse(self._form(f, templates))
            try:
                draft = await message_service.check(
                    session,
                    audience=f["audience"],
                    user_email=f["user_email"],
                    subject=f["subject"],
                    body=f["body"],
                )
            except AppError as exc:
                return HTMLResponse(self._form(f, templates, exc.message), status_code=400)
            f.update(subject=draft.subject, body=draft.body)
            if draft.user is not None:
                f["user_email"] = draft.user.email
            if action == "review":
                p = await message_service.preview(session, draft)
                to = _to_label(draft.audience, f["user_email"])
                html = _REVIEW.render(
                    css=_CSS,
                    title="Review and send",
                    f=f,
                    p=p,
                    to=to,
                    email_body=message_service.email_body(draft, None),
                )
                return HTMLResponse(html)
            if action != "send":
                return HTMLResponse(self._form(f, templates, "Unknown action."), status_code=400)
            try:
                broadcast, fresh = await message_service.send(
                    session,
                    draft,
                    send_email=f["send_email"],
                    client_token=f["token"],
                    actor_id=_actor(request),
                    template_id=_uuid(f["template_id"]),
                )
            except AppError as exc:
                return HTMLResponse(self._form(f, templates, exc.message), status_code=400)
        flag = "sent" if fresh else "again"
        return RedirectResponse(f"/admin/messages/sent/{broadcast.id}?{flag}=1", status_code=303)

    def _form(self, f: dict, templates: list, error: str = "") -> str:
        return _FORM.render(
            css=_CSS,
            title="New message",
            f=f,
            templates=templates,
            audiences=AUDIENCES,
            subject_max=SUBJECT_MAX,
            body_max=BODY_MAX,
            error=error,
        )

    @expose("/messages/templates", methods=["GET", "POST"], identity="messages-templates")
    async def template_page(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        error = done = ""
        e: dict = {}
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            tid = _uuid(form.get("id"))
            name = " ".join(str(form.get("name") or "").split())[:80]
            subject = " ".join(str(form.get("subject") or "").split())[:SUBJECT_MAX]
            body = message_service.clean_text(form.get("body"), BODY_MAX)
            e = {"id": str(tid) if tid else "", "name": name, "subject": subject, "body": body}
            try:
                async with session_scope() as session:
                    if action == "delete" and tid:
                        t = await session.get(MessageTemplate, tid)
                        if t is not None:
                            await session.delete(t)
                            await write_audit(
                                session,
                                action="message_template.deleted",
                                entity_type="message_template",
                                entity_id=str(tid),
                                actor_id=_actor(request),
                                before={"name": t.name},
                            )
                        done, e = "Template deleted.", {}
                    elif action == "save":
                        if len(name) < 2 or len(subject) < 3 or not body:
                            raise AppError(
                                "TEMPLATE_INCOMPLETE",
                                "Give the template a name, a subject (3 characters or more) and a message.",
                                status_code=422,
                            )
                        t = await session.get(MessageTemplate, tid) if tid else None
                        if t is None:
                            t = MessageTemplate(created_by=_actor(request))
                            session.add(t)
                        t.name, t.subject, t.body = name, subject, body
                        await session.flush()
                        await write_audit(
                            session,
                            action="message_template.saved",
                            entity_type="message_template",
                            entity_id=str(t.id),
                            actor_id=_actor(request),
                            after={"name": name, "subject": subject},
                        )
                        done, e = f"Template “{name}” saved.", {}
            except AppError as exc:
                error = exc.message
            except IntegrityError:
                error = "Another template already has that name."
        async with session_scope() as session:
            if request.method == "GET" and (eid := _uuid(request.query_params.get("edit"))):
                if (t := await session.get(MessageTemplate, eid)) is not None:
                    e = {"id": str(t.id), "name": t.name, "subject": t.subject, "body": t.body}
            templates = await _templates(session)
        html = _TEMPLATES.render(
            css=_CSS,
            title="Message templates",
            templates=templates,
            e=e,
            error=error,
            done=done,
            subject_max=SUBJECT_MAX,
            body_max=BODY_MAX,
        )
        return HTMLResponse(html, status_code=400 if error else 200)

    @expose("/messages/sent/{bid}", methods=["GET"], identity="messages-one")
    async def one(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        bid = _uuid(request.path_params["bid"])
        if bid is None:
            return HTMLResponse("Not found", status_code=404)
        status = request.query_params.get("status", "")
        if status not in dict(REPORT_FILTERS):
            status = ""
        async with session_scope() as session:
            b = await session.get(MessageBroadcast, bid)
            if b is None:
                return HTMLResponse("Not found", status_code=404)
            everyone = await message_service.recipient_report(session, bid)
            rows = (
                everyone
                if not status
                else await message_service.recipient_report(session, bid, status=status)
            )
            sender = await session.scalar(select(User.email).where(User.id == b.created_by))
            to_email = (
                await session.scalar(select(User.email).where(User.id == b.user_id))
                if b.user_id
                else None
            )
        q = request.query_params
        done = (
            f"Sent to {b.recipients} {'person' if b.recipients == 1 else 'people'}."
            if q.get("sent")
            else "This form was already sent; it was not sent again." if q.get("again") else ""
        )
        html = _DETAIL.render(
            css=_CSS,
            title=b.subject,
            b=b,
            to=_to_label(b.audience, to_email),
            sender=sender,
            t=message_service.tally(everyone),
            rows=rows,
            filters=REPORT_FILTERS,
            status=status,
            mail=MAIL_LABELS,
            badge=MAIL_BADGE,
            done=done,
        )
        return HTMLResponse(html)


MESSAGE_VIEWS = (MessagesView,)
