"""Under-construction page, restored design — every block is editable in the admin Listing
Editor and reaches the public API; nothing is invented.

The old page (deleted 2026-09-16) hard-coded most of its text. The restored page renders
each block only from these admin-entered sections, so the editor must be able to fill,
change and clear every one of them.
"""

# ruff: noqa: E501  (long literal form payloads keep the scenarios readable)
from __future__ import annotations

import uuid

import pytest

from app.core.errors import AppError
from app.services import listing_service

PW = "Passw0rd!23"
ADMIN_EMAIL = "uc-admin@x.com"


async def _admin(client, db) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": ADMIN_EMAIL, "password": PW, "full_name": "A"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=ADMIN_EMAIL)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    await client.post("/admin/login", data={"username": ADMIN_EMAIL, "password": PW})
    assert "session" in client.cookies


def _offplan(db, *, status="active", slug="uc-tower") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,slug,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'UC Tower',:s,'Dubai Creek','apartment','installment',:st,1000000,100,10000,10000,100)",
        id=pid,
        s=slug,
        st=status,
    )
    return pid


async def _post(client, pid, data) -> str:
    r = await client.post(f"/admin/listing/{pid}", data=data)
    assert r.status_code in (200, 303), r.text[:400]
    return r.text


async def _content(client, pid) -> dict:
    return (await client.get(f"/api/v1/properties/{pid}")).json()["content"]


@pytest.mark.asyncio
async def test_editor_shows_every_restored_block_for_an_offplan_listing(client, db):
    await _admin(client, db)
    pid = _offplan(db)
    html = (await client.get(f"/admin/listing/{pid}")).text
    for heading in (
        "Overview tab — ownership, scenarios &amp; risks",
        "Financials tab — projections, market, cash flow &amp; exit",
        "Construction status &amp; independent valuation",
        "Compliance points",
    ):
        assert heading in html, heading
    for field in (
        'name="ownership_structure"',
        'name="scenarios"',
        'name="risks"',
        'name="investment_structure"',
        'name="market_analysis"',
        'name="exit_mechanisms"',
        'name="rental_projection"',
        'name="valuation_provider"',
        'name="engineering_status"',
        'name="compliance"',
        'name="value_index"',
        'name="asset_holding"',
        'name="previous_projects"',
        'name="verified"',
    ):
        assert field in html, field


@pytest.mark.asyncio
async def test_row_sections_save_prefill_and_clear(client, db):
    await _admin(client, db)
    pid = _offplan(db)

    await _post(client, pid, {"action": "save_rows", "section": "risks", "risks": "Construction delay | Medium | Escrow and milestone audits\nMarket downturn | high"})
    await _post(client, pid, {"action": "save_rows", "section": "scenarios", "scenarios": "On-time delivery | About 18% by handover | positive"})
    await _post(client, pid, {"action": "save_rows", "section": "ownershipStructure", "ownership_structure": "Ownership vehicle | DIFC SPV"})
    await _post(client, pid, {"action": "save_rows", "section": "investmentStructure", "investment_structure": "Final settlement | On handover"})
    await _post(client, pid, {"action": "save_rows", "section": "marketAnalysis", "market_analysis": "Area pipeline | 12 active towers"})
    await _post(client, pid, {"action": "save_rows", "section": "exitMechanisms", "exit_mechanisms": "Secondary market | After handover | Sell units to other investors"})

    c = await _content(client, pid)
    assert c["risks"] == [
        {"label": "Construction delay", "level": "medium", "note": "Escrow and milestone audits"},
        {"label": "Market downturn", "level": "high"},
    ]
    assert c["scenarios"] == [{"label": "On-time delivery", "outcome": "About 18% by handover", "tone": "positive"}]
    assert c["ownershipStructure"] == [{"label": "Ownership vehicle", "value": "DIFC SPV"}]
    assert c["exitMechanisms"][0]["eta"] == "After handover"

    # the editor pre-fills the textarea with what was saved
    html = (await client.get(f"/admin/listing/{pid}")).text
    assert "Construction delay | medium | Escrow and milestone audits" in html

    # blank clears the block (the page hides it)
    await _post(client, pid, {"action": "save_rows", "section": "risks", "risks": ""})
    assert "risks" not in await _content(client, pid)

    audit = db(
        "SELECT COUNT(*) FROM audit_log WHERE entity_id=:p AND action='property.content.update'",
        p=pid,
    )[0][0]
    assert audit == 7


@pytest.mark.asyncio
async def test_bad_rows_are_refused_with_a_clear_message_and_nothing_saved(client, db):
    await _admin(client, db)
    pid = _offplan(db)
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "save_rows", "section": "risks", "risks": "Delay | extreme | x"},
    )
    assert r.status_code == 400
    assert "must be one of low, medium, high" in r.text
    assert "risks" not in await _content(client, pid)

    unknown = await client.post(
        f"/admin/listing/{pid}", data={"action": "save_rows", "section": "secret_owner_note"}
    )
    assert unknown.status_code == 400


@pytest.mark.asyncio
async def test_valuation_construction_cashflow_compliance_spv_and_developer(client, db):
    await _admin(client, db)
    pid = _offplan(db)
    await _post(client, pid, {"action": "save_valuation", "valuation_provider": "Knight Frank", "valuation_date": "June 2026", "valuation_value": "1,050,000", "valuation_impact": "+5% since foundation", "valuation_summary": "Supply is limited."})
    await _post(client, pid, {"action": "save_construction_status", "engineering_status": "Certified", "audit_status": "On track"})
    await _post(client, pid, {"action": "save_cashflow", "rental_projection": "Income after handover.", "costs": "", "exit_projection": "Secondary market."})
    await _post(client, pid, {"action": "save_compliance", "compliance": "SPV holds the title\n- Escrow-secured payments\n\nSPV holds the title"})
    await _post(client, pid, {"action": "save_spv", "jurisdiction": "DIFC", "asset_holding": "100% title held by the SPV", "investor_allocation": "Pro-rata certificates"})
    await _post(client, pid, {"action": "save_developer", "name": "Harbour Line", "verified": "1", "years_experience": "12", "on_time_delivery": "96", "previous_projects": "Marina Heights\nCreek Villas", "verifications": "Trade license verified"})

    c = await _content(client, pid)
    assert c["valuation"] == {
        "provider": "Knight Frank",
        "reportDate": "June 2026",
        "value": 1050000.0,
        "impactNote": "+5% since foundation",
        "summary": "Supply is limited.",
    }
    assert c["construction"] == {"engineeringStatus": "Certified", "auditStatus": "On track"}
    assert c["cashflow"] == {"rentalProjection": "Income after handover.", "exitProjection": "Secondary market."}
    assert c["compliance"] == ["SPV holds the title", "Escrow-secured payments"]
    assert c["spv"]["assetHolding"] == "100% title held by the SPV"
    assert c["spv"]["investorAllocation"] == "Pro-rata certificates"
    dev = c["developer"]
    assert (dev["verified"], dev["yearsExperience"], dev["onTimeDelivery"]) == (True, 12, 96.0)
    assert dev["previousProjects"] == ["Marina Heights", "Creek Villas"]

    # unticking the badge removes the claim
    await _post(client, pid, {"action": "save_developer", "name": "Harbour Line"})
    assert "verified" not in (await _content(client, pid))["developer"]


@pytest.mark.asyncio
async def test_milestone_price_index_is_editable_and_public(client, db):
    await _admin(client, db)
    pid = _offplan(db)
    await _post(client, pid, {"action": "ms_add", "title": "Foundation", "status": "in_progress", "progress_pct": "40", "target_date": "2026-12-31", "value_index": "105"})
    ms = (await client.get(f"/api/v1/properties/{pid}")).json()["milestones"]
    assert ms[0]["value_index"] == 105
    mid = db("SELECT id FROM property_milestones WHERE property_id=:p", p=pid)[0][0]
    await _post(client, pid, {"action": "ms_save", "ms_id": str(mid), "title": "Foundation", "status": "in_progress", "progress_pct": "40", "value_index": ""})
    ms = (await client.get(f"/api/v1/properties/{pid}")).json()["milestones"]
    assert ms[0]["value_index"] is None
    bad = await client.post(f"/admin/listing/{pid}", data={"action": "ms_add", "title": "X", "status": "planned", "value_index": "0"})
    assert bad.status_code == 400


def test_row_parser_rules():
    rows = listing_service.parse_rows(
        "A | b\n\n  C  |  d  ", "X", ("label", "value"), 5
    )
    assert rows == [{"label": "A", "value": "b"}, {"label": "C", "value": "d"}]
    with pytest.raises(AppError):
        listing_service.parse_rows("A|b\n" * 6, "X", ("label", "value"), 5)
    with pytest.raises(AppError):
        listing_service.parse_rows("A", "X", ("label", "value"), 5)
    assert listing_service.rows_to_text(rows, ("label", "value")) == "A | b\nC | d"
    assert listing_service.parse_lines("• one\n- two\none", "L", 5) == ["one", "two"]
