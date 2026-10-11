"""Estate claims in the admin panel (client, 2026-10-07).

A person the holder designated reports the holder's death on the public page and sends the
beneficiary certificate with their own identity document. Staff review it here: what the
claimant sent beside what the holder's register holds (the same person, the same document
number, the copy of the identity document the holder kept), the checks that follow from
comparing them, and the claimant's own account. They ask for more, reject with a message, or
approve: the claimant's share then moves to the claimant's OWN verified account. Nobody is
given the holder's account.

Full admins only. All writes go through ``estate_service`` (audited; the claimant is told).
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import func, select
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.admin_listing import _STYLE, is_full_admin
from app.core.db import session_scope
from app.core.errors import AppError
from app.models import EstateBeneficiary, EstateClaim
from app.services import estate_service
from app.services.integrations import storage

_env = Environment(autoescape=True)

_TABS = {
    "new": ("New", ("submitted",)),
    "review": ("In review", ("in_review",)),
    "waiting": ("Waiting for the claimant", ("needs_info",)),
    "approved": ("Approved", ("approved",)),
    "rejected": ("Rejected", ("rejected",)),
}
_BADGE = {
    "submitted": "draft",
    "in_review": "draft",
    "needs_info": "draft",
    "approved": "active",
    "rejected": "closed",
}

_HEAD = (
    """<!doctype html><html><head><meta charset="utf-8"><title>{{ page_title }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """ .tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px} .tabs a{padding:6px 12px;border:1px solid #d9dcd8;border-radius:999px;font-size:13px;text-decoration:none;color:#23302a;background:#fff}
 .tabs a.on{background:#198653;border-color:#198653;color:#fff;font-weight:600}
 dl.kv{display:grid;grid-template-columns:minmax(140px,220px) 1fr;gap:6px 14px;margin:0;font-size:14px} dl.kv dt{color:#6b726c} dl.kv dd{margin:0}
 .scroll{overflow-x:auto} .two{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}
 ul.checks{list-style:none;margin:0;padding:0} ul.checks li{padding:7px 10px 7px 34px;border-radius:8px;margin-bottom:6px;font-size:14px;position:relative}
 ul.checks li:before{position:absolute;left:11px;font-weight:700}
 ul.checks li.ok{background:#e7f5ec;border:1px solid #b7e0c6;color:#0f5b39} ul.checks li.ok:before{content:"\\2713"}
 ul.checks li.bad{background:#fdeaea;border:1px solid #f2c2c2;color:#b00} ul.checks li.bad:before{content:"\\2717"}
 ul.checks li.warn{background:#fff7e6;border:1px solid #f1d49a;color:#7a5200} ul.checks li.warn:before{content:"!"}
 button:disabled{opacity:.45;cursor:not-allowed}
 .docs{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
 .doc{border:1px solid #e8e6e1;border-radius:10px;background:#fafaf8;padding:8px;font-size:12px}
 .doc img{width:100%;height:130px;object-fit:contain;background:#fff;border-radius:6px;display:block;margin-bottom:6px}
 .doc .pdf{height:130px;display:flex;align-items:center;justify-content:center;background:#fff;border-radius:6px;margin-bottom:6px;color:#6b726c;font-weight:600}
 .doc b{display:block;margin-bottom:2px}
</style></head><body><div class="wrap">"""
)

_LIST_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/">&larr; Admin home</a></div><h1>Estate Claims</h1>
<p class="lead">Claims sent from the public page by a person an account holder designated. Review each one against the holder's beneficiary register; an approved claim moves the claimant's share to the claimant's own verified account.</p></div></div>
<div class="tabs">{% for key, label, count in tabs %}<a class="{{ 'on' if key == show else '' }}" href="?show={{ key }}">{{ label }} ({{ count }})</a>{% endfor %}</div>
<div class="card scroll">{% if rows %}<table><tr><th>Reference</th><th>Claimant</th><th>Account holder</th><th>Reason</th><th>Certificate</th><th>Received</th><th></th></tr>
{% for r in rows %}<tr>
<td><a href="/admin/estate-claims/{{ r.c.id }}">{{ r.c.reference }}</a></td>
<td>{{ r.c.claimant_name }}<div class="muted">{{ r.c.claimant_email }} · {{ r.c.claimant_country }}</div></td>
<td>{{ r.c.holder_name }}</td>
<td>{{ r.reason }}</td>
<td>{{ r.c.certificate_no or '—' }}<div class="muted">{{ 'matches a record' if r.c.beneficiary_id else 'no matching record' }}</div></td>
<td class="muted">{{ r.c.created_at.strftime('%Y-%m-%d') if r.c.created_at else '' }}</td>
<td><a class="btn mini" href="/admin/estate-claims/{{ r.c.id }}">Open</a></td></tr>{% endfor %}</table>
{% else %}<p class="muted">Nothing here.</p>{% endif %}</div>
</div></body></html>"""
)

_DOC = """{% macro doc_tile(d, href) -%}
<div class="doc">{% if d.content_type.startswith('image/') %}<a href="{{ href }}&amp;inline=1" target="_blank" rel="noopener"><img src="{{ href }}&amp;inline=1" alt="{{ d.filename }}"></a>{% else %}<div class="pdf">PDF</div>{% endif %}
<b>{{ d.label }}</b><span class="muted">{{ d.filename }}{% if d.by == 'staff' %} · added by staff{% endif %}</span>
<div class="actions" style="margin-top:6px"><a class="btn mini" href="{{ href }}&amp;inline=1" target="_blank" rel="noopener">View</a><a class="btn mini" href="{{ href }}">Download</a></div></div>
{%- endmacro %}"""

_CLAIM_PAGE = _env.from_string(
    _HEAD
    + _DOC
    + """
<div class="top"><div><div class="muted"><a href="/admin/estate-claims">&larr; Estate Claims</a></div>
<h1>Claim {{ c.reference }}</h1><p class="lead"><span class="badge {{ badge }}">{{ status_label }}</span> &nbsp;{{ reason }}{% if c.date_of_death %} on {{ c.date_of_death.strftime('%Y-%m-%d') }}{% endif %} &nbsp;·&nbsp; received {{ c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else '' }} UTC</p></div></div>
{% if message %}<div class="{{ 'err' if error else 'ok' }}">{{ message }}</div>{% endif %}

<div class="card"><h2>Checks</h2><p class="muted">What comparing the claim with the register shows. They inform your decision; the list under "Decision" is what actually stands in the way of an approval.</p>
<ul class="checks">{% for k in checks %}<li class="{{ k.level }}">{{ k.text }}</li>{% endfor %}</ul></div>

<div class="two">
<div class="card"><h2>What the claimant sent</h2><dl class="kv">
<dt>Name</dt><dd>{{ c.claimant_name }}</dd><dt>Email</dt><dd>{{ c.claimant_email }}</dd><dt>Phone</dt><dd>{{ c.claimant_phone or '—' }}</dd>
<dt>Country</dt><dd>{{ c.claimant_country }}</dd><dt>Relationship</dt><dd>{{ c.relationship or '—' }}</dd>
<dt>Identity document</dt><dd>{{ c.claimant_id_type or '—' }}</dd><dt>Document number</dt><dd>{{ c.claimant_id_number or '—' }}</dd>
<dt>Account holder</dt><dd>{{ c.holder_name }}</dd><dt>Holder's email</dt><dd>{{ c.holder_email or '—' }}</dd>
<dt>Certificate number</dt><dd>{{ c.certificate_no or '—' }}</dd>
<dt>Details</dt><dd style="white-space:pre-line">{{ c.details or '—' }}</dd></dl></div>

<div class="card"><h2>The beneficiary record</h2>{% if b %}<dl class="kv">
<dt>Name</dt><dd>{{ b.full_name }}</dd><dt>Email</dt><dd>{{ b.email or '—' }}</dd><dt>Phone</dt><dd>{{ b.phone or '—' }}</dd>
<dt>Designated as</dt><dd>{{ role }}</dd><dt>Relationship</dt><dd>{{ b.relationship or '—' }}</dd>
<dt>Identity document</dt><dd>{{ meta.idType or '—' }}</dd><dt>Document number</dt><dd>{{ meta.idNumber or '—' }}</dd>
<dt>Account holder</dt><dd>{{ holder.full_name or '—' }} <span class="muted">{{ holder.email }}</span></dd>
<dt>Allocation</dt><dd>{{ b.allocation_pct }}%</dd>
<dt>Certificate number</dt><dd>{{ b.certificate_no }} <span class="muted">Version {{ b.version }}</span></dd>
<dt>Recorded / last changed</dt><dd>{{ b.created_at.strftime('%Y-%m-%d') if b.created_at else '—' }} / {{ b.updated_at.strftime('%Y-%m-%d') if b.updated_at else '—' }}</dd>
<dt>Holder's note</dt><dd style="white-space:pre-line">{{ b.notes or '—' }}</dd></dl>
{% else %}<p class="muted">No record of the register is matched to this claim.</p>{% endif %}
{% if open %}<form method="post" style="margin-top:12px"><label for="certificate_no">Match to another certificate number</label><input type="text" id="certificate_no" name="certificate_no" placeholder="CPB-XXXX-XXXX">
<div class="help">Only when the claimant mistyped it: the number is printed on the certificate they attached.</div>
<div class="actions" style="margin-top:8px"><button type="submit" name="action" value="match">Match</button></div></form>{% endif %}</div>
</div>

<div class="card"><h2>Documents sent with the claim ({{ claim_docs|length }})</h2>
<div class="docs">{% for d in claim_docs %}{{ doc_tile(d, '/admin/estate-claim-doc?claim=' ~ c.id ~ '&doc=' ~ d.id) }}{% endfor %}</div>
{% if open %}<form method="post" enctype="multipart/form-data" style="margin-top:14px"><div class="cols"><div><label for="kind">Attach a document you received another way</label><select id="kind" name="kind">{% for value, label in doc_kinds %}<option value="{{ value }}" {{ 'selected' if value == 'evidence' }}>{{ label }}</option>{% endfor %}</select></div>
<div><label for="file">File (photo or PDF, up to 10 MB)</label><input type="file" id="file" name="file" accept=".pdf,.jpg,.jpeg,.png,.webp" required></div></div>
<div class="actions" style="margin-top:8px"><button type="submit" name="action" value="attach">Attach</button></div></form>{% endif %}</div>

<div class="card"><h2>The identity document the holder kept for this person ({{ record_docs|length }})</h2>
{% if record_docs %}<div class="docs">{% for d in record_docs %}{{ doc_tile(d, '/admin/estate-beneficiary-doc?b=' ~ b.id ~ '&doc=' ~ d.id) }}{% endfor %}</div>
{% else %}<p class="muted">The holder uploaded no copy. Compare the claimant's document with the name and the document number on the record.</p>{% endif %}</div>

<div class="two">
<div class="card"><h2>The claimant's own account</h2>{% if account %}<dl class="kv">
<dt>Name</dt><dd>{{ account.full_name or '—' }}</dd><dt>Email</dt><dd>{{ account.email }}</dd>
<dt>Identity (KYC)</dt><dd><span class="badge {{ 'active' if kyc == 'verified' else 'draft' }}">{{ kyc }}</span></dd>
<dt>Registered</dt><dd>{{ account.created_at.strftime('%Y-%m-%d') if account.created_at else '—' }}</dd></dl>
{% elif unconfirmed %}<p class="muted">An account is registered with {{ c.claimant_email }} (in the name {{ unconfirmed.full_name or '—' }}, opened {{ unconfirmed.created_at.strftime('%Y-%m-%d') if unconfirmed.created_at else '—' }}), but the address was never confirmed in it: anyone who knew the address could have opened it, so it is not taken as the claimant's. Once the claimant confirms the address (Account Settings, or this claim page while signed in), it is matched by itself.</p>
{% else %}<p class="muted">No account is registered with {{ c.claimant_email }} yet. The claimant was told to create one and verify their identity: the transfer goes to that account only.</p>{% endif %}
{% if open %}<form method="post" style="margin-top:12px"><label for="account_email">The claimant's account is under this address</label><input type="text" id="account_email" name="account_email" placeholder="name@example.com">
<div class="help">When they registered with another address, or when you know an account whose address is not confirmed is theirs.</div>
<div class="actions" style="margin-top:8px"><button type="submit" name="action" value="match">Link this account</button></div></form>{% endif %}</div>

<div class="card"><h2>The holder's account</h2>{% if b %}
<table><tr><th>Property</th><th>Held</th><th>Held back</th><th>Free</th></tr>{% for h in holdings %}<tr><td>{{ h.title }}</td><td>{{ h.net }}</td><td>{{ h.reserved }}</td><td>{{ h.available }}</td></tr>{% else %}<tr><td colspan="4" class="muted">The holder holds no units.</td></tr>{% endfor %}</table>
<p class="help">Held back: units in an open listing, an exit request, a scheduled gift or a pending family allocation. They are not part of the split.</p>
<dl class="kv" style="margin-top:8px"><dt>Wallet balance</dt><dd>{{ '${:,.2f}'.format(wallet.balance) }}{% if wallet.owed %} <span class="muted">less {{ '${:,.2f}'.format(wallet.owed) }} allocated to relatives who could not be paid yet: {{ '${:,.2f}'.format(wallet.base) }} is shared out</span>{% endif %}
<div class="help">{% if covers_wallet %}This record covers the wallet: {{ b.allocation_pct }}% of what is shared out goes to the claimant with the units.{% else %}This record does not cover the wallet (the holder ticked neither Wallet Balance nor Full Portfolio): no money moves with this claim.{% endif %}</div></dd>
<dt>The holder's account</dt><dd>{% if holder.closed_at %}<span class="badge draft">closed</span> {{ holder.closed_at.strftime('%Y-%m-%d') }} <span class="muted">{{ holder.closed_reason or '' }}</span>{% else %}<span class="badge active">open</span> <span class="muted">approving a claim for a death, or for a holder who can no longer manage the account, closes it</span>{% endif %}</dd>
<dt>Other beneficiaries</dt><dd>{% for o in others %}{{ o.full_name }} ({{ o.allocation_pct }}%){{ ', ' if not loop.last }}{% else %}none{% endfor %}</dd>
<dt>Transfer event</dt><dd>{% if event %}recorded {{ event.executed_at.strftime('%Y-%m-%d') if event.executed_at else '' }}: the register is closed{% else %}none yet: this approval records it and closes the register{% endif %}</dd></dl>
{% else %}<p class="muted">Unknown until the claim is matched to a record.</p>{% endif %}</div>
</div>

<div class="card"><h2>Decision</h2>
{% if done %}<h3>Already transferred to this beneficiary</h3><table>{% for m in done %}<tr><td>{{ m.property }}</td><td>{{ amount(m) }}</td><td>{{ m.status }}</td></tr>{% endfor %}</table>{% endif %}
{% if open %}
{% if to_move %}<h3>An approval transfers to the claimant's account</h3><table>{% for m in to_move %}<tr><td>{{ m.property }}</td><td>{{ amount(m) }}</td></tr>{% endfor %}</table>{% endif %}
{% if blockers %}<div class="warn" style="margin-top:10px"><b>Not ready to approve:</b>
{% for x in blockers %}• {{ x }}
{% endfor %}</div>{% endif %}
<form method="post"><label for="note">Message to the claimant <span class="muted">(required to ask for information or to reject)</span></label><textarea id="note" name="note"></textarea>
<div class="actions" style="margin-top:10px">
{% if c.status == 'submitted' %}<button type="submit" name="action" value="review">Start the review</button>{% endif %}
<button type="submit" name="action" value="ask">Ask the claimant for information</button>
<button class="primary" type="submit" name="action" value="approve" {{ 'disabled' if blockers }} onclick="return confirm('Approve this claim and transfer what is listed above to the claimant\\'s account? This cannot be undone.')">Approve and transfer</button>
<button class="danger" type="submit" name="action" value="reject" onclick="return confirm('Reject this claim?')">Reject</button></div></form>
{% else %}<p class="muted">{{ 'Approved' if c.status == 'approved' else 'Rejected' }}{% if c.decided_at %} on {{ c.decided_at.strftime('%Y-%m-%d %H:%M') }} UTC{% endif %}.</p>{% endif %}
{% if c.admin_note %}<dl class="kv" style="margin-top:10px"><dt>Last message to the claimant</dt><dd style="white-space:pre-line">{{ c.admin_note }}</dd></dl>{% endif %}</div>
</div></body></html>"""
)

def _amount(line: dict) -> str:
    """A share as the page prints it: money for the wallet, units for a property."""
    if line.get("amount") is not None:
        return f"${line['amount']:,.2f}"
    return f"{line['units']} unit(s)"


_DONE = {
    "review": "The review has started.",
    "ask": "The claimant was asked, with your message. The claim waits for them.",
    "reject": "Rejected. The claimant was told, with your message.",
    "attach": "The document was attached.",
    "match": "The claim was matched.",
    "approve": "Approved. The share is in the claimant's account, and the claimant was told.",
}


def _gate(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse("/admin/login", status_code=302)
    if not is_full_admin(request):
        return HTMLResponse("Forbidden", status_code=403)
    return None


def _actor(request: Request) -> uuid.UUID | None:
    actor = request.session.get("admin_id")
    return uuid.UUID(actor) if actor else None


def _tiles(docs: list, labels: dict[str, str] | None = None) -> list[dict]:
    """Stored documents as the page shows them (never their storage key)."""
    return [
        {
            "id": d.get("id"),
            "filename": d.get("filename") or "document",
            "content_type": d.get("content_type") or "application/octet-stream",
            "by": d.get("by"),
            "label": (labels or {}).get(d.get("kind") or "", "Identity document"),
        }
        for d in (docs or [])
    ]


class EstateClaimsView(BaseView):
    name = "Estate Claims"
    icon = "fa-solid fa-scale-balanced"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    # The first exposed page is the sidebar link (SQLAdmin registers them bottom-up).
    @expose("/estate-claims", methods=["GET"], identity="estate-claims")
    async def claims_index(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        show = request.query_params.get("show", "new")
        if show not in _TABS:
            show = "new"
        async with session_scope() as session:
            tabs = []
            for key, (label, statuses) in _TABS.items():
                count = await session.scalar(
                    select(func.count(EstateClaim.id)).where(EstateClaim.status.in_(statuses))
                )
                tabs.append((key, label, count or 0))
            claims = (
                (
                    await session.execute(
                        select(EstateClaim)
                        .where(EstateClaim.status.in_(_TABS[show][1]))
                        .order_by(EstateClaim.created_at.desc())
                        .limit(300)
                    )
                )
                .scalars()
                .all()
            )
            rows = [
                {"c": c, "reason": estate_service.CLAIM_REASONS.get(c.reason, c.reason)}
                for c in claims
            ]
            html = _LIST_PAGE.render(page_title="Estate Claims", rows=rows, tabs=tabs, show=show)
        return HTMLResponse(html)

    @expose("/estate-claims/{claim_id}", methods=["GET", "POST"], identity="estate-claim")
    async def claim_detail(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            claim_id = uuid.UUID(request.path_params["claim_id"])
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        message, error = "", False
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            if action not in _DONE:
                return HTMLResponse("Bad request", status_code=400)
            note = str(form.get("note") or "")
            try:
                async with session_scope() as session:
                    if action == "review":
                        await estate_service.claim_start_review(
                            session, claim_id=claim_id, actor_id=_actor(request)
                        )
                    elif action == "ask":
                        await estate_service.claim_request_info(
                            session, claim_id=claim_id, note=note, actor_id=_actor(request)
                        )
                    elif action == "reject":
                        await estate_service.claim_reject(
                            session, claim_id=claim_id, note=note, actor_id=_actor(request)
                        )
                    elif action == "match":
                        await estate_service.claim_set_match(
                            session,
                            claim_id=claim_id,
                            certificate_no=str(form.get("certificate_no") or ""),
                            account_email=str(form.get("account_email") or ""),
                            actor_id=_actor(request),
                        )
                    elif action == "attach":
                        upload = form.get("file")
                        sent = upload if isinstance(upload, UploadFile) else None
                        await estate_service.claim_attach_document(
                            session,
                            claim_id=claim_id,
                            kind=str(form.get("kind") or "evidence"),
                            filename=sent.filename if sent is not None else None,
                            data=await sent.read() if sent is not None else b"",
                            actor_id=_actor(request),
                        )
                    else:
                        await estate_service.claim_approve(
                            session, claim_id=claim_id, actor_id=_actor(request)
                        )
                return RedirectResponse(
                    f"/admin/estate-claims/{claim_id}?done={action}", status_code=303
                )
            except AppError as exc:
                message, error = exc.message, True
        done = request.query_params.get("done")
        if done and not message:
            message = _DONE.get(done, "")
        async with session_scope() as session:
            try:
                review = await estate_service.claim_review(session, claim_id)
            except AppError:
                return HTMLResponse("Not found", status_code=404)
            claim: EstateClaim = review["claim"]
            ben: EstateBeneficiary | None = review["beneficiary"]
            html = _CLAIM_PAGE.render(
                page_title=f"Claim {claim.reference}",
                c=claim,
                b=ben,
                meta=review["meta"],
                role=estate_service.ROLES.get(review["meta"].get("role", ""), "—"),
                holder=review["holder"],
                account=review["account"],
                unconfirmed=review["unconfirmed"],
                kyc=review["kyc"],
                event=review["event"],
                checks=review["checks"],
                blockers=review["blockers"],
                to_move=review["to_move"],
                done=review["done"],
                holdings=review["holdings"],
                wallet=review["wallet"],
                covers_wallet=review["covers_wallet"],
                amount=_amount,
                others=review["others"],
                claim_docs=_tiles(claim.documents, estate_service.CLAIM_DOC_KINDS),
                record_docs=_tiles(ben.id_documents if ben else []),
                doc_kinds=list(estate_service.CLAIM_DOC_KINDS.items()),
                reason=estate_service.CLAIM_REASONS.get(claim.reason, claim.reason),
                status_label=estate_service.CLAIM_STATUSES.get(claim.status, claim.status),
                badge=_BADGE.get(claim.status, ""),
                open=claim.status in estate_service.OPEN_CLAIM_STATUSES,
                message=message,
                error=error,
            )
        return HTMLResponse(html, status_code=400 if error else 200)


def _serve(doc: dict, *, inline: bool) -> Response:
    try:
        data = storage.load(doc["key"])
    except Exception:  # noqa: BLE001 — any storage error → not found
        return HTMLResponse("File missing", status_code=404)
    filename = doc.get("filename") or "document"
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=doc.get("content_type") or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, no-store",
            # stored files are photos and PDFs only (checked at upload): shown as what they
            # are, never guessed to be anything else
            "X-Content-Type-Options": "nosniff",
        },
    )


class EstateDocView(BaseView):
    """Session-authed view / download of a document sent with a claim, or of the identity
    document a holder kept for a beneficiary (never public)."""

    name = "Estate Document"

    def is_visible(self, request: Request) -> bool:
        return False

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    @expose("/estate-claim-doc", methods=["GET"], identity="estate-claim-doc")
    async def claim_doc(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            claim_id = uuid.UUID(request.query_params.get("claim", ""))
        except ValueError:
            return HTMLResponse("Bad request", status_code=400)
        async with session_scope() as session:
            claim = await session.get(EstateClaim, claim_id)
            docs = list(claim.documents or []) if claim else []
        doc = next((d for d in docs if d.get("id") == request.query_params.get("doc")), None)
        if doc is None:
            return HTMLResponse("Not found", status_code=404)
        return _serve(doc, inline=request.query_params.get("inline") == "1")

    @expose("/estate-beneficiary-doc", methods=["GET"], identity="estate-beneficiary-doc")
    async def beneficiary_doc(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            beneficiary_id = uuid.UUID(request.query_params.get("b", ""))
        except ValueError:
            return HTMLResponse("Bad request", status_code=400)
        async with session_scope() as session:
            ben = await session.get(EstateBeneficiary, beneficiary_id)
            docs = list(ben.id_documents or []) if ben else []
        doc = next((d for d in docs if d.get("id") == request.query_params.get("doc")), None)
        if doc is None:
            return HTMLResponse("Not found", status_code=404)
        return _serve(doc, inline=request.query_params.get("inline") == "1")


ESTATE_VIEWS = (EstateClaimsView, EstateDocView)
