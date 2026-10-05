"""Unit prices in the admin panel (0034).

A property under construction earns by its price going up. Each month, and at each sales
phase, staff record the property's new unit price here; the page also keeps every price it
has had. Recording a price is the only way to change the price of a listing investors hold
(the listing editor refuses), and it does everything that has to follow, in one step: new
buyers pay it, holdings are valued at it, holders are told, the offering's total and minimum
follow, and open liquidity-provider exit requests priced at the old price are closed.

Full admins only (it moves the value of every holding). All writes go through
``price_service.record_price`` (audited).
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

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
from app.models import Property, PropertyPrice
from app.models.base import PropertyStatus
from app.models.identity import User
from app.services import investment_service, listing_service, price_service

_env = Environment(autoescape=True)

# A property under construction is expected to get a new price about once a month.
STALE_AFTER_DAYS = 31

_HEAD = (
    """<!doctype html><html><head><meta charset="utf-8"><title>{{ page_title }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """ dl.kv{display:grid;grid-template-columns:minmax(140px,220px) 1fr;gap:6px 14px;margin:0;font-size:14px} dl.kv dt{color:#6b726c} dl.kv dd{margin:0}
 .scroll{overflow-x:auto}
 .up{color:#198653;font-weight:600} .down{color:#b3261e;font-weight:600} .big{font-size:26px;font-weight:700}
 .grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px} ul.plain{margin:6px 0 0;padding-left:18px;font-size:14px;color:#3d4a43}
 label.check{display:flex;gap:8px;align-items:flex-start;font-weight:400}
</style></head><body><div class="wrap">"""
)

_LIST_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/">&larr; Admin home</a></div><h1>Unit prices</h1>
<p class="lead">The current price of a unit of every published listing. A property under construction earns by its price going up: record its new price each month, and when a new sales phase opens. Investors see the price and its history on their dashboard, in their reports and on the property page.</p></div></div>
{% if due %}<div class="warn">{{ due }} under-construction listing{{ '' if due == 1 else 's' }} ha{{ 's' if due == 1 else 've' }} had no new price for more than {{ stale_days }} days.</div>{% endif %}
<div class="card scroll">{% if rows %}<table><tr><th>Listing</th><th>Kind</th><th>Price now</th><th>Launch price</th><th>Since launch</th><th>Last change</th><th></th></tr>
{% for r in rows %}<tr>
<td>{{ r.p.title }}<div class="muted">{{ r.p.location }}</div></td>
<td>{{ r.kind }}</td>
<td><strong>{{ r.current }}</strong></td>
<td>{{ r.launch }}</td>
<td class="{{ 'up' if r.move > 0 else ('down' if r.move < 0 else 'muted') }}">{{ r.move_label }}</td>
<td>{{ r.changed }}{% if r.stale %} <span class="badge draft">price due</span>{% endif %}</td>
<td><a class="btn mini" href="/admin/unit-prices/{{ r.p.id }}">Open</a></td></tr>{% endfor %}</table>
{% else %}<p class="muted">No published listings yet.</p>{% endif %}</div>
</div></body></html>"""
)

_DETAIL_PAGE = _env.from_string(
    _HEAD
    + """
<div class="top"><div><div class="muted"><a href="/admin/unit-prices">&larr; Unit prices</a> · <a href="/admin/listing/{{ p.id }}">Listing editor</a></div>
<h1>{{ p.title }}</h1><p class="lead">{{ kind }} · {{ p.location }}</p></div></div>
{% if message %}<div class="{{ 'err' if error else 'ok' }}">{{ message }}</div>{% endif %}
<div class="card"><div class="grid3">
<div><div class="muted">Price of a unit now</div><div class="big">{{ current }}</div></div>
<div><div class="muted">Launch price</div><div class="big">{{ launch }}</div></div>
<div><div class="muted">Since launch</div><div class="big {{ 'up' if move > 0 else ('down' if move < 0 else '') }}">{{ move_label }}</div></div>
</div><p class="muted" style="margin:10px 0 0">{{ p.available_units }} of {{ p.total_units }} units still for sale · {{ holders }} investor{{ ' holds or is' if holders == 1 else 's hold or are' }} paying for units.</p></div>

{% if published %}<div class="card"><h2>Record a new price</h2>
<p class="muted">Use this each month for a property under construction, and when a new sales phase opens. The moment you save:</p>
<ul class="plain"><li>new buyers pay the new price (an installment plan started before keeps the price it locked);</li>
<li>every holding of this property is valued at it, and it is the guide price for selling on the secondary market and for a liquidity-provider exit;</li>
<li>everyone who holds the property, or is paying for it by installments, is told (in the app and by email);</li>
<li>open liquidity-provider exit requests priced at the old price are closed, and their sellers are told to make a new one.</li></ul>
<form method="post" style="margin-top:12px">
<div class="cols"><div><label for="price">New price of one unit (USD)</label><input type="text" id="price" name="price" inputmode="decimal" required placeholder="{{ example }}" value="{{ form.price }}"><div class="help">Now {{ current }}. Digits only. <span class="eg">Example: {{ example }}</span></div></div>
<div><label for="label">Sales phase or stage <span class="muted">(optional)</span></label><input type="text" id="label" name="label" maxlength="60" placeholder="Phase 2" value="{{ form.label }}"><div class="help">Fill it in when this price opens a new phase. Investors see it on the price chart.</div></div></div>
<label for="note">Note for investors <span class="muted">(optional)</span></label><input type="text" id="note" name="note" maxlength="300" placeholder="Structure completed; independent valuation of June" value="{{ form.note }}"><div class="help">One line on why the price changed. Shown next to the price in its history.</div>
<label class="check" style="margin-top:10px"><input type="checkbox" name="confirm_large" value="1"{{ ' checked' if form.confirm_large else '' }}> <span>This is a change of more than {{ max_step }}% in one step, and it is correct.</span></label>
<div class="actions" style="margin-top:12px"><button class="primary" type="submit" onclick="return confirm('Record this as the new unit price? Holders are told at once and it cannot be undone (a wrong price is corrected by recording the right one).')">Record the new price</button></div></form></div>
{% else %}<div class="warn">This listing is not published. Until it is, set its price under Listing details in the listing editor.</div>{% endif %}

<div class="card scroll"><h2>Price history</h2><table><tr><th>Date (UTC)</th><th>Price</th><th>Change</th><th>Phase</th><th>Note</th><th>Recorded by</th></tr>
{% for h in history %}<tr><td>{{ h.at }}</td><td><strong>{{ h.price }}</strong></td>
<td class="{{ 'up' if h.move > 0 else ('down' if h.move < 0 else 'muted') }}">{{ h.move_label }}</td>
<td>{{ h.label or '—' }}</td><td>{{ h.note or '—' }}</td><td class="muted">{{ h.by or '—' }}</td></tr>{% endfor %}</table>
<p class="muted" style="margin:10px 0 0">A recorded price is never edited or removed. A mistake is corrected by recording the right price.</p></div>
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


def _kind(prop: Property) -> str:
    return listing_service.purchase_label(prop.model, prop.offplan_payment)


def _is_offplan(prop: Property) -> bool:
    return listing_service.profile_of(prop.model) in listing_service.OFFPLAN_PROFILES


def _move_label(move: decimal.Decimal) -> str:
    return "no change" if move == 0 else price_service.signed_pct(move)


class UnitPricesView(BaseView):
    name = "Unit prices"
    icon = "fa-solid fa-chart-line"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    # The first exposed page is the sidebar link (SQLAdmin registers them bottom-up).
    @expose("/unit-prices", methods=["GET"], identity="unit-prices")
    async def prices_index(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        now = dt.datetime.now(dt.UTC)
        async with session_scope() as session:
            props = (
                (
                    await session.execute(
                        select(Property)
                        .where(Property.status.in_(price_service.PUBLIC_STATUSES))
                        .order_by(Property.created_at.desc())
                        .limit(500)
                    )
                )
                .scalars()
                .all()
            )
            summaries = await price_service.summaries(session, [p.id for p in props])
        rows = []
        for p in props:
            info = summaries.get(p.id, {})
            launch = decimal.Decimal(info.get("launch_price", p.unit_price))
            move = price_service.change_pct(launch, p.unit_price)
            changed_at = info.get("updated_at")
            since = changed_at or p.created_at
            # a sample is for show: nobody holds it, so nobody waits for its price
            stale = (
                _is_offplan(p)
                and not investment_service.is_sample(p)
                and (now - since).days > STALE_AFTER_DAYS
            )
            rows.append(
                {
                    "p": p,
                    "kind": _kind(p),
                    "current": price_service.usd(p.unit_price),
                    "launch": price_service.usd(launch),
                    "move": move,
                    "move_label": _move_label(move),
                    "changed": changed_at.strftime("%Y-%m-%d") if changed_at else "never",
                    "stale": stale,
                    "offplan": _is_offplan(p),
                }
            )
        # what needs a price first, then the other under-construction listings, then the rest
        rows.sort(key=lambda r: (not r["stale"], not r["offplan"]))
        return HTMLResponse(
            _LIST_PAGE.render(
                page_title="Unit prices",
                rows=rows,
                due=sum(1 for r in rows if r["stale"]),
                stale_days=STALE_AFTER_DAYS,
            )
        )

    @expose("/unit-prices/{prop_id}", methods=["GET", "POST"], identity="unit-price")
    async def prices_detail(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            prop_id = uuid.UUID(request.path_params["prop_id"])
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        message, error = "", False
        form = {"price": "", "label": "", "note": "", "confirm_large": False}
        if request.method == "POST":
            posted = await request.form()
            form = {
                "price": str(posted.get("price") or "").strip(),
                "label": str(posted.get("label") or "").strip(),
                "note": str(posted.get("note") or "").strip(),
                "confirm_large": bool(posted.get("confirm_large")),
            }
            try:
                async with session_scope() as session:
                    await price_service.record_price(
                        session,
                        property_id=prop_id,
                        price=form["price"].replace(",", "").replace("$", ""),
                        label=form["label"],
                        note=form["note"],
                        actor_id=_actor(request),
                        confirm_large=form["confirm_large"],
                    )
                return RedirectResponse(f"/admin/unit-prices/{prop_id}?done=1", status_code=303)
            except AppError as exc:
                message, error = exc.message, True
        if request.query_params.get("done") and not message:
            message = "Recorded. It is the price of a unit from now on, and the holders were told."
        async with session_scope() as session:
            prop = await session.get(Property, prop_id)
            if prop is None:
                return HTMLResponse("Not found", status_code=404)
            rows = list(
                (
                    await session.execute(
                        select(PropertyPrice)
                        .where(PropertyPrice.property_id == prop_id)
                        .order_by(PropertyPrice.created_at.desc(), PropertyPrice.id.desc())
                    )
                )
                .scalars()
                .all()
            )
            names = {}
            for uid in {r.created_by for r in rows if r.created_by}:
                user = await session.get(User, uid)
                names[uid] = (user.full_name or user.email) if user else None
            holders = len(await price_service._holders(session, prop_id))
            launch = decimal.Decimal(rows[-1].previous_price) if rows else prop.unit_price
            history = [
                {
                    "at": r.created_at.strftime("%Y-%m-%d %H:%M"),
                    "price": price_service.usd(r.price),
                    "move": price_service.change_pct(r.previous_price, r.price),
                    "move_label": _move_label(price_service.change_pct(r.previous_price, r.price)),
                    "label": r.label,
                    "note": r.note,
                    "by": names.get(r.created_by),
                }
                for r in rows
            ]
            history.append(
                {
                    "at": prop.created_at.strftime("%Y-%m-%d %H:%M") if prop.created_at else "",
                    "price": price_service.usd(launch),
                    "move": decimal.Decimal(0),
                    "move_label": "launch price",
                    "label": None,
                    "note": None,
                    "by": None,
                }
            )
            move = price_service.change_pct(launch, prop.unit_price)
            example = (prop.unit_price * decimal.Decimal("1.01")).quantize(decimal.Decimal("0.01"))
            html = _DETAIL_PAGE.render(
                page_title=f"Unit price · {prop.title}",
                p=prop,
                kind=_kind(prop),
                published=prop.status in (PropertyStatus.active, PropertyStatus.funded),
                current=price_service.usd(prop.unit_price),
                launch=price_service.usd(launch),
                move=move,
                move_label=_move_label(move),
                holders=holders,
                history=history,
                example=f"{example.normalize():f}",
                max_step=int(price_service.MAX_STEP_PCT),
                form=form,
                message=message,
                error=error,
            )
        return HTMLResponse(html, status_code=400 if error else 200)


PRICING_VIEWS = (UnitPricesView,)
