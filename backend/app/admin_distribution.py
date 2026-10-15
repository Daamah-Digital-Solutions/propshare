"""Admin page to distribute a property's returns (client, 2026-10-15).

The raw create form of Distributions asked for the property's id typed by hand, and saving it
paid every investor at once, with no look at the amounts first. This page picks the property
by name, fills the period from a month, and shows what each investor would receive (gross,
management fee, net) before anything moves; the distribution runs only from that preview,
through ``distribution_service.run_distribution`` (the one audited path). The old create form
sends here (admin.py).
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import calendar
import datetime as dt
import decimal
import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.admin_listing import _STYLE, is_full_admin
from app.core.db import session_scope
from app.core.errors import AppError
from app.models import Property
from app.models.identity import User
from app.services import distribution_service

_env = Environment(autoescape=True)

KINDS = (
    ("rental", "Rental income (rent for the period)"),
    ("appreciation", "Appreciation (gain on the property's value)"),
    ("other", "Other return"),
)

_PAGE = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8"><title>Distribute returns</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """ .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
 .help{font-size:12px;color:#6b726c;margin-top:4px} table td.num,table th.num{text-align:right}
 .sum{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 14px}
 .sum div{background:#f4f7f3;border:1px solid #dfe5dd;border-radius:8px;padding:10px 12px}
 .sum b{display:block;font-size:18px;margin-top:2px} .sum span{font-size:12px;color:#6b726c}
 button:disabled{opacity:.45;cursor:not-allowed} .scroll{overflow-x:auto}
 input[type=month]{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #d9dcd8;border-radius:8px;font-size:14px;background:#fff}
</style></head><body><div class="wrap">
<div class="top"><div><div class="muted"><a href="/admin/distribution/list">&larr; Distributions</a></div><h1>Distribute returns</h1>
<p class="lead">Choose the property, the period and how much it pays, and check what each investor receives before anything moves. The total is shared by units held; for rental income each investor's management fee is withheld from their share; the net goes to their wallet with a notification and an email.</p></div></div>
{% if error %}<div class="err">{{ error }}</div>{% endif %}

<form method="post" class="card">
<div class="grid">
<div><label for="property_id">1. Property</label>
<select id="property_id" name="property_id" required><option value="">Choose a property…</option>
{% for p in properties %}<option value="{{ p.id }}" {{ 'selected' if p.id|string == f.property_id }}>{{ p.title }}{% if p.location %} — {{ p.location }}{% endif %} ({{ p.status }})</option>{% endfor %}</select></div>
<div><label for="kind">2. Type of return</label>
<select id="kind" name="kind">{% for value, label in kinds %}<option value="{{ value }}" {{ 'selected' if value == f.kind }}>{{ label }}</option>{% endfor %}</select></div>
</div>
<div class="grid" style="margin-top:14px">
<div><label for="month">3. Month</label><input id="month" type="month" value="{{ f.month }}">
<div class="help">Fills the period name and dates beside it; change them for another period.</div></div>
<div><label for="period_key">Period name</label><input id="period_key" name="period_key" type="text" required value="{{ f.period_key }}" placeholder="2026-10">
<div class="help">Shown to investors. A property is paid once per period name.</div></div>
<div><label for="period_start">From</label><input id="period_start" name="period_start" type="date" required value="{{ f.period_start }}"></div>
<div><label for="period_end">To</label><input id="period_end" name="period_end" type="date" required value="{{ f.period_end }}">
<div class="help">The last day of the period, included.</div></div>
</div>
<div class="grid" style="margin-top:14px">
<div><label for="basis">4. How much</label>
<select id="basis" name="basis">
<option value="yield" {{ 'selected' if f.basis == 'yield' }}>Gross yield, % a year</option>
<option value="amount" {{ 'selected' if f.basis == 'amount' }}>A total amount in USD</option></select></div>
<div class="by-yield"><label for="annual_yield_pct">Gross yield (% a year)</label>
<input id="annual_yield_pct" name="annual_yield_pct" type="number" step="0.01" min="0.01" max="100" value="{{ f.annual_yield_pct }}" placeholder="8">
<div class="help">On the value of the units held (units × unit price), for the days of the period.</div></div>
<div class="by-amount"><label for="gross_pool">Total to distribute (USD)</label>
<input id="gross_pool" name="gross_pool" type="number" step="0.01" min="0.01" value="{{ f.gross_pool }}">
<div class="help">For the whole property, before fees: not one investor's share.</div></div>
</div>
<div class="actions" style="margin-top:14px"><button class="primary" type="submit" name="action" value="preview">Preview the distribution</button></div>
</form>

{% if preview %}
<div class="card">
<h2>Preview: {{ preview.property.title }} — {{ f.period_key }}</h2>
{% if preview.already_distributed %}<div class="err">This period ({{ f.period_key }}) was already distributed for this property: it cannot be paid twice. Choose another period name.</div>{% endif %}
{% if calc %}<div class="explain">{{ calc.annual_yield_pct }}% a year on {{ '{:,}'.format(calc.units) }} units × ${{ '{:,.2f}'.format(calc.unit_price) }} = ${{ '{:,.2f}'.format(calc.value) }}, for {{ calc.days }} days of 365: <b>${{ '{:,.2f}'.format(calc.pool) }}</b> to distribute.</div>{% endif %}
<div class="sum">
<div><span>Investors</span><b>{{ preview.investors }}</b></div>
<div><span>Units sharing it</span><b>{{ '{:,}'.format(preview.units) }}</b></div>
<div><span>Total</span><b>${{ '{:,.2f}'.format(preview.gross) }}</b></div>
<div><span>Management fees withheld</span><b>${{ '{:,.2f}'.format(preview.fee) }}</b></div>
<div><span>Paid to wallets</span><b>${{ '{:,.2f}'.format(preview.net) }}</b></div>
</div>
<div class="scroll"><table><tr><th>Investor</th><th class="num">Units</th><th class="num">Share</th><th class="num">Management fee</th><th class="num">To their wallet</th></tr>
{% for line in lines %}<tr><td>{{ line.name }}<div class="muted">{{ line.email }}</div></td><td class="num">{{ '{:,}'.format(line.units) }}</td><td class="num">${{ '{:,.2f}'.format(line.gross) }}</td><td class="num">${{ '{:,.2f}'.format(line.fee) }}</td><td class="num"><b>${{ '{:,.2f}'.format(line.net) }}</b></td></tr>{% endfor %}
</table></div>
<p class="help">Units bought on an installment plan that is still running earn no return until the plan is paid in full, so they are not counted here.</p>
<form method="post" style="margin-top:12px">
{% for k in ('property_id','kind','period_key','period_start','period_end') %}<input type="hidden" name="{{ k }}" value="{{ f[k] }}">{% endfor %}
<input type="hidden" name="basis" value="amount"><input type="hidden" name="gross_pool" value="{{ preview.gross }}">
<div class="actions"><button class="primary" type="submit" name="action" value="confirm" {{ 'disabled' if preview.already_distributed }}
 onclick="return confirm('Pay ${{ '{:,.2f}'.format(preview.net) }} to {{ preview.investors }} investor(s) now? Money is credited to their wallets and cannot be taken back.')">Distribute now</button></div>
</form></div>
{% endif %}
</div>
<script>
function showBasis() {
  var y = document.getElementById('basis').value === 'yield';
  document.querySelector('.by-yield').style.display = y ? '' : 'none';
  document.querySelector('.by-amount').style.display = y ? 'none' : '';
}
document.getElementById('basis').addEventListener('change', showBasis); showBasis();
document.getElementById('month').addEventListener('change', function () {
  var v = this.value; if (!v) return;
  var y = +v.slice(0, 4), m = +v.slice(5, 7), last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  document.getElementById('period_key').value = v;
  document.getElementById('period_start').value = v + '-01';
  document.getElementById('period_end').value = v + '-' + String(last).padStart(2, '0');
});
</script></body></html>"""
)


def _gate(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse("/admin/login", status_code=302)
    if not is_full_admin(request):
        return HTMLResponse("Forbidden", status_code=403)
    return None


def _default_form() -> dict:
    """Last month, the usual one to pay rent for, priced as a yearly yield."""
    today = dt.datetime.now(dt.UTC).date()
    first = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    return {
        "property_id": "",
        "kind": "rental",
        "basis": "yield",
        "annual_yield_pct": "",
        "gross_pool": "",
        "month": f"{first:%Y-%m}",
        "period_key": f"{first:%Y-%m}",
        "period_start": first.isoformat(),
        "period_end": last.isoformat(),
    }


def _invalid(message: str) -> AppError:
    return AppError("INVALID_FORM", message, status_code=422)


def _number(raw: str, message: str) -> decimal.Decimal:
    try:
        value = decimal.Decimal(raw)
    except decimal.InvalidOperation as exc:
        raise _invalid(message) from exc
    if not value.is_finite():
        raise _invalid(message)
    return value


def _read(form) -> tuple[dict, dict, decimal.Decimal | None]:
    """The form as typed (to show it again), the values to compute with, and the yearly
    yield when the total is to be worked out from it."""
    f = {k: str(form.get(k) or "").strip() for k in _default_form()}
    f["month"] = f["period_key"] if len(f["period_key"]) == 7 else ""
    f["basis"] = "amount" if f["basis"] == "amount" else "yield"
    try:
        property_id = uuid.UUID(f["property_id"])
    except ValueError as exc:
        raise _invalid("Choose a property.") from exc
    try:
        start = dt.date.fromisoformat(f["period_start"])
        end = dt.date.fromisoformat(f["period_end"])
    except ValueError as exc:
        raise _invalid("Fill the period's dates (from and to).") from exc
    values = {
        "property_id": property_id,
        "kind": f["kind"],
        "period_key": f["period_key"],
        "period_start": start,
        "period_end": end,
    }
    if f["basis"] == "yield":
        return f, values, _number(f["annual_yield_pct"], "Enter the gross yield (% a year).")
    values["gross_pool"] = _number(f["gross_pool"], "Enter the total to distribute.")
    return f, values, None


class DistributeView(BaseView):
    name = "Distribute returns"
    icon = "fa-solid fa-hand-holding-dollar"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    @expose("/distribution/new", methods=["GET", "POST"], identity="distribution-new")
    async def distribute(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        f, error, preview, lines, calc = _default_form(), "", None, [], None
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "preview")
            try:
                f, values, annual_yield = _read(form)
                if annual_yield is not None:
                    async with session_scope() as session:
                        calc = await distribution_service.pool_from_yield(
                            session,
                            property_id=values["property_id"],
                            annual_yield_pct=annual_yield,
                            period_start=values["period_start"],
                            period_end=values["period_end"],
                        )
                    values["gross_pool"] = calc["pool"]
                if action == "confirm":
                    actor = request.session.get("admin_id")
                    async with session_scope() as session:
                        result = await distribution_service.run_distribution(
                            session,
                            **values,
                            created_by=uuid.UUID(actor) if actor else None,
                            idempotency_key=None,
                        )
                    return RedirectResponse(
                        f"/admin/distribution/details/{result['distribution_id']}",
                        status_code=303,
                    )
                async with session_scope() as session:
                    preview = await distribution_service.preview_distribution(session, **values)
                    names = {
                        uid: (name, email)
                        for uid, name, email in (
                            await session.execute(
                                select(User.id, User.full_name, User.email).where(
                                    User.id.in_([line[0] for line in preview["lines"]])
                                )
                            )
                        ).all()
                    }
                lines = [
                    {
                        "name": (names.get(uid, ("", ""))[0] or "").strip() or "—",
                        "email": names.get(uid, ("", ""))[1],
                        "units": units,
                        "gross": gross,
                        "fee": fee,
                        "net": net,
                    }
                    for uid, units, gross, fee, net in preview["lines"]
                ]
            except AppError as exc:
                error, preview, calc = exc.message, None, None
        async with session_scope() as session:
            properties = (
                (await session.execute(select(Property).order_by(Property.title))).scalars().all()
            )
        html = _PAGE.render(
            properties=properties,
            kinds=KINDS,
            f=f,
            error=error,
            preview=preview,
            lines=lines,
            calc=calc,
        )
        return HTMLResponse(html, status_code=400 if error else 200)


DISTRIBUTION_VIEWS = (DistributeView,)
