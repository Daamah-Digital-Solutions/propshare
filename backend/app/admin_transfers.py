"""Transfers desk in the admin panel (client, 2026-10-28).

Every transfer of units or wallet balance between members, by its TR- number: who sent what to
whom, its status, the fee, the dates, the recipient's state (no account yet, email not
confirmed, identity not verified, ready), the money and unit rows it wrote, and its history.
Two actions on a transfer not delivered yet: Deliver now (when it is due and the recipient is
ready; the run every 30 minutes does it too) and Cancel and return (with the reason the sender reads:
everything held goes back to them, once).
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
from app.models import KycVerification, Transaction
from app.models.compliance import AuditLog
from app.models.identity import User
from app.models.investments import OwnershipLedger
from app.models.transfers import OPEN, Transfer
from app.services import account_service, transfer_service
from app.services.transfer_service import STATUS_LABELS

_env = Environment(autoescape=True)

STATUS_FILTERS = ("scheduled", "waiting", "delivered", "cancelled", "expired", "failed")
BADGE = {
    "scheduled": "draft",
    "waiting": "draft",
    "delivered": "active",
    "cancelled": "closed",
    "expired": "closed",
    "failed": "closed",
}

_CSS = (
    _STYLE + """ .filters{display:flex;flex-wrap:wrap;gap:10px;align-items:end;margin-bottom:14px}
 .filters>div{min-width:150px} .num{text-align:right;white-space:nowrap} table td{font-size:13px}
 .kv{display:grid;grid-template-columns:200px 1fr;gap:6px 14px;font-size:14px} .kv div:nth-child(odd){color:#6b726c}
 .acts{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
 .acts form{border:1px solid #e8e6e1;border-radius:10px;padding:14px;background:#fafaf8} .acts h3{margin-top:0}
 input[type=text],input[type=search]{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #d9dcd8;border-radius:8px;font-size:14px}
 .scroll{overflow-x:auto} .mono{font-family:ui-monospace,Consolas,monospace;font-size:13px}
"""
)

_LIST = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8"><title>Transfers desk</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{{ css|safe }}</style></head><body><div class="wrap">
<div class="top"><div><div class="muted"><a href="/admin/">&larr; Admin</a></div>
<h1>Transfers desk</h1>
<p class="lead">Units or wallet balance members sent to another person. What is sent is held at once; it is delivered when the recipient's email is confirmed and identity verified, or comes back to the sender after {{ claim_days }} days.</p></div></div>
<form class="filters card" method="get">
<div><label for="status">Status</label><select id="status" name="status"><option value="">All</option>{% for s in status_filters %}<option value="{{ s }}" {{ 'selected' if s == f.status }}>{{ labels[s] }}</option>{% endfor %}</select></div>
<div><label for="asset">What</label><select id="asset" name="asset"><option value="">All</option><option value="units" {{ 'selected' if f.asset == 'units' }}>Units</option><option value="balance" {{ 'selected' if f.asset == 'balance' }}>Wallet balance</option></select></div>
<div style="flex:1;min-width:220px"><label for="q">Search</label><input id="q" type="search" name="q" value="{{ f.q }}" placeholder="Sender or recipient email, or TR- number"></div>
<div><button class="primary" type="submit">Show</button></div>
</form>
<div class="card scroll"><table>
<tr><th>Reference</th><th>From</th><th>To</th><th>What</th><th class="num">Value</th><th>Status</th><th>Sent</th></tr>
{% for t, sender in rows %}<tr>
<td><a class="mono" href="/admin/transfers-desk/{{ t.id }}">{{ t.reference }}</a></td>
<td>{{ sender or '—' }}</td><td>{{ t.recipient_email }}</td><td>{{ describe(t) }}</td>
<td class="num">${{ '{:,.2f}'.format(t.amount) }}</td>
<td><span class="badge {{ badge.get(t.status, '') }}">{{ labels.get(t.status, t.status) }}</span></td>
<td class="muted">{{ t.created_at.strftime('%d %b %Y %H:%M') if t.created_at }}</td></tr>
{% else %}<tr><td colspan="7" class="muted">No transfer matches.</td></tr>{% endfor %}
</table></div></div></body></html>"""
)

_DETAIL = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8"><title>{{ t.reference }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{{ css|safe }}</style></head><body><div class="wrap">
<div class="top"><div><div class="muted"><a href="/admin/transfers-desk">&larr; Transfers desk</a></div>
<h1>{{ t.reference }} <span class="badge {{ badge.get(t.status, '') }}">{{ labels.get(t.status, t.status) }}</span></h1>
<p class="lead">{{ describe(t) }} · sent {{ t.created_at.strftime('%d %b %Y %H:%M') }} UTC</p></div></div>
{% if error %}<div class="err">{{ error }}</div>{% endif %}{% if done %}<div class="ok">{{ done }}</div>{% endif %}
<div class="card"><h2>Transfer</h2><div class="kv">
<div>From</div><div>{{ sender.full_name or '—' }} · {{ sender.email }}</div>
<div>To</div><div>{{ t.recipient_name or '—' }} · {{ t.recipient_email }}</div>
<div>Recipient</div><div><b>{{ recipient_state }}</b></div>
<div>What</div><div>{{ describe(t) }}{% if t.asset == 'units' %} at ${{ '{:,.2f}'.format(t.unit_price) }} a unit{% endif %}</div>
<div>Value</div><div>${{ '{:,.2f}'.format(t.amount) }}</div>
<div>Fee</div><div>${{ '{:,.2f}'.format(t.fee) }} ({{ t.fee_pct.normalize() }}%)</div>
<div>Delivery date</div><div>{{ t.deliver_on.strftime('%d %b %Y') }}</div>
{% if t.expires_at %}<div>Must be received by</div><div>{{ t.expires_at.strftime('%d %b %Y %H:%M') }} UTC</div>{% endif %}
{% if t.delivered_at %}<div>Delivered</div><div>{{ t.delivered_at.strftime('%d %b %Y %H:%M') }} UTC</div>{% endif %}
{% if t.closed_reason %}<div>Closed</div><div>{{ t.closed_reason }}</div>{% endif %}
{% if t.message %}<div>Message</div><div>“{{ t.message }}”</div>{% endif %}
</div></div>
{% if can_act %}<div class="card"><h2>Act on it</h2><div class="acts">
<form method="post"><h3>Deliver now</h3><p class="help">When it is due and the recipient's email is confirmed and identity verified. The run every 30 minutes does this on its own.</p>
<input type="hidden" name="action" value="deliver"><button class="primary" type="submit">Deliver now</button></form>
<form method="post" onsubmit="return confirm('Cancel {{ t.reference }}? Everything held goes back to the sender.')"><h3>Cancel and return</h3>
<label for="reason">Why (the sender reads it)</label><input id="reason" type="text" name="reason" required minlength="3" maxlength="250">
<input type="hidden" name="action" value="cancel"><button class="danger" type="submit" style="margin-top:10px">Cancel and return to the sender</button></form>
</div></div>{% endif %}
<div class="card"><h2>Money and units</h2><div class="scroll"><table><tr><th>When (UTC)</th><th>Account</th><th>Row</th><th class="num">Amount / units</th></tr>
{% for r in money %}<tr><td class="muted">{{ r.at.strftime('%d %b %Y %H:%M') }}</td><td>{{ r.who }}</td><td>{{ r.what }}</td><td class="num">{{ r.value }}</td></tr>
{% else %}<tr><td colspan="4" class="muted">Nothing moved for this transfer.</td></tr>{% endfor %}</table></div></div>
<div class="card"><h2>History</h2><table><tr><th>When (UTC)</th><th>What</th><th>Details</th></tr>
{% for a in history %}<tr><td class="muted">{{ a.created_at.strftime('%d %b %Y %H:%M') }}</td><td>{{ a.action }}</td><td class="muted">{% for k, v in (a.after or {}).items() %}{{ k }}: {{ v }}{% if not loop.last %} · {% endif %}{% endfor %}</td></tr>{% endfor %}
</table></div>
</div></body></html>"""
)


def _gate(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse("/admin/login", status_code=302)
    if not is_full_admin(request):
        return HTMLResponse("Forbidden", status_code=403)
    return None


async def _recipient_state(session, t: Transfer) -> str:
    user = await account_service.by_address(session, t.recipient_email)
    if user is None:
        return "No account with this email yet (invited)"
    if user.closed_at is not None:
        return "Account closed"
    if not user.email_verified:
        return "Has an account; email not confirmed yet"
    kyc = await session.scalar(
        select(KycVerification.status).where(KycVerification.user_id == user.id)
    )
    if str(kyc) != "verified":
        return "Email confirmed; identity not verified yet"
    return "Ready to receive (email confirmed, identity verified)"


async def _money(session, t: Transfer) -> list[dict]:
    emails = dict(
        (
            await session.execute(
                select(User.id, User.email).where(
                    User.id.in_([i for i in (t.sender_id, t.recipient_id) if i])
                )
            )
        ).all()
    )
    rows = []
    for tx in (
        (
            await session.execute(
                select(Transaction)
                .where(Transaction.reference_id == t.id)
                .order_by(Transaction.created_at)
            )
        )
        .scalars()
        .all()
    ):
        rows.append(
            {
                "at": tx.created_at,
                "who": emails.get(tx.user_id, str(tx.user_id)),
                "what": f"Wallet · {tx.description or tx.type}",
                "value": f"{'+' if tx.amount > 0 else '−'}${abs(tx.amount):,.2f}",
            }
        )
    for led in (
        (
            await session.execute(
                select(OwnershipLedger)
                .where(OwnershipLedger.ref_id == t.id)
                .order_by(OwnershipLedger.created_at)
            )
        )
        .scalars()
        .all()
    ):
        rows.append(
            {
                "at": led.created_at,
                "who": emails.get(led.user_id, str(led.user_id)),
                "what": f"Units · {led.reason}",
                "value": f"{led.units:+d} units",
            }
        )
    return sorted(rows, key=lambda r: r["at"])


class TransfersDeskView(BaseView):
    name = "Transfers desk"
    icon = "fa-solid fa-right-left"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    @expose("/transfers-desk", methods=["GET"], identity="transfers-desk")
    async def desk(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        q = request.query_params
        f = {
            "status": q.get("status", "") if q.get("status", "") in STATUS_FILTERS else "",
            "asset": q.get("asset", "") if q.get("asset") in ("units", "balance") else "",
            "q": (q.get("q") or "").strip()[:100],
        }
        async with session_scope() as session:
            rows = await transfer_service.list_for_admin(
                session, status=f["status"] or None, asset=f["asset"] or None, search=f["q"] or None
            )
        html = _LIST.render(
            css=_CSS,
            rows=rows,
            f=f,
            labels=STATUS_LABELS,
            badge=BADGE,
            status_filters=STATUS_FILTERS,
            describe=transfer_service.describe,
            claim_days=transfer_service.CLAIM_DAYS,
        )
        return HTMLResponse(html)

    @expose("/transfers-desk/{tid}", methods=["GET", "POST"], identity="transfers-desk-one")
    async def one(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            tid = uuid.UUID(request.path_params["tid"])
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        error = done = ""
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            raw = request.session.get("admin_id")
            actor_id = uuid.UUID(str(raw)) if raw else None
            try:
                async with session_scope() as session:
                    if action == "deliver":
                        t = await transfer_service.admin_deliver(
                            session, transfer_id=tid, actor_id=actor_id
                        )
                        done = (
                            "Delivered. Both sides were told."
                            if t.status == "delivered"
                            else f"Not delivered: {t.closed_reason or STATUS_LABELS[t.status]}."
                        )
                    elif action == "cancel":
                        await transfer_service.admin_cancel(
                            session,
                            transfer_id=tid,
                            actor_id=actor_id,
                            reason=str(form.get("reason") or ""),
                        )
                        done = "Cancelled. Everything held went back to the sender, who was told."
                    else:
                        raise AppError("BAD_ACTION", "Unknown action.", status_code=422)
            except AppError as exc:
                error, done = exc.message, ""
        async with session_scope() as session:
            t = await session.get(Transfer, tid)
            if t is None:
                return HTMLResponse("Not found", status_code=404)
            sender = await session.get(User, t.sender_id)
            history = (
                (
                    await session.execute(
                        select(AuditLog)
                        .where(AuditLog.entity_type == "transfer", AuditLog.entity_id == str(tid))
                        .order_by(AuditLog.created_at)
                    )
                )
                .scalars()
                .all()
            )
            html = _DETAIL.render(
                css=_CSS,
                t=t,
                sender=sender,
                recipient_state=await _recipient_state(session, t),
                money=await _money(session, t),
                history=history,
                labels=STATUS_LABELS,
                badge=BADGE,
                can_act=t.status in OPEN,
                describe=transfer_service.describe,
                error=error,
                done=done,
            )
        return HTMLResponse(html, status_code=400 if error else 200)


TRANSFER_VIEWS = (TransfersDeskView,)
