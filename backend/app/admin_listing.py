"""Listing Editor — one admin page per property (go-live audit, Step 2 + owner additions).

Everything the public property page can show is editable here, in plain-English groups,
without touching raw JSON: listing details (title, model, location, offering, returns),
gallery, documents, key facts & amenities, developer block, SPV & legal structure,
commercial terms & listing fees, construction timeline (expected completion + milestones),
plus publish / unpublish / delete and a 24-hour **preview link** for drafts.

All writes go through the audited services (listing_service, listing_media_service,
document_service, property_service); this module only renders forms and routes POST actions.
Every error shown to the user is a plain sentence — never a code or a traceback.
"""

# ruff: noqa: E501  (inline HTML/CSS template lines)
from __future__ import annotations

import html as _html
import logging
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
from app.services import (
    document_service,
    listing_media_service,
    listing_service,
    property_service,
)
from app.services.integrations import storage

log = logging.getLogger("capimax.admin.listing")

_env = Environment(autoescape=True)

_STYLE = """
 body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f4f5f3;margin:0;padding:24px;color:#23302a}
 .wrap{max-width:1080px;margin:0 auto}
 .top{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px}
 h1{font-size:22px;margin:0} h2{font-size:16px;margin:0 0 6px} h3{font-size:14px;margin:18px 0 6px;color:#0f6e4e;text-transform:uppercase;letter-spacing:.04em}
 .lead{color:#6b726c;font-size:13px;margin:0 0 8px}
 .badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:#e8e6e1}
 .badge.active{background:#e7f5ec;color:#0f6e4e} .badge.draft{background:#fff4dc;color:#8a5a00} .badge.closed{background:#fdeaea;color:#b00}
 .card{background:#fff;border:1px solid #e8e6e1;border-radius:14px;padding:20px 22px;margin-bottom:18px;box-shadow:0 6px 22px rgba(20,40,30,.05)}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
 .img{border:1px solid #e8e6e1;border-radius:10px;overflow:hidden;background:#fafaf8}
 .img img{width:100%;height:110px;object-fit:cover;display:block}
 .img .bar{display:flex;flex-wrap:wrap;gap:4px;padding:6px}
 .img.cover{outline:2px solid #198653}
 button,.btn{padding:7px 12px;border:1px solid #d9dcd8;border-radius:8px;background:#fff;font-size:13px;cursor:pointer;color:#23302a;text-decoration:none;display:inline-block}
 button.primary,.btn.primary{background:#198653;border-color:#198653;color:#fff;font-weight:600}
 button.danger,.btn.danger{color:#b00;border-color:#f2c2c2}
 button.mini{padding:3px 7px;font-size:12px}
 label{display:block;font-weight:600;font-size:13px;margin:10px 0 4px}
 .req{color:#b00;font-weight:700}
 .help{color:#6b726c;font-size:12px;margin-top:3px;line-height:1.4} .help .eg{color:#0f6e4e}
 input[type=text],input[type=number],input[type=date],input[type=file],select,textarea{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #d9dcd8;border-radius:8px;font-size:14px;background:#fff}
 textarea{min-height:90px}
 .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
 table{width:100%;border-collapse:collapse;font-size:14px} td,th{padding:8px 6px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}
 .ok{background:#e7f5ec;border:1px solid #b7e0c6;color:#0f6e4e;padding:10px 12px;border-radius:8px;margin-bottom:14px}
 .err{background:#fdeaea;border:1px solid #f2c2c2;color:#b00;padding:10px 12px;border-radius:8px;margin-bottom:14px}
 .note{background:#f7f7f4;border:1px solid #e8e6e1;padding:10px 12px;border-radius:8px;font-size:13px;margin:8px 0 12px}
 .muted{color:#6b726c;font-size:13px} code{background:#f0f0ec;padding:2px 5px;border-radius:5px;font-size:12px}
 .actions{display:flex;flex-wrap:wrap;gap:8px}
 .inline{display:inline}
 .ms{border:1px solid #e8e6e1;border-radius:10px;padding:10px 12px;margin-bottom:10px;background:#fafaf8}
 .ms .cols{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
 .ms label{margin-top:4px;font-size:12px}
"""

# One macro renders every listing field from its FieldSpec: label, required mark, the
# right input type, and help text with an example. Tests assert this for each field.
_FIELD_MACRO = """
{% macro field(f, val) -%}
<div class="f" data-field="{{ f.name }}">
 <label for="f_{{ f.name }}">{{ f.label }}{% if f.required %} <span class="req" title="Required">*</span>{% endif %}</label>
 {% if f.kind == 'textarea' -%}
  <textarea id="f_{{ f.name }}" name="{{ f.name }}" placeholder="{{ f.example }}" {{ 'required' if f.required }}>{{ val if val is not none else '' }}</textarea>
 {%- elif f.kind == 'select' -%}
  <select id="f_{{ f.name }}" name="{{ f.name }}" {{ 'required' if f.required }}>{% for v, l in f.options %}<option value="{{ v }}" {{ 'selected' if v == val }}>{{ l }}</option>{% endfor %}</select>
 {%- elif f.kind == 'date' -%}
  <input type="date" id="f_{{ f.name }}" name="{{ f.name }}" value="{{ val if val is not none else '' }}" placeholder="{{ f.example }}" {{ 'required' if f.required }}>
 {%- elif f.kind in ('money', 'percent', 'int') -%}
  <input type="number" id="f_{{ f.name }}" name="{{ f.name }}" min="0" {{ 'max=100' if f.kind == 'percent' }} step="{{ '1' if f.kind == 'int' else '0.01' }}" value="{{ val if val is not none else '' }}" placeholder="{{ f.example }}" {{ 'required' if f.required }}>
 {%- else -%}
  <input type="text" id="f_{{ f.name }}" name="{{ f.name }}" value="{{ val if val is not none else '' }}" placeholder="{{ f.example }}" maxlength="{{ f.max_len }}" {{ 'required' if f.required }}>
 {%- endif %}
 <div class="help">{{ f.help }}{% if f.example and f.kind != 'select' %} <span class="eg">Example: {{ f.example }}</span>{% endif %}</div>
</div>
{%- endmacro %}
"""

_CREATE_PAGE = _env.from_string(
    _FIELD_MACRO
    + """<!doctype html><html><head><meta charset="utf-8"><title>New listing</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """</style></head><body><div class="wrap">
<div class="top"><div><div class="muted"><a href="/admin/property/list">&larr; Properties</a></div><h1>New listing</h1>
<p class="lead">Fill the basics to create a <b>draft</b>. Nothing is visible to investors until you press Publish. Photos, documents, facts and the rest are added on the next screen. Fields marked <span class="req">*</span> are required.</p></div></div>
{% if message %}<div class="{{ 'err' if error else 'ok' }}">{{ message }}</div>{% endif %}
<form method="post" class="card">
{% for group, fields in groups %}<h3>{{ group }}</h3><div class="cols">{% for f in fields %}{{ field(f, values.get(f.name)) }}{% endfor %}</div>{% endfor %}
<div class="actions" style="margin-top:16px"><button class="primary" type="submit">Create draft listing</button><a class="btn" href="/admin/property/list">Cancel</a></div>
</form></div></body></html>"""
)

_PAGE = _env.from_string(
    _FIELD_MACRO
    + """<!doctype html><html><head><meta charset="utf-8">
<title>Listing Editor · {{ p.title }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>"""
    + _STYLE
    + """</style></head><body><div class="wrap">
<div class="top">
  <div>
    <div class="muted"><a href="/admin/property/list">&larr; Properties</a> · <a href="/admin/listing/new">+ New listing</a></div>
    <h1>{{ p.title }} <span class="badge {{ 'active' if p.status.value in ('active','funded') else ('closed' if p.status.value == 'closed' else 'draft') }}">{{ status_label }}</span></h1>
    <div class="muted">{{ model_label }} · {{ p.location }} · web address <code>/property/{{ p.slug or p.id }}</code></div>
  </div>
  <div class="actions">
    {% if full_admin %}<a class="btn" href="/admin/property/edit/{{ p.id }}" title="Raw database fields (technical)">Raw fields</a>{% endif %}
    {% if p.status.value in ('active','funded') %}
      <a class="btn" href="{{ public_url }}" target="_blank" rel="noopener">Open public page ↗</a>
      <form method="post" class="inline" onsubmit="return confirm('Unpublish this listing? Investors will no longer see it.')"><input type="hidden" name="action" value="unpublish"><button class="danger" type="submit">Unpublish</button></form>
    {% else %}
      <form method="post" class="inline"><input type="hidden" name="action" value="make_preview"><button type="submit">Preview link (24h)</button></form>
      <form method="post" class="inline" onsubmit="return confirm('Publish this listing? It becomes visible to investors immediately.')"><input type="hidden" name="action" value="publish"><button class="primary" type="submit">Publish</button></form>
    {% endif %}
  </div>
</div>
{% if message %}<div class="{{ 'err' if error else 'ok' }}">{{ message }}</div>{% endif %}
{% if preview_url %}<div class="ok">Preview link (valid 24 hours, shows the page exactly as investors will see it): <a href="{{ preview_url }}" target="_blank" rel="noopener">{{ preview_url }}</a></div>{% endif %}

<div class="card">
 <h2>Listing details</h2>
 <p class="lead">The core of the listing. Fields marked <span class="req">*</span> are required. Units, price and model lock automatically once an investor holds units.</p>
 <form method="post"><input type="hidden" name="action" value="save_core">
 {% for group, fields in core_groups %}<h3>{{ group }}</h3><div class="cols">{% for f in fields %}{{ field(f, core_values.get(f.name)) }}{% endfor %}</div>{% endfor %}
 <button class="primary" type="submit" style="margin-top:14px">Save listing details</button>
 </form>
</div>

<div class="card">
 <h2>Photos</h2>
 <p class="lead">The first photo is the cover on the marketplace and the property page. JPEG, PNG or WebP; phone photos are fine — they are resized to 2000px automatically.</p>
 {% if images %}
 <div class="grid">
  {% for url in images %}
  <div class="img {{ 'cover' if loop.first else '' }}">
    <img src="{{ url }}" alt="photo {{ loop.index }}">
    <div class="bar">
      {% if loop.first %}<span class="badge active">cover</span>{% else %}
      <form method="post" class="inline"><input type="hidden" name="action" value="image_cover"><input type="hidden" name="url" value="{{ url }}"><button class="mini" type="submit">Make cover</button></form>{% endif %}
      <form method="post" class="inline"><input type="hidden" name="action" value="image_up"><input type="hidden" name="url" value="{{ url }}"><button class="mini" type="submit" title="Move earlier" {{ 'disabled' if loop.first }}>&larr;</button></form>
      <form method="post" class="inline"><input type="hidden" name="action" value="image_down"><input type="hidden" name="url" value="{{ url }}"><button class="mini" type="submit" title="Move later" {{ 'disabled' if loop.last }}>&rarr;</button></form>
      <form method="post" class="inline" onsubmit="return confirm('Delete this photo?')"><input type="hidden" name="action" value="image_delete"><input type="hidden" name="url" value="{{ url }}"><button class="mini danger" type="submit">Delete</button></form>
    </div>
  </div>
  {% endfor %}
 </div>
 {% else %}<p class="muted">No photos yet — the public page shows a “Photos coming soon” placeholder until you add some.</p>{% endif %}
 <form method="post" enctype="multipart/form-data" style="margin-top:12px">
  <input type="hidden" name="action" value="upload_images">
  <div data-field="files"><label for="f_files">Add photos <span class="req">*</span></label>
  <input id="f_files" type="file" name="files" accept="image/jpeg,image/png,image/webp" multiple required>
  <div class="help">You can select several at once. Max {{ max_mb }} MB each. <span class="eg">Example: exterior, living room, bedroom, view.</span></div></div>
  <button class="primary" type="submit" style="margin-top:8px">Upload photos</button>
 </form>
</div>

<div class="card">
 <h2>Documents</h2>
 <p class="lead">Shown in the Documents tab and downloadable by anyone who can see the listing. PDF, Word, Excel, CSV, text or images · max {{ max_mb }} MB.</p>
 {% if docs %}
 <table><tr><th>Title</th><th>Category</th><th>Added</th><th></th></tr>
 {% for d in docs %}
 <tr>
  <td>{{ d.title }}</td><td>{{ cat_labels.get(d.type, d.type) }}</td><td>{{ d.created_at.strftime('%Y-%m-%d') }}</td>
  <td class="actions">
   <a class="btn mini" href="/api/v1/documents/{{ d.id }}/download{{ '?preview=' ~ preview_token if preview_token else '' }}" target="_blank" rel="noopener">Download</a>
   <form method="post" enctype="multipart/form-data" class="inline"><input type="hidden" name="action" value="doc_replace"><input type="hidden" name="doc_id" value="{{ d.id }}"><input type="file" name="file" required style="width:200px;display:inline-block;padding:3px" title="Choose the new file"><button class="mini" type="submit">Replace file</button></form>
   <form method="post" class="inline" onsubmit="return confirm('Delete this document and its file?')"><input type="hidden" name="action" value="doc_delete"><input type="hidden" name="doc_id" value="{{ d.id }}"><button class="mini danger" type="submit">Delete</button></form>
  </td>
 </tr>
 {% endfor %}
 </table>
 {% else %}<p class="muted">No documents yet.</p>{% endif %}
 <form method="post" enctype="multipart/form-data" style="margin-top:12px">
  <input type="hidden" name="action" value="upload_doc">
  <div class="cols">
   <div data-field="title"><label for="f_doc_title">Document title <span class="req">*</span></label><input id="f_doc_title" type="text" name="title" required maxlength="200" placeholder="Independent Valuation Report"><div class="help">What investors see in the list. <span class="eg">Example: Independent Valuation Report</span></div></div>
   <div data-field="doc_type"><label for="f_doc_type">Category <span class="req">*</span></label><select id="f_doc_type" name="doc_type">{% for v,l in categories %}<option value="{{ v }}">{{ l }}</option>{% endfor %}</select><div class="help">Groups the document on the page. <span class="eg">Example: Valuation Reports</span></div></div>
   <div data-field="file"><label for="f_doc_file">File <span class="req">*</span></label><input id="f_doc_file" type="file" name="file" required><div class="help">PDF is best. <span class="eg">Example: valuation-2026.pdf</span></div></div>
  </div>
  <button class="primary" type="submit" style="margin-top:8px">Upload document</button>
 </form>
</div>

<div class="card">
 <h2>Key facts &amp; amenities</h2>
 <p class="lead">Shown in the facts strip under the title and in the Overview tab. Leave a fact blank to hide it.</p>
 <form method="post"><input type="hidden" name="action" value="save_facts">
  <div class="cols">
   <div data-field="bedrooms"><label for="f_bedrooms">Bedrooms</label><input id="f_bedrooms" type="number" name="bedrooms" min="0" max="50" placeholder="2" value="{{ details.bedrooms if details.bedrooms is not none }}"><div class="help">Whole number. <span class="eg">Example: 2</span></div></div>
   <div data-field="bathrooms"><label for="f_bathrooms">Bathrooms</label><input id="f_bathrooms" type="number" name="bathrooms" min="0" max="50" placeholder="2" value="{{ details.bathrooms if details.bathrooms is not none }}"><div class="help">Whole number. <span class="eg">Example: 2</span></div></div>
   <div data-field="area"><label for="f_area">Area (sq ft)</label><input id="f_area" type="number" name="area" min="0" step="0.1" placeholder="1350" value="{{ details.area if details.area is not none }}"><div class="help">Built-up area in square feet. <span class="eg">Example: 1350</span></div></div>
   <div data-field="parking"><label for="f_parking">Parking spaces</label><input id="f_parking" type="number" name="parking" min="0" max="100" placeholder="1" value="{{ details.parking if details.parking is not none }}"><div class="help">Whole number. <span class="eg">Example: 1</span></div></div>
   <div data-field="max_investment"><label for="f_max_investment">Maximum investment per investor (USD)</label><input id="f_max_investment" type="number" name="max_investment" min="0" step="0.01" placeholder="250000" value="{{ details.maxInvestment if details.maxInvestment is not none }}"><div class="help">Caps the calculator. Blank = up to the full property value. <span class="eg">Example: 250000</span></div></div>
  </div>
  <div data-field="amenities"><label for="f_amenities">Amenities</label>
  <textarea id="f_amenities" name="amenities" placeholder="Sea view&#10;Gym&#10;Pool&#10;24-hour security">{{ amenities_text }}</textarea>
  <div class="help">One per line (or comma-separated), up to 40. Shown as a tick list. <span class="eg">Example: Sea view, Gym, Pool, 24-hour security</span></div></div>
  <button class="primary" type="submit" style="margin-top:8px">Save facts</button>
 </form>
</div>

<div class="card">
 <h2>Developer</h2>
 <p class="lead">The developer card in the Overview tab. Shown only when a name is set; rating and projects appear only when filled.</p>
 <form method="post" enctype="multipart/form-data"><input type="hidden" name="action" value="save_developer">
  <div class="cols">
   <div data-field="name"><label for="f_dev_name">Developer name</label><input id="f_dev_name" type="text" name="name" maxlength="120" value="{{ developer.name or '' }}" placeholder="Emaar Properties"><div class="help">Company name as investors know it. <span class="eg">Example: Emaar Properties</span></div></div>
   <div data-field="rating"><label for="f_dev_rating">Rating (0–5)</label><input id="f_dev_rating" type="number" name="rating" min="0" max="5" step="0.1" placeholder="4.6" value="{{ developer.rating if developer.rating is not none }}"><div class="help">Your own assessment; blank hides it. <span class="eg">Example: 4.6</span></div></div>
   <div data-field="projects_completed"><label for="f_dev_projects">Projects completed</label><input id="f_dev_projects" type="number" name="projects_completed" min="0" placeholder="120" value="{{ developer.projectsCompleted if developer.projectsCompleted is not none }}"><div class="help">Whole number; blank hides it. <span class="eg">Example: 120</span></div></div>
   <div data-field="logo"><label for="f_dev_logo">Logo</label><input id="f_dev_logo" type="file" name="logo" accept="image/jpeg,image/png,image/webp">
     <div class="help">Square image looks best; blank keeps the current logo or shows the initial letter. <span class="eg">Example: emaar-logo.png</span></div>
     {% if developer.logo %}<div class="muted" style="margin-top:4px"><img src="{{ developer.logo }}" alt="logo" style="height:32px;vertical-align:middle;border-radius:6px"> <label class="inline" style="font-weight:400"><input type="checkbox" name="clear_logo" value="1"> remove logo</label></div>{% endif %}
   </div>
  </div>
  <button class="primary" type="submit" style="margin-top:8px">Save developer</button>
 </form>
</div>

<div class="card">
 <h2>SPV &amp; legal structure</h2>
 <p class="lead">The SPV Structure tab. Rows are shown only when filled.</p>
 <form method="post"><input type="hidden" name="action" value="save_spv">
  <div class="cols">{% for f in spv_fields %}{{ field(f, core_values.get(f.name)) }}{% endfor %}
   <div data-field="jurisdiction"><label for="f_jurisdiction">Jurisdiction</label><input id="f_jurisdiction" type="text" name="jurisdiction" maxlength="200" value="{{ spv.jurisdiction or '' }}" placeholder="DIFC, Dubai"><div class="help">Where the SPV is registered. <span class="eg">Example: DIFC, Dubai</span></div></div>
   <div data-field="trustee"><label for="f_trustee">Trustee</label><input id="f_trustee" type="text" name="trustee" maxlength="200" value="{{ spv.trustee or '' }}" placeholder="Gulf Corporate Trustees LLC"><div class="help">Blank hides the row. <span class="eg">Example: Gulf Corporate Trustees LLC</span></div></div>
   <div data-field="auditor"><label for="f_auditor">Auditor</label><input id="f_auditor" type="text" name="auditor" maxlength="200" value="{{ spv.auditor or '' }}" placeholder="KPMG Lower Gulf"><div class="help">Blank hides the row. <span class="eg">Example: KPMG Lower Gulf</span></div></div>
  </div>
  <button class="primary" type="submit" style="margin-top:8px">Save SPV &amp; legal</button>
 </form>
</div>

<div class="card">
 <h2>Terms &amp; listing fees</h2>
 <p class="lead">The Financials tab. Leave a field blank to hide its row. Platform, management and installment rates are global settings, not per listing.</p>
 <form method="post"><input type="hidden" name="action" value="save_terms">
  <div class="cols">
   <div data-field="distribution_frequency"><label for="f_dist">Distribution frequency</label><input id="f_dist" type="text" name="distribution_frequency" maxlength="160" value="{{ terms.distributionFrequency or '' }}" placeholder="Monthly"><div class="help">How often rental income is paid out. <span class="eg">Example: Monthly</span></div></div>
   <div data-field="investment_term"><label for="f_term">Investment period</label><input id="f_term" type="text" name="investment_term" maxlength="160" value="{{ terms.investmentTerm or '' }}" placeholder="5 years"><div class="help">Planned holding period. <span class="eg">Example: 5 years</span></div></div>
   <div data-field="exit_options"><label for="f_exit">Exit terms</label><input id="f_exit" type="text" name="exit_options" maxlength="160" value="{{ terms.exitOptions or '' }}" placeholder="Secondary market · Liquidity provider"><div class="help">How an investor can sell. <span class="eg">Example: Secondary market · Liquidity provider</span></div></div>
   <div data-field="performance_fee"><label for="f_perf">Performance fee (%)</label><input id="f_perf" type="number" name="performance_fee" min="0" max="100" step="0.1" placeholder="10" value="{{ fees.performance if fees.performance is not none }}"><div class="help">Share of profit above target, if any. <span class="eg">Example: 10</span></div></div>
   <div data-field="exit_fee"><label for="f_exitfee">Exit fee (%)</label><input id="f_exitfee" type="number" name="exit_fee" min="0" max="100" step="0.1" placeholder="2" value="{{ fees.exit if fees.exit is not none }}"><div class="help">Charged on the sale proceeds, if any. <span class="eg">Example: 2</span></div></div>
  </div>
  <button class="primary" type="submit" style="margin-top:8px">Save terms</button>
 </form>
</div>

<div class="card">
 <h2>Construction &amp; timeline</h2>
 <p class="lead">The Timeline tab (under-construction models only: future, option, shared development, installment, off-plan portfolio). Ready-income listings do not show it.</p>
 <form method="post"><input type="hidden" name="action" value="save_construction">
  <div class="cols">{% for f in construction_fields %}{{ field(f, core_values.get(f.name)) }}{% endfor %}</div>
  <button class="primary" type="submit" style="margin-top:8px">Save completion date</button>
 </form>
 <div class="note"><b>Construction progress shown to investors: {{ construction_progress }}%.</b> It is taken from the milestone marked <i>In progress</i> (its Progress %). Mark finished milestones <i>Completed</i>, the current one <i>In progress</i> with its percentage, and the rest <i>Planned</i>.</div>
 {% if milestones %}
  {% for m in milestones %}
  <form method="post" class="ms">
   <input type="hidden" name="ms_id" value="{{ m.id }}">
   <div class="cols">
    <div data-field="ms_title"><label for="ms_title_{{ loop.index }}">{{ loop.index }}. Milestone title <span class="req">*</span></label><input id="ms_title_{{ loop.index }}" type="text" name="title" maxlength="120" required value="{{ m.title }}" placeholder="Foundation complete"><div class="help"><span class="eg">Example: Foundation complete</span></div></div>
    <div data-field="ms_status"><label for="ms_status_{{ loop.index }}">Status</label><select id="ms_status_{{ loop.index }}" name="status">{% for v,l in ms_statuses %}<option value="{{ v }}" {{ 'selected' if v == m.status.value }}>{{ l }}</option>{% endfor %}</select><div class="help">Planned → In progress → Completed.</div></div>
    <div data-field="ms_progress"><label for="ms_prog_{{ loop.index }}">Progress %</label><input id="ms_prog_{{ loop.index }}" type="number" name="progress_pct" min="0" max="100" placeholder="40" value="{{ m.progress_pct if m.progress_pct is not none }}"><div class="help">Only matters for the In-progress one. <span class="eg">Example: 40</span></div></div>
    <div data-field="ms_date"><label for="ms_date_{{ loop.index }}">Target date</label><input id="ms_date_{{ loop.index }}" type="date" name="target_date" value="{{ m.target_date.isoformat() if m.target_date else '' }}"><div class="help"><span class="eg">Example: 2027-03-31</span></div></div>
   </div>
   <div data-field="ms_description"><label for="ms_desc_{{ loop.index }}">Description</label><input id="ms_desc_{{ loop.index }}" type="text" name="description" maxlength="500" value="{{ m.description or '' }}" placeholder="Piling and raft foundation signed off by the engineer"><div class="help">One sentence, optional. <span class="eg">Example: Piling and raft foundation signed off by the engineer</span></div></div>
   <div class="actions" style="margin-top:8px">
    <button class="mini primary" type="submit" name="action" value="ms_save">Save</button>
    <button class="mini" type="submit" name="action" value="ms_up" title="Move up" {{ 'disabled' if loop.first }}>&uarr;</button>
    <button class="mini" type="submit" name="action" value="ms_down" title="Move down" {{ 'disabled' if loop.last }}>&darr;</button>
    <button class="mini danger" type="submit" name="action" value="ms_delete" onclick="return confirm('Delete this milestone?')">Delete</button>
   </div>
  </form>
  {% endfor %}
 {% else %}<p class="muted">No milestones yet — the Timeline tab says “No project milestones have been published yet.”</p>{% endif %}
 <form method="post" class="ms" style="border-style:dashed">
  <input type="hidden" name="action" value="ms_add">
  <b>Add a milestone</b>
  <div class="cols">
   <div data-field="ms_title"><label for="ms_new_title">Milestone title <span class="req">*</span></label><input id="ms_new_title" type="text" name="title" maxlength="120" required placeholder="Structure complete"><div class="help"><span class="eg">Example: Structure complete</span></div></div>
   <div data-field="ms_status"><label for="ms_new_status">Status</label><select id="ms_new_status" name="status">{% for v,l in ms_statuses %}<option value="{{ v }}">{{ l }}</option>{% endfor %}</select><div class="help">Planned → In progress → Completed.</div></div>
   <div data-field="ms_progress"><label for="ms_new_prog">Progress %</label><input id="ms_new_prog" type="number" name="progress_pct" min="0" max="100" placeholder="0"><div class="help"><span class="eg">Example: 40</span></div></div>
   <div data-field="ms_date"><label for="ms_new_date">Target date</label><input id="ms_new_date" type="date" name="target_date"><div class="help"><span class="eg">Example: 2027-03-31</span></div></div>
  </div>
  <div data-field="ms_description"><label for="ms_new_desc">Description</label><input id="ms_new_desc" type="text" name="description" maxlength="500" placeholder="Concrete frame to roof level"><div class="help">One sentence, optional. <span class="eg">Example: Concrete frame to roof level</span></div></div>
  <button class="primary" type="submit" style="margin-top:8px">Add milestone</button>
 </form>
</div>

<div class="card" style="border-color:#f2c2c2">
 <h2>Delete listing</h2>
 <p class="lead">Removes the listing, its photos, documents and milestones permanently. Not possible once investors hold units — unpublish instead.</p>
 <form method="post" onsubmit="return confirm('Delete this listing and all its files? This cannot be undone.')"><input type="hidden" name="action" value="delete_listing"><button class="danger" type="submit">Delete this listing</button></form>
</div>
</div></body></html>"""
)

_INDEX_PAGE = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8"><title>Listings</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """</style></head><body><div class="wrap">
<div class="top"><div><div class="muted">{% if full_admin %}<a href="/admin/">&larr; Admin home</a>{% endif %}</div><h1>Listings</h1>
<p class="lead">Every property on the platform. Open one to edit photos, documents, facts, milestones — or create a new draft.</p></div>
<div class="actions"><a class="btn primary" href="/admin/listing/new">+ New listing</a></div></div>
<div class="card">
{% if rows %}<table><tr><th>Title</th><th>Model</th><th>Status</th><th>Location</th><th>Updated</th><th></th></tr>
{% for p in rows %}<tr>
 <td><a href="/admin/listing/{{ p.id }}">{{ p.title }}</a></td>
 <td class="muted">{{ model_labels.get(p.model, p.model) }}</td>
 <td><span class="badge {{ 'active' if p.status.value in ('active','funded') else ('closed' if p.status.value == 'closed' else 'draft') }}">{{ status_labels.get(p.status.value, p.status.value) }}</span></td>
 <td class="muted">{{ p.location }}</td>
 <td class="muted">{{ p.updated_at.strftime('%Y-%m-%d') if p.updated_at else '' }}</td>
 <td><a class="btn mini" href="/admin/listing/{{ p.id }}">Edit</a></td>
</tr>{% endfor %}</table>
{% else %}<p class="muted">No listings yet. Press “+ New listing” to create the first draft.</p>{% endif %}
</div></div></body></html>"""
)

_STATUS_LABELS = {
    "draft": "Draft — not visible",
    "under_review": "Under review",
    "active": "Published",
    "funded": "Fully funded",
    "closed": "Unpublished (closed)",
}

_GENERIC_ERROR = (
    "Something went wrong and nothing was saved. Please try again; if it keeps happening, "
    "tell support this reference: {ref}"
)


def _actor(request: Request) -> uuid.UUID | None:
    actor = request.session.get("admin_id")
    return uuid.UUID(actor) if actor else None


LISTING_ROLES = frozenset({"admin", "content_editor"})


def _roles(request: Request) -> list[str] | None:
    return request.session.get("admin_roles")


def is_full_admin(request: Request) -> bool:
    """Full admins see everything. Content editors (Step 3) only reach the Listing Editor.
    A session without a roles list predates Step 3 — only admins could log in then."""
    roles = _roles(request)
    return roles is None or "admin" in roles


def can_edit_listings(request: Request) -> bool:
    if not request.session.get("admin_id"):
        return False
    roles = _roles(request)
    return roles is None or bool(LISTING_ROLES & set(roles))


async def _read_upload(upload) -> tuple[str, bytes] | None:
    if upload is None or not hasattr(upload, "read"):
        return None
    data = await upload.read()
    if not data:
        return None
    return (getattr(upload, "filename", "file") or "file", data)


def _core_values(prop: Property) -> dict:
    out = {}
    for f in listing_service.CORE_FIELDS:
        v = getattr(prop, f.name, None)
        if f.kind == "date" and v is not None:
            v = v.isoformat()
        elif f.kind in ("money", "percent") and v is not None:
            v = f"{v:f}".rstrip("0").rstrip(".") if "." in f"{v:f}" else f"{v:f}"
        out[f.name] = v
    return out


def _groups(names: tuple[str, ...]) -> list[tuple[str, list]]:
    return [(g, listing_service.fields_in(g)) for g in names]


def _friendly(exc: Exception) -> str:
    """Never leak codes or tracebacks: AppError/ValueError carry a sentence; anything else
    is logged and replaced by a generic message with a support reference."""
    if isinstance(exc, AppError):
        return exc.message
    if isinstance(exc, ValueError):
        return str(exc)
    ref = uuid.uuid4().hex[:8]
    log.exception("listing editor failure ref=%s", ref)
    return _GENERIC_ERROR.format(ref=ref)


class ListingEditorView(BaseView):
    name = "Listings"
    icon = "fa-solid fa-pen-ruler"

    def is_accessible(self, request: Request) -> bool:
        return can_edit_listings(request)

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)

    @staticmethod
    def _gate(request: Request):
        """Redirect anonymous visitors to login; refuse sessions without a listing role."""
        if not request.session.get("admin_id"):
            return RedirectResponse("/admin/login", status_code=302)
        if not can_edit_listings(request):
            return HTMLResponse("Forbidden", status_code=403)
        return None

    # ------------------------------------------------------------------- index #
    @expose("/listing/", methods=["GET"])
    async def index(self, request: Request):
        if (resp := self._gate(request)) is not None:
            return resp
        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        select(Property).order_by(Property.updated_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            html = _INDEX_PAGE.render(
                rows=rows,
                status_labels=_STATUS_LABELS,
                model_labels=listing_service.MODEL_LABELS,
                full_admin=is_full_admin(request),
            )
        return HTMLResponse(html)

    # ------------------------------------------------------------------ create #
    @expose("/listing/new", methods=["GET", "POST"])
    async def create(self, request: Request):
        if (resp := self._gate(request)) is not None:
            return resp
        names = [f.name for f in listing_service.fields_in(*listing_service.CORE_FORM_GROUPS)]
        values: dict = {"model": "ready-income", "property_type": "apartment"}
        message, error = "", False
        if request.method == "POST":
            form = await request.form()
            values = {n: form.get(n) for n in names}
            try:
                data = listing_service.parse_core(form, names)
                async with session_scope() as session:
                    prop = await listing_service.create_listing(
                        session, data=data, actor_id=_actor(request)
                    )
                    new_id = prop.id
                return RedirectResponse(f"/admin/listing/{new_id}?created=1", status_code=303)
            except Exception as exc:  # noqa: BLE001 — every error becomes a sentence
                message, error = _friendly(exc), True
        html = _CREATE_PAGE.render(
            groups=_groups(listing_service.CORE_FORM_GROUPS),
            values=values,
            message=message,
            error=error,
        )
        return HTMLResponse(html, status_code=400 if error else 200)

    # ------------------------------------------------------------------ editor #
    @expose("/listing/{prop_id}", methods=["GET", "POST"])
    async def editor(self, request: Request):
        if (resp := self._gate(request)) is not None:
            return resp
        if request.path_params["prop_id"] == "new":  # route order: {prop_id} shadows /new
            return await self.create(request)
        try:
            prop_id = uuid.UUID(request.path_params["prop_id"])
        except ValueError:
            return HTMLResponse("Invalid property id", status_code=404)

        message, error, preview_url, preview_token = "", False, "", ""
        if request.query_params.get("created"):
            message = (
                "Draft created. Add photos, documents and details below, then Preview and Publish."
            )
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action") or "")
            cleanup: list[str] = []
            try:
                async with session_scope() as session:
                    prop = await session.get(Property, prop_id)
                    if prop is None:
                        return HTMLResponse("Property not found", status_code=404)
                    if action == "delete_listing":
                        cleanup = await listing_service.delete_listing(
                            session, prop=prop, actor_id=_actor(request)
                        )
                    else:
                        message, preview_token = await self._handle(
                            session, request, prop, action, form
                        )
            except Exception as exc:  # noqa: BLE001 — every error becomes a sentence
                message, error = _friendly(exc), True
            if action == "delete_listing" and not error:
                for key in cleanup:
                    try:
                        storage.delete(key)
                    except Exception:  # noqa: BLE001 — best effort, row already gone
                        log.warning("could not delete file %s", key)
                return RedirectResponse("/admin/property/list", status_code=303)

        async with session_scope() as session:
            prop = await session.get(Property, prop_id)
            if prop is None:
                return HTMLResponse("Property not found", status_code=404)
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
            milestones = await listing_service.list_milestones(session, prop.id)
            content = dict(prop.content or {})
            base = get_settings().app_base_url.rstrip("/")
            ref = prop.slug or str(prop.id)
            if preview_token:
                preview_url = f"{base}/property/{ref}?preview={preview_token}"
            html = _PAGE.render(
                p=prop,
                status_label=_STATUS_LABELS.get(prop.status.value, prop.status.value),
                model_label=listing_service.MODEL_LABELS.get(prop.model, prop.model),
                full_admin=is_full_admin(request),
                core_groups=_groups(listing_service.CORE_FORM_GROUPS),
                spv_fields=listing_service.fields_in(listing_service.GROUP_SPV),
                construction_fields=listing_service.fields_in(listing_service.GROUP_CONSTRUCTION),
                core_values=_core_values(prop),
                images=list(prop.images or []),
                docs=docs,
                details=content.get("details") or {},
                amenities_text="\n".join((content.get("details") or {}).get("amenities") or []),
                developer=content.get("developer") or {},
                spv=content.get("spv") or {},
                terms=content.get("terms") or {},
                fees=content.get("fees") or {},
                milestones=milestones,
                construction_progress=listing_service.construction_progress(milestones),
                ms_statuses=list(listing_service.MILESTONE_STATUS_LABELS.items()),
                categories=document_service.DOC_CATEGORIES,
                cat_labels=dict(document_service.DOC_CATEGORIES),
                max_mb=get_settings().storage_max_upload_mb,
                public_url=f"{base}/property/{ref}",
                preview_url=preview_url,
                preview_token=preview_token,
                message=message,
                error=error,
            )
        return HTMLResponse(html, status_code=400 if error else 200)

    async def _handle(self, session, request: Request, prop: Property, action: str, form):
        actor = _actor(request)
        preview_token = ""
        # --- status ----------------------------------------------------------------- #
        if action == "make_preview":
            preview_token = property_service.make_preview_token(prop.id)
            return "Preview link created — it works for 24 hours.", preview_token
        if action == "publish":
            await property_service.admin_moderate(
                session, actor_id=actor, prop_id=prop.id, action="approve"
            )
            return "Published — investors can now see this listing.", preview_token
        if action == "unpublish":
            await property_service.admin_moderate(
                session, actor_id=actor, prop_id=prop.id, action="close"
            )
            return "Unpublished — the listing is hidden from investors.", preview_token
        # --- core columns ----------------------------------------------------------- #
        if action in ("save_core", "save_construction"):
            groups = (
                listing_service.CORE_FORM_GROUPS
                if action == "save_core"
                else (listing_service.GROUP_CONSTRUCTION,)
            )
            names = [f.name for f in listing_service.fields_in(*groups)]
            data = listing_service.parse_core(form, names)
            changed = await listing_service.update_core(
                session, prop=prop, data=data, actor_id=actor
            )
            if not changed:
                return "No changes to save.", preview_token
            return (
                "Listing details saved." if action == "save_core" else "Completion date saved."
            ), preview_token
        # --- gallery ---------------------------------------------------------------- #
        if action == "upload_images":
            files = []
            for up in form.getlist("files"):
                got = await _read_upload(up)
                if got:
                    files.append(got)
            if not files:
                raise ValueError("Choose at least one photo to upload.")
            await listing_media_service.add_images(session, prop=prop, files=files, actor_id=actor)
            return f"Added {len(files)} photo(s).", preview_token
        url = str(form.get("url") or "")
        if action == "image_delete":
            await listing_media_service.remove_image(session, prop=prop, url=url, actor_id=actor)
            return "Photo deleted.", preview_token
        if action == "image_cover":
            await listing_media_service.set_cover(session, prop=prop, url=url, actor_id=actor)
            return "Cover photo updated.", preview_token
        if action in ("image_up", "image_down"):
            order = listing_media_service.moved(
                list(prop.images or []), url, -1 if action == "image_up" else 1
            )
            await listing_media_service.reorder_images(
                session, prop=prop, order=order, actor_id=actor
            )
            return "Photo order updated.", preview_token
        # --- documents -------------------------------------------------------------- #
        if action == "upload_doc":
            got = await _read_upload(form.get("file"))
            if not got:
                raise ValueError("Choose a file to upload.")
            title = str(form.get("title") or "").strip()
            if not title:
                raise ValueError(
                    "Document title: this field is required. Example: Independent Valuation Report."
                )
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
                session, doc_id=_uuid(form.get("doc_id")), actor_id=actor
            )
            return "Document deleted (file removed from storage).", preview_token
        if action == "doc_replace":
            got = await _read_upload(form.get("file"))
            if not got:
                raise ValueError("Choose the replacement file.")
            await document_service.replace_document_file(
                session,
                doc_id=_uuid(form.get("doc_id")),
                filename=got[0],
                data=got[1],
                actor_id=actor,
            )
            return "Document file replaced.", preview_token
        # --- structured content ----------------------------------------------------- #
        if action == "save_facts":
            new = listing_service.with_details(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="details", actor_id=actor
            )
            return "Key facts saved.", preview_token
        if action == "save_developer":
            logo_url = None
            got = await _read_upload(form.get("logo"))
            if got:
                blob, ext, ctype = listing_media_service.process_image(got[1])
                key = f"property-images/{prop.id}/developer-logo-{uuid.uuid4().hex}.{ext}"
                storage.save(key, blob, ctype)
                logo_url = storage.public_url(key)
            new = listing_service.with_developer(prop.content or {}, form, logo_url=logo_url)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="developer", actor_id=actor
            )
            return "Developer saved.", preview_token
        if action == "save_spv":
            names = [f.name for f in listing_service.fields_in(listing_service.GROUP_SPV)]
            data = listing_service.parse_core(form, names)
            await listing_service.update_core(session, prop=prop, data=data, actor_id=actor)
            new = listing_service.with_spv(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="spv", actor_id=actor
            )
            return "SPV & legal structure saved.", preview_token
        if action == "save_terms":
            new = listing_service.with_terms(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="terms", actor_id=actor
            )
            return "Terms saved.", preview_token
        # --- milestones ------------------------------------------------------------- #
        if action == "ms_add":
            data = listing_service.parse_milestone(form)
            await listing_service.add_milestone(session, prop=prop, data=data, actor_id=actor)
            return "Milestone added.", preview_token
        ms_id = str(form.get("ms_id") or "")
        if action == "ms_save":
            data = listing_service.parse_milestone(form)
            await listing_service.update_milestone(
                session, prop=prop, milestone_id=ms_id, data=data, actor_id=actor
            )
            return "Milestone saved.", preview_token
        if action == "ms_delete":
            await listing_service.delete_milestone(
                session, prop=prop, milestone_id=ms_id, actor_id=actor
            )
            return "Milestone deleted.", preview_token
        if action in ("ms_up", "ms_down"):
            await listing_service.move_milestone(
                session,
                prop=prop,
                milestone_id=ms_id,
                delta=-1 if action == "ms_up" else 1,
                actor_id=actor,
            )
            return "Milestone order updated.", preview_token
        raise ValueError("That action is not recognised. Please reload the page and try again.")


def _uuid(raw) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except ValueError as exc:
        raise ValueError("That item no longer exists. Please reload the page.") from exc
