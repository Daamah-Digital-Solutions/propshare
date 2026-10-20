"""Withdrawals desk in the admin panel (owner brief, 2026-10-20).

A member asks for a withdrawal; the team pays it by hand to the saved bank account or crypto
wallet on the request and closes it here: Mark as processing (the transfer has started), Mark
as PAID (with the bank transfer number or the transaction hash), or Mark as FAILED (with the
reason: the amount goes back to the member's wallet, once). An automatic withdrawal that got
stuck (Stripe balance short, over the limit) can be finished the same way. The only things
typed here are the transfer number and the reason; the status moves through these actions
only. The older Withdrawal list (Approve / Mark paid / Reject) stays as it was.
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.admin_listing import _STYLE, is_full_admin
from app.core.db import session_scope
from app.core.errors import AppError
from app.models import Withdrawal
from app.models.compliance import AuditLog
from app.models.identity import User
from app.services import withdrawal_service

_env = Environment(autoescape=True)

STATUS_LABELS = {
    "pending_review": "Pending",
    "approved": "Approved (automatic)",
    "processing": "Processing",
    "completed": "Paid",
    "failed": "Failed (returned)",
    "rejected": "Rejected (returned)",
    "returned": "Returned",
}
STATUS_FILTERS = ("pending_review", "processing", "approved", "completed", "failed", "rejected")
BADGE = {
    "pending_review": "draft",
    "approved": "draft",
    "processing": "draft",
    "completed": "active",
    "failed": "closed",
    "rejected": "closed",
    "returned": "closed",
}

_CSS = (
    _STYLE + """ .filters{display:flex;flex-wrap:wrap;gap:10px;align-items:end;margin-bottom:14px}
 .filters>div{min-width:150px} .num{text-align:right;white-space:nowrap}
 table td{font-size:13px} .kv{display:grid;grid-template-columns:200px 1fr;gap:6px 14px;font-size:14px}
 .kv div:nth-child(odd){color:#6b726c} .acts{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
 .acts form{border:1px solid #e8e6e1;border-radius:10px;padding:14px;background:#fafaf8}
 .acts h3{margin-top:0} input[type=text],input[type=search]{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #d9dcd8;border-radius:8px;font-size:14px}
 .scroll{overflow-x:auto} .mono{font-family:ui-monospace,Consolas,monospace;font-size:13px}
"""
)

_LIST = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8"><title>Withdrawals desk</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{{ css|safe }}</style></head><body><div class="wrap">
<div class="top"><div><div class="muted"><a href="/admin/">&larr; Admin</a> · <a href="/admin/withdrawal/list">Withdrawal list (automatic actions)</a></div>
<h1>Withdrawals desk</h1>
<p class="lead">Pay a request by hand to the account shown on it, then close it: Mark as processing when the transfer starts, Mark as PAID with the transfer number, or Mark as FAILED with the reason (the amount goes back to the member's wallet, once).</p></div></div>
<form class="filters card" method="get">
<div><label for="status">Status</label><select id="status" name="status"><option value="">All</option>{% for s in status_filters %}<option value="{{ s }}" {{ 'selected' if s == f.status }}>{{ labels[s] }}</option>{% endfor %}</select></div>
<div><label for="method">Method</label><select id="method" name="method"><option value="">All</option><option value="bank" {{ 'selected' if f.method == 'bank' }}>Bank</option><option value="crypto" {{ 'selected' if f.method == 'crypto' }}>Crypto</option></select></div>
<div><label for="kind">Kind</label><select id="kind" name="kind"><option value="">All</option><option value="manual" {{ 'selected' if f.kind == 'manual' }}>Manual</option><option value="auto" {{ 'selected' if f.kind == 'auto' }}>Automatic</option></select></div>
<div style="flex:1;min-width:220px"><label for="q">Search</label><input id="q" type="search" name="q" value="{{ f.q }}" placeholder="Email or WD- number"></div>
<div><button class="primary" type="submit">Show</button></div>
</form>
<div class="card scroll"><table>
<tr><th>Reference</th><th>Member</th><th class="num">Amount</th><th>Method</th><th>Kind</th><th>Pay to</th><th>Status</th><th>Asked</th></tr>
{% for w, email in rows %}<tr>
<td><a class="mono" href="/admin/withdrawals-desk/{{ w.id }}">{{ w.reference or w.id|string|truncate(8, True, '') }}</a></td>
<td>{{ email or '—' }}</td><td class="num">${{ '{:,.2f}'.format(w.amount) }}</td><td>{{ w.method|capitalize }}</td>
<td>{{ 'Manual' if w.provider == 'manual' else 'Automatic' }}</td><td>{{ w.destination_label or '—' }}</td>
<td><span class="badge {{ badge.get(w.status, '') }}">{{ labels.get(w.status, w.status) }}</span></td>
<td class="muted">{{ w.created_at.strftime('%d %b %Y %H:%M') if w.created_at }}</td></tr>
{% else %}<tr><td colspan="8" class="muted">No withdrawal matches.</td></tr>{% endfor %}
</table></div></div></body></html>"""
)

_DETAIL = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8"><title>{{ w.reference }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{{ css|safe }}</style></head><body><div class="wrap">
<div class="top"><div><div class="muted"><a href="/admin/withdrawals-desk">&larr; Withdrawals desk</a></div>
<h1>{{ w.reference }} <span class="badge {{ badge.get(w.status, '') }}">{{ labels.get(w.status, w.status) }}</span></h1>
<p class="lead">${{ '{:,.2f}'.format(w.amount) }} by {{ w.method }} · {{ 'Manual' if w.provider == 'manual' else 'Automatic (' ~ w.provider ~ ')' }} · asked {{ w.created_at.strftime('%d %b %Y %H:%M') }} UTC</p></div></div>
{% if error %}<div class="err">{{ error }}</div>{% endif %}{% if done %}<div class="ok">{{ done }}</div>{% endif %}
<div class="card"><h2>Member</h2><div class="kv">
<div>Name</div><div>{{ member.full_name or '—' }}</div><div>Email</div><div>{{ member.email }}</div></div></div>
<div class="card"><h2>Pay to</h2><div class="kv">
<div>As asked</div><div><b>{{ w.destination_label or '—' }}</b></div>
{% for k, label in fields %}{% if dest.get(k) %}<div>{{ label }}</div><div class="mono">{{ dest[k] }}</div>{% endif %}{% endfor %}
{% if w.speed == 'instant' %}<div>Speed</div><div>Instant (fee ${{ w.fee }})</div>{% endif %}
</div><p class="help">A copy taken when the member asked: it stays here even if they delete the saved account.</p></div>
{% if w.transfer_reference or w.failure_reason or w.provider_payout_id %}<div class="card"><h2>Outcome</h2><div class="kv">
{% if w.transfer_reference %}<div>Transfer reference</div><div class="mono">{{ w.transfer_reference }}</div>{% endif %}
{% if w.provider_payout_id %}<div>Provider payout</div><div class="mono">{{ w.provider_payout_id }}</div>{% endif %}
{% if w.failure_reason %}<div>Reason</div><div>{{ w.failure_reason }}</div>{% endif %}
{% if w.completed_at %}<div>Paid</div><div>{{ w.completed_at.strftime('%d %b %Y %H:%M') }} UTC</div>{% endif %}
</div></div>{% endif %}
{% if can.processing or can.paid or can.failed %}<div class="card"><h2>Close it</h2><div class="acts">
{% if can.processing %}<form method="post"><h3>Mark as processing</h3><p class="help">You started the transfer. The member is told it is on its way.</p>
<input type="hidden" name="action" value="processing"><button class="primary" type="submit">Mark as processing</button></form>{% endif %}
{% if can.paid %}<form method="post" onsubmit="return confirm('Mark {{ w.reference }} as PAID? The member is told the money was sent.')"><h3>Mark as PAID</h3>
<label for="transfer_reference">Bank transfer number or transaction hash</label><input id="transfer_reference" type="text" name="transfer_reference" required minlength="3" maxlength="200">
<input type="hidden" name="action" value="paid"><button class="primary" type="submit" style="margin-top:10px">Mark as PAID</button></form>{% endif %}
{% if can.failed %}<form method="post" onsubmit="return confirm('Mark {{ w.reference }} as FAILED? ${{ '{:,.2f}'.format(w.amount) }} goes back to the member\\'s wallet.')"><h3>Mark as FAILED</h3>
<label for="reason">Why it was not sent (the member reads it)</label><input id="reason" type="text" name="reason" required minlength="3" maxlength="500">
<input type="hidden" name="action" value="failed"><button class="danger" type="submit" style="margin-top:10px">Mark as FAILED and return the money</button></form>{% endif %}
</div>{% if note %}<p class="help">{{ note }}</p>{% endif %}</div>{% endif %}
<div class="card"><h2>History</h2><table><tr><th>When (UTC)</th><th>What</th><th>Details</th></tr>
{% for a in history %}<tr><td class="muted">{{ a.created_at.strftime('%d %b %Y %H:%M') }}</td><td>{{ a.action }}</td><td class="muted">{% for k, v in (a.after or {}).items() %}{{ k }}: {{ v }}{% if not loop.last %} · {% endif %}{% endfor %}</td></tr>{% endfor %}
</table></div>
</div></body></html>"""
)

_DEST_FIELDS = (
    ("bank_name", "Bank"),
    ("account_holder", "Account holder"),
    ("iban", "IBAN"),
    ("account_number", "Account number"),
    ("swift_bic", "SWIFT / BIC"),
    ("country", "Country"),
    ("currency", "Currency"),
    ("network", "Network"),
    ("address", "Wallet address"),
    ("connect_account_id", "Stripe account"),
    ("admin_note", "Note"),
)


def _gate(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse("/admin/login", status_code=302)
    if not is_full_admin(request):
        return HTMLResponse("Forbidden", status_code=403)
    return None


def _can(w: Withdrawal) -> dict:
    with_provider = w.status == "processing" and bool(w.provider_payout_id)
    return {
        "processing": w.status in ("pending_review", "approved"),
        "paid": w.status in ("pending_review", "approved", "processing"),
        "failed": w.status in ("pending_review", "approved", "processing") and not with_provider,
    }


class WithdrawalsDeskView(BaseView):
    name = "Withdrawals desk"
    icon = "fa-solid fa-hand-holding-dollar"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    @expose("/withdrawals-desk", methods=["GET"], identity="withdrawals-desk")
    async def desk(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        q = request.query_params
        f = {
            "status": q.get("status", "") if q.get("status", "") in STATUS_FILTERS else "",
            "method": q.get("method", "") if q.get("method") in ("bank", "crypto") else "",
            "kind": q.get("kind", "") if q.get("kind") in ("manual", "auto") else "",
            "q": (q.get("q") or "").strip()[:100],
        }
        async with session_scope() as session:
            rows = await withdrawal_service.list_for_admin(
                session,
                status=f["status"] or None,
                method=f["method"] or None,
                provider=f["kind"] or None,
                search=f["q"] or None,
            )
        html = _LIST.render(
            css=_CSS,
            rows=rows,
            f=f,
            labels=STATUS_LABELS,
            badge=BADGE,
            status_filters=STATUS_FILTERS,
        )
        return HTMLResponse(html)

    @expose("/withdrawals-desk/{wid}", methods=["GET", "POST"], identity="withdrawals-desk-one")
    async def one(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            wid = uuid.UUID(request.path_params["wid"])
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        error = done = ""
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            actor = request.session.get("admin_id")
            actor_id = uuid.UUID(actor) if actor else None
            try:
                async with session_scope() as session:
                    if action == "processing":
                        await withdrawal_service.admin_mark_processing(
                            session, withdrawal_id=wid, actor_id=actor_id
                        )
                        done = "Marked as processing. The member was told."
                    elif action == "paid":
                        ref = str(form.get("transfer_reference") or "").strip()
                        if len(ref) < 3:
                            raise AppError(
                                "REFERENCE_REQUIRED",
                                "Enter the bank transfer number or the transaction hash.",
                                status_code=422,
                            )
                        await withdrawal_service.admin_mark_paid(
                            session, withdrawal_id=wid, actor_id=actor_id, reference=ref[:200]
                        )
                        done = "Marked as PAID. The member was told by notice and email."
                    elif action == "failed":
                        await withdrawal_service.admin_mark_failed(
                            session,
                            withdrawal_id=wid,
                            actor_id=actor_id,
                            reason=str(form.get("reason") or "")[:500],
                        )
                        done = "Marked as FAILED. The amount is back in the member's wallet."
                    else:
                        raise AppError("BAD_ACTION", "Unknown action.", status_code=422)
            except AppError as exc:
                error, done = exc.message, ""
        async with session_scope() as session:
            w = await session.get(Withdrawal, wid)
            if w is None:
                return HTMLResponse("Not found", status_code=404)
            member = await session.get(User, w.user_id)
            history = (
                (
                    await session.execute(
                        select(AuditLog)
                        .where(AuditLog.entity_type == "withdrawal", AuditLog.entity_id == str(wid))
                        .order_by(AuditLog.created_at)
                    )
                )
                .scalars()
                .all()
            )
        can = _can(w)
        note = (
            "This one is with the payment provider: it settles or fails there."
            if w.status == "processing" and w.provider_payout_id
            else ""
        )
        html = _DETAIL.render(
            css=_CSS,
            w=w,
            member=member,
            dest=w.destination if isinstance(w.destination, dict) else {},
            fields=_DEST_FIELDS,
            history=history,
            labels=STATUS_LABELS,
            badge=BADGE,
            can=can,
            note=note,
            error=error,
            done=done,
        )
        return HTMLResponse(html, status_code=400 if error else 200)


WITHDRAWAL_VIEWS = (WithdrawalsDeskView,)
