"""Card waitlist, in the admin panel (client, 2026-11-19).

Cards are not issued yet; the cards section reads "Coming soon · Join the Waitlist" and every
member who joins is listed here with the card they asked for, newest first. Read only.
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.admin_listing import _STYLE, is_full_admin
from app.core.db import session_scope
from app.models import Profile
from app.models.cards import CardWaitlistEntry
from app.models.identity import User
from app.services.card_waitlist_service import CARD_TYPES

_env = Environment(autoescape=True)

_PAGE = _env.from_string("""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Card waitlist</title><style>{{ css }}</style></head><body><div class="wrap">
<p><a href="/admin/">&larr; Admin home</a></p>
<h1>Card waitlist</h1>
<div class="card">
 <p class="lead">Cards are not issued yet: the cards section reads <b>Coming soon · Join the Waitlist</b>. Each member who joined is listed with the card they asked for. {{ rows|length }} member{{ '' if rows|length == 1 else 's' }}{% if counts %} — {% for name, n in counts %}{{ name }}: {{ n }}{{ ', ' if not loop.last }}{% endfor %}{% endif %}.</p>
 {% if rows %}
 <table><tr><th>Member</th><th>Email</th><th>Card</th><th>Joined</th><th>Last changed</th></tr>
 {% for r in rows %}<tr><td>{{ r.name or '—' }}</td><td>{{ r.email }}</td><td>{{ r.card }}</td><td>{{ r.joined }}</td><td>{{ r.changed }}</td></tr>{% endfor %}
 </table>
 {% else %}<p class="muted">Nobody has joined yet.</p>{% endif %}
</div></div></body></html>""")


class CardWaitlistView(BaseView):
    name = "Card waitlist"
    icon = "fa-solid fa-credit-card"

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id")) and is_full_admin(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    @expose("/card-waitlist", methods=["GET"], identity="card-waitlist")
    async def index(self, request: Request):
        if not request.session.get("admin_id"):
            return RedirectResponse("/admin/login", status_code=302)
        if not is_full_admin(request):
            return HTMLResponse("Forbidden", status_code=403)
        async with session_scope() as session:
            res = await session.execute(
                select(CardWaitlistEntry, User.email, Profile.full_name)
                .join(User, User.id == CardWaitlistEntry.user_id)
                .outerjoin(Profile, Profile.id == CardWaitlistEntry.user_id)
                .order_by(CardWaitlistEntry.created_at.desc())
            )
            rows = []
            counts: dict[str, int] = {}
            for entry, email, name in res.all():
                card = CARD_TYPES.get(entry.card_type, entry.card_type)
                counts[card] = counts.get(card, 0) + 1
                rows.append(
                    {
                        "name": name,
                        "email": email,
                        "card": card,
                        "joined": entry.created_at.strftime("%Y-%m-%d %H:%M"),
                        "changed": entry.updated_at.strftime("%Y-%m-%d %H:%M")
                        if entry.updated_at and entry.updated_at != entry.created_at
                        else "—",
                    }
                )
        return HTMLResponse(_PAGE.render(css=_STYLE, rows=rows, counts=sorted(counts.items())))


CARD_VIEWS = (CardWaitlistView,)
