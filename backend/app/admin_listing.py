"""Listing Editor — one admin page per property (go-live audit, Step 2).

Everything the public property page can show, editable in one place without touching raw
JSON: gallery (upload / reorder / cover / delete), documents (upload with category + delete
+ replace), key facts & amenities, developer block, SPV extras, commercial terms & listing
fees, plus a 24-hour **preview link** that opens the real public page for a draft.

All writes go through the audited services (listing_media_service, document_service,
listing_service); this module only renders forms and routes POST actions.
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import html as _html
import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.errors import AppError
from app.models import Document, Property
from app.services import document_service, listing_media_service, listing_service, property_service

_env = Environment(autoescape=True)

_PAGE = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8">
<title>Listing Editor · {{ p.title }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f4f5f3;margin:0;padding:24px;color:#23302a}
 .wrap{max-width:1080px;margin:0 auto}
 .top{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px}
 h1{font-size:22px;margin:0} h2{font-size:16px;margin:0 0 10px}
 .badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:#e8e6e1}
 .badge.active{background:#e7f5ec;color:#0f6e4e} .badge.draft{background:#fff4dc;color:#8a5a00}
 .card{background:#fff;border:1px solid #e8e6e1;border-radius:14px;padding:20px 22px;margin-bottom:18px;box-shadow:0 6px 22px rgba(20,40,30,.05)}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
 .img{border:1px solid #e8e6e1;border-radius:10px;overflow:hidden;background:#fafaf8}
 .img img{width:100%;height:110px;object-fit:cover;display:block}
 .img .bar{display:flex;flex-wrap:wrap;gap:4px;padding:6px}
 .img.cover{outline:2px solid #198653}
 button,.btn{padding:7px 12px;border:1px solid #d9dcd8;border-radius:8px;background:#fff;font-size:13px;cursor:pointer;color:#23302a;text-decoration:none;display:inline-block}
 button.primary,.btn.primary{background:#198653;border-color:#198653;color:#fff;font-weight:600}
 button.danger{color:#b00;border-color:#f2c2c2}
 button.mini{padding:3px 7px;font-size:12px}
 label{display:block;font-weight:600;font-size:13px;margin:10px 0 4px}
 input[type=text],input[type=number],input[type=file],select,textarea{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #d9dcd8;border-radius:8px;font-size:14px}
 textarea{min-height:90px}
 .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
 table{width:100%;border-collapse:collapse;font-size:14px} td,th{padding:8px 6px;border-bottom:1px solid #eee;text-align:left;vertical-align:middle}
 .ok{background:#e7f5ec;border:1px solid #b7e0c6;color:#0f6e4e;padding:10px 12px;border-radius:8px;margin-bottom:14px}
 .err{background:#fdeaea;border:1px solid #f2c2c2;color:#b00;padding:10px 12px;border-radius:8px;margin-bottom:14px}
 .muted{color:#6b726c;font-size:13px} code{background:#f0f0ec;padding:2px 5px;border-radius:5px;font-size:12px}
 .actions{display:flex;flex-wrap:wrap;gap:8px}
 .inline{display:inline}
</style></head><body><div class="wrap">
<div class="top">
  <div>
    <div class="muted"><a href="/admin/property/list">&larr; Properties</a></div>
    <h1>{{ p.title }} <span class="badge {{ 'active' if p.status.value in ('active','funded') else 'draft' }}">{{ p.status.value }}</span></h1>
    <div class="muted">{{ p.model }} · {{ p.location }} · slug <code>{{ p.slug or '—' }}</code></div>
  </div>
  <div class="actions">
    <a class="btn" href="/admin/property/edit/{{ p.id }}">Edit fields</a>
    <a class="btn" href="/admin/property-milestone/list?search={{ p.id }}">Milestones</a>
    {% if p.status.value in ('active','funded') %}
      <a class="btn" href="{{ public_url }}" target="_blank" rel="noopener">Open public page ↗</a>
      <a class="btn danger" href="/admin/property/action/close?pks={{ p.id }}" onclick="return confirm('Unpublish (close) this listing?')">Unpublish</a>
    {% else %}
      <form method="post" class="inline"><input type="hidden" name="action" value="make_preview"><button type="submit">Preview link (24h)</button></form>
      <a class="btn primary" href="/admin/property/action/approve?pks={{ p.id }}" onclick="return confirm('Publish this listing to investors?')">Publish</a>
    {% endif %}
  </div>
</div>
{% if message %}<div class="{{ 'err' if error else 'ok' }}">{{ message }}</div>{% endif %}
{% if preview_url %}<div class="ok">Preview (valid 24 h, read-only, this property only): <a href="{{ preview_url }}" target="_blank" rel="noopener">{{ preview_url }}</a></div>{% endif %}

<div class="card">
 <h2>Gallery <span class="muted">— first image is the cover · JPEG/PNG/WebP · auto-resized to 2000px</span></h2>
 {% if images %}
 <div class="grid">
  {% for url in images %}
  <div class="img {{ 'cover' if loop.first else '' }}">
    <img src="{{ url }}" alt="image {{ loop.index }}">
    <div class="bar">
      {% if loop.first %}<span class="badge active">cover</span>{% else %}
      <form method="post" class="inline"><input type="hidden" name="action" value="image_cover"><input type="hidden" name="url" value="{{ url }}"><button class="mini" type="submit">Make cover</button></form>{% endif %}
      <form method="post" class="inline"><input type="hidden" name="action" value="image_up"><input type="hidden" name="url" value="{{ url }}"><button class="mini" type="submit" {{ 'disabled' if loop.first }}>&larr;</button></form>
      <form method="post" class="inline"><input type="hidden" name="action" value="image_down"><input type="hidden" name="url" value="{{ url }}"><button class="mini" type="submit" {{ 'disabled' if loop.last }}>&rarr;</button></form>
      <form method="post" class="inline" onsubmit="return confirm('Delete this image?')"><input type="hidden" name="action" value="image_delete"><input type="hidden" name="url" value="{{ url }}"><button class="mini danger" type="submit">Delete</button></form>
    </div>
  </div>
  {% endfor %}
 </div>
 {% else %}<p class="muted">No images yet — the public page shows a “Photos coming soon” placeholder.</p>{% endif %}
 <form method="post" enctype="multipart/form-data" style="margin-top:12px">
  <input type="hidden" name="action" value="upload_images">
  <label>Add images (you can select several)</label>
  <input type="file" name="files" accept="image/jpeg,image/png,image/webp" multiple required>
  <button class="primary" type="submit" style="margin-top:8px">Upload images</button>
 </form>
</div>

<div class="card">
 <h2>Documents <span class="muted">— PDF/DOCX/XLSX/CSV/TXT/images · max {{ max_mb }} MB · public on the listing page</span></h2>
 {% if docs %}
 <table><tr><th>Title</th><th>Category</th><th>Added</th><th></th></tr>
 {% for d in docs %}
 <tr>
  <td>{{ d.title }}</td><td>{{ cat_labels.get(d.type, d.type) }}</td><td>{{ d.created_at.strftime('%Y-%m-%d') }}</td>
  <td class="actions">
   <a class="btn mini" href="/api/v1/documents/{{ d.id }}/download{{ '?preview=' ~ preview_token if preview_token else '' }}" target="_blank" rel="noopener">Download</a>
   <form method="post" enctype="multipart/form-data" class="inline"><input type="hidden" name="action" value="doc_replace"><input type="hidden" name="doc_id" value="{{ d.id }}"><input type="file" name="file" required style="width:200px;display:inline-block;padding:3px"><button class="mini" type="submit">Replace file</button></form>
   <form method="post" class="inline" onsubmit="return confirm('Delete this document and its file?')"><input type="hidden" name="action" value="doc_delete"><input type="hidden" name="doc_id" value="{{ d.id }}"><button class="mini danger" type="submit">Delete</button></form>
  </td>
 </tr>
 {% endfor %}
 </table>
 {% else %}<p class="muted">No documents yet.</p>{% endif %}
 <form method="post" enctype="multipart/form-data" style="margin-top:12px">
  <input type="hidden" name="action" value="upload_doc">
  <div class="cols">
   <div><label>Title</label><input type="text" name="title" required placeholder="e.g. Independent Valuation Report"></div>
   <div><label>Category</label><select name="doc_type">{% for v,l in categories %}<option value="{{ v }}">{{ l }}</option>{% endfor %}</select></div>
   <div><label>File</label><input type="file" name="file" required></div>
  </div>
  <button class="primary" type="submit" style="margin-top:8px">Upload document</button>
 </form>
</div>

<div class="card">
 <h2>Key facts &amp; amenities <span class="muted">— shown in the facts strip and the Overview tab</span></h2>
 <form method="post"><input type="hidden" name="action" value="save_facts">
  <div class="cols">
   <div><label>Bedrooms</label><input type="number" name="bedrooms" min="0" value="{{ details.bedrooms if details.bedrooms is not none }}"></div>
   <div><label>Bathrooms</label><input type="number" name="bathrooms" min="0" value="{{ details.bathrooms if details.bathrooms is not none }}"></div>
   <div><label>Area (sq ft)</label><input type="number" name="area" min="0" step="0.1" value="{{ details.area if details.area is not none }}"></div>
   <div><label>Parking spaces</label><input type="number" name="parking" min="0" value="{{ details.parking if details.parking is not none }}"></div>
   <div><label>Maximum investment ($, optional)</label><input type="number" name="max_investment" min="0" step="0.01" value="{{ details.maxInvestment if details.maxInvestment is not none }}"></div>
  </div>
  <label>Amenities (one per line)</label>
  <textarea name="amenities" placeholder="24-hour concierge&#10;Rooftop lounge&#10;Underground parking">{{ amenities_text }}</textarea>
  <button class="primary" type="submit" style="margin-top:8px">Save facts</button>
 </form>
</div>

<div class="card">
 <h2>Developer</h2>
 <form method="post" enctype="multipart/form-data"><input type="hidden" name="action" value="save_developer">
  <div class="cols">
   <div><label>Name</label><input type="text" name="name" value="{{ developer.name or '' }}" placeholder="Crestmark Estates"></div>
   <div><label>Rating (0–5, optional)</label><input type="number" name="rating" min="0" max="5" step="0.1" value="{{ developer.rating if developer.rating is not none }}"></div>
   <div><label>Projects completed (optional)</label><input type="number" name="projects_completed" min="0" value="{{ developer.projectsCompleted if developer.projectsCompleted is not none }}"></div>
   <div><label>Logo (image, optional)</label><input type="file" name="logo" accept="image/jpeg,image/png,image/webp">
     {% if developer.logo %}<div class="muted" style="margin-top:4px"><img src="{{ developer.logo }}" alt="logo" style="height:32px;vertical-align:middle;border-radius:6px"> <label class="inline" style="font-weight:400"><input type="checkbox" name="clear_logo" value="1"> remove logo</label></div>{% endif %}
   </div>
  </div>
  <button class="primary" type="submit" style="margin-top:8px">Save developer</button>
 </form>
</div>

<div class="card">
 <h2>SPV details <span class="muted">— name &amp; registration number are on “Edit fields”</span></h2>
 <form method="post"><input type="hidden" name="action" value="save_spv">
  <div class="cols">
   <div><label>Jurisdiction</label><input type="text" name="jurisdiction" value="{{ spv.jurisdiction or '' }}" placeholder="England & Wales"></div>
   <div><label>Trustee</label><input type="text" name="trustee" value="{{ spv.trustee or '' }}"></div>
   <div><label>Auditor</label><input type="text" name="auditor" value="{{ spv.auditor or '' }}"></div>
  </div>
  <button class="primary" type="submit" style="margin-top:8px">Save SPV details</button>
 </form>
</div>

<div class="card">
 <h2>Terms &amp; listing fees <span class="muted">— Financials tab; leave blank to hide a row. Platform/management/installment rates are global settings.</span></h2>
 <form method="post"><input type="hidden" name="action" value="save_terms">
  <div class="cols">
   <div><label>Distribution frequency</label><input type="text" name="distribution_frequency" value="{{ terms.distributionFrequency or '' }}" placeholder="Monthly"></div>
   <div><label>Investment term</label><input type="text" name="investment_term" value="{{ terms.investmentTerm or '' }}" placeholder="7–10 years"></div>
   <div><label>Exit options</label><input type="text" name="exit_options" value="{{ terms.exitOptions or '' }}" placeholder="Secondary market · Liquidity provider"></div>
   <div><label>Performance fee % (optional)</label><input type="number" name="performance_fee" min="0" max="100" step="0.1" value="{{ fees.performance if fees.performance is not none }}"></div>
   <div><label>Exit fee % (optional)</label><input type="number" name="exit_fee" min="0" max="100" step="0.1" value="{{ fees.exit if fees.exit is not none }}"></div>
  </div>
  <button class="primary" type="submit" style="margin-top:8px">Save terms</button>
 </form>
</div>
</div></body></html>"""
)


def _actor(request: Request) -> uuid.UUID | None:
    actor = request.session.get("admin_id")
    return uuid.UUID(actor) if actor else None


async def _read_upload(upload) -> tuple[str, bytes] | None:
    if upload is None or not hasattr(upload, "read"):
        return None
    data = await upload.read()
    if not data:
        return None
    return (getattr(upload, "filename", "file") or "file", data)


class ListingEditorView(BaseView):
    name = "Listing Editor"
    icon = "fa-solid fa-pen-ruler"

    def is_visible(self, request: Request) -> bool:  # reached from the Properties list
        return False

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_id"))

    @expose("/listing/{prop_id}", methods=["GET", "POST"])
    async def editor(self, request: Request):
        if not request.session.get("admin_id"):
            return RedirectResponse("/admin/login", status_code=302)
        try:
            prop_id = uuid.UUID(request.path_params["prop_id"])
        except ValueError:
            return HTMLResponse("Invalid property id", status_code=404)

        message, error, preview_url, preview_token = "", False, "", ""
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            try:
                async with session_scope() as session:
                    prop = await session.get(Property, prop_id)
                    if prop is None:
                        return HTMLResponse("Property not found", status_code=404)
                    message, preview_token = await self._handle(session, request, prop, action, form)
            except (AppError, ValueError) as exc:
                message, error = getattr(exc, "message", None) or str(exc), True

        async with session_scope() as session:
            prop = await session.get(Property, prop_id)
            if prop is None:
                return HTMLResponse("Property not found", status_code=404)
            docs = (
                await session.execute(
                    select(Document)
                    .where(Document.property_id == prop.id)
                    .order_by(Document.created_at.desc())
                )
            ).scalars().all()
            content = dict(prop.content or {})
            base = get_settings().app_base_url.rstrip("/")
            ref = prop.slug or str(prop.id)
            if preview_token:
                preview_url = f"{base}/property/{ref}?preview={preview_token}"
            html = _PAGE.render(
                p=prop,
                images=list(prop.images or []),
                docs=docs,
                details=content.get("details") or {},
                amenities_text="\n".join((content.get("details") or {}).get("amenities") or []),
                developer=content.get("developer") or {},
                spv=content.get("spv") or {},
                terms=content.get("terms") or {},
                fees=content.get("fees") or {},
                categories=document_service.DOC_CATEGORIES,
                cat_labels=dict(document_service.DOC_CATEGORIES),
                max_mb=get_settings().storage_max_upload_mb,
                public_url=f"{base}/property/{ref}",
                preview_url=preview_url,
                preview_token=preview_token,
                message=message,
                error=error,
            )
        return HTMLResponse(html)

    async def _handle(self, session, request: Request, prop: Property, action: str, form):
        actor = _actor(request)
        preview_token = ""
        if action == "make_preview":
            preview_token = property_service.make_preview_token(prop.id)
            return "Preview link created — it works for 24 hours.", preview_token
        if action == "upload_images":
            files = []
            for up in form.getlist("files"):
                got = await _read_upload(up)
                if got:
                    files.append(got)
            if not files:
                raise ValueError("Choose at least one image.")
            await listing_media_service.add_images(session, prop=prop, files=files, actor_id=actor)
            return f"Added {len(files)} image(s).", preview_token
        url = str(form.get("url") or "")
        if action == "image_delete":
            await listing_media_service.remove_image(session, prop=prop, url=url, actor_id=actor)
            return "Image deleted.", preview_token
        if action == "image_cover":
            await listing_media_service.set_cover(session, prop=prop, url=url, actor_id=actor)
            return "Cover image updated.", preview_token
        if action in ("image_up", "image_down"):
            order = listing_media_service.moved(
                list(prop.images or []), url, -1 if action == "image_up" else 1
            )
            await listing_media_service.reorder_images(session, prop=prop, order=order, actor_id=actor)
            return "Gallery order updated.", preview_token
        if action == "upload_doc":
            got = await _read_upload(form.get("file"))
            if not got:
                raise ValueError("Choose a file.")
            title = str(form.get("title") or "").strip()
            if not title:
                raise ValueError("Title is required.")
            await document_service.admin_create_property_document(
                session,
                prop_id=prop.id,
                title=title,
                doc_type=str(form.get("doc_type") or "other"),
                filename=got[0],
                data=got[1],
            )
            return f"Uploaded “{_html.escape(title)}”.", preview_token
        if action == "doc_delete":
            await document_service.delete_document(
                session, doc_id=uuid.UUID(str(form.get("doc_id"))), actor_id=actor
            )
            return "Document deleted (file removed from storage).", preview_token
        if action == "doc_replace":
            got = await _read_upload(form.get("file"))
            if not got:
                raise ValueError("Choose a replacement file.")
            await document_service.replace_document_file(
                session,
                doc_id=uuid.UUID(str(form.get("doc_id"))),
                filename=got[0],
                data=got[1],
                actor_id=actor,
            )
            return "Document file replaced.", preview_token
        if action == "save_facts":
            new = listing_service.with_details(prop.content or {}, form)
            await listing_service.apply_content(session, prop=prop, new_content=new, section="details", actor_id=actor)
            return "Key facts saved.", preview_token
        if action == "save_developer":
            logo_url = None
            got = await _read_upload(form.get("logo"))
            if got:
                blob, ext, ctype = listing_media_service.process_image(got[1])
                from app.services.integrations import storage

                key = f"property-images/{prop.id}/developer-logo-{uuid.uuid4().hex}.{ext}"
                storage.save(key, blob, ctype)
                logo_url = storage.public_url(key)
            new = listing_service.with_developer(prop.content or {}, form, logo_url=logo_url)
            await listing_service.apply_content(session, prop=prop, new_content=new, section="developer", actor_id=actor)
            return "Developer saved.", preview_token
        if action == "save_spv":
            new = listing_service.with_spv(prop.content or {}, form)
            await listing_service.apply_content(session, prop=prop, new_content=new, section="spv", actor_id=actor)
            return "SPV details saved.", preview_token
        if action == "save_terms":
            new = listing_service.with_terms(prop.content or {}, form)
            await listing_service.apply_content(session, prop=prop, new_content=new, section="terms", actor_id=actor)
            return "Terms saved.", preview_token
        raise ValueError("Unknown action.")
