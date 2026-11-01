"""Arabic and French versions of a listing's written text (client, 2026-11-01): typed in the
admin Listing Editor, shown on the public pages in the language asked for, English when a box was
left blank, and never in the way of what the English listing does."""

# ruff: noqa: E501
from __future__ import annotations

import uuid

import pytest

from app.services import listing_translation as lt

PW = "Passw0rd!23"
ADMIN_EMAIL = "tr-admin@x.com"


async def _admin(client, db) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": ADMIN_EMAIL, "password": PW, "full_name": "A"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=ADMIN_EMAIL)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    await client.post("/admin/login", data={"username": ADMIN_EMAIL, "password": PW})
    assert "session" in client.cookies


def _listing(db, *, slug="tr-tower", status="active") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,slug,subtitle,description,location,country,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Creek Tower',:s,'Waterfront homes','A tower on the creek.','Dubai Creek','UAE','apartment',"
        "'installment',:st,1000000,100,10000,10000,100)",
        id=pid,
        s=slug,
        st=status,
    )
    return pid


async def _post(client, pid, **data) -> str:
    r = await client.post(f"/admin/listing/{pid}", data=data)
    assert r.status_code in (200, 303), r.text[:400]
    return r.text


async def _filled(client, db, pid) -> None:
    await _admin(client, db)
    await _post(
        client,
        pid,
        action="save_developer",
        name="Crest Developments",
        about="Founded in 1997.",
        previous_projects="Marina Heights\nCreek Villas",
        rating="4.5",
    )
    await _post(
        client,
        pid,
        action="save_rows",
        section="risks",
        risks="Construction delay | medium | Escrow audits\nMarket risk | low | Long lease",
    )
    await _post(
        client,
        pid,
        action="save_rows",
        section="scenarios",
        scenarios="On time | About 18% | positive",
    )
    await _post(client, pid, action="save_facts", amenities="Gym\nPool")


async def _get(client, pid, lang=None) -> dict:
    q = f"?lang={lang}" if lang else ""
    r = await client.get(f"/api/v1/properties/{pid}{q}")
    assert r.status_code == 200, r.text
    return r.json()


def _content(db, pid) -> dict:
    return db("SELECT content FROM properties WHERE id=:i", i=pid)[0][0]


@pytest.mark.asyncio
async def test_a_version_typed_in_the_editor_reaches_the_public_page(client, db):
    pid = _listing(db)
    await _filled(client, db, pid)
    html = await _post(
        client,
        pid,
        action="save_translation",
        lang="ar",
        **{
            "v__title": "برج الخور",
            "v__subtitle": "منازل على الواجهة المائية",
            "v__location": "خور دبي",
            "v__description": "برج على الخور.\n\nفقرة ثانية.",
            "v__details.amenities": "صالة رياضية\nمسبح",
            "v__developer.name": "كريست للتطوير",
            "v__developer.about": "تأسست عام 1997.",
            "v__developer.previousProjects": "مارينا هايتس",
            "r__risks__0__label": "تأخر البناء",
            "r__risks__0__note": "تدقيق الضمان",
            "r__scenarios__0__outcome": "حوالي 18%",
        },
    )
    assert "Arabic version saved." in html

    en, ar = await _get(client, pid), await _get(client, pid, "ar")
    assert en["title"] == "Creek Tower" and en["description"] == "A tower on the creek."
    assert en["developer_name"] == "Crest Developments"
    assert "translations" not in en["content"] and "translations" not in ar["content"]

    assert ar["title"] == "برج الخور" and ar["subtitle"] == "منازل على الواجهة المائية"
    assert ar["location"] == "خور دبي"
    assert ar["description"] == "برج على الخور.\n\nفقرة ثانية."  # paragraphs kept
    assert ar["content"]["details"]["amenities"] == ["صالة رياضية", "مسبح"]
    dev = ar["content"]["developer"]
    assert dev["name"] == "كريست للتطوير" and dev["about"] == "تأسست عام 1997."
    assert dev["previousProjects"] == ["مارينا هايتس"]
    assert dev["rating"] == 4.5  # figures are not text
    assert ar["developer_name"] == "كريست للتطوير"
    # the profile link is the same in every language
    assert ar["developer_slug"] == en["developer_slug"] == "crest-developments"

    risks = ar["content"]["risks"]
    assert risks[0] == {"label": "تأخر البناء", "level": "medium", "note": "تدقيق الضمان"}
    assert risks[1] == {
        "label": "Market risk",
        "level": "low",
        "note": "Long lease",
    }  # not translated yet
    scenario = ar["content"]["scenarios"][0]
    assert scenario == {"label": "On time", "outcome": "حوالي 18%", "tone": "positive"}

    # the marketplace cards say the same; the filters keep the English country
    item = next(
        i
        for i in (await client.get("/api/v1/properties?lang=ar")).json()["items"]
        if i["id"] == pid
    )
    assert item["title"] == "برج الخور" and item["location"] == "خور دبي"
    assert item["country"] == "UAE" and item["developer_name"] == "كريست للتطوير"

    # a language with no version, and an unknown one, read as English
    assert (await _get(client, pid, "fr"))["title"] == "Creek Tower"
    assert (await _get(client, pid, "de"))["title"] == "Creek Tower"


@pytest.mark.asyncio
async def test_english_is_the_master(client, db):
    pid = _listing(db, slug="tr-master")
    await _filled(client, db, pid)
    await _post(
        client,
        pid,
        action="save_translation",
        lang="fr",
        **{"v__developer.about": "Fondée en 1997.", "r__risks__1__label": "Risque de marché"},
    )
    fr = await _get(client, pid, "fr")
    assert fr["content"]["developer"]["about"] == "Fondée en 1997."
    assert fr["content"]["risks"][0]["label"] == "Construction delay"  # kept in its place
    assert fr["content"]["risks"][1]["label"] == "Risque de marché"
    assert fr["description"] == "A tower on the creek."  # a blank box shows the English

    # the English saved again keeps the versions
    await _post(
        client,
        pid,
        action="save_developer",
        name="Crest Developments",
        about="Founded in 1997, in Dubai.",
    )
    assert (await _get(client, pid, "fr"))["content"]["developer"]["about"] == "Fondée en 1997."
    # removed from the English: gone in every language
    await _post(client, pid, action="save_developer", name="Crest Developments", about="")
    assert "about" not in (await _get(client, pid, "fr"))["content"]["developer"]
    # a line more in the English than in the version stays in English, a line less is dropped
    await _post(
        client, pid, action="save_rows", section="risks", risks="Construction delay | medium"
    )
    assert [r["label"] for r in (await _get(client, pid, "fr"))["content"]["risks"]] == [
        "Construction delay"
    ]

    # saving the form again with empty boxes removes the version
    await _post(client, pid, action="save_translation", lang="fr")
    assert _content(db, pid)["translations"]["fr"] == {}


@pytest.mark.asyncio
async def test_the_form_shows_only_what_the_listing_says_with_the_english_beside_it(client, db):
    pid = _listing(db, slug="tr-form")
    await _admin(client, db)
    html = (await client.get(f"/admin/listing/{pid}")).text
    assert (
        "Arabic &amp; French versions" in html
        and 'data-version="ar"' in html
        and 'data-version="fr"' in html
    )
    assert 'name="v__description"' in html and "English: A tower on the creek." in html
    assert 'dir="rtl"' in html and 'dir="ltr"' in html
    assert 'name="v__developer.about"' not in html  # no developer text yet, no box
    assert "0 of 4 filled" in html  # title, subtitle, location, description

    await _post(client, pid, action="save_developer", name="Crest", about="Founded in 1997.")
    html = await _post(
        client,
        pid,
        action="save_translation",
        lang="ar",
        **{"v__description": "برج <b>على</b> الخور"},
    )
    assert 'name="v__developer.about"' in html
    assert "1 of 6 filled" in html and "0 of 6 filled" in html
    assert "برج &lt;b&gt;على&lt;/b&gt; الخور" in html  # escaped in the box
    assert '<details class="tr" data-version="ar" open>' in html  # stays open after saving

    # too long for its place, refused with a sentence, nothing saved
    r = await client.post(
        f"/admin/listing/{pid}",
        data={"action": "save_translation", "lang": "ar", "v__title": "x" * 201},
    )
    html = r.text
    assert r.status_code == 400
    assert "Listing title" in html and "at most 200" in html
    assert _content(db, pid)["translations"]["ar"]["columns"] == {
        "description": "برج <b>على</b> الخور"
    }
    # a language that does not exist
    r = await client.post(
        f"/admin/listing/{pid}", data={"action": "save_translation", "lang": "de", "v__title": "x"}
    )
    html = r.text
    assert r.status_code == 400
    assert "not recognised" in html and "de" not in _content(db, pid)["translations"]

    audit = db(
        "SELECT count(*) FROM audit_log WHERE action='property.content.update' AND entity_id=:i",
        i=pid,
    )[0][0]
    assert audit >= 2


@pytest.mark.asyncio
async def test_milestones_documents_and_the_developer_profile_follow(client, db):
    pid = _listing(db, slug="tr-more")
    await _filled(client, db, pid)
    await _post(
        client,
        pid,
        action="ms_add",
        title="Foundation complete",
        description="Signed off",
        status="planned",
    )
    ms = db("SELECT id FROM property_milestones WHERE property_id=:i", i=pid)[0][0]
    doc = str(uuid.uuid4())
    db(
        "INSERT INTO documents (id,property_id,title,type,file_url) VALUES (:d,:i,'Valuation report','valuation','k/v.pdf')",
        d=doc,
        i=pid,
    )
    await _post(
        client,
        pid,
        action="save_translation",
        lang="fr",
        **{
            f"m__{ms}__title": "Fondations terminées",
            f"d__{doc}__title": "Rapport d'évaluation",
            "v__developer.name": "Crest Développements",
            "v__developer.about": "Fondée en 1997.",
        },
    )
    fr = await _get(client, pid, "fr")
    assert fr["milestones"][0]["title"] == "Fondations terminées"
    assert fr["milestones"][0]["description"] == "Signed off"
    assert (await _get(client, pid))["milestones"][0]["title"] == "Foundation complete"

    docs = (await client.get(f"/api/v1/properties/{pid}/documents?lang=fr")).json()
    assert docs[0]["title"] == "Rapport d'évaluation" and docs[0]["type"] == "valuation"
    docs = (await client.get(f"/api/v1/properties/{pid}/documents")).json()
    assert docs[0]["title"] == "Valuation report"

    profile = (await client.get("/api/v1/developers/crest-developments?lang=fr")).json()
    assert profile["name"] == "Crest Développements" and profile["about"] == "Fondée en 1997."
    assert profile["properties"][0]["developer_name"] == "Crest Développements"
    profile = (await client.get("/api/v1/developers/crest-developments")).json()
    assert profile["name"] == "Crest Developments" and profile["about"] == "Founded in 1997."


@pytest.mark.asyncio
async def test_the_unit_price_history_follows(client, db):
    pid = _listing(db, slug="tr-prices")
    await _admin(client, db)
    row = str(uuid.uuid4())
    db(
        "INSERT INTO property_prices (id,property_id,previous_price,price,label,note) VALUES "
        "(:r,:i,100,110,'Phase 2','Structure completed')",
        r=row,
        i=pid,
    )
    html = (await client.get(f"/admin/listing/{pid}")).text
    assert f'name="p__{row}__note"' in html and "English: Structure completed" in html
    await _post(
        client,
        pid,
        action="save_translation",
        lang="ar",
        **{f"p__{row}__label": "المرحلة الثانية", f"p__{row}__note": "اكتمل الهيكل"},
    )
    ar = (await client.get(f"/api/v1/properties/{pid}/prices?lang=ar")).json()
    assert (
        ar["points"][-1]["label"] == "المرحلة الثانية"
        and ar["points"][-1]["note"] == "اكتمل الهيكل"
    )
    assert ar["phase"] == "المرحلة الثانية"
    assert ar["points"][0]["label"] == "Launch price"  # the site's own words: its dictionary
    en = (await client.get(f"/api/v1/properties/{pid}/prices")).json()
    assert en["phase"] == "Phase 2" and en["points"][-1]["note"] == "Structure completed"


@pytest.mark.asyncio
async def test_a_draft_preview_reads_in_the_language_too(client, db):
    from app.services import property_service

    pid = _listing(db, slug="tr-draft", status="draft")
    await _admin(client, db)
    await _post(client, pid, action="save_translation", lang="ar", **{"v__title": "برج المسودة"})
    assert (await client.get(f"/api/v1/properties/{pid}?lang=ar")).status_code == 404
    token = property_service.make_preview_token(uuid.UUID(pid))
    r = await client.get(f"/api/v1/properties/{pid}?preview={token}&lang=ar")
    assert r.json()["title"] == "برج المسودة"


# --- what the merging does not depend on ------------------------------------------------------ #
def test_the_merge_keeps_the_shape_of_the_english():
    content = {
        "developer": {"name": "Crest", "rating": 4.5},
        "risks": [{"label": "Delay", "level": "high"}],
        "translations": {
            "ar": {
                "columns": {"title": "برج", "subtitle": 5},
                "content": {
                    "developer": {"name": "كريست", "rating": 1, "about": "not in the English"},
                    "risks": [{"label": "تأخر", "level": "low"}, {"label": "no such row"}],
                },
            },
            "fr": "not a version",
        },
    }
    data = {"title": "Tower", "subtitle": "Homes", "content": lt.public_content(content)}
    out = lt.localized_detail(dict(data), content, "ar")
    assert out["title"] == "برج" and out["subtitle"] == "Homes"
    assert out["content"]["developer"] == {"name": "كريست", "rating": 4.5}
    assert len(out["content"]["risks"]) == 1 and out["content"]["risks"][0]["label"] == "تأخر"
    assert (
        out["content"]["risks"][0]["level"] == "تأخر"
        or out["content"]["risks"][0]["level"] == "low"
    )
    # a stored value of the wrong shape is ignored
    assert lt.localized_detail(dict(data), content, "fr")["title"] == "Tower"
    # the listing itself is never touched
    assert content["developer"]["name"] == "Crest"
    assert data["title"] == "Tower"
    assert lt.public_content(None) == {}
    assert lt.language("ar") == "ar" and lt.language("en") is None and lt.language(None) is None


@pytest.mark.asyncio
async def test_an_owner_saving_their_listing_keeps_the_versions(client, db):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "tr-owner@x.com", "password": PW, "full_name": "Owner"},
    )
    uid = db("SELECT id FROM users WHERE email=:e", e="tr-owner@x.com")[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'owner')", i=uid)
    db("UPDATE users SET active_role='owner' WHERE id=:i", i=uid)
    r = await client.post("/api/v1/auth/login", json={"email": "tr-owner@x.com", "password": PW})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = _listing(db, slug="tr-owner", status="draft")
    db("UPDATE properties SET owner_id=:o WHERE id=:i", o=uid, i=pid)
    kept = {"ar": {"columns": {"title": "برج"}}}
    import json

    db(
        "UPDATE properties SET content=CAST(:c AS jsonb) WHERE id=:i",
        c=json.dumps({"badge": "New", "translations": kept}),
        i=pid,
    )
    # what the owner reads has no versions, and what they send back cannot change them
    listed = (await client.get("/api/v1/owner/properties", headers=h)).json()
    assert "translations" not in next(p for p in listed if p["id"] == pid)["content"]
    r = await client.patch(
        f"/api/v1/properties/{pid}",
        json={"content": {"badge": "Newer", "translations": {"ar": {"columns": {"title": "x"}}}}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    stored = _content(db, pid)
    assert stored["badge"] == "Newer" and stored["translations"] == kept
