"""Developers, in the admin panel (client letter, 2026-11-18).

Each developer's full profile is kept once (``saved_developers``): the fields a listing's
developer card shows (name, logo, rating, projects, about, website, years of experience, on-time
delivery, previous projects, verification points, the verified badge). The list fills itself
from the Listing Editor; this page adds a developer, edits or removes one, and can apply a saved
profile to every listing that names that developer. In the Listing Editor, "Fill from a saved
developer" copies a profile into a new listing's card.

The developer's Arabic and French text is kept here too (client 2026-11-19), so it is typed once
and comes with the developer to every listing that picks it.
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import html as _html
import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.admin_listing import _STYLE, _actor, _read_upload, can_edit_listings
from app.core.db import session_scope
from app.core.errors import AppError
from app.models.developers import SavedDeveloper
from app.services import developer_service, listing_media_service, listing_service
from app.services.integrations import storage
from app.services.listing_translation import LANGUAGES

_env = Environment(autoescape=True)

_CSS = (
    _STYLE
    + """ .devrow{display:flex;align-items:center;gap:10px} .devrow img{height:36px;width:36px;object-fit:contain;border-radius:8px;border:1px solid #e8e6e1;background:#fff}
 .initial{height:36px;width:36px;border-radius:8px;background:#e7f5ec;color:#0f6e4e;display:flex;align-items:center;justify-content:center;font-weight:700}
"""
)

_FIELDS = """
  <div class="cols">
   <div data-field="name"><label for="f_dev_name">Developer name <span class="req">*</span></label><input id="f_dev_name" type="text" name="name" maxlength="120" required value="{{ d.name or '' }}" placeholder="Emaar Properties"><div class="help">Company name as investors know it. <span class="eg">Example: Emaar Properties</span></div></div>
   <div data-field="rating"><label for="f_dev_rating">Rating (0–5)</label><input id="f_dev_rating" type="number" name="rating" min="0" max="5" step="0.1" placeholder="4.6" value="{{ d.rating if d.rating is not none }}"><div class="help">Blank hides it. <span class="eg">Example: 4.6</span></div></div>
   <div data-field="projects_completed"><label for="f_dev_projects">Projects completed</label><input id="f_dev_projects" type="number" name="projects_completed" min="0" placeholder="120" value="{{ d.projectsCompleted if d.projectsCompleted is not none }}"><div class="help">Blank hides it. <span class="eg">Example: 120</span></div></div>
   <div data-field="website"><label for="f_dev_website">Website</label><input id="f_dev_website" type="text" name="website" maxlength="200" value="{{ d.website or '' }}" placeholder="https://www.emaar.com"><div class="help">Blank hides it. <span class="eg">Example: https://www.emaar.com</span></div></div>
   <div data-field="about" style="grid-column:1/-1"><label for="f_dev_about">About the developer</label><textarea id="f_dev_about" name="about" rows="4" maxlength="1200" placeholder="Founded in 1997, Emaar has delivered more than 100 projects across the Gulf…">{{ d.about or '' }}</textarea><div class="help">Facts you can stand behind, no promises of returns. <span class="eg">Example: Founded in 1997, delivered 120 projects in Dubai and Riyadh.</span></div></div>
   <div data-field="years_experience"><label for="f_dev_years">Years of experience</label><input id="f_dev_years" type="number" name="years_experience" min="0" max="200" placeholder="12" value="{{ d.yearsExperience if d.yearsExperience is not none }}"><div class="help">Blank hides it. <span class="eg">Example: 12</span></div></div>
   <div data-field="on_time_delivery"><label for="f_dev_ontime">On-time delivery (%)</label><input id="f_dev_ontime" type="number" name="on_time_delivery" min="0" max="100" step="0.1" placeholder="96" value="{{ d.onTimeDelivery if d.onTimeDelivery is not none }}"><div class="help">Only a figure you can document. <span class="eg">Example: 96</span></div></div>
   <div data-field="previous_projects" style="grid-column:1/-1"><label for="f_dev_prev">Previous projects</label><textarea id="f_dev_prev" name="previous_projects" rows="3" placeholder="Marina Heights Tower&#10;Creek Harbour Villas">{{ (d.previousProjects or []) | join('\\n') }}</textarea><div class="help">One per line (max 12). <span class="eg">Example: Marina Heights Tower</span></div></div>
   <div data-field="verifications" style="grid-column:1/-1"><label for="f_dev_ver">Verification points</label><textarea id="f_dev_ver" name="verifications" rows="3" placeholder="Trade license verified&#10;Audited financial statements on file">{{ (d.verifications or []) | join('\\n') }}</textarea><div class="help">What Capimax checked, one per line (max 8). <span class="eg">Example: Trade license verified</span></div></div>
   <div data-field="verified" style="grid-column:1/-1"><label class="inline" style="font-weight:600"><input type="checkbox" name="verified" value="1" {{ 'checked' if d.verified }}> Show a “Verified developer” badge</label><div class="help">Tick only after Capimax has actually verified this developer.</div></div>
   <div data-field="logo"><label for="f_dev_logo">Logo</label><input id="f_dev_logo" type="file" name="logo" accept="image/jpeg,image/png,image/webp">
     <div class="help">Square image looks best; blank keeps the current logo.</div>
     {% if d.logo %}<div class="muted" style="margin-top:4px"><img src="{{ d.logo }}" alt="logo" style="height:32px;vertical-align:middle;border-radius:6px"> <label class="inline" style="font-weight:400"><input type="checkbox" name="clear_logo" value="1"> remove logo</label></div>{% endif %}
   </div>
  </div>
"""

_VERSIONS = """
  <h2 style="margin-top:18px">Arabic &amp; French versions</h2>
  <p class="lead">What a visitor reads about this developer when the site is in Arabic or French. Typed once here, it comes with the developer to every listing that picks it. A box left blank shows the English. A listing's own Arabic or French version, when saved, also updates it here.</p>
  {% for v in version_boxes %}
  <details class="tr" data-version="{{ v.lang }}" {{ 'open' if v.filled }}>
   <summary><b>{{ v.name }}</b> <span class="muted">{{ v.filled }} of {{ v.fields|length }} filled</span></summary>
   {% for f in v.fields %}
   <div class="f" data-field="v_{{ v.lang }}__{{ f.key }}"><label for="f_v_{{ v.lang }}_{{ f.key }}">{{ f.label }}</label>
    {% if f.kind == 'line' %}<input type="text" id="f_v_{{ v.lang }}_{{ f.key }}" name="v_{{ v.lang }}__{{ f.key }}" dir="{{ v.dir }}" lang="{{ v.lang }}" maxlength="{{ f.max_len }}" value="{{ f.value }}">
    {% else %}<textarea id="f_v_{{ v.lang }}_{{ f.key }}" name="v_{{ v.lang }}__{{ f.key }}" dir="{{ v.dir }}" lang="{{ v.lang }}" rows="{{ 4 if f.kind == 'text' else 3 }}">{{ f.value }}</textarea>{% endif %}
    <div class="help">{% if f.kind == 'lines' %}One per line, in the order of the English. {% endif %}{% if f.english %}English: {{ f.english }}{% endif %}</div>
   </div>
   {% endfor %}
  </details>
  {% endfor %}
"""

_LIST = _env.from_string("""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Developers</title><style>{{ css }}</style></head><body><div class="wrap">
<p><a href="/admin/listing">&larr; Listings</a></p>
<h1>Developers</h1>
{% if msg %}<div class="ok">{{ msg }}</div>{% endif %}
<div class="card">
 <p class="lead">Each developer's full profile, kept once. In the Listing Editor, <b>Fill from a saved developer</b> copies a profile into a listing's developer card. A developer is also saved here every time a listing's developer card is saved.</p>
 <p><a class="btn primary" href="/admin/developers/new">Add a developer</a></p>
 {% if rows %}
 <table><tr><th>Developer</th><th>Rating</th><th>Projects</th><th>Listings</th><th></th></tr>
 {% for r in rows %}
 <tr><td><div class="devrow">{% if r.d.profile.logo %}<img src="{{ r.d.profile.logo }}" alt="">{% else %}<span class="initial">{{ r.d.name[:1] }}</span>{% endif %}<b>{{ r.d.name }}</b>{% if r.d.profile.verified %} <span class="badge active">verified</span>{% endif %}</div></td>
 <td>{{ r.d.profile.rating if r.d.profile.rating is not none else '—' }}</td><td>{{ r.d.profile.projectsCompleted if r.d.profile.projectsCompleted is not none else '—' }}</td><td>{{ r.listings }}</td>
 <td><a class="btn mini" href="/admin/developers/profile/{{ r.d.id }}">Edit</a></td></tr>
 {% endfor %}
 </table>
 {% else %}<p class="muted">No developer saved yet.</p>{% endif %}
</div></div></body></html>""")

_EDIT = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }}</title><style>{{ css }}</style></head><body><div class="wrap">
<p><a href="/admin/developers">&larr; Developers</a></p>
<h1>{{ title }}</h1>
{% if msg %}<div class="ok">{{ msg }}</div>{% endif %}{% if err %}<div class="err">{{ err }}</div>{% endif %}
<div class="card">
 <form method="post" enctype="multipart/form-data"><input type="hidden" name="action" value="save">
 """
    + _FIELDS
    + _VERSIONS
    + """
  {% if listings %}<div class="note"><label class="inline" style="font-weight:600"><input type="checkbox" name="apply" value="1"> Also update the {{ listings|length }} listing(s) that name this developer</label>
   <div class="help">{% for p in listings %}{{ p.title }}{{ ', ' if not loop.last }}{% endfor %}. Unticked, they keep their own copy.</div></div>{% endif %}
  <button class="primary" type="submit" style="margin-top:8px">Save developer</button>
 </form>
</div>
{% if dev_id %}
<div class="card">
 <h2>Remove</h2>
 <p class="lead">Forgets this saved profile. Listings that name the developer keep their own copy.</p>
 <form method="post" onsubmit="return confirm('Remove this saved developer?')"><input type="hidden" name="action" value="delete"><button class="danger" type="submit">Remove developer</button></form>
</div>
{% endif %}
</div></body></html>"""
)


def _as_text(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(x) for x in value)
    return "" if value is None else str(value)


def _version_boxes(profile: dict, versions: dict | None = None, form=None) -> list[dict]:
    """The Arabic / French boxes: the saved text, or what was typed when a save was refused."""
    boxes = []
    for lang, name in LANGUAGES.items():
        mine = (versions or {}).get(lang) or {}
        fields = []
        for key, label, kind, max_len, _items in developer_service.VERSION_FIELDS:
            value = (
                str(form.get(f"v_{lang}__{key}") or "")
                if form is not None
                else _as_text(mine.get(key))
            )
            english = profile.get(key)
            english = " · ".join(english) if isinstance(english, list) else (english or "")
            fields.append(
                {
                    "key": key,
                    "label": label,
                    "kind": kind,
                    "max_len": max_len,
                    "value": value,
                    "english": english,
                }
            )
        boxes.append(
            {
                "lang": lang,
                "name": name,
                "dir": "rtl" if lang == "ar" else "ltr",
                "fields": fields,
                "filled": sum(1 for f in fields if f["value"].strip()),
            }
        )
    return boxes


def _gate(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse("/admin/login", status_code=302)
    if not can_edit_listings(request):
        return HTMLResponse("Forbidden", status_code=403)
    return None


async def _logo(form) -> str | None:
    got = await _read_upload(form.get("logo"))
    if not got:
        return None
    blob, ext, ctype = listing_media_service.process_image(got[1])
    key = f"developers/developer-logo-{uuid.uuid4().hex}.{ext}"
    storage.save(key, blob, ctype)
    return storage.public_url(key)


class DevelopersView(BaseView):
    name = "Developers"
    icon = "fa-solid fa-helmet-safety"

    def is_accessible(self, request: Request) -> bool:
        return can_edit_listings(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    @expose("/developers", methods=["GET"], identity="developers")
    async def index(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        async with session_scope() as session:
            saved = await developer_service.list_saved(session)
            rows = [
                {"d": d, "listings": len(await developer_service.listings_of(session, d.slug))}
                for d in saved
            ]
        msg = {"saved": "Developer saved.", "removed": "Developer removed."}.get(
            request.query_params.get("done") or "", ""
        )
        return HTMLResponse(_LIST.render(css=_CSS, rows=rows, msg=msg))

    @expose("/developers/new", methods=["GET", "POST"], identity="developers-new")
    async def new(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        if request.method == "GET":
            return HTMLResponse(
                _EDIT.render(
                    css=_CSS,
                    title="Add a developer",
                    d={},
                    listings=[],
                    version_boxes=_version_boxes({}),
                )
            )
        form = await request.form()
        try:
            async with session_scope() as session:
                content = listing_service.with_developer({}, form, logo_url=await _logo(form))
                profile = developer_service.profile_of(content)
                if not str(profile.get("name") or "").strip():
                    raise ValueError("Developer name: this field is required.")
                versions = developer_service.parse_versions(form)
                dev = await developer_service.remember(
                    session, profile, actor_id=_actor(request), versions=versions
                )
                dev_id = dev.id
        except (ValueError, AppError) as exc:
            msg = exc.message if isinstance(exc, AppError) else str(exc)
            return HTMLResponse(
                _EDIT.render(
                    css=_CSS,
                    title="Add a developer",
                    d=dict(form),
                    listings=[],
                    err=msg,
                    version_boxes=_version_boxes({}, form=form),
                ),
                status_code=400,
            )
        return RedirectResponse(f"/admin/developers/profile/{dev_id}?done=saved", status_code=303)

    @expose("/developers/profile/{dev_id}", methods=["GET", "POST"], identity="developers-edit")
    async def edit(self, request: Request):
        if (resp := _gate(request)) is not None:
            return resp
        try:
            dev_id = uuid.UUID(request.path_params["dev_id"])
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        msg = err = ""
        refused_form = None
        async with session_scope() as session:
            dev = await session.get(SavedDeveloper, dev_id)
            if dev is None:
                return HTMLResponse("Not found", status_code=404)
            if request.method == "POST":
                form = await request.form()
                action = str(form.get("action") or "")
                actor = _actor(request)
                if action == "delete":
                    await developer_service.delete_saved(session, dev, actor_id=actor)
                    return RedirectResponse("/admin/developers?done=removed", status_code=303)
                try:
                    async with session.begin_nested():
                        await developer_service.update_saved(
                            session, dev, form, logo_url=await _logo(form), actor_id=actor
                        )
                        msg = "Developer saved."
                        if str(form.get("apply") or "") == "1":
                            n = await developer_service.apply_to_listings(
                                session, dev, actor_id=actor
                            )
                            msg += f" {n} listing(s) updated."
                except (ValueError, AppError) as exc:
                    err = exc.message if isinstance(exc, AppError) else str(exc)
                    refused_form = form
                    await session.refresh(dev)
            elif request.query_params.get("done") == "saved":
                msg = "Developer saved."
            listings = await developer_service.listings_of(session, dev.slug)
            html = _EDIT.render(
                css=_CSS,
                title=dev.name,
                d=dev.profile,
                dev_id=str(dev.id),
                listings=listings,
                msg=msg,
                err=_html.unescape(err),
                version_boxes=_version_boxes(dev.profile or {}, dev.versions, form=refused_form),
            )
        return HTMLResponse(html, status_code=400 if err else 200)


DEVELOPER_VIEWS = (DevelopersView,)
