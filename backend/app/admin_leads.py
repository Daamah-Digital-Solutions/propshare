"""Broker leads in the admin panel (client feedback #2).

What brokers bring: properties (ready) and projects (off-plan) with the owner / developer
contact and documents, and the clients they invited. Staff review a property / project,
mark it contacted, decline it with a message the broker sees, or create the listing from it
in the Listing Editor (which then marks the lead "listed" and tells the broker).

Full admins only. All writes go through ``broker_lead_service`` (audited, notifies the broker).
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.admin_listing import _STYLE, is_full_admin
from app.core.db import session_scope
from app.core.errors import AppError
from app.models import BrokerLead
from app.models.identity import User
from app.services import broker_lead_service
from app.services.integrations import storage

_env = Environment(autoescape=True)

_SHOW = {
    "new": (
        "New",
        lambda: BrokerLead.kind.in_(("property", "project")) & (BrokerLead.status == "new"),
    ),
    "contacted": (
        "Contacted",
        lambda: BrokerLead.kind.in_(("property", "project")) & (BrokerLead.status == "contacted"),
    ),
    "closed": (
        "Listed / declined / withdrawn",
        lambda: (
            BrokerLead.kind.in_(("property", "project"))
            & BrokerLead.status.in_(("listed", "declined", "withdrawn"))
        ),
    ),
    "clients": ("Client invitations", lambda: BrokerLead.kind == "client"),
}

STATUS_LABELS = {
    "new": ("New — not reviewed", "draft"),
    "contacted": ("Contacted", "draft"),
    "listed": ("Listed", "active"),
    "declined": ("Declined", "closed"),
    "withdrawn": ("Withdrawn by the broker", "closed"),
    "invited": ("Invited", "draft"),
    "joined": ("Joined through the broker's link", "active"),
    "cancelled": ("Cancelled", "closed"),
}

_HEAD = (
    """<!doctype html><html><head><meta charset="utf-8"><title>{{ page_title }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """ .tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px} .tabs a{padding:6px 12px;border:1px solid #d9dcd8;border-radius:999px;font-size:13px;text-decoration:none;color:#23302a;background:#fff}
 .tabs a.on{background:#198653;border-color:#198653;color:#fff;font-weight:600}
 dl.kv{display:grid;grid-template-columns:minmax(140px,220px) 1fr;gap:6px 14px;margin:0;font-size:14px} dl.kv dt{color:#6b726c} dl.kv dd{margin:0}
 .scroll{overflow-x:auto}
</style></head><body><div class="wrap">"""
)

_LIST_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/">&larr; Admin home</a></div><h1>Broker Leads</h1>
<p class="lead">Properties and projects brokers introduced for listing, and the clients they invited. A lead never becomes a listing by itself — create the listing from it when it is ready.</p></div></div>
<div class="tabs">{% for key, label, count in tabs %}<a class="{{ 'on' if key == show else '' }}" href="?show={{ key }}">{{ label }} ({{ count }})</a>{% endfor %}</div>
<div class="card scroll">{% if rows %}<table><tr><th>{{ 'Client' if show == 'clients' else 'Property / project' }}</th><th>Broker</th><th>{{ 'Contact' if show == 'clients' else 'Owner / developer' }}</th><th>Status</th><th>Received</th><th></th></tr>
{% for r in rows %}<tr>
<td>{% if show != 'clients' %}<a href="/admin/broker-leads/{{ r.l.id }}">{{ r.l.name }}</a><div class="muted">{{ r.l.kind }} · {{ r.l.details.get('location', '') }}</div>{% else %}{{ r.l.name }}{% endif %}</td>
<td>{{ r.broker }}</td>
<td>{% if show != 'clients' %}{{ r.l.details.get('owner_name', '—') }}<div class="muted">{{ r.l.email or '' }}{% if r.l.phone %} · {{ r.l.phone }}{% endif %}</div>{% else %}{{ r.l.email or '' }}{% if r.l.phone %}<div class="muted">{{ r.l.phone }}</div>{% endif %}{% endif %}</td>
<td><span class="badge {{ r.css }}">{{ r.label }}</span></td>
<td class="muted">{{ r.l.created_at.strftime('%Y-%m-%d') if r.l.created_at else '' }}</td>
<td>{% if show != 'clients' %}<a class="btn mini" href="/admin/broker-leads/{{ r.l.id }}">Open</a>{% endif %}</td></tr>{% endfor %}</table>
{% else %}<p class="muted">Nothing here.</p>{% endif %}</div>
</div></body></html>"""
)

_LEAD_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/broker-leads">&larr; Broker Leads</a></div>
<h1>{{ l.name }}</h1><p class="lead"><span class="badge {{ css }}">{{ label }}</span> &nbsp;{{ l.kind }} introduced by {{ broker }}</p></div>
{% if l.property_id %}<div class="actions"><a class="btn" href="/admin/listing/{{ l.property_id }}">Open the listing</a></div>{% endif %}</div>
{% if message %}<div class="{{ 'err' if error else 'ok' }}">{{ message }}</div>{% endif %}
{% if open %}<div class="card"><h2>Decision</h2><p class="muted">The broker sees the status in their Listings &amp; Referrals table and gets your message by email.</p>
<form method="post"><label for="note">Message to the broker <span class="muted">(required to decline)</span></label><textarea id="note" name="note"></textarea>
<div class="actions" style="margin-top:10px">
<a class="btn primary" href="/admin/listing/new?lead={{ l.id }}&amp;model={{ 'installment' if l.kind == 'project' else 'ready-income' }}">Create the listing from this lead</a>
{% if l.status == 'new' %}<button type="submit" name="action" value="contacted">Mark as contacted</button>{% endif %}
<button class="danger" type="submit" name="action" value="decline" onclick="return confirm('Decline this lead?')">Decline</button></div></form></div>{% endif %}
<div class="card"><h2>What the broker sent</h2><dl class="kv">
<dt>Location</dt><dd>{{ l.details.get('location', '—') }}</dd><dt>Type</dt><dd>{{ l.details.get('property_type') or '—' }}</dd>
<dt>Estimated value</dt><dd>{{ l.details.get('estimated_value') or '—' }}</dd><dt>Expected completion</dt><dd>{{ l.details.get('expected_completion') or '—' }}</dd>
<dt>Owner / developer</dt><dd>{{ l.details.get('owner_name', '—') }}</dd><dt>Email</dt><dd>{{ l.email or '—' }}</dd><dt>Phone</dt><dd>{{ l.phone or '—' }}</dd>
<dt>Notes</dt><dd style="white-space:pre-line">{{ l.details.get('notes') or '—' }}</dd>
{% if l.admin_note %}<dt>Last message to the broker</dt><dd style="white-space:pre-line">{{ l.admin_note }}</dd>{% endif %}</dl></div>
<div class="card scroll"><h2>Documents ({{ docs|length }})</h2>{% if docs %}<table>{% for d in docs %}<tr><td>{{ d.filename }}</td><td><a class="btn mini" href="/admin/broker-lead-doc?lead={{ l.id }}&amp;i={{ loop.index0 }}">Download</a></td></tr>{% endfor %}</table>{% else %}<p class="muted">No documents.</p>{% endif %}</div>
<div class="card"><h2>Broker</h2><dl class="kv"><dt>Name</dt><dd>{{ broker }}</dd><dt>Email</dt><dd>{{ broker_email }}</dd></dl></div>
</div></body></html>"""
)


def _gate(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse("/admin/login", status_code=302)
    if not is_full_admin(request):
        return HTMLResponse("Forbidden", status_code=403)
    return None


def _actor(request: Request) -> uuid.UUID | None:
    actor = request.session.get("admin_id")
    return uuid.UUID(actor) if actor else None


class BrokerLeadsView(BaseView):
    name = "Broker Leads"
    icon = "fa-solid fa-handshake"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    # The first exposed page is the sidebar link (SQLAdmin registers them bottom-up).
    @expose("/broker-leads", methods=["GET"], identity="broker-leads")
    async def leads_index(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        show = request.query_params.get("show", "new")
        if show not in _SHOW:
            show = "new"
        async with session_scope() as session:
            tabs = []
            for key, (label, cond) in _SHOW.items():
                tabs.append(
                    (
                        key,
                        label,
                        await session.scalar(select(func.count(BrokerLead.id)).where(cond())) or 0,
                    )
                )
            leads = (
                (
                    await session.execute(
                        select(BrokerLead)
                        .where(_SHOW[show][1]())
                        .order_by(BrokerLead.created_at.desc())
                        .limit(300)
                    )
                )
                .scalars()
                .all()
            )
            rows = []
            for lead in leads:
                label, css = STATUS_LABELS.get(lead.status, (lead.status, ""))
                broker = lead.broker
                rows.append(
                    {
                        "l": lead,
                        "label": label,
                        "css": css,
                        "broker": (broker.full_name or broker.email) if broker else "—",
                    }
                )
        return HTMLResponse(
            _LIST_PAGE.render(page_title="Broker Leads", rows=rows, tabs=tabs, show=show)
        )

    @expose("/broker-leads/{lead_id}", methods=["GET", "POST"], identity="broker-lead")
    async def lead_detail(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            lead_id = uuid.UUID(request.path_params["lead_id"])
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        message, error = "", False
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            if action not in ("contacted", "decline"):
                return HTMLResponse("Bad request", status_code=400)
            try:
                async with session_scope() as session:
                    await broker_lead_service.admin_decide(
                        session,
                        lead_id=lead_id,
                        decision=action,
                        note=str(form.get("note") or ""),
                        actor_id=_actor(request),
                    )
                return RedirectResponse(
                    f"/admin/broker-leads/{lead_id}?done={action}", status_code=303
                )
            except AppError as exc:
                message, error = exc.message, True
        done = request.query_params.get("done")
        if done and not message:
            message = {
                "contacted": "Marked as contacted — the broker was told.",
                "decline": "Declined — the broker was told, with your message.",
                "listed": "Listing created from this lead — the broker was told.",
            }.get(done, "")
        async with session_scope() as session:
            lead = await session.get(BrokerLead, lead_id)
            if lead is None or lead.kind == "client":
                return HTMLResponse("Not found", status_code=404)
            broker = await session.get(User, lead.broker_id)
            label, css = STATUS_LABELS.get(lead.status, (lead.status, ""))
            html = _LEAD_PAGE.render(
                page_title=lead.name,
                l=lead,
                label=label,
                css=css,
                broker=(broker.full_name or broker.email) if broker else "—",
                broker_email=broker.email if broker else "—",
                docs=list(lead.documents or []),
                open=lead.status in ("new", "contacted"),
                message=message,
                error=error,
            )
        return HTMLResponse(html, status_code=400 if error else 200)


class BrokerLeadDocView(BaseView):
    """Session-authed download of a document a broker attached to a lead (never public)."""

    name = "Broker Lead Document"

    def is_visible(self, request: Request) -> bool:
        return False

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    @expose("/broker-lead-doc", methods=["GET"], identity="broker-lead-doc")
    async def broker_lead_doc(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            lead_id = uuid.UUID(request.query_params.get("lead", ""))
            i = int(request.query_params.get("i", "0"))
        except (ValueError, TypeError):
            return HTMLResponse("Bad request", status_code=400)
        async with session_scope() as session:
            lead = await session.get(BrokerLead, lead_id)
            docs = list(lead.documents or []) if lead else []
        if not docs or i < 0 or i >= len(docs):
            return HTMLResponse("Not found", status_code=404)
        doc = docs[i]
        try:
            data = storage.load(doc["key"])
        except Exception:  # noqa: BLE001 — any storage error → not found
            return HTMLResponse("File missing", status_code=404)
        filename = doc.get("filename") or "document"
        return Response(
            content=data,
            media_type=doc.get("content_type") or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


async def lead_prefill(lead_id: str | None) -> dict:
    """Listing Editor "new" form values from a broker's property / project lead."""
    from app.services import listing_service

    try:
        lid = uuid.UUID(lead_id or "")
    except ValueError:
        return {}
    async with session_scope() as session:
        lead = await session.get(BrokerLead, lid)
    if lead is None or lead.kind == "client":
        return {}
    d = lead.details or {}
    values: dict = {"title": lead.name, "location": d.get("location") or ""}
    ptype = str(d.get("property_type") or "").strip().lower()
    if ptype in dict(listing_service.PROPERTY_TYPES):
        values["property_type"] = ptype
    raw_value = "".join(
        ch for ch in str(d.get("estimated_value") or "") if ch.isdigit() or ch == "."
    )
    if raw_value:
        values["total_value"] = raw_value
    if d.get("expected_completion"):
        values["expected_completion"] = str(d["expected_completion"])[:10]
    if d.get("notes"):
        values["description"] = str(d["notes"])
    return values


BROKER_LEAD_VIEWS = (BrokerLeadsView, BrokerLeadDocView)
