"""Property owners in the admin panel — their submissions and their file (client feedback).

What an owner submits is not a listing yet: it waits in **Owner Submissions** (not in
Listings / Properties, which hold what the platform lists) until an admin approves it,
asks for changes (the owner edits and resubmits) or declines it. Every decision carries a
message the owner sees in their dashboard and by email.

**Property Owners** is the owner's file, like the ones brokers and investors have: account
and contact data, identity verification, every listing they submitted with its outcome, the
documents they uploaded, and any role application.

Full admins only. All decisions go through ``property_service.admin_moderate`` — the same
audited path (publish checklist, notifications) as the Listing Editor and the admin API.
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import logging
import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import and_, func, or_, select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.admin_listing import _STYLE, is_full_admin
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.errors import AppError
from app.models import Document, KycVerification, Property, UserRole
from app.models.base import PropertyStatus
from app.models.compliance import AuditLog
from app.models.identity import RoleGrantRequest, User
from app.services import document_service, listing_service, property_service
from app.services.integrations import storage

log = logging.getLogger("capimax.admin.owner")

_env = Environment(autoescape=True)

# Owner submissions = rows an owner created (owner_id set). Until approved they are "under
# listing", not listed: the Listings index and the Properties list leave these out.
WAITING_STATUSES = (PropertyStatus.draft, PropertyStatus.under_review)
LISTED_STATUSES = (PropertyStatus.active, PropertyStatus.funded, PropertyStatus.closed)


def is_owner_submission_pending(prop: Property) -> bool:
    return prop.owner_id is not None and prop.status in WAITING_STATUSES


def platform_listing_filter():
    """SQL condition for the Listings / Properties lists: platform listings in any state,
    owner submissions only once approved (live, funded, or closed after being live). A
    declined submission was never listed: it stays in Owner Submissions only."""
    return or_(
        Property.owner_id.is_(None),
        and_(
            Property.status.in_(LISTED_STATUSES),
            func.coalesce(Property.review_outcome, "") != "declined",
        ),
    )


def submission_state(prop: Property) -> tuple[str, str]:
    """(label, badge css class) of an owner submission, as staff should read it."""
    status = prop.status.value if hasattr(prop.status, "value") else str(prop.status)
    if status == "under_review":
        return "Waiting for review", "draft"
    if status == "draft":
        if prop.review_outcome == "changes_requested":
            return "Changes requested — waiting for the owner", "draft"
        if prop.submitted_at is None:
            return "Draft — not submitted yet", ""
        return "Draft", ""
    if status == "active":
        return "Listed — open for investment", "active"
    if status == "funded":
        return "Listed — fully funded", "active"
    if prop.review_outcome == "declined":
        return "Not approved", "closed"
    return "Closed", "closed"


_SHOW = {
    "review": ("Waiting for review", lambda: Property.status == PropertyStatus.under_review),
    "changes": (
        "Changes requested",
        lambda: (
            (Property.status == PropertyStatus.draft)
            & (Property.review_outcome == "changes_requested")
        ),
    ),
    "drafts": (
        "Not submitted yet",
        lambda: (Property.status == PropertyStatus.draft) & Property.submitted_at.is_(None),
    ),
    "decided": ("Decided", lambda: Property.status.in_(LISTED_STATUSES)),
    "all": ("All", lambda: Property.id.is_not(None)),
}

_ACTION_LABELS = {
    "property.create": "Created as a draft by the owner",
    "property.submit": "Submitted for review by the owner",
    "property.approve": "Approved and published",
    "property.request_changes": "Changes requested",
    "property.reject": "Sent back to the owner",
    "property.decline": "Declined",
    "property.close": "Closed / unpublished",
}

_HEAD = (
    """<!doctype html><html><head><meta charset="utf-8"><title>{{ page_title }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """ .tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px} .tabs a{padding:6px 12px;border:1px solid #d9dcd8;border-radius:999px;font-size:13px;text-decoration:none;color:#23302a;background:#fff}
 .tabs a.on{background:#198653;border-color:#198653;color:#fff;font-weight:600}
 dl.kv{display:grid;grid-template-columns:minmax(140px,220px) 1fr;gap:6px 14px;margin:0;font-size:14px} dl.kv dt{color:#6b726c} dl.kv dd{margin:0}
 .thumbs{display:flex;flex-wrap:wrap;gap:8px} .thumbs img{width:150px;height:100px;object-fit:cover;border-radius:8px;border:1px solid #e8e6e1}
 .scroll{overflow-x:auto}
</style></head><body><div class="wrap">"""
)
_FOOT = "</div></body></html>"

_SUBMISSIONS_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/">&larr; Admin home</a></div><h1>Owner Submissions</h1>
<p class="lead">Properties that owners sent us to list. They are not on the marketplace and not in Listings until you approve them. Open one to see the owner, the documents and to decide.</p></div>
<div class="actions"><a class="btn" href="/admin/property-owners">Property Owners</a><a class="btn" href="/admin/listing/">Listings</a></div></div>
<div class="tabs">{% for key, label, count in tabs %}<a class="{{ 'on' if key == show else '' }}" href="?show={{ key }}">{{ label }} ({{ count }})</a>{% endfor %}</div>
<div class="card scroll">
{% if rows %}<table><tr><th>Property</th><th>Owner</th><th>Status</th><th>Submitted</th><th>Files</th><th></th></tr>
{% for r in rows %}<tr>
 <td><a href="/admin/owner-submissions/{{ r.p.id }}">{{ r.p.title }}</a><div class="muted">{{ r.model }} · {{ r.p.location }}</div></td>
 <td>{{ r.owner_name }}<div class="muted">{{ r.owner_email }}{% if r.owner_phone %} · {{ r.owner_phone }}{% endif %}</div></td>
 <td><span class="badge {{ r.css }}">{{ r.label }}</span>{% if r.p.review_note %}<div class="muted">“{{ r.p.review_note|truncate(80) }}”</div>{% endif %}</td>
 <td class="muted">{{ r.p.submitted_at.strftime('%Y-%m-%d %H:%M') if r.p.submitted_at else '—' }}</td>
 <td class="muted">{{ r.docs }} doc(s) · {{ r.photos }} photo(s)</td>
 <td><a class="btn mini" href="/admin/owner-submissions/{{ r.p.id }}">Review</a></td>
</tr>{% endfor %}</table>
{% else %}<p class="muted">Nothing here.</p>{% endif %}
</div>"""
    + _FOOT
)

_SUBMISSION_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/owner-submissions">&larr; Owner Submissions</a></div>
<h1>{{ p.title }}</h1><p class="lead"><span class="badge {{ css }}">{{ label }}</span> &nbsp;{{ model }} · {{ p.property_type }} · {{ p.location }}</p></div>
<div class="actions"><a class="btn" href="/admin/listing/{{ p.id }}">Open in Listing Editor</a>{% if public_url %}<a class="btn" href="{{ public_url }}" target="_blank">View on marketplace</a>{% endif %}</div></div>
{% if message %}<div class="{{ 'err' if error else 'ok' }}">{{ message }}</div>{% endif %}
{% if blocked %}<div class="note">Complete the missing facts in the <a href="/admin/listing/{{ p.id }}">Listing Editor</a>, then approve again (or ask the owner for them with “Request changes”).</div>{% endif %}

{% if can_decide %}<div class="card"><h2>Decision</h2>
<p class="muted">The owner is told by email and in their dashboard. Your message is shown to them exactly as written.</p>
<form method="post"><label for="note">Message to the owner <span class="muted">(required for “Request changes” and “Decline”)</span></label>
<textarea id="note" name="note" placeholder="e.g. Please upload the title deed and the latest valuation report.">{{ note or '' }}</textarea>
<div class="actions" style="margin-top:10px">
<button class="primary" type="submit" name="action" value="approve" onclick="return confirm('Approve and publish this listing? Investors can see it immediately.')">Approve &amp; publish</button>
<button type="submit" name="action" value="request_changes">Request changes</button>
<button class="danger" type="submit" name="action" value="decline" onclick="return confirm('Decline this listing? The owner cannot resubmit it.')">Decline</button>
</div></form></div>{% endif %}

<div class="card"><h2>Owner</h2>
<dl class="kv"><dt>Name</dt><dd>{{ owner.full_name or '—' }}</dd>
<dt>Email</dt><dd>{{ owner.email }}</dd><dt>Phone</dt><dd>{{ owner.phone or '—' }}</dd>
<dt>Identity check (KYC)</dt><dd>{{ kyc_label }}</dd><dt>Member since</dt><dd>{{ owner.created_at.strftime('%Y-%m-%d') if owner.created_at else '—' }}</dd></dl>
<p style="margin-top:10px"><a class="btn mini" href="/admin/property-owners/{{ owner.id }}">Open the owner's file</a></p></div>

<div class="card"><h2>What the owner submitted</h2>
<dl class="kv">
<dt>Submitted</dt><dd>{{ p.submitted_at.strftime('%Y-%m-%d %H:%M') if p.submitted_at else 'not submitted yet' }}</dd>
<dt>Total value</dt><dd>{{ money(p.total_value) }}</dd><dt>Unit price</dt><dd>{{ money(p.unit_price) }}</dd>
<dt>Units</dt><dd>{{ p.total_units }}</dd><dt>Minimum investment</dt><dd>{{ money(p.minimum_investment) }}</dd>
<dt>Target yield</dt><dd>{{ pct(p.target_yield) }}</dd><dt>Expected completion</dt><dd>{{ p.expected_completion or '—' }}</dd>
<dt>SPV</dt><dd>{{ p.spv_name or '—' }}{% if p.spv_registration %} ({{ p.spv_registration }}){% endif %}</dd>
<dt>Legal structure</dt><dd>{{ p.legal_structure or '—' }}</dd>
<dt>Description</dt><dd style="white-space:pre-line">{{ p.description or '—' }}</dd></dl></div>

<div class="card"><h2>Photos ({{ photos|length }})</h2>{% if photos %}<div class="thumbs">{% for u in photos %}<a href="{{ u }}" target="_blank"><img src="{{ u }}" alt="photo"></a>{% endfor %}</div>{% else %}<p class="muted">No photos uploaded.</p>{% endif %}</div>

<div class="card scroll"><h2>Documents ({{ docs|length }})</h2>{% if docs %}<table><tr><th>Title</th><th>Type</th><th>Uploaded</th><th></th></tr>
{% for d in docs %}<tr><td>{{ d.title }}</td><td class="muted">{{ d.type }}</td><td class="muted">{{ d.created_at.strftime('%Y-%m-%d') if d.created_at else '' }}</td><td><a class="btn mini" href="/admin/owner-document?doc={{ d.id }}">Download</a></td></tr>{% endfor %}</table>
{% else %}<p class="muted">No documents uploaded.</p>{% endif %}</div>

<div class="card scroll"><h2>Review history</h2>{% if history %}<table><tr><th>When</th><th>What</th><th>By</th><th>Message</th></tr>
{% for h in history %}<tr><td class="muted">{{ h.at }}</td><td>{{ h.what }}</td><td class="muted">{{ h.by }}</td><td style="white-space:pre-line">{{ h.note or '' }}</td></tr>{% endfor %}</table>
{% else %}<p class="muted">No history yet.</p>{% endif %}</div>"""
    + _FOOT
)

_OWNERS_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/">&larr; Admin home</a></div><h1>Property Owners</h1>
<p class="lead">Everyone who lists (or can list) property with us, and their file: contact data, identity check, submissions and documents.</p></div>
<div class="actions"><a class="btn" href="/admin/owner-submissions">Owner Submissions</a></div></div>
<div class="card scroll">{% if rows %}<table><tr><th>Owner</th><th>Phone</th><th>Identity check</th><th>Listings</th><th>Joined</th><th></th></tr>
{% for r in rows %}<tr><td><a href="/admin/property-owners/{{ r.u.id }}">{{ r.u.full_name or r.u.email }}</a><div class="muted">{{ r.u.email }}</div></td>
<td class="muted">{{ r.u.phone or '—' }}</td><td>{{ r.kyc }}</td>
<td>{{ r.total }} total{% if r.waiting %} · <b>{{ r.waiting }} waiting</b>{% endif %}{% if r.live %} · {{ r.live }} listed{% endif %}</td>
<td class="muted">{{ r.u.created_at.strftime('%Y-%m-%d') if r.u.created_at else '' }}</td>
<td><a class="btn mini" href="/admin/property-owners/{{ r.u.id }}">Open file</a></td></tr>{% endfor %}</table>
{% else %}<p class="muted">No property owners yet.</p>{% endif %}</div>"""
    + _FOOT
)

_OWNER_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/property-owners">&larr; Property Owners</a></div>
<h1>{{ u.full_name or u.email }}</h1><p class="lead">Property owner file</p></div></div>
<div class="card"><h2>Account</h2><dl class="kv">
<dt>Name</dt><dd>{{ u.full_name or '—' }}</dd><dt>Email</dt><dd>{{ u.email }} {% if u.email_verified %}<span class="badge active">verified</span>{% else %}<span class="badge draft">not verified</span>{% endif %}</dd>
<dt>Phone</dt><dd>{{ u.phone or '—' }}</dd><dt>Roles</dt><dd>{{ roles|join(', ') or '—' }}{% if u.active_role %} (using: {{ u.active_role }}){% endif %}</dd>
<dt>Member since</dt><dd>{{ u.created_at.strftime('%Y-%m-%d') if u.created_at else '—' }}</dd></dl>
<p style="margin-top:10px"><a class="btn mini" href="/admin/user/details/{{ u.id }}">Open the user record</a></p></div>

<div class="card"><h2>Identity check (KYC)</h2><dl class="kv"><dt>Status</dt><dd>{{ kyc_label }}</dd>
{% if kyc and kyc.verified_at %}<dt>Verified</dt><dd>{{ kyc.verified_at.strftime('%Y-%m-%d') }}</dd>{% endif %}
{% if kyc and kyc.rejection_reason %}<dt>Reason</dt><dd>{{ kyc.rejection_reason }}</dd>{% endif %}</dl>
{% if kyc %}<p style="margin-top:10px"><a class="btn mini" href="/admin/kyc-verification/details/{{ kyc.id }}">Open the KYC record</a></p>{% endif %}
<p class="muted">Company verification (KYB) and signed listing agreements are not collected by the platform yet; documents the owner uploads with a listing are below.</p></div>

<div class="card scroll"><h2>Listings ({{ props|length }})</h2>{% if props %}<table><tr><th>Property</th><th>Status</th><th>Submitted</th><th>Last decision</th></tr>
{% for r in props %}<tr><td><a href="/admin/owner-submissions/{{ r.p.id }}">{{ r.p.title }}</a><div class="muted">{{ r.p.location }}</div></td>
<td><span class="badge {{ r.css }}">{{ r.label }}</span></td><td class="muted">{{ r.p.submitted_at.strftime('%Y-%m-%d') if r.p.submitted_at else '—' }}</td>
<td class="muted">{{ r.p.reviewed_at.strftime('%Y-%m-%d') if r.p.reviewed_at else '—' }}{% if r.p.review_note %}<div>“{{ r.p.review_note|truncate(100) }}”</div>{% endif %}</td></tr>{% endfor %}</table>
{% else %}<p class="muted">No listings submitted.</p>{% endif %}</div>

<div class="card scroll"><h2>Documents ({{ docs|length }})</h2>{% if docs %}<table><tr><th>Title</th><th>Type</th><th>Listing</th><th>Uploaded</th><th></th></tr>
{% for d in docs %}<tr><td>{{ d.doc.title }}</td><td class="muted">{{ d.doc.type }}</td><td class="muted">{{ d.property or '—' }}</td><td class="muted">{{ d.doc.created_at.strftime('%Y-%m-%d') if d.doc.created_at else '' }}</td><td><a class="btn mini" href="/admin/owner-document?doc={{ d.doc.id }}">Download</a></td></tr>{% endfor %}</table>
{% else %}<p class="muted">No documents uploaded.</p>{% endif %}</div>

{% if applications %}<div class="card scroll"><h2>Role applications</h2><table><tr><th>Role</th><th>Status</th><th>Submitted</th><th>Documents</th></tr>
{% for a in applications %}<tr><td>{{ a.role }}</td><td>{{ a.status }}</td><td class="muted">{{ a.created }}</td><td>{% for d in a.docs %}<a href="{{ d.href }}" target="_blank">{{ d.label }}</a>{% if not loop.last %}, {% endif %}{% endfor %}</td></tr>{% endfor %}</table></div>{% endif %}"""
    + _FOOT
)


def _money(value) -> str:
    return "—" if value is None else f"${float(value):,.2f}"


def _pct(value) -> str:
    return "—" if value is None else f"{float(value):g}%"


_KYC_LABELS = {
    "verified": "Verified",
    "submitted": "Submitted — being checked",
    "pending": "Not completed",
    "rejected": "Rejected",
}


def _kyc_label(kyc: KycVerification | None) -> str:
    if kyc is None:
        return "Not started"
    status = kyc.status.value if hasattr(kyc.status, "value") else str(kyc.status)
    return _KYC_LABELS.get(status, status)


def _actor(request: Request) -> uuid.UUID | None:
    actor = request.session.get("admin_id")
    return uuid.UUID(actor) if actor else None


def _gate(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse("/admin/login", status_code=302)
    if not is_full_admin(request):
        return HTMLResponse("Forbidden", status_code=403)
    return None


async def _history(session, prop: Property) -> list[dict]:
    rows = (
        (
            await session.execute(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == "property",
                    AuditLog.entity_id == str(prop.id),
                    AuditLog.action.in_(list(_ACTION_LABELS)),
                )
                .order_by(AuditLog.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    actor_ids = {r.actor_id for r in rows if r.actor_id}
    emails = {}
    if actor_ids:
        emails = dict(
            (await session.execute(select(User.id, User.email).where(User.id.in_(actor_ids)))).all()
        )
    out = []
    for r in rows:
        after = r.after if isinstance(r.after, dict) else {}
        what = _ACTION_LABELS.get(r.action, r.action)
        if r.action == "property.submit" and after.get("resubmission"):
            what = "Resubmitted by the owner"
        out.append(
            {
                "at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
                "what": what,
                "by": emails.get(r.actor_id, "system") if r.actor_id else "system",
                "note": after.get("reason"),
            }
        )
    return out


class OwnerSubmissionsView(BaseView):
    """The queue of owner submissions and the review page of each one."""

    name = "Owner Submissions"
    icon = "fa-solid fa-inbox"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    # The first exposed page is the sidebar link (SQLAdmin registers them bottom-up).
    @expose("/owner-submissions", methods=["GET"], identity="owner-submissions")
    async def submissions_index(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        show = request.query_params.get("show", "review")
        if show not in _SHOW:
            show = "review"
        async with session_scope() as session:
            tabs = []
            for key, (label, cond) in _SHOW.items():
                count = await session.scalar(
                    select(func.count(Property.id)).where(Property.owner_id.is_not(None), cond())
                )
                tabs.append((key, label, count or 0))
            props = (
                (
                    await session.execute(
                        select(Property)
                        .where(Property.owner_id.is_not(None), _SHOW[show][1]())
                        .order_by(func.coalesce(Property.submitted_at, Property.created_at).desc())
                        .limit(300)
                    )
                )
                .scalars()
                .all()
            )
            owners = await _users(session, {p.owner_id for p in props})
            docs = await _doc_counts(session, [p.id for p in props])
            rows = []
            for p in props:
                label, css = submission_state(p)
                owner = owners.get(p.owner_id)
                rows.append(
                    {
                        "p": p,
                        "label": label,
                        "css": css,
                        "model": listing_service.MODEL_LABELS.get(p.model, p.model),
                        "owner_name": (owner.full_name or owner.email) if owner else "—",
                        "owner_email": owner.email if owner else "",
                        "owner_phone": owner.phone if owner else "",
                        "docs": docs.get(p.id, 0),
                        "photos": len(p.images or []),
                    }
                )
        return HTMLResponse(
            _SUBMISSIONS_PAGE.render(
                page_title="Owner Submissions", rows=rows, tabs=tabs, show=show
            )
        )

    @expose("/owner-submissions/{prop_id}", methods=["GET", "POST"], identity="owner-submission")
    async def submission_detail(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            prop_id = uuid.UUID(request.path_params["prop_id"])
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        message, error, blocked, note = "", False, False, ""
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            note = str(form.get("note") or "")
            if action not in ("approve", "request_changes", "decline"):
                return HTMLResponse("Bad request", status_code=400)
            try:
                async with session_scope() as session:
                    prop = await session.get(Property, prop_id)
                    if prop is None or prop.owner_id is None:
                        return HTMLResponse("Not found", status_code=404)
                    if prop.status not in WAITING_STATUSES:
                        raise AppError(
                            "ALREADY_DECIDED",
                            "This submission was already decided.",
                            status_code=409,
                        )
                    await property_service.admin_moderate(
                        session,
                        actor_id=_actor(request),
                        prop_id=prop_id,
                        action=action,
                        reason=note,
                    )
                return RedirectResponse(
                    f"/admin/owner-submissions/{prop_id}?done={action}", status_code=303
                )
            except AppError as exc:
                message, error = exc.message, True
                blocked = exc.code == "PUBLISH_BLOCKED"
        done = request.query_params.get("done")
        if done and not message:
            message = {
                "approve": "Approved — the listing is live and the owner was told.",
                "request_changes": "Sent back to the owner with your message.",
                "decline": "Declined — the owner was told, with your message.",
            }.get(done, "")
        async with session_scope() as session:
            prop = await session.get(Property, prop_id)
            if prop is None or prop.owner_id is None:
                return HTMLResponse("Not found", status_code=404)
            owner = await session.get(User, prop.owner_id)
            if owner is None:  # the account was deleted; keep the submission readable
                owner = User(id=prop.owner_id, email="(deleted account)")
            kyc = await session.scalar(
                select(KycVerification).where(KycVerification.user_id == prop.owner_id)
            )
            docs = (
                (
                    await session.execute(
                        select(Document)
                        .where(Document.property_id == prop.id)
                        .order_by(Document.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            history = await _history(session, prop)
            label, css = submission_state(prop)
            public = prop.status in property_service.PUBLIC_STATUSES
            html = _SUBMISSION_PAGE.render(
                page_title=prop.title,
                p=prop,
                owner=owner,
                kyc_label=_kyc_label(kyc),
                label=label,
                css=css,
                model=listing_service.MODEL_LABELS.get(prop.model, prop.model),
                # only files we store or http(s) links (the schema refuses anything else;
                # older rows are filtered here too)
                photos=[
                    u
                    for u in (prop.images or [])
                    if isinstance(u, str)
                    and u.startswith(("/api/v1/files/", "https://", "http://"))
                ],
                docs=docs,
                history=history,
                can_decide=prop.status in WAITING_STATUSES,
                public_url=(
                    f"{get_settings().app_base_url.rstrip('/')}/property/{prop.slug or prop.id}"
                    if public
                    else ""
                ),
                message=message,
                error=error,
                blocked=blocked,
                note=note,
                money=_money,
                pct=_pct,
            )
        return HTMLResponse(html, status_code=400 if error else 200)


class PropertyOwnersView(BaseView):
    """The owner's file: account, identity check, listings, documents, applications."""

    name = "Property Owners"
    icon = "fa-solid fa-user-tie"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    @expose("/property-owners", methods=["GET"], identity="property-owners")
    async def owners_index(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        async with session_scope() as session:
            role_holders = select(UserRole.user_id).where(UserRole.role == "owner")
            submitters = select(Property.owner_id).where(Property.owner_id.is_not(None))
            users = (
                (
                    await session.execute(
                        select(User)
                        .where(or_(User.id.in_(role_holders), User.id.in_(submitters)))
                        .order_by(User.created_at.desc())
                        .limit(500)
                    )
                )
                .scalars()
                .all()
            )
            ids = [u.id for u in users]
            kycs = await _kycs(session, ids)
            counts: dict[uuid.UUID, dict[str, int]] = {}
            if ids:
                for owner_id, status, n in (
                    await session.execute(
                        select(Property.owner_id, Property.status, func.count(Property.id))
                        .where(Property.owner_id.in_(ids))
                        .group_by(Property.owner_id, Property.status)
                    )
                ).all():
                    c = counts.setdefault(owner_id, {"total": 0, "waiting": 0, "live": 0})
                    c["total"] += n
                    if status == PropertyStatus.under_review:
                        c["waiting"] += n
                    if status in property_service.PUBLIC_STATUSES:
                        c["live"] += n
            rows = [
                {
                    "u": u,
                    "kyc": _kyc_label(kycs.get(u.id)),
                    **counts.get(u.id, {"total": 0, "waiting": 0, "live": 0}),
                }
                for u in users
            ]
        return HTMLResponse(_OWNERS_PAGE.render(page_title="Property Owners", rows=rows))

    @expose("/property-owners/{user_id}", methods=["GET"], identity="property-owner")
    async def owner_file(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            user_id = uuid.UUID(request.path_params["user_id"])
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        async with session_scope() as session:
            user = await session.get(User, user_id)
            if user is None:
                return HTMLResponse("Not found", status_code=404)
            roles = [
                r.value if hasattr(r, "value") else str(r)
                for r in (
                    await session.execute(select(UserRole.role).where(UserRole.user_id == user_id))
                ).scalars()
            ]
            kyc = await session.scalar(
                select(KycVerification).where(KycVerification.user_id == user_id)
            )
            props = (
                (
                    await session.execute(
                        select(Property)
                        .where(Property.owner_id == user_id)
                        .order_by(Property.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            titles = {p.id: p.title for p in props}
            doc_rows = (
                (
                    await session.execute(
                        select(Document)
                        .where(
                            or_(
                                Document.user_id == user_id,
                                Document.property_id.in_(list(titles) or [uuid.uuid4()]),
                            )
                        )
                        .order_by(Document.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            applications = []
            for req in (
                (
                    await session.execute(
                        select(RoleGrantRequest)
                        .where(RoleGrantRequest.user_id == user_id)
                        .order_by(RoleGrantRequest.created_at.desc())
                    )
                )
                .scalars()
                .all()
            ):
                app_docs = (req.application or {}).get("documents", []) or []
                applications.append(
                    {
                        "role": req.role.value if hasattr(req.role, "value") else str(req.role),
                        "status": req.status,
                        "created": req.created_at.strftime("%Y-%m-%d") if req.created_at else "",
                        "docs": [
                            {
                                "label": str(
                                    d.get("label") or d.get("filename") or f"Document {i + 1}"
                                ),
                                "href": f"/admin/role-application-doc?req={req.id}&i={i}",
                            }
                            for i, d in enumerate(app_docs)
                        ],
                    }
                )
            html = _OWNER_PAGE.render(
                page_title=user.full_name or user.email,
                u=user,
                roles=roles,
                kyc=kyc,
                kyc_label=_kyc_label(kyc),
                props=[
                    {"p": p, "label": submission_state(p)[0], "css": submission_state(p)[1]}
                    for p in props
                ],
                docs=[{"doc": d, "property": titles.get(d.property_id)} for d in doc_rows],
                applications=applications,
            )
        return HTMLResponse(html)


class OwnerDocumentView(BaseView):
    """Session-authed download of a document an owner uploaded (a listing under review is not
    public, so the public download route refuses it). A link target, not a menu item."""

    name = "Owner Document"

    def is_visible(self, request: Request) -> bool:
        return False

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    @expose("/owner-document", methods=["GET"], identity="owner-document")
    async def owner_document(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            doc_id = uuid.UUID(request.query_params.get("doc", ""))
        except ValueError:
            return HTMLResponse("Bad request", status_code=400)
        async with session_scope() as session:
            doc = await session.get(Document, doc_id)
        if doc is None:
            return HTMLResponse("Not found", status_code=404)
        try:
            data = storage.load(doc.file_url)
        except Exception:  # noqa: BLE001 — any storage error → not found
            return HTMLResponse("File missing", status_code=404)
        filename = doc.file_url.rsplit("/", 1)[-1] or "document"
        return Response(
            content=data,
            media_type=document_service.content_type_for(doc.file_url),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


async def _users(session, ids: set) -> dict[uuid.UUID, User]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {u.id: u for u in rows}


async def _kycs(session, ids: list) -> dict[uuid.UUID, KycVerification]:
    if not ids:
        return {}
    rows = (
        (await session.execute(select(KycVerification).where(KycVerification.user_id.in_(ids))))
        .scalars()
        .all()
    )
    return {k.user_id: k for k in rows}


async def _doc_counts(session, prop_ids: list) -> dict[uuid.UUID, int]:
    if not prop_ids:
        return {}
    return dict(
        (
            await session.execute(
                select(Document.property_id, func.count(Document.id))
                .where(Document.property_id.in_(prop_ids))
                .group_by(Document.property_id)
            )
        ).all()
    )


OWNER_VIEWS = (OwnerSubmissionsView, PropertyOwnersView, OwnerDocumentView)
