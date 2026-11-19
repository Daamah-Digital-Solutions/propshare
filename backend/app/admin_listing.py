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

import copy
import datetime as dt
import decimal
import html as _html
import logging
import uuid

from jinja2 import Environment
from sqladmin import BaseView, expose
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.errors import AppError
from app.models import Document, Property
from app.models.base import PropertyStatus
from app.services import (
    developer_service,
    document_service,
    listing_media_service,
    listing_service,
    listing_translation,
    listing_translation_form,
    price_service,
    property_service,
    valuation_service,
)
from app.services.integrations import storage
from app.services.property_service import developer_slug

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
 textarea{min-height:90px;font-family:inherit;line-height:1.55;resize:vertical}
 .cols>.f.wide{grid-column:1/-1}
 table.rowed{margin:4px 0 6px} table.rowed td{padding:3px 4px;vertical-align:middle} table.rowed th{font-size:12px;padding:4px}
 table.rowed input,table.rowed select{padding:6px 8px;font-size:13px} td.rowact{white-space:nowrap;width:1%}
 .drop{display:block;border:2px dashed #c9d3cc;border-radius:12px;padding:18px;text-align:center;cursor:pointer;background:#fafcfa;font-weight:400;font-size:14px}
 .drop.over{border-color:#198653;background:#eef8f1}
 .drop span{display:block;margin-top:4px}
 .drop input[type=file]{margin-top:10px;max-width:420px}
 .pendwrap{overflow-x:auto;margin-top:10px} table.pending input,table.pending select{padding:6px 8px;font-size:13px;min-width:90px}
 table.pending .thumb{display:block;height:34px;width:34px;object-fit:cover;border-radius:6px;margin-bottom:4px}
 table.pending .state{font-size:11px;color:#6b726c;margin-top:2px;word-break:normal} table.pending .state.st-ok{color:#0f6e4e} table.pending .state.st-bad{color:#b00}
 table.pending td.fname{min-width:150px} table.pending input[name=title]{min-width:170px}
 table.pending td{vertical-align:middle} table.pending td.fname{font-size:12px;color:#6b726c;max-width:160px;word-break:break-all}
 details.edit{display:inline-block} details.edit summary{list-style:none} details.edit[open] form{display:block;margin-top:6px;padding:10px;border:1px solid #e8e6e1;border-radius:8px;background:#fafaf8;min-width:240px}
 details.edit label{margin:6px 0 2px;font-size:12px}
 textarea.long{min-height:340px;max-height:75vh;font-size:15px;padding:12px 14px}
 .longbar{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:4px;font-size:12px;color:#6b726c}
 textarea.long.full{position:fixed;top:58px;left:16px;right:16px;bottom:16px;z-index:1000;max-height:none;min-height:0;height:auto!important;font-size:16px;line-height:1.75;padding:20px 26px;box-shadow:0 10px 40px rgba(0,0,0,.25);resize:none}
 body.editing-full::before{content:"";position:fixed;inset:0;background:rgba(20,30,25,.5);z-index:999}
 .longbar button.floating{position:fixed;top:14px;right:16px;z-index:1001;font-size:14px;padding:8px 14px}
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
 .explain{background:#eef6f1;border:1px solid #cfe6d8;color:#0f5b39;padding:8px 12px;border-radius:8px;font-size:13px;margin:6px 0 4px}
 .warn{background:#fff7e6;border:1px solid #f1d49a;color:#7a5200;padding:10px 12px;border-radius:8px;margin-bottom:14px}
 .calc{font-size:12px;margin-top:3px;color:#0f5b39} .calc.bad{color:#b00}
 .checklist ul{margin:6px 0 10px 18px;padding:0} .checklist li{margin:3px 0;font-size:13px}
 .err,.ok,.warn{white-space:pre-line}
 [hidden]{display:none!important}
 details.tr{border:1px solid #e8e6e1;border-radius:10px;padding:10px 12px;margin-top:10px;background:#fafaf8}
 details.tr summary{cursor:pointer;font-size:15px}
 details.tr .f{margin-bottom:10px}
 details.tr .english{white-space:pre-line;direction:ltr;text-align:left}
"""

# One macro renders every listing field from its FieldSpec: label, required mark, the
# right input type, and help text with an example. Tests assert this for each field.
_FIELD_MACRO = """
{% macro field(f, val, profile, model_locked=False) -%}
{%- set shown = f.shown(profile) -%}
{%- set req = f.is_required(profile) and not f.computed -%}
<div class="f{{ ' wide' if f.kind == 'textarea' }}" data-field="{{ f.name }}"{% if not shown %} hidden{% endif %}>
 <label for="f_{{ f.name }}"><span class="txt">{{ f.label_for(profile) }}</span>{% if req %}<span class="req" title="Required"> *</span>{% endif %}</label>
 {% if f.name == 'model' and model_locked -%}
  <input type="hidden" name="model" value="{{ val }}">
  <input type="text" id="f_model" value="{{ model_labels.get(val, val) }}" readonly>
 {%- elif f.computed -%}
  <input type="text" id="f_{{ f.name }}" value="{{ val if val is not none else '' }}" readonly tabindex="-1" style="background:#f4f5f3">
 {%- elif f.kind == 'textarea' -%}
  <textarea class="long" id="f_{{ f.name }}" name="{{ f.name }}" placeholder="{{ f.example }}" {{ 'required' if req and shown }} {{ 'disabled' if not shown }}>{{ val if val is not none else '' }}</textarea>
 {%- elif f.kind == 'select' -%}
  <select id="f_{{ f.name }}" name="{{ f.name }}" {{ 'required' if req and shown }} {{ 'disabled' if not shown }}>{% if f.name == 'model' and val not in f.options|map('first')|list %}<option value="" selected>Choose an available model</option>{% endif %}{% for v, l in f.options %}<option value="{{ v }}" {{ 'selected' if v == val }}>{{ l }}</option>{% endfor %}</select>
 {%- elif f.kind == 'date' -%}
  <input type="date" id="f_{{ f.name }}" name="{{ f.name }}" value="{{ val if val is not none else '' }}" placeholder="{{ f.example }}" {{ 'required' if req and shown }} {{ 'disabled' if not shown }}>
 {%- elif f.kind in ('money', 'percent', 'int') -%}
  <input type="number" id="f_{{ f.name }}" name="{{ f.name }}" min="0" {{ 'max=100' if f.kind == 'percent' }} step="{{ '1' if f.kind == 'int' else '0.01' }}" value="{{ val if val is not none else '' }}" placeholder="{{ f.example }}" {{ 'required' if req and shown }} {{ 'disabled' if not shown }}>
 {%- else -%}
  <input type="text" id="f_{{ f.name }}" name="{{ f.name }}" value="{{ val if val is not none else '' }}" placeholder="{{ f.example }}" maxlength="{{ f.max_len }}" {{ 'required' if req and shown }} {{ 'disabled' if not shown }}>
 {%- endif %}
 <div class="help"><span class="txt">{{ f.help_for(profile) }}</span>{% if f.example and f.kind != 'select' and not f.computed %} <span class="eg">Example: {{ f.example }}</span>{% endif %}</div>
 {% if f.name == 'model' %}<div class="explain" data-explain>{{ model_explain.get(val, '') }}</div>{% if model_locked %}<div class="warn">This listing uses an ownership model that is no longer offered. Investors already hold units, so the model stays as it is.</div>{% endif %}{% endif %}
 {% if f.name in ('total_units', 'minimum_investment', 'total_return') %}<div class="calc" data-calc="{{ f.name }}"></div>{% endif %}
</div>
{%- endmacro %}

{% macro installment_notice(terms, profile) -%}
<div class="note" data-profiles="offplan_single offplan_portfolio"{% if profile not in ('offplan_single', 'offplan_portfolio') %} hidden{% endif %}>
 <b>Standard installment plan (same for every off-plan listing).</b> Custom terms per property are not available yet.
 Investors lock today's unit price and choose {% for t in terms.plans %}{{ t.months }}{{ ', ' if not loop.last else '' }}{% endfor %} months,
 with a down payment of {% for t in terms.plans %}{{ t.down }}%{{ ', ' if not loop.last else '' }}{% endfor %} respectively.
 An installment fee of {{ terms.fee }}% applies to the down payment and to each installment. Units vest as payments are made.
 A missed payment gets reminders, with no late fee and no automatic forfeit.
</div>
{%- endmacro %}

{% macro adapt_script(rules, offering_locked=False) -%}
<script id="listing-rules" type="application/json">{{ rules|tojson }}</script>
<script>
(function () {
  var R = JSON.parse(document.getElementById("listing-rules").textContent);
  var LOCKED = {{ 'true' if offering_locked else 'false' }};
  var sel = document.querySelector("select[name=model]") || document.querySelector("input[name=model]");
  if (!sel) return;
  function num(name) { var e = document.getElementById("f_" + name); if (!e || e.value === "") return null; var v = Number(e.value); return isNaN(v) ? null : v; }
  function usd(v) { return "$" + v.toLocaleString("en-US", { maximumFractionDigits: 2 }); }
  function say(name, text, bad) { var e = document.querySelector('[data-calc="' + name + '"]'); if (e) { e.textContent = text || ""; e.className = "calc" + (bad ? " bad" : ""); } }
  function calc() {
    var tv = num("total_value"), up = num("unit_price"), mn = num("minimum_investment");
    var units = document.getElementById("f_total_units");
    if (LOCKED) { say("total_units", "Fixed: investors hold units. A new price is recorded under Unit price (top of this page).", false); }
    else if (tv !== null && up) {
      var u = tv / up;
      if (Number.isInteger(u)) { if (units) units.value = u; say("total_units", usd(tv) + " \u00f7 " + usd(up) + " = " + u.toLocaleString("en-US") + " units", false); }
      else { if (units) units.value = ""; var lo = Math.floor(u) * up; say("total_units", usd(tv) + " \u00f7 " + usd(up) + " is not a whole number of units. Use " + usd(lo) + " or " + usd(lo + up) + ".", true); }
    }
    if (mn !== null && up) {
      if (mn < up) say("minimum_investment", usd(mn) + " is less than one unit (" + usd(up) + "). Use " + usd(up) + " or a multiple of it.", true);
      else if (mn % up !== 0) { var w = Math.floor(mn / up); say("minimum_investment", usd(mn) + " buys only " + w + " whole unit" + (w === 1 ? "" : "s") + ". Use " + usd(w * up) + " or " + usd((w + 1) * up) + ".", true); }
      else say("minimum_investment", "= " + (mn / up) + " whole unit" + (mn / up === 1 ? "" : "s"), false);
    }
    var y = num("expected_yield"), a = num("capital_appreciation"), t = num("total_return"), tr = document.getElementById("f_total_return");
    if (y !== null && a !== null) {
      var sum = Math.round((y + a) * 100) / 100;
      if (tr) tr.placeholder = String(sum);
      if (t === null) say("total_return", "Will be saved as " + sum + "% (yield + appreciation).", false);
      else if (Math.abs(t - sum) > 0.05) say("total_return", "Differs from yield + appreciation (" + sum + "%). You can save, but check the figures.", true);
      else say("total_return", "", false);
    }
  }
  function apply() {
    var model = sel.value, p = R.profiles[model] || "ready_single";
    document.querySelectorAll("[data-explain]").forEach(function (e) { e.textContent = R.explain[model] || ""; });
    Object.keys(R.fields).forEach(function (name) {
      var r = R.fields[name][p], w = document.querySelector('.f[data-field="' + name + '"]');
      if (!w) return;
      w.hidden = !r.show;
      var lab = w.querySelector("label .txt"); if (lab) lab.textContent = r.label;
      var help = w.querySelector(".help .txt"); if (help) help.textContent = r.help;
      var star = w.querySelector("label .req"), label = w.querySelector("label");
      if (r.required && r.show && !star) { star = document.createElement("span"); star.className = "req"; star.title = "Required"; star.textContent = " *"; label.appendChild(star); }
      if (!(r.required && r.show) && star) star.remove();
      var input = w.querySelector("input[name],select[name],textarea[name]");
      if (input && input.type !== "hidden") { input.required = r.required && r.show; input.disabled = !r.show; }
    });
    document.querySelectorAll("[data-profiles]").forEach(function (e) {
      var on = e.getAttribute("data-profiles").split(" ").indexOf(p) >= 0;
      e.hidden = !on;
      e.querySelectorAll("input[name],select[name],textarea[name]").forEach(function (i) { if (i.type !== "hidden") i.disabled = !on; });
    });
    var area = document.querySelector("label[for=f_area] .txt"); if (area) area.textContent = R.area_labels[p];
    calc();
  }
  sel.addEventListener("change", apply);
  ["total_value", "unit_price", "minimum_investment", "expected_yield", "capital_appreciation", "total_return"].forEach(function (n) {
    var e = document.getElementById("f_" + n); if (e) e.addEventListener("input", calc);
  });
  calc();
})();
// Tables instead of "Label | value" lines (client letter, 2026-11-18: staff found the written
// format hard). Each list becomes rows of fields (a year or item, a % or value, a choice where
// the page needs one) with Add row / remove / move; the hidden box keeps the same lines, so the
// server reads exactly what it read before.
(function () {
  var SPECS = {
    ownership_structure: { cols: [["Item", "Ownership vehicle"], ["Value", "DIFC SPV"]] },
    investment_structure: { cols: [["Year or item", "Year 1"], ["Return % or value", "8.5% / $120,000"]] },
    market_analysis: { cols: [["Item", "Area pipeline"], ["Value", "12 active towers"]] },
    scenarios: { cols: [["Scenario", "Base case"], ["Outcome", "+18% by handover"], ["Tone", ["positive", "neutral", "negative"]]], need: 2 },
    risks: { cols: [["Risk", "Construction delay"], ["Level", ["low", "medium", "high"]], ["How it is mitigated", "Escrow and milestone audits"]], need: 2 },
    exit_mechanisms: { cols: [["Name", "Secondary market"], ["Timing", "After handover"], ["Description", "Sell units to other investors"]], need: 1 }
  };
  var SEP = String.fromCharCode(124); // the separator the server reads
  Object.keys(SPECS).forEach(function (name) {
    var box = document.querySelector('textarea[name="' + name + '"]');
    if (!box) return;
    var spec = SPECS[name];

    var help = box.parentElement.querySelector(".help");
    var m = help ? /max ([0-9]+)/.exec(help.textContent) : null;
    var max = m ? Number(m[1]) : 12;
    box.hidden = true;
    var wrap = document.createElement("div");
    wrap.className = "rowed";
    var table = document.createElement("table");
    table.className = "rowed";
    var head = "<thead><tr>" + spec.cols.map(function (c, i) {
      return "<th>" + c[0] + (i < (spec.need || spec.cols.length) ? ' <span class="req">*</span>' : "") + "</th>";
    }).join("") + "<th></th></tr></thead>";
    table.innerHTML = head + "<tbody></tbody>";
    var body = table.querySelector("tbody");
    var add = document.createElement("button");
    add.type = "button"; add.className = "mini"; add.textContent = "+ Add row";
    wrap.appendChild(table); wrap.appendChild(add);
    box.parentElement.insertBefore(wrap, box);
    if (help) {

      help.textContent = "One row per item, up to " + max + ". Empty rows are ignored. ";
    }
    function clean(v) { return String(v || "").split(SEP).join("/").trim(); }
    function sync() {
      var lines = [];
      body.querySelectorAll("tr").forEach(function (tr) {
        var vals = Array.prototype.map.call(tr.querySelectorAll("input,select"), function (e) { return clean(e.value); });
        if (vals.some(function (v) { return v; })) lines.push(vals.join(" " + SEP + " ").replace(/[ |]+$/, ""));
      });
      box.value = lines.join(String.fromCharCode(10));
      add.disabled = body.children.length >= max;
    }
    function row(vals) {
      var tr = document.createElement("tr");
      spec.cols.forEach(function (c, i) {
        var td = document.createElement("td");
        var el;
        if (Array.isArray(c[1])) {
          el = document.createElement("select");
          el.innerHTML = '<option value="">—</option>' + c[1].map(function (o) { return '<option value="' + o + '">' + o + "</option>"; }).join("");
          el.value = (vals[i] || "").toLowerCase();
        } else {
          el = document.createElement("input");
          el.type = "text"; el.maxLength = 240; el.placeholder = c[1]; el.value = vals[i] || "";
        }
        el.setAttribute("aria-label", c[0]);
        el.addEventListener("input", sync); el.addEventListener("change", sync);
        td.appendChild(el); tr.appendChild(td);
      });
      var act = document.createElement("td");
      act.className = "rowact";
      [["Move up", "&uarr;", -1], ["Move down", "&darr;", 1]].forEach(function (b) {
        var btn = document.createElement("button");
        btn.type = "button"; btn.className = "mini"; btn.title = b[0]; btn.innerHTML = b[1];
        btn.addEventListener("click", function () {
          var to = b[2] < 0 ? tr.previousElementSibling : tr.nextElementSibling;
          if (!to) return;
          if (b[2] < 0) body.insertBefore(tr, to); else body.insertBefore(to, tr);
          sync();
        });
        act.appendChild(btn);
      });
      var rm = document.createElement("button");
      rm.type = "button"; rm.className = "mini danger"; rm.title = "Remove this row"; rm.innerHTML = "&times;";
      rm.addEventListener("click", function () { tr.remove(); sync(); });
      act.appendChild(rm);
      tr.appendChild(act);
      body.appendChild(tr);
    }
    var lines = box.value.split(String.fromCharCode(10)).filter(function (l) { return l.trim(); });
    lines.forEach(function (l) { row(l.split(SEP).map(function (x) { return x.trim(); })); });
    if (!lines.length) row([]);
    add.addEventListener("click", function () { if (body.children.length < max) { row([]); sync(); } });
    sync();
  });
})();
// Developer card: filled from a saved developer (client letter, 2026-11-18).
(function () {
  var pick = document.querySelector("[data-saved-developer]");
  var data = document.getElementById("saved-developers");
  if (!pick || !data) return;
  var saved = JSON.parse(data.textContent);
  var form = pick.closest("form");
  function set(name, v) {
    var e = form.querySelector('[name="' + name + '"]');
    if (!e) return;
    if (e.type === "checkbox") e.checked = Boolean(v);
    else e.value = v === undefined || v === null ? "" : Array.isArray(v) ? v.join(String.fromCharCode(10)) : v;
  }
  pick.addEventListener("change", function () {
    var d = saved.filter(function (x) { return x.id === pick.value; })[0];
    form.querySelector('[name="saved_developer_id"]').value = d ? d.id : "";
    if (!d) return;
    var p = d.profile || {};
    set("name", p.name); set("rating", p.rating); set("projects_completed", p.projectsCompleted);
    set("website", p.website); set("about", p.about); set("years_experience", p.yearsExperience);
    set("on_time_delivery", p.onTimeDelivery); set("previous_projects", p.previousProjects);
    set("verifications", p.verifications); set("verified", p.verified);
    var note = form.querySelector("[data-saved-logo]");
    if (!note) {
      note = document.createElement("div"); note.className = "muted"; note.setAttribute("data-saved-logo", "");
      form.querySelector('[data-field="logo"]').appendChild(note);
    }
    note.innerHTML = p.logo ? 'The saved logo is used: <img alt="logo" style="height:28px;vertical-align:middle;border-radius:6px">' : "";
    if (p.logo) note.querySelector("img").src = p.logo;
  });
})();
// Photos: dropped or chosen, previewed before upload.
(function () {
  var drop = document.querySelector("[data-drop-photos]");
  if (!drop) return;
  var input = drop.querySelector("input[type=file]");
  var box = document.querySelector("[data-photo-previews]");
  var count = drop.querySelector("[data-photo-count]");
  function show() {
    box.innerHTML = "";
    var files = Array.prototype.slice.call(input.files || []);
    if (files.length) count.textContent = files.length + (files.length === 1 ? " photo ready to upload" : " photos ready to upload");
    files.forEach(function (f) {
      var d = document.createElement("div"); d.className = "img";
      var im = document.createElement("img"); im.src = URL.createObjectURL(f); im.alt = f.name;
      d.appendChild(im); box.appendChild(d);
    });
  }
  input.addEventListener("change", show);
  ["dragenter", "dragover"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); }); });
  ["dragleave", "drop"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); }); });
  drop.addEventListener("drop", function (e) {
    if (!e.dataTransfer || !e.dataTransfer.files.length) return;
    var dt = new DataTransfer();
    Array.prototype.slice.call(input.files || []).forEach(function (g) { dt.items.add(g); });
    Array.prototype.slice.call(e.dataTransfer.files).forEach(function (g) { if (g.type.indexOf("image/") === 0) dt.items.add(g); });
    input.files = dt.files; show();
  });
})();
// Documents: several files at once, dropped or chosen (client letter, 2026-11-18, as on
// Capimax BRX). Each file is uploaded the moment it is picked and kept until the rows are saved;
// its row has its name in English (from the file name), Arabic and French, a category guessed
// from the name, who issued it and its date. Removing a row removes its file.
(function () {
  var form = document.querySelector("[data-doc-upload]");
  if (!form) return;
  var input = form.querySelector("input[type=file]");
  var drop = form.querySelector("[data-drop]");
  var table = form.querySelector("[data-pending]");
  var body = table.querySelector("tbody");
  var single = form.querySelector("[data-single]");
  var button = form.querySelector("[data-upload-label]");
  var cats = document.getElementById("doc-categories").innerHTML;
  var stageUrl = form.getAttribute("data-stage-url");
  var unstageUrl = form.getAttribute("data-unstage-url");
  var busy = 0;
  function title(name) {
    var stem = name.replace(/\\.[^.]+$/, "").replace(/[_-]+/g, " ").replace(/\\s+/g, " ").trim();
    return stem || "Document";
  }
  function guess(name) {
    var n = name.toLowerCase();
    if (/valu|apprais/.test(n)) return "valuation";
    if (/insur|policy/.test(n)) return "insurance";
    if (/diligence|\\bdd\\b/.test(n)) return "due_diligence";
    if (/legal|title.?deed|contract/.test(n)) return "legal";
    if (/spv|incorporat|memorandum|articles/.test(n)) return "spv";
    if (/audit/.test(n)) return "audit";
    if (/agreement|subscription/.test(n)) return "agreement";
    if (/financ|feasib|study|projection/.test(n)) return "financial";
    return "other";
  }
  function cell(html) { var td = document.createElement("td"); td.innerHTML = html; return td; }
  function refresh() {
    var all = body.querySelectorAll("tr").length;
    var ready = body.querySelectorAll("tr[data-ready]").length;
    table.parentNode.hidden = all === 0;
    single.hidden = all > 0;
    single.querySelectorAll("input,select").forEach(function (e) { e.disabled = all > 0; });
    input.required = all === 0;
    button.disabled = busy > 0 || (all > 0 && ready === 0);
    if (busy > 0) button.textContent = "Uploading " + busy + " file" + (busy > 1 ? "s" : "") + "…";
    else if (ready > 1) button.textContent = "Save " + ready + " documents";
    else if (ready === 1) button.textContent = "Save document";
    else button.textContent = "Upload document";
  }
  function add(f) {
    var tr = document.createElement("tr");
    var file = cell(""); file.className = "fname";
    if (f.type.indexOf("image/") === 0) {
      var img = document.createElement("img"); img.className = "thumb"; img.alt = "";
      img.src = URL.createObjectURL(f); file.appendChild(img);
    }
    file.appendChild(document.createTextNode(f.name));
    var state = document.createElement("div"); state.className = "state"; state.textContent = "Uploading…";
    file.appendChild(state);
    var token = document.createElement("input"); token.type = "hidden"; token.name = "staged"; token.disabled = true;
    file.appendChild(token);
    tr.appendChild(file);
    var t = cell('<input type="text" name="title" maxlength="200" required>'); t.querySelector("input").value = title(f.name); tr.appendChild(t);
    tr.appendChild(cell('<input type="text" name="title_ar" maxlength="200" dir="rtl" lang="ar">'));
    tr.appendChild(cell('<input type="text" name="title_fr" maxlength="200" lang="fr">'));
    var c = cell('<select name="doc_type">' + cats + "</select>"); c.querySelector("select").value = guess(f.name); tr.appendChild(c);
    tr.appendChild(cell('<input type="text" name="issuer" maxlength="200" placeholder="Knight Frank">'));
    tr.appendChild(cell('<input type="date" name="issued_on">'));
    var rm = cell('<button type="button" class="mini danger" title="Remove this file">&times;</button>');
    rm.querySelector("button").addEventListener("click", function () {
      if (token.value) {
        var fd = new FormData(); fd.append("token", token.value);
        fetch(unstageUrl, { method: "POST", body: fd, credentials: "same-origin" });
      }
      tr.remove(); refresh();
    });
    tr.appendChild(rm);
    body.appendChild(tr);
    busy++; refresh();
    var fd = new FormData(); fd.append("file", f);
    fetch(stageUrl, { method: "POST", body: fd, credentials: "same-origin" })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (!r.ok || !j.token) throw new Error(j.error || "The upload failed. Remove the row and choose the file again.");
          return j;
        });
      })
      .then(function (j) {
        token.value = j.token; token.disabled = false; tr.setAttribute("data-ready", "");
        state.textContent = "Uploaded · kept, attached when you save"; state.className = "state st-ok";
      })
      .catch(function (e) {
        state.textContent = e.message; state.className = "state st-bad";
        tr.querySelectorAll("input,select").forEach(function (x) { x.disabled = true; });
      })
      .then(function () { busy--; refresh(); });
  }
  input.addEventListener("change", function () {
    Array.prototype.slice.call(input.files || []).forEach(add);
    input.value = "";
  });
  ["dragenter", "dragover"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); });
  });
  drop.addEventListener("drop", function (e) {
    if (!e.dataTransfer || !e.dataTransfer.files.length) return;
    Array.prototype.slice.call(e.dataTransfer.files).forEach(add);
  });
  form.addEventListener("submit", function (e) { if (busy > 0) e.preventDefault(); });
})();
// The long texts (the description and its translations) grow with what is written, so the
// whole text is read without scrolling inside the box; very long ones stop at 3/4 of the screen.
(function () {
  function fit(t) {
    if (!t.offsetParent || t.classList.contains("full")) return; // closed section / full screen
    t.style.height = "auto";
    t.style.height = t.scrollHeight + 2 + "px";
  }
  var boxes = document.querySelectorAll("textarea.long");
  boxes.forEach(function (t) { fit(t); t.addEventListener("input", function () { fit(t); }); });
  // Under each long box: how long it is, and a full-screen mode to read and edit several
  // paragraphs at once (client, 2026-11-19). Esc or the button goes back to the form.
  function full(t, btn, on) {
    t.classList.toggle("full", on);
    document.body.classList.toggle("editing-full", on);
    btn.classList.toggle("floating", on);
    btn.textContent = on ? "Done, back to the form" : "Expand to full screen";
    if (on) { t.style.height = ""; t.focus(); } else { fit(t); t.scrollIntoView({ block: "center" }); }
  }
  boxes.forEach(function (t) {
    var bar = document.createElement("div"); bar.className = "longbar";
    var count = document.createElement("span");
    var btn = document.createElement("button"); btn.type = "button"; btn.className = "mini";
    btn.textContent = "Expand to full screen"; btn.setAttribute("data-expand", "");
    bar.appendChild(count); bar.appendChild(btn);
    t.parentNode.insertBefore(bar, t.nextSibling);
    function counts() {
      var s = t.value.trim();
      var words = s ? s.split(/\\s+/).length : 0;
      var paras = s ? s.split(/\\n\\s*\\n/).length : 0;
      count.textContent = paras + " paragraph" + (paras === 1 ? "" : "s") + " · " + words + " word" + (words === 1 ? "" : "s");
    }
    counts(); t.addEventListener("input", counts);
    btn.addEventListener("click", function () { full(t, btn, !t.classList.contains("full")); });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var open = document.querySelector("textarea.long.full");
    if (open) open.nextSibling.querySelector("[data-expand]").click();
  });
  document.querySelectorAll("details").forEach(function (d) {
    d.addEventListener("toggle", function () { d.querySelectorAll("textarea.long").forEach(fit); });
  });
  window.addEventListener("resize", function () { boxes.forEach(fit); });
})();
</script>
{%- endmacro %}
"""

_CREATE_PAGE = _env.from_string(
    _FIELD_MACRO
    + """<!doctype html><html><head><meta charset="utf-8"><title>New listing</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """</style></head><body><div class="wrap">
<div class="top"><div><div class="muted"><a href="/admin/listing/">&larr; Listings</a></div><h1>New listing</h1>
<p class="lead">Fill the basics to create a <b>draft</b>. Nothing is visible to investors until you press Publish. Photos, documents, facts and the rest are added on the next screen. Fields marked <span class="req">*</span> are required.</p></div></div>
{% if message %}<div class="{{ 'err' if error else 'ok' }}">{{ message }}</div>{% endif %}
<form method="post" class="card">
{% for group, fields in groups %}<h3{% if group == construction_group %} data-profiles="offplan_single offplan_portfolio"{% if profile not in ('offplan_single', 'offplan_portfolio') %} hidden{% endif %}{% endif %}>{{ group }}</h3><div class="cols">{% for f in fields %}{{ field(f, values.get(f.name), profile) }}{% endfor %}</div>{% if loop.first %}{{ installment_notice(installment_terms, profile) }}{% endif %}{% endfor %}
<div class="actions" style="margin-top:16px"><button class="primary" type="submit">Create draft listing</button><a class="btn" href="/admin/listing/">Cancel</a></div>
</form>{{ adapt_script(rules) }}</div></body></html>"""
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
    <h1>{{ p.title }} <span class="badge {{ 'active' if p.status.value in ('active','funded') else ('closed' if p.status.value == 'closed' else 'draft') }}">{{ status_label }}</span>{% if is_sample %} <span class="badge draft" data-sample-badge title="Investments are refused on this listing">Sample listing, not open for investment</span>{% endif %}</h1>
    <div class="muted">{{ model_label }} · {{ p.location }} · web address <code>/property/{{ p.slug or p.id }}</code></div>
  </div>
  <div class="actions">
    {% if full_admin %}<a class="btn" href="/admin/unit-prices/{{ p.id }}" title="The price of a unit now, its history, and recording a new price">Unit price</a>{% endif %}
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
{% for w in save_warnings %}<div class="warn">{{ w }}</div>{% endfor %}

<div class="card checklist" data-checklist>
 <h2>{% if p.status.value in ('active', 'funded') %}Listing check{% else %}Before you publish{% endif %}</h2>
 {% if checklist.blockers %}
  <div class="err" data-blockers><b>Publishing is blocked until these are fixed:</b><ul>{% for b in checklist.blockers %}<li>{{ b }}</li>{% endfor %}</ul></div>
 {% else %}
  <div class="ok" data-ready>Everything required is in place{% if p.status.value not in ('active', 'funded') %}: this listing can be published{% endif %}.</div>
 {% endif %}
 {% if checklist.warnings %}<div class="warn" data-warnings><b>Please check:</b><ul>{% for w in checklist.warnings %}<li>{{ w }}</li>{% endfor %}</ul></div>{% endif %}
 {% if checklist.recommended %}<div class="note" data-recommended><b>Recommended (not blocking):</b><ul>{% for r in checklist.recommended %}<li>{{ r }}</li>{% endfor %}</ul></div>{% endif %}
</div>

<div class="card">
 <h2>Listing details</h2>
 <p class="lead">The core of the listing. Fields marked <span class="req">*</span> are required. The form changes with the ownership model. Units, price and model lock automatically once an investor holds units{% if full_admin %}; after that the price changes only by recording a new one under <a href="/admin/unit-prices/{{ p.id }}">Unit price</a>{% endif %}.</p>
 <form method="post"><input type="hidden" name="action" value="save_core">
 {% for group, fields in core_groups %}<h3>{{ group }}</h3><div class="cols">{% for f in fields %}{{ field(f, core_values.get(f.name), profile, model_locked) }}{% endfor %}</div>{% if loop.first %}{{ installment_notice(installment_terms, profile) }}{% endif %}{% endfor %}
 <button class="primary" type="submit" style="margin-top:14px">Save listing details</button>
 </form>
</div>

<div class="card" id="translations" data-translations>
 <h2>Arabic &amp; French versions</h2>
 <p class="lead">What a visitor reads when the site is in Arabic or French. Only the text this listing has appears here, with the English under each box. A box left blank shows the English. Text removed from the English goes in every language. Save the English first: photos, figures and dates are the same in every language.</p>
 {% for v in translation_forms %}
 <details class="tr" data-version="{{ v.lang }}" {{ 'open' if v.lang == translation_open }}>
  <summary><b>{{ v.name }}</b> <span class="muted">{{ v.filled }} of {{ v.total }} filled</span></summary>
  {% if v.groups %}
  <form method="post"><input type="hidden" name="action" value="save_translation"><input type="hidden" name="lang" value="{{ v.lang }}">
   {% for g in v.groups %}<h3>{{ g.title }}</h3>
    {% for f in g.fields %}
    <div class="f" data-field="{{ f.name }}">
     <label for="t_{{ v.lang }}_{{ loop.index }}_{{ f.name }}">{{ f.label }}</label>
     {% if f.kind == 'line' %}<input type="text" id="t_{{ v.lang }}_{{ loop.index }}_{{ f.name }}" name="{{ f.name }}" dir="{{ v.dir }}" lang="{{ v.lang }}" maxlength="{{ f.max_len }}" value="{{ f.value }}">
     {% else %}<textarea {% if f.kind == 'text' %}class="long" {% endif %}id="t_{{ v.lang }}_{{ loop.index }}_{{ f.name }}" name="{{ f.name }}" dir="{{ v.dir }}" lang="{{ v.lang }}" rows="{{ 6 if f.kind == 'text' else 3 }}">{{ f.value }}</textarea>{% endif %}
     <div class="help english">{% if f.kind == 'lines' %}One per line. {% endif %}English: {{ f.english }}</div>
    </div>
    {% endfor %}
   {% endfor %}
   <button class="primary" type="submit" style="margin-top:8px">Save {{ v.name }} version</button>
  </form>
  {% else %}<p class="muted">Nothing to translate yet: write the listing in English first.</p>{% endif %}
 </details>
 {% endfor %}
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
  <div data-field="files"><label class="drop" for="f_files" data-drop-photos><b>Drop photos here</b> or <u>choose photos</u> — several at once
  <span class="muted" data-photo-count>Max {{ max_mb }} MB each. Example: exterior, living room, bedroom, view.</span>
  <input id="f_files" type="file" name="files" accept="image/jpeg,image/png,image/webp" multiple required></label>
  <div class="grid" data-photo-previews style="margin-top:8px"></div></div>
  <button class="primary" type="submit" style="margin-top:8px">Upload photos</button>
 </form>
</div>

<div class="card">
 <h2>Documents</h2>
 <p class="lead">Shown in the Documents tab, grouped by category, and downloadable by anyone who can see the listing. Valuation reports, insurance certificates and the legal due diligence also appear in the <b>Due Diligence</b> tab. PDF, Word, Excel, CSV, text or images · max {{ max_mb }} MB each.</p>
 {% if docs %}
 <table class="docs"><tr><th>Title</th><th>Category</th><th>Issued by</th><th>Date</th><th></th></tr>
 {% for d in docs %}
 <tr>
  <td>{{ d.title }}</td><td>{{ cat_labels.get(d.type, d.type) }}</td><td>{{ d.issuer or '—' }}</td><td>{{ d.issued_on.isoformat() if d.issued_on else d.created_at.strftime('%Y-%m-%d') ~ ' (uploaded)' }}</td>
  <td class="actions">
   <a class="btn mini" href="/api/v1/documents/{{ d.id }}/download{{ '?preview=' ~ preview_token if preview_token else '' }}" target="_blank" rel="noopener">Download</a>
   <details class="edit"><summary class="btn mini">Edit</summary>
    <form method="post" class="docedit"><input type="hidden" name="action" value="doc_edit"><input type="hidden" name="doc_id" value="{{ d.id }}">
     <label>Name (English)</label><input type="text" name="title" maxlength="200" required value="{{ d.title }}">
     <label>Name in Arabic</label><input type="text" name="title_ar" maxlength="200" dir="rtl" lang="ar" value="{{ (doc_titles.get(d.id|string) or {}).get('ar', '') }}">
     <label>Name in French</label><input type="text" name="title_fr" maxlength="200" lang="fr" value="{{ (doc_titles.get(d.id|string) or {}).get('fr', '') }}">
     <label>Category</label><select name="doc_type">{% for v,l in categories %}<option value="{{ v }}" {{ 'selected' if v == d.type }}>{{ l }}</option>{% endfor %}</select>
     <label>Issued by</label><input type="text" name="issuer" maxlength="200" value="{{ d.issuer or '' }}" placeholder="Knight Frank">
     <label>Date on the document</label><input type="date" name="issued_on" value="{{ d.issued_on.isoformat() if d.issued_on else '' }}">
     <button class="mini primary" type="submit" style="margin-top:6px">Save</button>
    </form>
   </details>
   <form method="post" enctype="multipart/form-data" class="inline"><input type="hidden" name="action" value="doc_replace"><input type="hidden" name="doc_id" value="{{ d.id }}"><input type="file" name="file" required style="width:200px;display:inline-block;padding:3px" title="Choose the new file"><button class="mini" type="submit">Replace file</button></form>
   <form method="post" class="inline" onsubmit="return confirm('Delete this document and its file?')"><input type="hidden" name="action" value="doc_delete"><input type="hidden" name="doc_id" value="{{ d.id }}"><button class="mini danger" type="submit">Delete</button></form>
  </td>
 </tr>
 {% endfor %}
 </table>
 {% else %}<p class="muted">No documents yet.</p>{% endif %}
 <form method="post" enctype="multipart/form-data" style="margin-top:12px" data-doc-upload data-stage-url="/admin/listing/{{ p.id }}/stage-doc" data-unstage-url="/admin/listing/{{ p.id }}/unstage-doc">
  <input type="hidden" name="action" value="upload_doc">
  <label class="drop" for="f_doc_file" data-drop>
   <b>Drop files here</b> or <u>choose files</u> — several at once
   <span class="muted">Each file is uploaded as soon as you pick it. Its row takes its name from the file, in English, with its Arabic and French names, category, issuer and date; nothing is listed until you save.</span>
   <input id="f_doc_file" type="file" name="file" multiple required>
  </label>
  <div class="pendwrap" hidden><table class="pending" data-pending><thead><tr><th>File</th><th>Name (English) <span class="req">*</span></th><th>Name in Arabic</th><th>Name in French</th><th>Category <span class="req">*</span></th><th>Issued by</th><th>Date on the document</th><th></th></tr></thead><tbody></tbody></table></div>
  <div class="cols" data-single>
   <div data-field="title"><label for="f_doc_title">Document title</label><input id="f_doc_title" type="text" name="title" maxlength="200" placeholder="Independent Valuation Report"><div class="help">What investors see in the list; blank uses the file name. <span class="eg">Example: Independent Valuation Report</span></div></div>
   <div data-field="doc_type"><label for="f_doc_type">Category <span class="req">*</span></label><select id="f_doc_type" name="doc_type">{% for v,l in categories %}<option value="{{ v }}">{{ l }}</option>{% endfor %}</select><div class="help">Groups the document on the page. <span class="eg">Example: Valuation Reports</span></div></div>
   <div data-field="issuer"><label for="f_doc_issuer">Issued by</label><input id="f_doc_issuer" type="text" name="issuer" maxlength="200" placeholder="Knight Frank"><div class="help">The valuer, insurer or law firm. <span class="eg">Example: Knight Frank</span></div></div>
   <div data-field="issued_on"><label for="f_doc_date">Date on the document</label><input id="f_doc_date" type="date" name="issued_on"><div class="help">Blank shows the upload date.</div></div>
   <div data-field="title_ar"><label for="f_doc_title_ar">Name in Arabic</label><input id="f_doc_title_ar" type="text" name="title_ar" maxlength="200" dir="rtl" lang="ar"><div class="help">Shown when the site is in Arabic; blank shows the English.</div></div>
   <div data-field="title_fr"><label for="f_doc_title_fr">Name in French</label><input id="f_doc_title_fr" type="text" name="title_fr" maxlength="200" lang="fr"><div class="help">Shown when the site is in French; blank shows the English.</div></div>
  </div>
  <button class="primary" type="submit" style="margin-top:8px" data-upload-label>Upload document</button>
 </form>
 <template id="doc-categories">{% for v,l in categories %}<option value="{{ v }}">{{ l }}</option>{% endfor %}</template>
</div>

<div class="card">
 <h2>Key facts &amp; amenities</h2>
 <p class="lead">Shown in the facts strip under the title and in the Overview tab. Leave a fact blank to hide it.</p>
 <form method="post"><input type="hidden" name="action" value="save_facts">
  <div class="cols">
   <div data-profiles="ready_single offplan_single"{% if profile not in ('ready_single', 'offplan_single') %} hidden{% endif %} data-field="bedrooms"><label for="f_bedrooms">Bedrooms</label><input id="f_bedrooms" type="number" name="bedrooms" min="0" max="50" placeholder="2" value="{{ details.bedrooms if details.bedrooms is not none }}"><div class="help">Whole number. <span class="eg">Example: 2</span></div></div>
   <div data-profiles="ready_single offplan_single"{% if profile not in ('ready_single', 'offplan_single') %} hidden{% endif %} data-field="bathrooms"><label for="f_bathrooms">Bathrooms</label><input id="f_bathrooms" type="number" name="bathrooms" min="0" max="50" placeholder="2" value="{{ details.bathrooms if details.bathrooms is not none }}"><div class="help">Whole number. <span class="eg">Example: 2</span></div></div>
   <div data-field="area"><label for="f_area"><span class="txt">{{ area_label }}</span></label><input id="f_area" type="number" name="area" min="0" step="0.1" placeholder="1350" value="{{ details.area if details.area is not none }}"><div class="help">Built-up area in square feet. <span class="eg">Example: 1350</span></div></div>
   <div data-profiles="ready_single offplan_single"{% if profile not in ('ready_single', 'offplan_single') %} hidden{% endif %} data-field="parking"><label for="f_parking">Parking spaces</label><input id="f_parking" type="number" name="parking" min="0" max="100" placeholder="1" value="{{ details.parking if details.parking is not none }}"><div class="help">Whole number. <span class="eg">Example: 1</span></div></div>
   <div data-field="max_investment"><label for="f_max_investment">Maximum investment per investor (USD)</label><input id="f_max_investment" type="number" name="max_investment" min="0" step="0.01" placeholder="250000" value="{{ details.maxInvestment if details.maxInvestment is not none }}"><div class="help">Caps the calculator. Blank = up to the full property value. <span class="eg">Example: 250000</span></div></div>
  </div>
  <div data-profiles="ready_single offplan_single"{% if profile not in ('ready_single', 'offplan_single') %} hidden{% endif %} data-field="amenities"><label for="f_amenities">Amenities</label>
  <textarea id="f_amenities" name="amenities" placeholder="Sea view&#10;Gym&#10;Pool&#10;24-hour security">{{ amenities_text }}</textarea>
  <div class="help">One per line (or comma-separated), up to 40. Shown as a tick list. <span class="eg">Example: Sea view, Gym, Pool, 24-hour security</span></div></div>
  <button class="primary" type="submit" style="margin-top:8px">Save facts</button>
 </form>
</div>

<div class="card">
 <h2>Developer</h2>
 <p class="lead">The developer card in the Overview tab, and the developer's public profile page that its <b>View Profile</b> button opens. Every listing with the same developer name shares one profile. Shown only when a name is set; the other fields appear only when filled. Saving also keeps this developer in <a href="/admin/developers">Developers</a>, ready for the next listing.</p>
 <form method="post" enctype="multipart/form-data" data-developer-form><input type="hidden" name="action" value="save_developer"><input type="hidden" name="saved_developer_id" value="">
  {% if saved_developers %}
  <div data-field="saved_developer" class="note"><label for="f_saved_dev" style="margin-top:0">Fill from a saved developer</label>
   <select id="f_saved_dev" data-saved-developer><option value="">Choose a developer…</option>{% for d in saved_developers %}<option value="{{ d.id }}">{{ d.name }}</option>{% endfor %}</select>
   <div class="help">Fills every field below from the saved profile, logo included. Review, then <b>Save developer</b>: the developer's Arabic and French versions come with it.</div>
  </div>
  <script type="application/json" id="saved-developers">{{ saved_developers|tojson }}</script>
  {% endif %}
  <div class="cols">
   <div data-field="name"><label for="f_dev_name">Developer name</label><input id="f_dev_name" type="text" name="name" maxlength="120" value="{{ developer.name or '' }}" placeholder="Emaar Properties"><div class="help">Company name as investors know it. <span class="eg">Example: Emaar Properties</span></div></div>
   <div data-field="rating"><label for="f_dev_rating">Rating (0–5)</label><input id="f_dev_rating" type="number" name="rating" min="0" max="5" step="0.1" placeholder="4.6" value="{{ developer.rating if developer.rating is not none }}"><div class="help">Your own assessment; blank hides it. <span class="eg">Example: 4.6</span></div></div>
   <div data-field="projects_completed"><label for="f_dev_projects">Projects completed</label><input id="f_dev_projects" type="number" name="projects_completed" min="0" placeholder="120" value="{{ developer.projectsCompleted if developer.projectsCompleted is not none }}"><div class="help">Whole number; blank hides it. <span class="eg">Example: 120</span></div></div>
   <div data-field="website"><label for="f_dev_website">Website</label><input id="f_dev_website" type="text" name="website" maxlength="200" value="{{ developer.website or '' }}" placeholder="https://www.emaar.com"><div class="help">Opens from the developer profile; blank hides it. <span class="eg">Example: https://www.emaar.com</span></div></div>
   <div data-field="about" style="grid-column:1/-1"><label for="f_dev_about">About the developer</label><textarea id="f_dev_about" name="about" rows="4" maxlength="1200" placeholder="Founded in 1997, Emaar has delivered more than 100 projects across the Gulf…">{{ developer.about or '' }}</textarea><div class="help">Two or three short paragraphs for the profile page; facts you can stand behind, no promises of returns. Blank hides the section. <span class="eg">Example: Founded in 1997, delivered 120 projects in Dubai and Riyadh.</span></div></div>
   <div data-field="years_experience"><label for="f_dev_years">Years of experience</label><input id="f_dev_years" type="number" name="years_experience" min="0" max="200" placeholder="12" value="{{ developer.yearsExperience if developer.yearsExperience is not none }}"><div class="help">Blank hides it. <span class="eg">Example: 12</span></div></div>
   <div data-field="on_time_delivery"><label for="f_dev_ontime">On-time delivery (%)</label><input id="f_dev_ontime" type="number" name="on_time_delivery" min="0" max="100" step="0.1" placeholder="96" value="{{ developer.onTimeDelivery if developer.onTimeDelivery is not none }}"><div class="help">Share of past projects delivered on schedule — only a figure you can document. Blank hides it. <span class="eg">Example: 96</span></div></div>
   <div data-field="previous_projects" style="grid-column:1/-1"><label for="f_dev_prev">Previous projects</label><textarea id="f_dev_prev" name="previous_projects" rows="3" placeholder="Marina Heights Tower&#10;Creek Harbour Villas">{{ (developer.previousProjects or []) | join('\n') }}</textarea><div class="help">One project per line (max 12). Blank hides the list. <span class="eg">Example: Marina Heights Tower</span></div></div>
   <div data-field="verifications" style="grid-column:1/-1"><label for="f_dev_ver">Verification points</label><textarea id="f_dev_ver" name="verifications" rows="3" placeholder="Trade license verified&#10;Audited financial statements on file">{{ (developer.verifications or []) | join('\n') }}</textarea><div class="help">What Capimax checked about this developer, one per line (max 8). Blank hides the list. <span class="eg">Example: Trade license verified</span></div></div>
   <div data-field="verified" style="grid-column:1/-1"><label class="inline" style="font-weight:600"><input type="checkbox" name="verified" value="1" {{ 'checked' if developer.verified }}> Show a “Verified developer” badge</label><div class="help">Tick only after Capimax has actually verified this developer.</div></div>
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
  <div class="cols">{% for f in spv_fields %}{{ field(f, core_values.get(f.name), profile) }}{% endfor %}
   <div data-field="jurisdiction"><label for="f_jurisdiction">Jurisdiction</label><input id="f_jurisdiction" type="text" name="jurisdiction" maxlength="200" value="{{ spv.jurisdiction or '' }}" placeholder="DIFC, Dubai"><div class="help">Where the SPV is registered. <span class="eg">Example: DIFC, Dubai</span></div></div>
   <div data-field="trustee"><label for="f_trustee">Trustee</label><input id="f_trustee" type="text" name="trustee" maxlength="200" value="{{ spv.trustee or '' }}" placeholder="Gulf Corporate Trustees LLC"><div class="help">Blank hides the row. <span class="eg">Example: Gulf Corporate Trustees LLC</span></div></div>
   <div data-field="auditor"><label for="f_auditor">Auditor</label><input id="f_auditor" type="text" name="auditor" maxlength="200" value="{{ spv.auditor or '' }}" placeholder="KPMG Lower Gulf"><div class="help">Blank hides the row. <span class="eg">Example: KPMG Lower Gulf</span></div></div>
   <div data-field="asset_holding"><label for="f_asset_holding">Asset holding</label><input id="f_asset_holding" type="text" name="asset_holding" maxlength="200" value="{{ spv.assetHolding or '' }}" placeholder="100% title held by the SPV"><div class="help">How the SPV holds the property. Blank hides the row. <span class="eg">Example: 100% title held by the SPV</span></div></div>
   <div data-field="investor_allocation"><label for="f_investor_allocation">Investor allocation</label><input id="f_investor_allocation" type="text" name="investor_allocation" maxlength="200" value="{{ spv.investorAllocation or '' }}" placeholder="Pro-rata digital share certificates"><div class="help">What each investor holds. Blank hides the row. <span class="eg">Example: Pro-rata digital share certificates</span></div></div>
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

<div class="card" data-profiles="offplan_single offplan_portfolio"{% if profile not in ('offplan_single', 'offplan_portfolio') %} hidden{% endif %}>
 <h2>Overview tab — ownership, scenarios &amp; risks</h2>
 <p class="lead">Blocks of the under-construction page. Write one row per line, parts separated by <b>|</b>. A block with no rows is hidden.</p>
  <form method="post" style="margin-top:10px"><input type="hidden" name="action" value="save_rows"><input type="hidden" name="section" value="ownershipStructure">
   <div data-field="ownership_structure"><label for="f_ownership_structure">Ownership structure</label><textarea id="f_ownership_structure" name="ownership_structure" rows="4" placeholder="Ownership vehicle | DIFC SPV&#10;Title transfer | On full settlement">{{ rows_text.ownershipStructure }}</textarea><div class="help">Label | value, max 10 lines. Also shown in the sidebar and the SPV tab. <span class="eg">Example: Ownership vehicle | DIFC SPV</span></div></div>
   <button class="primary" type="submit" style="margin-top:6px">Save ownership structure</button>
  </form>
  <form method="post" style="margin-top:10px"><input type="hidden" name="action" value="save_rows"><input type="hidden" name="section" value="scenarios">
   <div data-field="scenarios"><label for="f_scenarios">Scenarios</label><textarea id="f_scenarios" name="scenarios" rows="4" placeholder="On-time delivery | About 18% appreciation by handover | positive&#10;3-month delay | Schedule extended, no extra cost | neutral">{{ rows_text.scenarios }}</textarea><div class="help">Name | outcome | positive, neutral or negative — max 4 lines. Outcomes are projections, never promises. <span class="eg">Example: On-time delivery | About 18% appreciation by handover | positive</span></div></div>
   <button class="primary" type="submit" style="margin-top:6px">Save scenarios</button>
  </form>
  <form method="post" style="margin-top:10px"><input type="hidden" name="action" value="save_rows"><input type="hidden" name="section" value="risks">
   <div data-field="risks"><label for="f_risks">Risk disclosures</label><textarea id="f_risks" name="risks" rows="4" placeholder="Construction delay | medium | Escrow and milestone audits">{{ rows_text.risks }}</textarea><div class="help">Risk | low, medium or high | how it is mitigated — max 10 lines. <span class="eg">Example: Construction delay | medium | Escrow and milestone audits</span></div></div>
   <button class="primary" type="submit" style="margin-top:6px">Save risk disclosures</button>
  </form>
</div>

<div class="card" data-profiles="offplan_single offplan_portfolio"{% if profile not in ('offplan_single', 'offplan_portfolio') %} hidden{% endif %}>
 <h2>Financials tab — projections, market, cash flow &amp; exit</h2>
 <p class="lead">Each block is hidden until it has content. Figures here are projections — say so in the wording.</p>
  <form method="post" style="margin-top:10px"><input type="hidden" name="action" value="save_rows"><input type="hidden" name="section" value="investmentStructure">
   <div data-field="investment_structure"><label for="f_investment_structure">Financial projections</label><textarea id="f_investment_structure" name="investment_structure" rows="4" placeholder="Final settlement | On handover">{{ rows_text.investmentStructure }}</textarea><div class="help">Label | value, max 12 lines. <span class="eg">Example: Final settlement | On handover</span></div></div>
   <button class="primary" type="submit" style="margin-top:6px">Save financial projections</button>
  </form>
  <form method="post" style="margin-top:10px"><input type="hidden" name="action" value="save_rows"><input type="hidden" name="section" value="marketAnalysis">
   <div data-field="market_analysis"><label for="f_market_analysis">Market analysis</label><textarea id="f_market_analysis" name="market_analysis" rows="4" placeholder="Area pipeline | 12 active towers">{{ rows_text.marketAnalysis }}</textarea><div class="help">Label | value, max 12 lines. <span class="eg">Example: Area pipeline | 12 active towers</span></div></div>
   <button class="primary" type="submit" style="margin-top:6px">Save market analysis</button>
  </form>
  <form method="post" style="margin-top:10px"><input type="hidden" name="action" value="save_cashflow">
   <div class="cols">
    <div data-field="rental_projection"><label for="f_rental">Rental / income projection</label><textarea id="f_rental" name="rental_projection" rows="3" maxlength="400" placeholder="Income-producing once delivered; distributions paid monthly.">{{ cashflow.rentalProjection or '' }}</textarea><div class="help">Blank hides it. <span class="eg">Example: Income-producing once delivered.</span></div></div>
    <div data-field="costs"><label for="f_costs">Development &amp; operating costs</label><textarea id="f_costs" name="costs" rows="3" maxlength="400" placeholder="Land, construction, SPV administration and valuation costs are in the offering memorandum.">{{ cashflow.costs or '' }}</textarea><div class="help">Blank hides it.</div></div>
    <div data-field="exit_projection"><label for="f_exitproj">Exit projection</label><textarea id="f_exitproj" name="exit_projection" rows="3" maxlength="400" placeholder="Sale on the secondary market after handover.">{{ cashflow.exitProjection or '' }}</textarea><div class="help">Blank hides it.</div></div>
   </div>
   <button class="primary" type="submit" style="margin-top:6px">Save cash flow notes</button>
  </form>
  <form method="post" style="margin-top:10px"><input type="hidden" name="action" value="save_rows"><input type="hidden" name="section" value="exitMechanisms">
   <div data-field="exit_mechanisms"><label for="f_exit_mechanisms">Exit mechanisms</label><textarea id="f_exit_mechanisms" name="exit_mechanisms" rows="4" placeholder="Secondary market | After handover | Sell units to other investors">{{ rows_text.exitMechanisms }}</textarea><div class="help">Name | timing | description, max 6 lines. <span class="eg">Example: Secondary market | After handover | Sell units to other investors</span></div></div>
   <button class="primary" type="submit" style="margin-top:6px">Save exit mechanisms</button>
  </form>
</div>

<div class="card" data-profiles="offplan_single offplan_portfolio"{% if profile not in ('offplan_single', 'offplan_portfolio') %} hidden{% endif %}>
 <h2>Construction status</h2>
 <p class="lead">The Construction Progress card. Each field is hidden when blank. The valuation is in <b>Valuation, insurance &amp; legal due diligence</b> below.</p>
 <form method="post"><input type="hidden" name="action" value="save_construction_status">
  <div class="cols">
   <div data-field="engineering_status"><label for="f_eng">Engineering status</label><input id="f_eng" type="text" name="engineering_status" maxlength="60" value="{{ construction.engineeringStatus or '' }}" placeholder="Certified"><div class="help">As stated in the latest engineering report. <span class="eg">Example: Certified</span></div></div>
   <div data-field="audit_status"><label for="f_audit">Milestone audit</label><input id="f_audit" type="text" name="audit_status" maxlength="60" value="{{ construction.auditStatus or '' }}" placeholder="On track"><div class="help">Latest milestone audit result. <span class="eg">Example: On track</span></div></div>
  </div>
  <button class="primary" type="submit" style="margin-top:6px">Save construction status</button>
 </form>
</div>

<div class="card" id="due-diligence">
 <h2>Valuation, insurance &amp; legal due diligence</h2>
 <p class="lead">The property page's <b>Due Diligence</b> tab: one card each for the valuation, the insurance and the legal due diligence, with who issued it, the date, an explanation and the documents of its category (Valuation Reports, Insurance Certificates, Legal Due Diligence). A card with nothing filled says it is not published yet.</p>
 <h3>Valuation</h3>
 <div class="{{ 'warn' if val_status.due else 'note' }}" data-valuation-status>
  {% if val_status.last %}Latest valuation on record: <b>{{ val_status.last }}</b> ({{ val_status.days }} day{{ '' if val_status.days == 1 else 's' }} ago).{% else %}No valuation on record yet.{% endif %}
  {% if val_quarterly %}{% if val_status.due %} <b>The quarterly valuation is due</b>: investors are told an under-construction property is revalued every 3 months. Save the new valuation here.{% else %} The next quarterly valuation is due by <b>{{ val_status.next_due }}</b>; the admins are reminded when it is.{% endif %}{% endif %}
 </div>
 <form method="post"><input type="hidden" name="action" value="save_valuation">
  <div class="cols">
   <div data-field="valuation_provider"><label for="f_val_prov">Valuation provider</label><input id="f_val_prov" type="text" name="valuation_provider" maxlength="200" value="{{ valuation.provider or '' }}" placeholder="Knight Frank"><div class="help"><span class="eg">Example: Knight Frank</span></div></div>
   <div data-field="valuation_date"><label for="f_val_date">Report date</label><input id="f_val_date" type="text" name="valuation_date" maxlength="60" value="{{ valuation.reportDate or '' }}" placeholder="June 2026"><div class="help"><span class="eg">Example: June 2026</span></div></div>
   <div data-field="valuation_value"><label for="f_val_value">Latest valuation (USD)</label><input id="f_val_value" type="number" name="valuation_value" min="0" step="1" value="{{ valuation.get('value')|int if valuation.get('value') is not none else '' }}" placeholder="1520000"><div class="help">The figure in the signed report. <span class="eg">Example: 1520000</span></div></div>
   <div data-field="valuation_impact"><label for="f_val_impact">Development impact</label><input id="f_val_impact" type="text" name="valuation_impact" maxlength="240" value="{{ valuation.impactNote or '' }}" placeholder="+5% since foundation sign-off"><div class="help"><span class="eg">Example: +5% since foundation sign-off</span></div></div>
   <div data-field="valuation_summary" style="grid-column:1/-1"><label for="f_val_summary">About the valuation</label><textarea id="f_val_summary" name="valuation_summary" rows="3" maxlength="800" placeholder="Prime-area supply is limited; comparable off-plan units sold 8% higher this quarter.">{{ valuation.summary or '' }}</textarea><div class="help">How the value was reached, in a short paragraph from the report. Blank shows a standard explanation.</div></div>
  </div>
  {% if p.status.value in ('active', 'funded') %}
  <div class="note" data-field="valuation_unit_price"><label for="f_val_price" style="margin-top:0">New unit price from this valuation (USD)</label>
   <input id="f_val_price" type="number" name="valuation_unit_price" min="0.01" step="0.01" placeholder="{{ '%.2f'|format(p.unit_price) }}">
   <div class="help">The current unit price is <b>${{ '%.2f'|format(p.unit_price) }}</b>.{% if val_implied %} This valuation divided by the {{ p.total_units }} units is <b>${{ val_implied }}</b> <button type="button" class="mini" data-use-implied onclick="document.getElementById('f_val_price').value='{{ val_implied }}'">Use it</button>.{% endif %} Filled in, it becomes the unit price when you save: the price history gets a Valuation entry, the units still for sale are offered at it, and every holder and installment payer is told by email and in the app, as on the Unit prices page. Blank keeps the current price.</div>
   <label class="inline" style="font-weight:400"><input type="checkbox" name="confirm_large" value="1"> The change is more than {{ val_max_step }}% in one step and it is right</label>
  </div>
  {% else %}<div class="note">Once the listing is published, a new valuation can set the unit price here. Until then the price is set under Listing details.</div>{% endif %}
  <div class="note">Upload each valuation report in <b>Documents</b> with the category <i>Valuation Reports</i>, who issued it and its date: they are listed under the valuation, newest first.</div>
  <button class="primary" type="submit" style="margin-top:6px">Save valuation</button>
 </form>

 <h3>Insurance</h3>
 <form method="post"><input type="hidden" name="action" value="save_insurance">
  <div class="cols">
   <div data-field="insurance_provider"><label for="f_ins_prov">Insurance provider</label><input id="f_ins_prov" type="text" name="insurance_provider" maxlength="200" value="{{ insurance.provider or '' }}" placeholder="AXA Gulf"><div class="help">The insurer. <span class="eg">Example: AXA Gulf</span></div></div>
   <div data-field="insurance_policy"><label for="f_ins_policy">Policy number</label><input id="f_ins_policy" type="text" name="insurance_policy" maxlength="80" value="{{ insurance.policyNumber or '' }}" placeholder="PRP-2026-00418"><div class="help">Blank hides it. <span class="eg">Example: PRP-2026-00418</span></div></div>
   <div data-field="insurance_coverage"><label for="f_ins_cov">Coverage amount (USD)</label><input id="f_ins_cov" type="number" name="insurance_coverage" min="0" step="1" value="{{ insurance.get('coverage')|int if insurance.get('coverage') is not none else '' }}" placeholder="1650000"><div class="help">Blank hides it. <span class="eg">Example: 1650000</span></div></div>
   <div data-field="insurance_summary" style="grid-column:1/-1"><label for="f_ins_summary">About the insurance</label><textarea id="f_ins_summary" name="insurance_summary" rows="3" maxlength="800" placeholder="Building and contents insured against fire, flood and third-party liability for the full reinstatement value.">{{ insurance.summary or '' }}</textarea><div class="help">What the policy covers. Blank shows a standard explanation.</div></div>
  </div>
  <div class="note">Upload the policy or certificate in <b>Documents</b> with the category <i>Insurance Certificates</i>.</div>
  <button class="primary" type="submit" style="margin-top:6px">Save insurance</button>
 </form>
 <h3>Legal due diligence</h3>
 <form method="post"><input type="hidden" name="action" value="save_legal_dd">
  <div class="cols">
   <div data-field="legal_dd_provider"><label for="f_ldd_prov">Law firm</label><input id="f_ldd_prov" type="text" name="legal_dd_provider" maxlength="200" value="{{ legal_dd.provider or '' }}" placeholder="Al Tamimi &amp; Company"><div class="help">Who carried out the review. <span class="eg">Example: Al Tamimi &amp; Company</span></div></div>
   <div data-field="legal_dd_date"><label for="f_ldd_date">Review date</label><input id="f_ldd_date" type="date" name="legal_dd_date" value="{{ legal_dd.date or '' }}"><div class="help">The date on the report.</div></div>
   <div data-field="legal_dd_summary" style="grid-column:1/-1"><label for="f_ldd_summary">About the review</label><textarea id="f_ldd_summary" name="legal_dd_summary" rows="3" maxlength="800" placeholder="Title deed, SPV ownership and the offering documents reviewed; no encumbrances found.">{{ legal_dd.summary or '' }}</textarea><div class="help">What was checked and found. Blank shows a standard explanation.</div></div>
  </div>
  <div class="note">Upload the report in <b>Documents</b> with the category <i>Legal Due Diligence</i>.</div>
  <button class="primary" type="submit" style="margin-top:6px">Save legal due diligence</button>
 </form>
</div>

<div class="card" data-profiles="offplan_single offplan_portfolio"{% if profile not in ('offplan_single', 'offplan_portfolio') %} hidden{% endif %}>
 <h2>Compliance points</h2>
 <p class="lead">The Compliance &amp; Legal Framework list on the SPV tab and the Compliance card in the sidebar. Only list what is actually in place.</p>
 <form method="post"><input type="hidden" name="action" value="save_compliance">
  <div data-field="compliance"><label for="f_compliance">Compliance points</label><textarea id="f_compliance" name="compliance" rows="4" placeholder="SPV holds direct, ring-fenced ownership of the asset&#10;Independent escrow agent secures all capital flows">{{ (content_compliance or []) | join('\n') }}</textarea><div class="help">One per line, max 10. Blank hides the list. <span class="eg">Example: KYC / AML verified investor base</span></div></div>
  <button class="primary" type="submit" style="margin-top:6px">Save compliance points</button>
 </form>
</div>

<div class="card" data-profiles="offplan_single offplan_portfolio"{% if profile not in ('offplan_single', 'offplan_portfolio') %} hidden{% endif %}>
 <h2>Construction &amp; timeline</h2>
 <p class="lead">For off-plan listings: the expected completion date appears in the investment sidebar and the milestones in the Timeline tab and the Construction Progress card. Give milestones a <b>Price index</b> (100 = launch price) to show the Price &amp; Appreciation card; without it that card stays hidden.</p>
 <form method="post"><input type="hidden" name="action" value="save_construction">
  <div class="cols">{% for f in construction_fields %}{{ field(f, core_values.get(f.name), profile) }}{% endfor %}</div>
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
    <div data-field="ms_value_index"><label for="ms_vi_{{ loop.index }}">Price index</label><input id="ms_vi_{{ loop.index }}" type="number" name="value_index" min="1" max="1000" placeholder="105" value="{{ m.value_index if m.value_index is not none }}"><div class="help">Expected unit price at this stage, 100 = launch price. Blank = no price step. <span class="eg">Example: 105 (5% above launch)</span></div></div>
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
   <div data-field="ms_value_index"><label for="ms_new_vi">Price index</label><input id="ms_new_vi" type="number" name="value_index" min="1" max="1000" placeholder="105"><div class="help">100 = launch price. Blank = no price step. <span class="eg">Example: 105</span></div></div>
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
{{ adapt_script(rules, offering_locked) }}
</div></body></html>"""
)

_INDEX_PAGE = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8"><title>Listings</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>"""
    + _STYLE
    + """</style></head><body><div class="wrap">
<div class="top"><div><div class="muted">{% if full_admin %}<a href="/admin/">&larr; Admin home</a>{% endif %}</div><h1>Listings</h1>
<p class="lead">Every property the platform lists. Open one to edit photos, documents, facts, milestones — or create a new draft.</p></div>
<div class="actions">{% if full_admin %}<a class="btn" href="/admin/owner-submissions">Owner submissions{% if owner_waiting %} ({{ owner_waiting }} waiting){% endif %}</a>{% endif %}<a class="btn primary" href="/admin/listing/new">+ New listing</a></div></div>
{% if full_admin and owner_waiting %}<div class="warn">{{ owner_waiting }} propert{{ 'y' if owner_waiting == 1 else 'ies' }} submitted by owners {{ 'is' if owner_waiting == 1 else 'are' }} waiting for review in <a href="/admin/owner-submissions">Owner Submissions</a>. They join this list once approved.</div>{% endif %}
{% if valuation_due %}<div class="warn" data-valuation-due>{{ valuation_due|length }} under-construction listing{{ '' if valuation_due|length == 1 else 's' }} {{ 'has' if valuation_due|length == 1 else 'have' }} gone 3 months without a valuation (investors are told it is every 3 months): {% for pid, d in valuation_due.items() %}<a href="/admin/listing/{{ pid }}#due-diligence">{{ d.title }}</a> ({{ d.days }} days){{ ', ' if not loop.last }}{% endfor %}.</div>{% endif %}
<div class="card">
{% if rows %}<table><tr><th>Title</th><th>Model</th><th>Status</th><th>Location</th><th>Updated</th><th></th></tr>
{% for p in rows %}<tr>
 <td><a href="/admin/listing/{{ p.id }}">{{ p.title }}</a></td>
 <td class="muted">{{ model_labels.get(p.model, p.model) }}</td>
 <td><span class="badge {{ 'active' if p.status.value in ('active','funded') else ('closed' if p.status.value == 'closed' else 'draft') }}">{{ status_labels.get(p.status.value, p.status.value) }}</span>{% if valuation_due.get(p.id|string) %} <span class="badge closed">Valuation due</span>{% endif %}</td>
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


async def _mark_lead_listed(lead_id: str, prop_id: uuid.UUID, actor: uuid.UUID | None) -> None:
    """The listing was created from a broker's lead: link them and tell the broker. Its own
    transaction, so a lead already closed never undoes the listing that was just created."""
    from app.services import broker_lead_service

    try:
        lid = uuid.UUID(lead_id)
        async with session_scope() as session:
            await broker_lead_service.admin_decide(
                session,
                lead_id=lid,
                decision="listed",
                note=None,
                actor_id=actor,
                property_id=prop_id,
            )
    except (ValueError, AppError) as exc:
        log.info("listing %s created from lead %s without linking it: %s", prop_id, lead_id, exc)


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


async def _installment_terms(session) -> dict:
    """The platform's single installment plan, read live (no per-property terms exist)."""
    from app.services import installment_service, settings_service

    fee = await settings_service.get_installment_fee_pct(session)
    return {
        "plans": [
            {"months": m, "down": d} for m, d in sorted(installment_service._DOWN_PCT.items())
        ],
        "fee": f"{fee.normalize():f}",
    }


def _common_context() -> dict:
    return {
        "rules": listing_service.form_rules_json(),
        "model_labels": listing_service.MODEL_LABELS,
        "model_explain": listing_service.MODEL_EXPLAIN,
        "construction_group": listing_service.GROUP_CONSTRUCTION,
    }


def _form_with_kept_facts(form, prop: Property):
    """Hidden key facts (e.g. bedrooms on a portfolio) keep their stored values."""
    profile = listing_service.profile_of(prop.model)
    details = (prop.content or {}).get("details") or {}
    merged = {k: form.get(k) for k in form.keys()}
    stored = {
        "bedrooms": details.get("bedrooms"),
        "bathrooms": details.get("bathrooms"),
        "parking": details.get("parking"),
        "amenities": "\n".join(details.get("amenities") or []),
    }
    for key, value in stored.items():
        if profile not in listing_service.FACT_RULES[key]["show_in"]:
            merged[key] = "" if value is None else str(value)
    return merged


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
            from app.admin_owner import platform_listing_filter

            # What the platform lists. Owner submissions waiting for a decision live in
            # Owner Submissions and join this list once approved.
            rows = (
                (
                    await session.execute(
                        select(Property)
                        .where(platform_listing_filter())
                        .order_by(Property.updated_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            waiting = await session.scalar(
                select(func.count(Property.id)).where(
                    Property.owner_id.is_not(None),
                    Property.status == PropertyStatus.under_review,
                )
            )
            valuation_due = {
                str(r["property"].id): {"title": r["property"].title, "days": r["days"]}
                for r in await valuation_service.due_listings(session)
            }
            html = _INDEX_PAGE.render(
                rows=rows,
                valuation_due=valuation_due,
                status_labels=_STATUS_LABELS,
                model_labels=listing_service.MODEL_LABELS,
                full_admin=is_full_admin(request),
                owner_waiting=waiting or 0,
            )
        return HTMLResponse(html)

    # ------------------------------------------------------------------ create #
    @expose("/listing/new", methods=["GET", "POST"])
    async def create(self, request: Request):
        if (resp := self._gate(request)) is not None:
            return resp
        names = [f.name for f in listing_service.fields_in(*listing_service.CREATE_FORM_GROUPS)]
        start_model = request.query_params.get("model", "ready-income")
        if start_model not in listing_service.ENABLED_MODELS:
            start_model = "ready-income"
        values: dict = {"model": start_model, "property_type": "apartment"}
        message, error = "", False
        # Started from a broker's property / project introduction (Broker Leads page)
        lead_id = request.query_params.get("lead")
        if lead_id and request.method == "GET":
            from app.admin_leads import lead_prefill

            prefill = await lead_prefill(lead_id)
            if prefill:
                values.update(prefill)
                message = (
                    "Filled in from the broker's introduction. Check every field and complete "
                    "the offering before creating the draft."
                )
        if request.method == "POST":
            form = await request.form()
            values = {n: form.get(n) for n in names}
            try:
                model = str(form.get("model") or "")
                listing_service.validate_model_choice(model)
                data = listing_service.parse_core(form, names, model=model)
                data, _warnings = listing_service.apply_offering_rules(data)
                async with session_scope() as session:
                    prop = await listing_service.create_listing(
                        session, data=data, actor_id=_actor(request)
                    )
                    new_id = prop.id
                if lead_id:
                    await _mark_lead_listed(lead_id, new_id, _actor(request))
                return RedirectResponse(f"/admin/listing/{new_id}?created=1", status_code=303)
            except Exception as exc:  # noqa: BLE001 — every error becomes a sentence
                message, error = _friendly(exc), True
        async with session_scope() as session:
            terms = await _installment_terms(session)
        html = _CREATE_PAGE.render(
            groups=_groups(listing_service.CREATE_FORM_GROUPS),
            values=values,
            profile=listing_service.profile_of(values.get("model")),
            installment_terms=terms,
            message=message,
            error=error,
            **_common_context(),
        )
        return HTMLResponse(html, status_code=400 if error else 200)

    # ------------------------------------------------------------------ editor #
    # ------------------------------------------------------- picked documents #
    # Each file the Documents card is given is uploaded the moment it is picked (client
    # letter, 2026-11-18, as on Capimax BRX) and answered with a signed token; the card's save
    # turns the tokens into documents. A file removed from the card before saving is deleted.
    @expose("/listing/{prop_id}/stage-doc", methods=["POST"])
    async def stage_doc(self, request: Request):
        if self._gate(request) is not None:
            return JSONResponse({"error": "Sign in again."}, status_code=401)
        try:
            prop_id = uuid.UUID(request.path_params["prop_id"])
        except ValueError:
            return JSONResponse({"error": "Listing not found."}, status_code=404)
        form = await request.form()
        got = await _read_upload(form.get("file"))
        if not got:
            return JSONResponse({"error": "The file is empty."}, status_code=422)
        async with session_scope() as session:
            if await session.get(Property, prop_id) is None:
                return JSONResponse({"error": "Listing not found."}, status_code=404)
        try:
            staged = document_service.stage_property_file(prop_id, got[0], got[1])
        except AppError as exc:
            return JSONResponse({"error": exc.message}, status_code=exc.status_code)
        return JSONResponse(staged)

    @expose("/listing/{prop_id}/unstage-doc", methods=["POST"])
    async def unstage_doc(self, request: Request):
        if self._gate(request) is not None:
            return JSONResponse({"error": "Sign in again."}, status_code=401)
        try:
            prop_id = uuid.UUID(request.path_params["prop_id"])
        except ValueError:
            return JSONResponse({"error": "Listing not found."}, status_code=404)
        form = await request.form()
        try:
            async with session_scope() as session:
                await document_service.unstage_property_file(
                    session, str(form.get("token") or ""), prop_id
                )
        except AppError as exc:
            return JSONResponse({"error": exc.message}, status_code=exc.status_code)
        return JSONResponse({"removed": True})

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
        request.state.listing_warnings = []
        request.state.translation_open = ""
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
            positions = await listing_service.count_positions(session, prop.id)
            checklist = listing_service.publish_checklist(
                prop, milestones=len(milestones), has_positions=positions > 0
            )
            profile = listing_service.profile_of(prop.model)
            terms = await _installment_terms(session)
            content = dict(prop.content or {})
            saved_developers = developer_service.options(
                await developer_service.list_saved(session)
            )
            last_val = (await valuation_service.last_valuations(session, [prop])).get(prop.id)
            val_status = valuation_service.status_of(prop, last_val, dt.datetime.now(dt.UTC).date())
            val_value = (content.get("valuation") or {}).get("value")
            val_implied = (
                f"{decimal.Decimal(str(val_value)) / prop.total_units:.2f}"
                if val_value and prop.total_units
                else ""
            )
            base = get_settings().app_base_url.rstrip("/")
            ref = prop.slug or str(prop.id)
            if preview_token:
                preview_url = f"{base}/property/{ref}?preview={preview_token}"
            html = _PAGE.render(
                p=prop,
                status_label=_STATUS_LABELS.get(prop.status.value, prop.status.value),
                is_sample=bool((prop.content or {}).get("sample")),
                model_label=listing_service.MODEL_LABELS.get(prop.model, prop.model),
                full_admin=is_full_admin(request),
                core_groups=_groups(listing_service.CORE_FORM_GROUPS),
                profile=profile,
                model_locked=prop.model in listing_service.HIDDEN_MODELS and positions > 0,
                offering_locked=positions > 0,
                checklist=checklist,
                save_warnings=[] if error else list(request.state.listing_warnings),
                installment_terms=terms,
                area_label=listing_service.AREA_LABELS[profile],
                **_common_context(),
                spv_fields=listing_service.fields_in(listing_service.GROUP_SPV),
                construction_fields=listing_service.fields_in(listing_service.GROUP_CONSTRUCTION),
                core_values=_core_values(prop),
                images=list(prop.images or []),
                docs=docs,
                details=content.get("details") or {},
                amenities_text="\n".join((content.get("details") or {}).get("amenities") or []),
                developer=content.get("developer") or {},
                saved_developers=saved_developers,
                spv=content.get("spv") or {},
                valuation=content.get("valuation") or {},
                val_status=val_status,
                val_quarterly=valuation_service.is_quarterly(prop),
                val_implied=val_implied,
                val_max_step=price_service.MAX_STEP_PCT,
                insurance=content.get("insurance") or {},
                legal_dd=content.get("legalDueDiligence") or {},
                construction=content.get("construction") or {},
                cashflow=content.get("cashflow") or {},
                content_compliance=content.get("compliance") or [],
                rows_text={
                    key: listing_service.rows_to_text(content.get(key), spec["keys"])
                    for key, spec in listing_service.ROW_SECTIONS.items()
                },
                terms=content.get("terms") or {},
                fees=content.get("fees") or {},
                milestones=milestones,
                translation_forms=listing_translation_form.form_model(
                    prop, milestones, docs, await price_service._rows(session, prop.id)
                ),
                translation_open=request.state.translation_open,
                construction_progress=listing_service.construction_progress(milestones),
                ms_statuses=list(listing_service.MILESTONE_STATUS_LABELS.items()),
                categories=document_service.DOC_CATEGORIES,
                doc_titles=_doc_titles(content),
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
            model = str(form.get("model") or prop.model) if action == "save_core" else prop.model
            listing_service.validate_model_choice(model, current=prop.model)
            data = listing_service.parse_core(form, names, model=model)
            positions = await listing_service.count_positions(session, prop.id)
            data, warnings = listing_service.apply_offering_rules(
                data, current=prop, positions=positions
            )
            request.state.listing_warnings = warnings
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
            # Several files at once (client letter, 2026-11-18, as on Capimax BRX). With the
            # page's script each file was uploaded when picked and comes back as a signed
            # token; without it the files come in the form. Each row has its name in English,
            # Arabic and French, its category, issuer and date, in the order chosen. Every row
            # is checked before any document is made, so a refused one makes nothing.
            tokens = [str(t) for t in form.getlist("staged") if str(t).strip()]
            ups = [] if tokens else [u for u in form.getlist("file") if getattr(u, "filename", "")]
            if not tokens and not ups:
                raise ValueError("Choose at least one file to upload.")

            def nth(name: str, i: int) -> str:
                vals = form.getlist(name)
                return str(
                    vals[i] if i < len(vals) else (vals[0] if len(vals) == 1 else "")
                ).strip()

            def names(i: int) -> dict[str, str]:
                return {
                    lang: " ".join(nth(f"title_{lang}", i).split())[:200]
                    for lang in listing_translation.LANGUAGES
                }

            if tokens:
                rows = []
                for i, token in enumerate(tokens):
                    _key, fname = document_service.read_stage_token(token, prop.id)
                    title = nth("title", i) or _title_from_filename(fname)
                    doc_type = document_service.validate_doc_type(nth("doc_type", i) or "other")
                    issued_on = _form_day(nth("issued_on", i), f"{title}: date")
                    rows.append(
                        (token, title[:200], doc_type, nth("issuer", i), issued_on, names(i))
                    )
                made = []
                for token, title, doc_type, issuer, issued_on, langs in rows:
                    doc = await document_service.attach_staged_document(
                        session,
                        prop_id=prop.id,
                        token=token,
                        title=title,
                        doc_type=doc_type,
                        issuer=issuer,
                        issued_on=issued_on,
                    )
                    made.append((doc, title, langs))
                await _save_doc_titles(session, prop, made, actor)
                if len(made) == 1:
                    return f"Uploaded “{_html.escape(made[0][1])}”.", preview_token
                return f"Uploaded {len(made)} documents.", preview_token

            batch = []
            for i, up in enumerate(ups):
                got = await _read_upload(up)
                if not got:
                    raise ValueError(f"{_html.escape(up.filename)}: the file is empty.")
                title = nth("title", i) or _title_from_filename(got[0])
                doc_type = document_service.validate_doc_type(nth("doc_type", i) or "other")
                document_service.validate_file(got[0], got[1])
                issued_on = _form_day(nth("issued_on", i), f"{title}: date")
                batch.append((title[:200], doc_type, nth("issuer", i), issued_on, got, names(i)))
            made = []
            for title, doc_type, issuer, issued_on, got, langs in batch:
                doc = await document_service.admin_create_property_document(
                    session,
                    prop_id=prop.id,
                    title=title,
                    doc_type=doc_type,
                    filename=got[0],
                    data=got[1],
                    issuer=issuer,
                    issued_on=issued_on,
                )
                made.append((doc, title, langs))
            await _save_doc_titles(session, prop, made, actor)
            if len(batch) == 1:
                return f"Uploaded “{_html.escape(batch[0][0])}”.", preview_token
            return f"Uploaded {len(batch)} documents.", preview_token
        if action == "doc_edit":
            title = str(form.get("title") or "").strip()
            await document_service.update_document_details(
                session,
                doc_id=_uuid(form.get("doc_id")),
                title=title,
                doc_type=str(form.get("doc_type") or "other"),
                issuer=str(form.get("issuer") or ""),
                issued_on=_form_day(str(form.get("issued_on") or ""), "Date"),
                actor_id=actor,
            )
            if any(f"title_{lang}" in form for lang in listing_translation.LANGUAGES):
                doc_id = _uuid(form.get("doc_id"))
                langs = {
                    lang: " ".join(str(form.get(f"title_{lang}") or "").split())[:200]
                    for lang in listing_translation.LANGUAGES
                }
                new = _with_doc_titles(prop.content or {}, {str(doc_id): langs}, clear_blank=True)
                if new != (prop.content or {}):
                    await listing_service.apply_content(
                        session,
                        prop=prop,
                        new_content=new,
                        section=listing_translation.KEY,
                        actor_id=actor,
                    )
            return f"Saved “{_html.escape(title)}”.", preview_token
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
            new = listing_service.with_details(
                prop.content or {}, _form_with_kept_facts(form, prop)
            )
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
            saved_id = str(form.get("saved_developer_id") or "").strip()
            picked = (
                await developer_service.get_saved(session, _uuid(saved_id)) if saved_id else None
            )
            if logo_url is None and picked is not None and str(form.get("clear_logo") or "") != "1":
                # filled from a saved developer: its logo comes with it
                logo_url = (picked.profile or {}).get("logo") or None
            before = prop.content or {}
            old_name = str(developer_service.profile_of(before).get("name") or "")
            new = listing_service.with_developer(before, form, logo_url=logo_url)
            new_name = str(developer_service.profile_of(new).get("name") or "")
            # the developer's Arabic / French text (client 2026-11-19): a developer picked from
            # the saved list brings its own; one typed by name fills the languages not yet
            # translated; the text of the developer the card named before goes with it
            saved = await developer_service.find_saved(session, new_name)
            new = developer_service.with_versions(
                new,
                saved.versions if saved is not None else {},
                replace=picked is not None and saved is not None and saved.id == picked.id,
                drop_missing=developer_slug(old_name) != developer_slug(new_name),
            )
            came = [
                name
                for lang, name in listing_translation.LANGUAGES.items()
                if (saved is not None and (saved.versions or {}).get(lang))
                and developer_service.versions_in(new).get(lang)
                != developer_service.versions_in(before).get(lang)
            ]
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="developer", actor_id=actor
            )
            await developer_service.remember(
                session,
                developer_service.profile_of(new),
                actor_id=actor,
                versions=developer_service.versions_in(new),
            )
            if came:
                return (
                    f"Developer saved, with its {' and '.join(came)} version"
                    f"{'s' if len(came) > 1 else ''} from the saved developer.",
                    preview_token,
                )
            return "Developer saved.", preview_token
        if action == "save_spv":
            names = [f.name for f in listing_service.fields_in(listing_service.GROUP_SPV)]
            data = listing_service.parse_core(form, names, model=prop.model)
            await listing_service.update_core(session, prop=prop, data=data, actor_id=actor)
            new = listing_service.with_spv(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="spv", actor_id=actor
            )
            return "SPV & legal structure saved.", preview_token
        if action == "save_rows":
            section = str(form.get("section") or "")
            if section not in listing_service.ROW_SECTIONS:
                raise ValueError("That section is not recognised. Please reload the page.")
            new = listing_service.with_rows(prop.content or {}, form, section)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section=section, actor_id=actor
            )
            return f"{listing_service.ROW_LABELS[section]} saved.", preview_token
        if action == "save_valuation":
            before = dict((prop.content or {}).get("valuation") or {})
            new = listing_service.with_valuation(prop.content or {}, form)
            after = dict(new.get("valuation") or {})
            raw_price = str(form.get("valuation_unit_price") or "").strip()
            changed = any(
                before.get(k) != after.get(k)
                for k in ("provider", "reportDate", "value", "impactNote", "summary")
            )
            if (changed or raw_price) and any(
                after.get(k) for k in ("provider", "reportDate", "value")
            ):
                # the day of this valuation: the quarterly reminder counts from it
                after["recordedOn"] = dt.datetime.now(dt.UTC).date().isoformat()
                new["valuation"] = after
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="valuation", actor_id=actor
            )
            if not raw_price:
                return "Valuation saved.", preview_token
            # adopted as the unit price in the same step (client letter, 2026-11-18): the price
            # history, the repricing and the notice to every holder, as on Unit prices
            old_price = decimal.Decimal(prop.unit_price)
            note = ", ".join(str(x) for x in (after.get("provider"), after.get("reportDate")) if x)
            await price_service.record_price(
                session,
                property_id=prop.id,
                price=raw_price,
                label=valuation_service.PRICE_LABEL,
                note=note or None,
                actor_id=actor,
                confirm_large=str(form.get("confirm_large") or "") == "1",
            )
            return (
                f"Valuation saved and adopted as the unit price: {price_service.usd(old_price)} "
                f"to {price_service.usd(decimal.Decimal(prop.unit_price))}. Every holder and "
                "installment payer is told by email and in the app.",
                preview_token,
            )
        if action == "save_insurance":
            new = listing_service.with_insurance(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="insurance", actor_id=actor
            )
            return "Insurance saved.", preview_token
        if action == "save_legal_dd":
            new = listing_service.with_legal_due_diligence(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="legalDueDiligence", actor_id=actor
            )
            return "Legal due diligence saved.", preview_token
        if action == "save_construction_status":
            new = listing_service.with_construction_status(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="construction", actor_id=actor
            )
            return "Construction status saved.", preview_token
        if action == "save_cashflow":
            new = listing_service.with_cashflow(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="cashflow", actor_id=actor
            )
            return "Cash flow notes saved.", preview_token
        if action == "save_compliance":
            new = listing_service.with_compliance(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="compliance", actor_id=actor
            )
            return "Compliance points saved.", preview_token
        if action == "save_terms":
            new = listing_service.with_terms(prop.content or {}, form)
            await listing_service.apply_content(
                session, prop=prop, new_content=new, section="terms", actor_id=actor
            )
            return "Terms saved.", preview_token
        if action == "save_translation":
            lang = str(form.get("lang") or "")
            request.state.translation_open = lang
            milestones = await listing_service.list_milestones(session, prop.id)
            docs = (
                (await session.execute(select(Document).where(Document.property_id == prop.id)))
                .scalars()
                .all()
            )
            prices = await price_service._rows(session, prop.id)
            new = listing_translation_form.with_version(
                prop, form, lang, milestones, list(docs), prices
            )
            await listing_service.apply_content(
                session,
                prop=prop,
                new_content=new,
                section=listing_translation.KEY,
                actor_id=actor,
            )
            # the developer's text in this language is kept with the saved developer, for the
            # next listing that picks it (client 2026-11-19)
            await developer_service.remember_version(session, new, lang, actor_id=actor)
            return f"{listing_translation.LANGUAGES[lang]} version saved.", preview_token
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


def _doc_titles(content: dict) -> dict[str, dict[str, str]]:
    """{document id: {lang: name}} of the listing's Arabic / French document names."""
    out: dict[str, dict[str, str]] = {}
    for lang in listing_translation.LANGUAGES:
        docs = listing_translation.version(content, lang).get("documents")
        for doc_id, cells in (docs if isinstance(docs, dict) else {}).items():
            if isinstance(cells, dict) and cells.get("title"):
                out.setdefault(str(doc_id), {})[lang] = str(cells["title"])
    return out


def _with_doc_titles(
    content: dict, titles: dict[str, dict[str, str]], *, clear_blank: bool = False
) -> dict:
    """The listing's content with these documents' Arabic / French names (the same place the
    translations card keeps them). A blank name is left alone, or removed with ``clear_blank``."""
    new = copy.deepcopy(content or {})
    versions = new.get(listing_translation.KEY)
    versions = versions if isinstance(versions, dict) else {}
    for doc_id, by_lang in titles.items():
        for lang in listing_translation.LANGUAGES:
            name = (by_lang.get(lang) or "").strip()
            if not name and not clear_blank:
                continue
            version = versions.get(lang) if isinstance(versions.get(lang), dict) else {}
            docs = version.get("documents") if isinstance(version.get("documents"), dict) else {}
            if name:
                docs[str(doc_id)] = {"title": name}
            else:
                docs.pop(str(doc_id), None)
            if docs:
                version["documents"] = docs
            else:
                version.pop("documents", None)
            if version:
                versions[lang] = version
            else:
                versions.pop(lang, None)
    new[listing_translation.KEY] = versions
    if not versions:
        new.pop(listing_translation.KEY, None)
    return new


async def _save_doc_titles(session, prop: Property, made: list, actor) -> None:
    """Keep the Arabic / French names typed next to the files just uploaded."""
    titles = {str(doc.id): langs for doc, _title, langs in made if any(langs.values())}
    if not titles:
        return
    await listing_service.apply_content(
        session,
        prop=prop,
        new_content=_with_doc_titles(prop.content or {}, titles),
        section=listing_translation.KEY,
        actor_id=actor,
    )


def _title_from_filename(name: str) -> str:
    """A document's title when none is typed: its file name without the extension, with
    "_" / "-" as spaces ("valuation_report-2026.pdf" -> "valuation report 2026")."""
    stem = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = stem.rsplit(".", 1)[0] if "." in stem else stem
    return " ".join(stem.replace("_", " ").replace("-", " ").split()) or "Document"


def _form_day(raw: str, field: str):
    """A date field (YYYY-MM-DD) or None when blank."""
    import datetime as _dt

    s = (raw or "").strip()
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"{field}: must be a date.") from exc
