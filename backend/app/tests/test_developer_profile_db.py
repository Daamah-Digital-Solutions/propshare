"""Public developer profile — the page the "View Profile" button on a property opens.

What must hold:
  * every property carries a ``developer_slug`` the SPA can link to, built by the same
    function that resolves the profile (so the link can never 404 on a public listing);
  * the profile groups every PUBLIC listing with that developer name and nothing else —
    drafts, under-review and closed listings of the same developer never leak through;
  * the figures are live (listings, active/funded, raised, investors), the descriptive
    facts come only from what the admin entered, and nothing is invented;
  * a listing without a developer block falls back to its owner's name, like the card does;
  * Arabic names keep their letters; unknown slugs 404.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.services.listing_service import with_developer


def _owner(db, email: str, name: str) -> str:
    uid = str(uuid.uuid4())
    db(
        "INSERT INTO users (id,email,password_hash,full_name,email_verified) "
        "VALUES (:i,:e,'x',:n,true)",
        i=uid,
        e=email,
        n=name,
    )
    return uid


def _prop(
    db,
    *,
    title: str,
    status: str = "active",
    developer: dict | None = None,
    owner: str | None = None,
    funded: float = 0,
    investors: int = 0,
) -> str:
    pid = str(uuid.uuid4())
    content = {"developer": developer} if developer else {}
    db(
        "INSERT INTO properties (id,owner_id,title,slug,location,city,country,property_type,model,"
        "status,total_value,unit_price,total_units,available_units,minimum_investment,"
        "expected_yield,funded_amount,investors_count,content) VALUES "
        "(:id,:o,:t,:s,'Dubai Marina, Dubai','Dubai','UAE','apartment','ready-income',:st,"
        "100000,100,1000,1000,200,7,:f,:inv,CAST(:c AS jsonb))",
        id=pid,
        o=owner,
        t=title,
        s=f"{title.lower().replace(' ', '-')}-{pid[:6]}",
        st=status,
        f=funded,
        inv=investors,
        c=json.dumps(content),
    )
    return pid


EMAAR = {
    "name": "Emaar Properties",
    "logo": "/assets/emaar.png",
    "about": "Founded in 1997.\n\nDelivered 120 projects.",
    "website": "https://www.emaar.com",
    "rating": 4.6,
    "projectsCompleted": 120,
}


@pytest.mark.asyncio
async def test_property_links_to_its_developer_and_the_profile_resolves(client, db):
    pid = _prop(db, title="Marina Loft", developer=EMAAR, funded=25000, investors=12)
    detail = (await client.get(f"/api/v1/properties/{pid}")).json()
    assert detail["developer_slug"] == "emaar-properties"

    r = await client.get("/api/v1/developers/emaar-properties")
    assert r.status_code == 200, r.text
    prof = r.json()
    assert prof["name"] == "Emaar Properties"
    assert prof["about"] == "Founded in 1997.\n\nDelivered 120 projects."
    assert prof["website"] == "https://www.emaar.com"
    assert (prof["rating"], prof["projects_completed"]) == (4.6, 120)
    assert [p["id"] for p in prof["properties"]] == [pid]
    assert prof["stats"] == {
        "listings": 1,
        "active": 1,
        "funded": 0,
        "total_raised": 25000.0,
        "investors": 12,
    }


@pytest.mark.asyncio
async def test_profile_groups_public_listings_and_hides_everything_else(client, db):
    a = _prop(db, title="Tower A", developer=EMAAR, funded=10000, investors=3)
    b = _prop(db, title="Tower B", status="funded", developer={"name": "EMAAR  properties"},
              funded=100000, investors=40)
    _prop(db, title="Secret Draft", status="draft", developer=EMAAR)
    _prop(db, title="Pending", status="under_review", developer=EMAAR)
    _prop(db, title="Other Dev", developer={"name": "Damac"})

    prof = (await client.get("/api/v1/developers/emaar-properties")).json()
    ids = {p["id"] for p in prof["properties"]}
    assert ids == {a, b}  # spelling variants of the same name group together
    titles = {p["title"] for p in prof["properties"]}
    assert "Secret Draft" not in titles and "Pending" not in titles
    assert prof["stats"]["active"] == 1 and prof["stats"]["funded"] == 1
    assert prof["stats"]["total_raised"] == 110000.0
    assert prof["stats"]["investors"] == 43


@pytest.mark.asyncio
async def test_a_developer_with_only_drafts_has_no_public_profile(client, db):
    _prop(db, title="Hidden", status="draft", developer={"name": "Stealth Builders"})
    r = await client.get("/api/v1/developers/stealth-builders")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "DEVELOPER_NOT_FOUND"


@pytest.mark.asyncio
async def test_listing_without_developer_block_falls_back_to_the_owner(client, db):
    owner = _owner(db, "dev@owner.com", "Horizon Developments")
    pid = _prop(db, title="Horizon One", owner=owner)
    detail = (await client.get(f"/api/v1/properties/{pid}")).json()
    assert detail["developer_name"] == "Horizon Developments"
    assert detail["developer_slug"] == "horizon-developments"

    prof = (await client.get("/api/v1/developers/horizon-developments")).json()
    assert prof["name"] == "Horizon Developments"
    # nothing was entered for this developer, so nothing is shown
    assert (prof["about"], prof["website"], prof["rating"], prof["logo"]) == (None,) * 4


@pytest.mark.asyncio
async def test_arabic_developer_names_keep_their_letters(client, db):
    pid = _prop(db, title="Riyadh Heights", developer={"name": "إعمار العقارية"})
    slug = (await client.get(f"/api/v1/properties/{pid}")).json()["developer_slug"]
    assert slug == "إعمار-العقارية"
    r = await client.get(f"/api/v1/developers/{slug}")
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "إعمار العقارية"


@pytest.mark.asyncio
async def test_unknown_slug_is_404(client, db):
    assert (await client.get("/api/v1/developers/nobody-at-all")).status_code == 404


def test_admin_developer_fields_are_validated():
    from app.core.errors import AppError

    out = with_developer({}, {"name": "E", "about": " a \n\n\n\n b ", "website": "emaar.com"})
    assert out["developer"]["about"] == "a\n\nb"
    assert out["developer"]["website"] == "https://emaar.com"
    for bad in ("javascript:alert(1)", "notaurl", "ftp://files.example.com"):
        with pytest.raises(AppError):
            with_developer({}, {"name": "E", "website": bad})
    with pytest.raises(AppError):
        with_developer({}, {"name": "E", "about": "x" * 1201})
