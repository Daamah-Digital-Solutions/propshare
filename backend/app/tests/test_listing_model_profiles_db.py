"""Model-aware listing admin (approved plan: four profiles, hidden models, consistency, checklist).

Each test pins a gap found in the review:
  * the New listing form and the editor were identical for every ownership model;
  * option / future / shared-development could be created although none of their mechanics
    exist (they silently behaved like an installment purchase);
  * total units were typed by hand (the client's real draft: $1,220,000 at $100 = 100 units);
  * the minimum could be below one unit or not a whole number of units ($10 at $100);
  * listings could be published with blank returns, which the public page renders as "0%"
    (PropertyDetails shows yield, appreciation and total return for EVERY model; the
    marketplace card shows the yield);
  * off-plan listings were not told their installment terms are the platform-wide plan.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import re
import uuid

import pytest

from app.services import listing_service as ls

PW = "Passw0rd!23"


async def _panel(client, db, email="profiles-admin@x.com", role="admin") -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "A"}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db(
        "INSERT INTO user_roles (user_id, role) VALUES (:i,:r) ON CONFLICT DO NOTHING",
        i=uid,
        r=role,
    )
    db("UPDATE users SET active_role=:r WHERE id=:i", i=uid, r=role)
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert "session" in client.cookies
    return str(uid)


def _seed(
    db,
    *,
    model="installment",
    status="draft",
    tv=1_000_000,
    up=100,
    units=10_000,
    minimum=500,
    yield_=7.5,
    appr=3,
    total=10.5,
    completion="2027-06-30",
    slug=None,
) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,slug,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment,expected_yield,"
        "capital_appreciation,total_return,expected_completion) VALUES "
        "(:id,'Profile Tower',:s,'Dubai','apartment',:m,:st,:tv,:up,:u,:u,:mn,:y,:a,:t,:c)",
        id=pid,
        s=slug or f"profile-{pid[:8]}",
        m=model,
        st=status,
        tv=tv,
        up=up,
        u=units,
        mn=minimum,
        y=yield_,
        a=appr,
        t=total,
        c=completion,
    )
    return pid


def _wrapper(html: str, name: str) -> str:
    m = re.search(rf'<div class="f" data-field="{name}"( hidden)?>', html)
    assert m, f"no wrapper for {name}"
    return m.group(0)


def _field_label(html: str, name: str) -> str:
    m = re.search(
        rf'<div class="f" data-field="{name}"[^>]*>\s*<label[^>]*><span class="txt">([^<]*)</span>',
        html,
    )
    assert m, name
    return m.group(1)


FORM = {
    "title": "Profiles Tower",
    "model": "installment",
    "property_type": "apartment",
    "description": "Off-plan tower.",
    "location": "Business Bay, Dubai",
    "total_value": "3200000",
    "unit_price": "100",
    "minimum_investment": "500",
    "expected_yield": "8",
    "capital_appreciation": "4",
    "total_return": "",
}


# --- 1. the rules themselves ---------------------------------------------------------------- #
def test_profile_rules_match_the_approved_table():
    R = ls.form_rules_json()
    assert R["profiles"] == {
        "ready-income": "ready_single",
        "ready-portfolio": "ready_portfolio",
        "installment": "offplan_single",
        "construction-portfolio": "offplan_portfolio",
        "future": "offplan_single",
        "option": "offplan_single",
        "shared-development": "offplan_single",
    }
    f = R["fields"]
    for p in ls.ALL_PROFILES:
        assert f["total_units"][p]["required"] is False  # calculated, never typed
        assert f["target_yield"][p]["show"] is False  # mirrored from the yield
        for name in (
            "expected_yield",
            "capital_appreciation",
            "total_value",
            "unit_price",
            "minimum_investment",
        ):
            assert f[name][p]["show"] and f[name][p]["required"], (name, p)
        assert f["total_return"][p]["show"] and not f["total_return"][p]["required"]
    for p in ls.READY_PROFILES:
        assert f["expected_completion"][p]["show"] is False
        assert f["expected_yield"][p]["label"] == "Expected annual rental yield (%)"
    for p in ls.OFFPLAN_PROFILES:
        assert f["expected_completion"][p]["show"] is True
        assert (
            f["expected_yield"][p]["label"] == "Expected rental yield after handover (% per year)"
        )
    for fact in ("bedrooms", "bathrooms", "parking", "amenities"):
        assert R["facts"][fact] == {
            "ready_single": True,
            "ready_portfolio": False,
            "offplan_single": True,
            "offplan_portfolio": False,
        }
    assert R["facts"]["area"] == dict.fromkeys(ls.ALL_PROFILES, True)
    assert ls.MODEL_LABELS["installment"] == "Off-plan, paid in installments"


# --- 2. adaptive New listing form (server render per model + live-rules payload) ------------ #
@pytest.mark.asyncio
@pytest.mark.parametrize("model", ls.ENABLED_MODELS)
async def test_new_listing_form_adapts_to_each_model(client, db, model):
    await _panel(client, db)
    html = (await client.get(f"/admin/listing/new?model={model}")).text
    profile = ls.profile_of(model)
    offplan = profile in ls.OFFPLAN_PROFILES
    # completion date + installment notice only for off-plan
    assert ("hidden" in _wrapper(html, "expected_completion")) is (not offplan)
    notice = re.search(
        r'<div class="note" data-profiles="offplan_single offplan_portfolio"( hidden)?>', html
    )
    assert notice and (notice.group(1) is None) is offplan
    # label and required star follow the profile
    assert _field_label(html, "expected_yield") == ls.CORE_BY_NAME["expected_yield"].label_for(
        profile
    )
    for name in ("expected_yield", "capital_appreciation", "minimum_investment"):
        block = html[html.index(f'data-field="{name}"') :]
        assert '<span class="req"' in block[: block.index("</label>")], name
    # the one-line explanation of the selected model
    assert ls.MODEL_EXPLAIN[model].replace("'", "&#39;") in html
    # units are shown read-only (never submitted)
    assert re.search(r'<input type="text" id="f_total_units"[^>]*readonly', html)
    assert 'name="total_units"' not in html
    # the page embeds exactly the server rules, so the live switch cannot drift from validation
    payload = re.search(
        r'<script id="listing-rules" type="application/json">(.*?)</script>', html, re.S
    ).group(1)
    assert json.loads(payload) == json.loads(json.dumps(ls.form_rules_json()))


@pytest.mark.asyncio
async def test_hidden_models_never_appear_in_admin_dropdowns(client, db):
    """Fails if option / future / shared-development is offered anywhere in the admin."""
    await _panel(client, db)
    pid = _seed(db, model="ready-income", completion=None)
    pages = {
        "new listing": (await client.get("/admin/listing/new")).text,
        "listing editor": (await client.get(f"/admin/listing/{pid}")).text,
        "raw create form": (await client.get("/admin/property/create")).text,
        "raw edit form": (await client.get(f"/admin/property/edit/{pid}")).text,
    }
    for page, html in pages.items():
        for select in re.findall(r'<select[^>]*name="model"[^>]*>(.*?)</select>', html, re.S):
            offered = set(re.findall(r'<option[^>]*value="([^"]*)"', select)) - {""}
            assert offered <= set(ls.ENABLED_MODELS), (page, offered)
            assert offered == set(ls.ENABLED_MODELS), (page, offered)
        assert re.search(r'<select[^>]*name="model"', html), f"{page}: no model dropdown"


# --- 3. hidden models rejected everywhere, with a clear message ----------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize("model", ls.HIDDEN_MODELS)
async def test_hidden_models_rejected_on_every_create_and_switch_path(client, db, model):
    await _panel(client, db)
    msg = f"The '{model}' ownership model is not available"
    html_msg = msg.replace("'", "&#39;")
    r = await client.post("/admin/listing/new", data={**FORM, "model": model})
    assert r.status_code == 400 and html_msg in r.text
    pid = _seed(db, model="installment")
    r = await client.post(
        f"/admin/listing/{pid}", data={"action": "save_core", **FORM, "model": model}
    )
    assert r.status_code == 400 and html_msg in r.text
    assert db("SELECT model FROM properties WHERE id=:i", i=pid)[0][0] == "installment"
    # raw SQLAdmin form (dropdown refuses the value before our hook)
    r = await client.post(
        f"/admin/property/edit/{pid}",
        data={
            "title": "X",
            "slug": "x-slug",
            "model": model,
            "property_type": "apartment",
            "location": "Dubai",
            "total_value": "1000000",
            "unit_price": "100",
            "total_units": "10000",
            "minimum_investment": "500",
            "content": "{}",
            "fees": "{}",
        },
    )
    assert r.status_code == 400
    assert db("SELECT model FROM properties WHERE id=:i", i=pid)[0][0] == "installment"
    # owner API
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"own-{model}@x.com", "password": PW, "full_name": "O"},
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=f"own-{model}@x.com")[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'owner')", i=uid)
    db("UPDATE users SET active_role='owner' WHERE id=:i", i=uid)
    tok = (
        await client.post(
            "/api/v1/auth/login", json={"email": f"own-{model}@x.com", "password": PW}
        )
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    body = {
        "title": "Owner Tower",
        "property_type": "apartment",
        "location": "Dubai",
        "total_value": 1000000,
        "unit_price": 100,
    }
    r = await client.post("/api/v1/properties", json={**body, "model": model}, headers=h)
    assert (
        r.status_code == 422
        and r.json()["error"]["code"] == "MODEL_NOT_AVAILABLE"
        and msg in r.json()["error"]["message"]
    )
    ok = await client.post("/api/v1/properties", json={**body, "model": "installment"}, headers=h)
    assert ok.status_code == 201, ok.text
    r = await client.patch(
        f"/api/v1/properties/{ok.json()['id']}", json={"model": model}, headers=h
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "MODEL_NOT_AVAILABLE"
    assert reg.status_code == 201


@pytest.mark.asyncio
async def test_legacy_hidden_model_listing_must_choose_a_model_to_publish(client, db):
    await _panel(client, db)
    pid = _seed(db, model="option")
    html = (await client.get(f"/admin/listing/{pid}")).text
    assert '<option value="" selected>Choose an available model</option>' in html
    assert "Ownership model: &#39;option&#39; is not available" in html
    r = await client.post(f"/admin/listing/{pid}", data={"action": "publish"})
    assert r.status_code == 400 and "cannot be published yet" in r.text
    assert db("SELECT status FROM properties WHERE id=:i", i=pid)[0][0] == "draft"


# --- 4. consistency checks ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_units_are_calculated_and_mismatch_is_explained(client, db):
    await _panel(client, db)
    r = await client.post(
        "/admin/listing/new", data={**FORM, "total_value": "1000050"}, follow_redirects=False
    )
    assert r.status_code == 400
    assert (
        "Total units: $1,000,050 ÷ $100 is not a whole number of units (10000.50). "
        "Use $1,000,000 or $1,000,100 as the total property value, or change the price per unit."
    ) in r.text
    # typed units are ignored: the server calculates them
    r = await client.post(
        "/admin/listing/new", data={**FORM, "total_units": "100"}, follow_redirects=False
    )
    assert r.status_code == 303
    pid = r.headers["location"].split("/admin/listing/")[1].split("?")[0]
    assert db("SELECT total_units, available_units FROM properties WHERE id=:i", i=pid)[0] == (
        32000,
        32000,
    )
    # changing the price recalculates units on save
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "save_core", **FORM, "unit_price": "200", "minimum_investment": "1000"},
    )
    assert r.status_code == 200, r.text[:400]
    assert db("SELECT total_units, available_units FROM properties WHERE id=:i", i=pid)[0] == (
        16000,
        16000,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "minimum,expected",
    [
        (
            "10",
            "Minimum investment: $10 is less than one unit ($100). Use $100 or a multiple of $100.",
        ),
        ("250", "Minimum investment: $250 buys only 2 whole units at $100 each. Use $200 or $300."),
        ("150", "Minimum investment: $150 buys only 1 whole unit at $100 each. Use $100 or $200."),
        (
            "4000000",
            "Minimum investment: $4,000,000 is more than the total property value ($3,200,000).",
        ),
    ],
)
async def test_minimum_must_be_whole_units(client, db, minimum, expected):
    await _panel(client, db)
    r = await client.post("/admin/listing/new", data={**FORM, "minimum_investment": minimum})
    assert r.status_code == 400 and expected in r.text


@pytest.mark.asyncio
async def test_total_return_is_calculated_and_mismatch_warns_without_blocking(client, db):
    await _panel(client, db)
    r = await client.post("/admin/listing/new", data=FORM, follow_redirects=False)
    pid = r.headers["location"].split("/admin/listing/")[1].split("?")[0]
    ey, ty, tr = db(
        "SELECT expected_yield, target_yield, total_return FROM properties WHERE id=:i", i=pid
    )[0]
    assert (float(ey), float(ty), float(tr)) == (
        8.0,
        8.0,
        12.0,
    )  # blank -> yield + appreciation; target mirrored
    r = await client.post(
        f"/admin/listing/{pid}", data={"action": "save_core", **FORM, "total_return": "15"}
    )
    assert r.status_code == 200 and "Listing details saved" in r.text
    warning = (
        "Total expected return is 15% but expected rental yield (8%) plus capital appreciation (4%) "
        "is 12%. Check the figures: the property page shows all three side by side."
    )
    assert r.text.count(warning) == 2  # save banner + checklist
    assert float(db("SELECT total_return FROM properties WHERE id=:i", i=pid)[0][0]) == 15.0


@pytest.mark.asyncio
async def test_zero_returns_rejected_on_the_form(client, db):
    await _panel(client, db)
    r = await client.post("/admin/listing/new", data={**FORM, "capital_appreciation": "0"})
    assert r.status_code == 400
    assert (
        "Expected capital appreciation (% per year): must be greater than 0. The property page would show 0%."
        in r.text
    )
    r = await client.post("/admin/listing/new", data={**FORM, "expected_yield": ""})
    assert "Expected rental yield after handover (% per year): this field is required." in r.text


# --- 5. publish checklist on every publish path -------------------------------------------- #
CLIENT_DRAFT_BLOCKERS = [
    "Total units: the listing has 100 units but $1,220,000 ÷ $100 = 12,200. Open Listing details and press Save to recalculate.",
    "Minimum investment: $10 is less than one unit ($100). Use $100 or a multiple of $100.",
    "Expected rental yield after handover (% per year): is empty. The property page would show 0%. Enter a figure greater than 0 under Listing details.",
    "Expected capital appreciation: is empty. The property page would show 0%. Enter a figure greater than 0 under Listing details.",
    "Total expected return: is empty. The property page would show 0%. Enter a figure greater than 0 under Listing details.",
    "Expected completion date: is empty. Off-plan listings must show when the property is expected to be handed over. Set it under Construction and timeline.",
]


@pytest.mark.asyncio
async def test_client_draft_shape_is_blocked_with_exact_messages_on_every_path(client, db):
    """Same figures as the client's production draft (not the row itself)."""
    uid = await _panel(client, db)
    pid = _seed(
        db,
        tv=1_220_000,
        up=100,
        units=100,
        minimum=10,
        yield_=None,
        appr=None,
        total=None,
        completion=None,
    )
    html = (await client.get(f"/admin/listing/{pid}")).text
    block = html[html.index("data-blockers") : html.index("</div>", html.index("data-blockers"))]
    assert re.findall(r"<li>(.*?)</li>", block) == [
        b.replace("'", "&#39;") for b in CLIENT_DRAFT_BLOCKERS
    ]
    # editor publish
    r = await client.post(f"/admin/listing/{pid}", data={"action": "publish"})
    assert (
        r.status_code == 400 and "This listing cannot be published yet. Fix these first:" in r.text
    )
    # SQLAdmin bulk action
    r = await client.get(f"/admin/property/action/approve?pks={pid}")
    assert r.status_code == 409 and "Nothing was changed" in r.text
    # admin API
    login = await client.post(
        "/api/v1/auth/login", json={"email": "profiles-admin@x.com", "password": PW}
    )
    r = await client.post(
        f"/api/v1/admin/properties/{pid}/approve",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "PUBLISH_BLOCKED"
    assert r.json()["error"]["details"]["blockers"] == CLIENT_DRAFT_BLOCKERS
    assert db("SELECT status FROM properties WHERE id=:i", i=pid)[0][0] == "draft"
    assert uid
    # fixing everything through the editor makes it publishable
    fix = {
        **FORM,
        "total_value": "1220000",
        "minimum_investment": "100",
        "expected_yield": "7",
        "capital_appreciation": "3",
    }
    assert (
        await client.post(f"/admin/listing/{pid}", data={"action": "save_core", **fix})
    ).status_code == 200
    assert (
        await client.post(
            f"/admin/listing/{pid}",
            data={"action": "save_construction", "expected_completion": "2028-03-31"},
        )
    ).status_code == 200
    r = await client.post(f"/admin/listing/{pid}", data={"action": "publish"})
    assert r.status_code == 200 and "Published" in r.text, r.text[:500]
    assert db("SELECT status, total_units FROM properties WHERE id=:i", i=pid)[0] == (
        "active",
        12200,
    )


@pytest.mark.asyncio
async def test_ready_listing_needs_returns_but_not_a_completion_date(client, db):
    await _panel(client, db)
    pid = _seed(db, model="ready-income", completion=None)
    r = await client.post(f"/admin/listing/{pid}", data={"action": "publish"})
    assert r.status_code == 200 and "Published" in r.text
    pid2 = _seed(db, model="ready-portfolio", completion=None, total=0)
    r = await client.post(f"/admin/listing/{pid2}", data={"action": "publish"})
    assert (
        r.status_code == 400
        and "Total expected return: is 0. The property page would show 0%." in r.text
    )


@pytest.mark.asyncio
async def test_live_listing_with_investors_keeps_legacy_units_editable(client, db):
    uid = await _panel(client, db)
    pid = _seed(
        db,
        model="ready-income",
        status="active",
        tv=1_220_000,
        units=100,
        minimum=100,
        completion=None,
    )
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) VALUES (:u,:p,2,100,'purchase')",
        u=uid,
        p=pid,
    )
    form = {
        **FORM,
        "model": "ready-income",
        "total_value": "1220000",
        "minimum_investment": "100",
        "subtitle": "Now with a tagline",
    }
    r = await client.post(f"/admin/listing/{pid}", data={"action": "save_core", **form})
    assert r.status_code == 200 and "Listing details saved" in r.text, r.text[:400]
    assert db("SELECT total_units, subtitle FROM properties WHERE id=:i", i=pid)[0] == (
        100,
        "Now with a tagline",
    )
    r = await client.post(
        f"/admin/listing/{pid}", data={"action": "save_core", **form, "unit_price": "200"}
    )
    assert r.status_code == 400 and "locked" in r.text


# --- 6. editor sections per profile + live installment notice ------------------------------ #
@pytest.mark.asyncio
async def test_editor_sections_follow_the_profile_and_notice_reads_live_settings(client, db):
    await _panel(client, db)
    db(
        "INSERT INTO platform_settings (key, value) VALUES ('installment_fee_pct','3.5') ON CONFLICT (key) DO UPDATE SET value='3.5'"
    )
    ready = (
        await client.get(f"/admin/listing/{_seed(db, model='ready-income', completion=None)}")
    ).text
    port = (await client.get(f"/admin/listing/{_seed(db, model='construction-portfolio')}")).text
    assert re.search(
        r'<div class="card" data-profiles="offplan_single offplan_portfolio" hidden>\s*<h2>Construction',
        ready,
    )
    assert re.search(
        r'<div class="card" data-profiles="offplan_single offplan_portfolio">\s*<h2>Construction',
        port,
    )
    assert re.search(
        r'data-profiles="ready_single offplan_single" hidden data-field="bedrooms"', port
    )
    assert re.search(r'data-profiles="ready_single offplan_single" data-field="bedrooms"', ready)
    assert "Total area across all projects (sq ft)" in port
    notice = re.sub(r"\s+", " ", port[port.index("Standard installment plan") :])
    assert (
        "choose 6, 12, 18, 24 months, with a down payment of 30%, 25%, 20%, 15% respectively"
        in notice
    )
    assert (
        "An installment fee of 3.5% applies to the down payment and to each installment" in notice
    )


@pytest.mark.asyncio
async def test_hidden_facts_keep_their_stored_values(client, db):
    await _panel(client, db)
    pid = _seed(db, model="ready-income", completion=None)
    await client.post(
        f"/admin/listing/{pid}",
        data={"action": "save_facts", "bedrooms": "3", "area": "1000", "amenities": "Gym"},
    )
    db("UPDATE properties SET model='ready-portfolio' WHERE id=:i", i=pid)
    await client.post(f"/admin/listing/{pid}", data={"action": "save_facts", "area": "5000"})
    details = db("SELECT content FROM properties WHERE id=:i", i=pid)[0][0]["details"]
    assert details == {"bedrooms": 3, "area": 5000.0, "amenities": ["Gym"]}
