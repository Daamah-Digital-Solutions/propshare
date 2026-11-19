"""Client (2026-11-19): a saved developer must not be typed again in Arabic and French for every
listing. Its text in each language is kept with it (learned from a listing's saved version, or
typed on the Developers page) and comes with it when another listing picks it."""

# ruff: noqa: E501
from __future__ import annotations

import pytest

from app.services import developer_service
from app.tests.test_listing_translation_db import _admin, _content, _get, _listing, _post

CREST = {
    "action": "save_developer",
    "name": "Crest Developments",
    "about": "Founded in 1997.",
    "previous_projects": "Marina Heights\nCreek Villas",
    "rating": "4.5",
}
CREST_AR = {
    "v__developer.name": "كريست للتطوير",
    "v__developer.about": "تأسست عام 1997.",
    "v__developer.previousProjects": "مارينا هايتس\nفلل الخور",
}


def _versions(db, slug="crest-developments") -> dict:
    return db("SELECT versions FROM saved_developers WHERE slug=:s", s=slug)[0][0]


def _saved_id(db, slug="crest-developments") -> str:
    return str(db("SELECT id FROM saved_developers WHERE slug=:s", s=slug)[0][0])


def _dev_version(db, pid, lang) -> dict | None:
    return (
        ((_content(db, pid).get("translations") or {}).get(lang) or {})
        .get("content", {})
        .get("developer")
    )


@pytest.mark.asyncio
async def test_a_listings_arabic_developer_comes_with_the_saved_developer(client, db):
    await _admin(client, db)
    first = _listing(db, slug="dv-first")
    await _post(client, first, **CREST)
    assert _versions(db) == {}
    await _post(
        client, first, action="save_translation", lang="ar", v__title="برج الخور", **CREST_AR
    )
    # the Arabic developer text is now the saved developer's
    assert _versions(db) == {
        "ar": {
            "name": "كريست للتطوير",
            "about": "تأسست عام 1997.",
            "previousProjects": ["مارينا هايتس", "فلل الخور"],
        }
    }

    # a second listing picks it: English and Arabic both arrive, nothing typed in Arabic
    second = _listing(db, slug="dv-second")
    html = await _post(client, second, **CREST, saved_developer_id=_saved_id(db))
    assert "Developer saved, with its Arabic version from the saved developer." in html
    assert _dev_version(db, second, "ar") == _versions(db)["ar"]
    assert _dev_version(db, second, "fr") is None
    ar = (await _get(client, second, "ar"))["content"]["developer"]
    assert ar["name"] == "كريست للتطوير" and ar["previousProjects"] == ["مارينا هايتس", "فلل الخور"]
    assert ar["rating"] == 4.5
    # the Arabic boxes of the second listing's editor show it, ready to adjust
    page = (await client.get(f"/admin/listing/{second}")).text
    assert "تأسست عام 1997." in page


@pytest.mark.asyncio
async def test_typing_a_saved_developers_name_fills_only_what_is_not_translated(client, db):
    await _admin(client, db)
    first = _listing(db, slug="dv-a")
    await _post(client, first, **CREST)
    await _post(client, first, action="save_translation", lang="ar", **CREST_AR)

    # a listing that already has its own Arabic developer text keeps it when the name is typed
    other = _listing(db, slug="dv-b")
    await _post(client, other, **CREST)
    await _post(
        client,
        other,
        action="save_translation",
        lang="ar",
        **{"v__developer.about": "نص خاص بهذا العقار."},
    )
    await _post(client, other, **{**CREST, "rating": "4.7"})
    assert _dev_version(db, other, "ar") == {"about": "نص خاص بهذا العقار."}

    # ...and the saved developer learned that listing's newer Arabic (the last one saved wins)
    assert _versions(db)["ar"] == {"about": "نص خاص بهذا العقار."}

    # a listing with no Arabic developer text gets it from the saved developer by its name alone
    third = _listing(db, slug="dv-c")
    await _post(client, third, **CREST)
    assert _dev_version(db, third, "ar") == {"about": "نص خاص بهذا العقار."}


@pytest.mark.asyncio
async def test_another_developer_takes_the_old_developers_translation_away(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="dv-switch")
    await _post(client, pid, **CREST)
    await _post(client, pid, action="save_translation", lang="ar", v__title="برج الخور", **CREST_AR)
    assert _dev_version(db, pid, "ar")

    await _post(client, pid, action="save_developer", name="Harbour Builders", about="Since 2004.")
    # the Arabic text described Crest: it goes; the rest of the Arabic version stays
    assert _dev_version(db, pid, "ar") is None
    assert _content(db, pid)["translations"]["ar"]["columns"]["title"] == "برج الخور"
    ar = await _get(client, pid, "ar")
    assert ar["content"]["developer"]["about"] == "Since 2004." and ar["title"] == "برج الخور"
    # Crest keeps its Arabic for the next listing
    assert _versions(db)["ar"]["name"] == "كريست للتطوير"


@pytest.mark.asyncio
async def test_a_blank_version_does_not_wipe_the_saved_developers_text(client, db):
    await _admin(client, db)
    first = _listing(db, slug="dv-keep-1")
    await _post(client, first, **CREST)
    await _post(client, first, action="save_translation", lang="ar", **CREST_AR)
    second = _listing(db, slug="dv-keep-2")
    await _post(client, second, **CREST)
    # the second listing's Arabic is saved with its developer boxes emptied
    await _post(
        client,
        second,
        action="save_translation",
        lang="ar",
        v__title="برج",
        **{"v__developer.name": "", "v__developer.about": "", "v__developer.previousProjects": ""},
    )
    assert _versions(db)["ar"]["name"] == "كريست للتطوير"


@pytest.mark.asyncio
async def test_the_developers_page_keeps_arabic_and_french_and_applies_them(client, db):
    await _admin(client, db)
    pid = _listing(db, slug="dv-page")
    await _post(client, pid, **CREST)
    dev_id = _saved_id(db)
    page = (await client.get(f"/admin/developers/profile/{dev_id}")).text
    assert "Arabic &amp; French versions" in page and 'name="v_ar__about"' in page
    assert 'dir="rtl"' in page and "English: Founded in 1997." in page

    form = {
        "action": "save",
        "name": "Crest Developments",
        "about": "Founded in 1997.",
        "previous_projects": "Marina Heights\nCreek Villas",
        "rating": "4.5",
        "v_ar__name": "كريست للتطوير",
        "v_ar__about": "تأسست عام 1997.",
        "v_fr__about": "Fondée en 1997.",
        "v_fr__previousProjects": "Marina Heights\nVillas du Creek",
        "apply": "1",
    }
    r = await client.post(f"/admin/developers/profile/{dev_id}", data=form)
    assert r.status_code == 200 and "1 listing(s) updated." in r.text
    assert _versions(db) == {
        "ar": {"name": "كريست للتطوير", "about": "تأسست عام 1997."},
        "fr": {
            "about": "Fondée en 1997.",
            "previousProjects": ["Marina Heights", "Villas du Creek"],
        },
    }
    fr = (await _get(client, pid, "fr"))["content"]["developer"]
    assert fr["about"] == "Fondée en 1997." and fr["previousProjects"] == [
        "Marina Heights",
        "Villas du Creek",
    ]
    assert (await _get(client, pid, "ar"))["developer_name"] == "كريست للتطوير"
    # the page shows what was saved
    assert "Fondée en 1997." in r.text and "2 of 4 filled" in r.text

    # a box over its limit is refused and what was typed stays on the page
    bad = {**form, "v_ar__about": "ن" * 1300}
    r = await client.post(f"/admin/developers/profile/{dev_id}", data=bad)
    assert r.status_code == 400 and "About the developer (Arabic)" in r.text
    assert _versions(db)["ar"]["about"] == "تأسست عام 1997."


@pytest.mark.asyncio
async def test_a_new_developer_can_be_typed_in_every_language_at_once(client, db):
    await _admin(client, db)
    r = await client.post(
        "/admin/developers/new",
        data={"name": "Dune Estates", "about": "Est. 2010.", "v_ar__about": "تأسست عام 2010."},
    )
    assert r.status_code == 303
    assert _versions(db, "dune-estates") == {"ar": {"about": "تأسست عام 2010."}}

    pid = _listing(db, slug="dv-dune")
    await _post(
        client,
        pid,
        action="save_developer",
        name="Dune Estates",
        about="Est. 2010.",
        saved_developer_id=_saved_id(db, "dune-estates"),
    )
    assert (await _get(client, pid, "ar"))["content"]["developer"]["about"] == "تأسست عام 2010."


def test_with_versions_rules():
    content = {
        "developer": {"name": "A"},
        "translations": {
            "ar": {"columns": {"title": "ع"}, "content": {"developer": {"about": "قديم"}}}
        },
    }
    saved = {"ar": {"about": "جديد"}, "fr": {"about": "nouveau"}}
    # picked: every saved language replaces
    got = developer_service.with_versions(content, saved, replace=True, drop_missing=False)
    assert developer_service.versions_in(got) == saved
    assert got["translations"]["ar"]["columns"] == {"title": "ع"}
    # typed: only the languages not translated are filled
    got = developer_service.with_versions(content, saved, replace=False, drop_missing=False)
    assert developer_service.versions_in(got) == {
        "ar": {"about": "قديم"},
        "fr": {"about": "nouveau"},
    }
    # another developer with nothing saved: the old developer's text goes, nothing else
    got = developer_service.with_versions(content, {}, replace=False, drop_missing=True)
    assert developer_service.versions_in(got) == {}
    assert got["translations"] == {"ar": {"columns": {"title": "ع"}}}
    # the input is never changed
    assert content["translations"]["ar"]["content"]["developer"] == {"about": "قديم"}
