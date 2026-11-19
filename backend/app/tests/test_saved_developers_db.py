"""Client letter (2026-11-18): the admin panel keeps each developer's full profile once; a new
listing fills its developer card from a saved developer instead of typing it again."""

from __future__ import annotations

import json

import pytest

from app.tests.test_listing_step2_db import _admin_session, _seed_property


def _content(db, pid):
    raw = db("SELECT content FROM properties WHERE id=:p", p=pid)[0][0]
    return raw if isinstance(raw, dict) else json.loads(raw)


def _saved(db):
    return db("SELECT id, slug, name, profile FROM saved_developers ORDER BY name")


EMAAR = {
    "action": "save_developer",
    "name": "Emaar Properties",
    "rating": "4.8",
    "projects_completed": "120",
    "about": "Founded in 1997.",
    "previous_projects": "Burj Khalifa\nDubai Hills Estate",
    "verified": "1",
}


@pytest.mark.asyncio
async def test_saving_a_listings_developer_keeps_it_for_the_next_listing(client, db):
    await _admin_session(client, db)
    first = _seed_property(db, slug="dev-first")
    r = await client.post(f"/admin/listing/{first}", data=EMAAR)
    assert "Developer saved." in r.text
    saved = _saved(db)
    assert [(s[1], s[2]) for s in saved] == [("emaar-properties", "Emaar Properties")]
    profile = saved[0][3]
    assert profile["rating"] == 4.8 and profile["previousProjects"] == [
        "Burj Khalifa",
        "Dubai Hills Estate",
    ]

    # the next listing offers it, and saving with it fills the card (the form sends the fields)
    second = _seed_property(db, slug="dev-second")
    page = (await client.get(f"/admin/listing/{second}")).text
    assert "Fill from a saved developer" in page and "Emaar Properties" in page
    form = {**EMAAR, "saved_developer_id": str(saved[0][0])}
    r = await client.post(f"/admin/listing/{second}", data=form)
    assert _content(db, second)["developer"]["name"] == "Emaar Properties"
    assert len(_saved(db)) == 1  # the same developer, not a second one


@pytest.mark.asyncio
async def test_a_saved_logo_comes_with_the_saved_developer(client, db):
    await _admin_session(client, db)
    db(
        "INSERT INTO saved_developers (slug, name, profile) VALUES ('damac', 'Damac', "
        "CAST(:p AS jsonb))",
        p=json.dumps({"name": "Damac", "logo": "/api/v1/files/developers/damac.png"}),
    )
    dev_id = _saved(db)[0][0]
    pid = _seed_property(db, slug="dev-logo")
    await client.post(
        f"/admin/listing/{pid}",
        data={"action": "save_developer", "name": "Damac", "saved_developer_id": str(dev_id)},
    )
    assert _content(db, pid)["developer"]["logo"] == "/api/v1/files/developers/damac.png"
    # "remove logo" wins over the saved one
    other = _seed_property(db, slug="dev-nologo")
    await client.post(
        f"/admin/listing/{other}",
        data={
            "action": "save_developer",
            "name": "Damac",
            "saved_developer_id": str(dev_id),
            "clear_logo": "1",
        },
    )
    assert "logo" not in _content(db, other)["developer"]


@pytest.mark.asyncio
async def test_the_developers_page_adds_edits_applies_and_removes(client, db):
    await _admin_session(client, db)
    r = await client.post(
        "/admin/developers/new",
        data={"name": "Sobha Realty", "rating": "4.5", "website": "sobha.com"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    dev_id, slug, name, profile = _saved(db)[0]
    assert (slug, profile["website"]) == ("sobha-realty", "https://sobha.com")
    listing = _seed_property(db, slug="dev-sobha")
    await client.post(
        f"/admin/listing/{listing}", data={"action": "save_developer", "name": "Sobha Realty"}
    )

    page = (await client.get("/admin/developers")).text
    assert "Sobha Realty" in page and f"/admin/developers/profile/{dev_id}" in page

    # edit without applying: the listing keeps its copy
    await client.post(
        f"/admin/developers/profile/{dev_id}",
        data={"action": "save", "name": "Sobha Realty", "rating": "4.9"},
    )
    assert _content(db, listing)["developer"].get("rating") is None
    # apply: the listing takes the saved profile
    r = await client.post(
        f"/admin/developers/profile/{dev_id}",
        data={"action": "save", "name": "Sobha Realty", "rating": "4.9", "apply": "1"},
    )
    assert "1 listing(s) updated." in r.text
    assert _content(db, listing)["developer"]["rating"] == 4.9
    assert db("SELECT count(*) FROM audit_log WHERE action='developer.updated'")[0][0] >= 2

    # a bad value is refused and nothing changes
    r = await client.post(
        f"/admin/developers/profile/{dev_id}",
        data={"action": "save", "name": "Sobha Realty", "rating": "9"},
    )
    assert r.status_code == 400
    assert _saved(db)[0][3]["rating"] == 4.9

    r = await client.post(
        f"/admin/developers/profile/{dev_id}", data={"action": "delete"}, follow_redirects=False
    )
    assert r.status_code == 303 and _saved(db) == []
    assert _content(db, listing)["developer"]["name"] == "Sobha Realty"  # listings keep theirs
