"""Nova Sukuk certificates in the admin panel (0032).

An investor can pay for units — a purchase, or an installment plan's down payment — with a Nova
Digital Finance sukuk certificate (PDF). No money passes through the platform: staff open the
certificate, check it covers the amount due, and approve it (the held units become the
investor's, pledged to Nova Finance) or reject it with a reason the investor reads. When Nova
Finance clears the financing, staff release the pledge so the units can be sold or transferred.

Full admins only. All writes go through ``sukuk_service`` (audited, notifies the investor).
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import datetime as dt
import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.admin_listing import _STYLE, is_full_admin
from app.core.db import session_scope
from app.core.errors import AppError
from app.models import InstallmentPlan, Investment, Property, SukukCertificate
from app.models.identity import User
from app.services import sukuk_service
from app.services.integrations import storage

_env = Environment(autoescape=True)

_SHOW = {
    "pending": "Waiting for review",
    "approved": "Approved — pledged to Nova",
    "rejected": "Not accepted",
    "released": "Pledge released",
}

STATUS_LABELS = {
    "pending": ("Waiting for review", "draft"),
    "approved": ("Approved — units pledged to Nova Finance", "active"),
    "rejected": ("Not accepted", "closed"),
    "released": ("Pledge released", "active"),
}

_HEAD = (
    """<!doctype html><html><head><meta charset="utf-8"><title>{{ page_title }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """ .tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px} .tabs a{padding:6px 12px;border:1px solid #d9dcd8;border-radius:999px;font-size:13px;text-decoration:none;color:#23302a;background:#fff}
 .tabs a.on{background:#198653;border-color:#198653;color:#fff;font-weight:600}
 dl.kv{display:grid;grid-template-columns:minmax(140px,220px) 1fr;gap:6px 14px;margin:0;font-size:14px} dl.kv dt{color:#6b726c} dl.kv dd{margin:0}
 .scroll{overflow-x:auto} .warn{background:#fff7e6;border:1px solid #f0c36d;border-radius:8px;padding:10px 12px;margin:0 0 12px;font-size:14px}
</style></head><body><div class="wrap">"""
)

_LIST_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/">&larr; Admin home</a></div><h1>Nova Sukuk</h1>
<p class="lead">Investors who paid for units with a Nova Digital Finance sukuk certificate. The units are held while the certificate waits for review. Approve it when it covers the amount due; the units then stay pledged to Nova Finance until you release the pledge.</p></div></div>
<div class="tabs">{% for key, label, count in tabs %}<a class="{{ 'on' if key == show else '' }}" href="?show={{ key }}">{{ label }} ({{ count }})</a>{% endfor %}</div>
<div class="card scroll">{% if rows %}<table><tr><th>Investor</th><th>Property</th><th>Pays for</th><th>Amount due</th><th>Certificate</th><th>Submitted</th><th></th></tr>
{% for r in rows %}<tr>
<td>{{ r.investor }}<div class="muted">{{ r.email }}</div></td>
<td>{{ r.property }}</td>
<td>{{ r.what }}</td>
<td>{{ r.c.amount_due }} USD</td>
<td>{{ r.c.certificate_no or '—' }}<div class="muted">{{ r.c.issuer or '' }}{% if r.c.certificate_value is not none %} · {{ r.c.certificate_value }} USD{% endif %}</div></td>
<td class="muted">{{ r.c.created_at.strftime('%Y-%m-%d') if r.c.created_at else '' }}</td>
<td><a class="btn mini" href="/admin/sukuk-review/{{ r.c.id }}">Open</a></td></tr>{% endfor %}</table>
{% else %}<p class="muted">Nothing here.</p>{% endif %}</div>
</div></body></html>"""
)

_DETAIL_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/sukuk-review">&larr; Nova Sukuk</a></div>
<h1>{{ what }}</h1><p class="lead"><span class="badge {{ css }}">{{ label }}</span> &nbsp;{{ property }} · {{ investor }}</p></div>
<div class="actions"><a class="btn" href="/admin/sukuk-certificate?cert={{ c.id }}" target="_blank" rel="noopener">Open the certificate (PDF)</a></div></div>
{% if message %}<div class="{{ 'err' if error else 'ok' }}">{{ message }}</div>{% endif %}
{% for w in warnings %}<div class="warn">{{ w }}</div>{% endfor %}
{% if c.status == 'pending' %}<div class="card"><h2>Decision</h2><p class="muted">Approving confirms the units for the investor exactly like a paid checkout{{ ' and starts the installment plan' if c.plan_id else '' }}; they stay pledged to Nova Finance. Rejecting releases the held units. The investor is told either way, by email too.</p>
<form method="post"><label for="note">Message to the investor <span class="muted">(required to reject)</span></label><textarea id="note" name="note"></textarea>
<div class="actions" style="margin-top:10px">
<button class="primary" type="submit" name="action" value="approve" onclick="return confirm('Approve this certificate? The units become the investor\\'s.')">Approve — the certificate covers {{ c.amount_due }} USD</button>
<button class="danger" type="submit" name="action" value="reject" onclick="return confirm('Reject this certificate?')">Reject</button></div></form></div>{% endif %}
{% if c.status == 'approved' %}<div class="card"><h2>Pledge</h2><p class="muted">These {{ c.units }} unit(s) cannot be sold, exited, gifted or transferred until you release the pledge. Release it once Nova Finance confirms the financing is settled.</p>
<form method="post"><label for="note">Note <span class="muted">(optional, e.g. Nova's clearance reference)</span></label><textarea id="note" name="note"></textarea>
<div class="actions" style="margin-top:10px"><button type="submit" name="action" value="release" onclick="return confirm('Release the Nova pledge on these units?')">Release the pledge</button></div></form></div>{% endif %}
<div class="card"><h2>What the investor submitted</h2><dl class="kv">
<dt>Pays for</dt><dd>{{ what }}</dd><dt>Units</dt><dd>{{ c.units }}</dd><dt>Amount due</dt><dd>{{ c.amount_due }} USD <span class="muted">({{ basis }})</span></dd>
<dt>Certificate no.</dt><dd>{{ c.certificate_no or '—' }}</dd><dt>Issuer</dt><dd>{{ c.issuer or '—' }}</dd>
<dt>Certificate value</dt><dd>{{ (c.certificate_value ~ ' USD') if c.certificate_value is not none else '—' }}</dd><dt>Valid until</dt><dd>{{ c.valid_until or '—' }}</dd>
<dt>File</dt><dd>{{ c.file_name }} <span class="muted">({{ (c.file_size / 1024)|round(1) }} KB)</span></dd>
<dt>Submitted</dt><dd>{{ c.created_at.strftime('%Y-%m-%d %H:%M UTC') if c.created_at else '—' }}</dd>
{% if c.reviewed_at %}<dt>Decided</dt><dd>{{ c.reviewed_at.strftime('%Y-%m-%d %H:%M UTC') }}{% if reviewer %} by {{ reviewer }}{% endif %}</dd>{% endif %}
{% if c.released_at %}<dt>Pledge released</dt><dd>{{ c.released_at.strftime('%Y-%m-%d %H:%M UTC') }}</dd>{% endif %}
{% if c.review_note %}<dt>Message / note</dt><dd style="white-space:pre-line">{{ c.review_note }}</dd>{% endif %}</dl></div>
<div class="card"><h2>Investor</h2><dl class="kv"><dt>Name</dt><dd>{{ investor }}</dd><dt>Email</dt><dd>{{ email }}</dd></dl></div>
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


def _what(c: SukukCertificate) -> str:
    if c.investment_id:
        return f"Purchase of {c.units} unit(s)"
    return f"Installment plan down payment ({c.units} unit(s) vest with it)"


def _person(user: User | None) -> tuple[str, str]:
    if user is None:
        return "—", "—"
    return user.full_name or user.email, user.email


class SukukReviewView(BaseView):
    name = "Nova Sukuk"
    icon = "fa-solid fa-file-signature"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    # The first exposed page is the sidebar link (SQLAdmin registers them bottom-up).
    @expose("/sukuk-review", methods=["GET"], identity="sukuk-review")
    async def sukuk_index(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        show = request.query_params.get("show", "pending")
        if show not in _SHOW:
            show = "pending"
        async with session_scope() as session:
            tabs = [
                (
                    key,
                    label,
                    await session.scalar(
                        select(func.count(SukukCertificate.id)).where(
                            SukukCertificate.status == key
                        )
                    )
                    or 0,
                )
                for key, label in _SHOW.items()
            ]
            certs = (
                (
                    await session.execute(
                        select(SukukCertificate)
                        .where(SukukCertificate.status == show)
                        .order_by(SukukCertificate.created_at.desc())
                        .limit(300)
                    )
                )
                .scalars()
                .all()
            )
            rows = []
            for c in certs:
                investor, email = _person(await session.get(User, c.user_id))
                prop = await session.get(Property, c.property_id)
                rows.append(
                    {
                        "c": c,
                        "investor": investor,
                        "email": email,
                        "property": prop.title if prop else "—",
                        "what": _what(c),
                    }
                )
        return HTMLResponse(
            _LIST_PAGE.render(page_title="Nova Sukuk", rows=rows, tabs=tabs, show=show)
        )

    @expose("/sukuk-review/{cert_id}", methods=["GET", "POST"], identity="sukuk-certificate")
    async def sukuk_detail(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            cert_id = uuid.UUID(request.path_params["cert_id"])
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        message, error = "", False
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            note = str(form.get("note") or "")
            decide = {
                "approve": lambda s: sukuk_service.approve(
                    s, certificate_id=cert_id, admin_id=_actor(request), note=note
                ),
                "reject": lambda s: sukuk_service.reject(
                    s, certificate_id=cert_id, admin_id=_actor(request), reason=note
                ),
                "release": lambda s: sukuk_service.release_pledge(
                    s, certificate_id=cert_id, admin_id=_actor(request), note=note
                ),
            }.get(action)
            if decide is None:
                return HTMLResponse("Bad request", status_code=400)
            try:
                async with session_scope() as session:
                    await decide(session)
                return RedirectResponse(
                    f"/admin/sukuk-review/{cert_id}?done={action}", status_code=303
                )
            except AppError as exc:
                message, error = exc.message, True
        done = request.query_params.get("done")
        if done and not message:
            message = {
                "approve": "Approved — the units are the investor's (pledged to Nova Finance). The investor was told.",
                "reject": "Rejected — the held units are back on sale. The investor was told, with your message.",
                "release": "Pledge released — the units can be sold or transferred. The investor was told.",
            }.get(done, "")
        async with session_scope() as session:
            c = await session.get(SukukCertificate, cert_id)
            if c is None:
                return HTMLResponse("Not found", status_code=404)
            investor, email = _person(await session.get(User, c.user_id))
            reviewer = await session.get(User, c.reviewed_by) if c.reviewed_by else None
            prop = await session.get(Property, c.property_id)
            basis = "purchase total: units + platform fee"
            warnings = []
            if c.investment_id:
                inv = await session.get(Investment, c.investment_id)
                if c.status == "pending" and inv is not None and str(inv.status) != "pending":
                    warnings.append(f"This purchase is {inv.status}: it can no longer be approved.")
            else:
                basis = "the down payment and its installment fee"
                plan = await session.get(InstallmentPlan, c.plan_id)
                if c.status == "pending" and plan is not None and plan.status != "pending_review":
                    warnings.append(f"This plan is {plan.status}: it can no longer be approved.")
            if c.certificate_value is not None and c.certificate_value < c.amount_due:
                warnings.append(
                    f"The value the investor entered ({c.certificate_value} USD) is below the amount due ({c.amount_due} USD). Check the certificate itself."
                )
            if c.valid_until is not None and c.valid_until < dt.datetime.now(dt.UTC).date():
                warnings.append(f"The certificate's validity date ({c.valid_until}) has passed.")
            label, css = STATUS_LABELS.get(c.status, (c.status, ""))
            html = _DETAIL_PAGE.render(
                page_title="Nova Sukuk certificate",
                c=c,
                what=_what(c),
                basis=basis,
                label=label,
                css=css,
                investor=investor,
                email=email,
                property=prop.title if prop else "—",
                reviewer=_person(reviewer)[0] if reviewer else None,
                warnings=warnings,
                message=message,
                error=error,
            )
        return HTMLResponse(html, status_code=400 if error else 200)


class SukukCertificateFileView(BaseView):
    """Session-authed view of a certificate PDF an investor uploaded (never public)."""

    name = "Nova Sukuk Certificate"

    def is_visible(self, request: Request) -> bool:
        return False

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    @expose("/sukuk-certificate", methods=["GET"], identity="sukuk-certificate-file")
    async def sukuk_certificate_file(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            cert_id = uuid.UUID(request.query_params.get("cert", ""))
        except ValueError:
            return HTMLResponse("Bad request", status_code=400)
        async with session_scope() as session:
            c = await session.get(SukukCertificate, cert_id)
        if c is None:
            return HTMLResponse("Not found", status_code=404)
        try:
            data = storage.load(c.file_key)
        except Exception:  # noqa: BLE001 — any storage error → not found
            return HTMLResponse("File missing", status_code=404)
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{c.file_name}"'},
        )


SUKUK_VIEWS = (SukukReviewView, SukukCertificateFileView)
