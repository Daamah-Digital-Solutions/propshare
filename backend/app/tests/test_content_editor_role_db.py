"""Content-editor role (Step 3): the platform owner edits listings without admin power.

Reproduces the gap: before this role, the only way to let the owner manage listings was a
full admin account with access to money, users, KYC, roles, settings and audit actions.

Now a `content_editor` can log into /admin and reach ONLY the Listing Editor. This test
sweeps EVERY registered admin view — list / details / create / edit / delete / export and
every custom @action — plus the custom upload / role-document views and every
``/api/v1/admin/*`` route, and expects 403 for all of them, while the Listing Editor works.
"""

from __future__ import annotations

import re
import uuid

import pytest
from sqladmin import ModelView

from app.main import app

PW = "Passw0rd!23"


async def _user_with_role(client, db, email: str, role: str) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": role}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db(
        "INSERT INTO user_roles (user_id, role) VALUES (:i,:r) ON CONFLICT DO NOTHING",
        i=uid,
        r=role,
    )
    db("UPDATE users SET active_role=:r WHERE id=:i", i=uid, r=role)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return str(uid), login.json()["access_token"]


async def _panel_login(client, email: str) -> None:
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert r.status_code in (200, 302, 303) and "session" in client.cookies, r.text[:200]


def _seed_property(db, slug="ce-tower") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,slug,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment,expected_yield,"
        "capital_appreciation,total_return,expected_completion) VALUES "
        "(:id,'CE Tower',:s,'London','residential','installment','draft',1000000,100,10000,"
        "10000,100,7,3,10,'2027-06-30')",
        id=pid,
        s=slug,
    )
    return pid


def _model_views() -> list[ModelView]:
    return [v for v in app.state.admin.views if isinstance(v, ModelView)]


def _action_slugs(view: ModelView) -> list[str]:
    slugs = []
    for attr in dir(type(view)):
        fn = getattr(type(view), attr, None)
        slug = getattr(fn, "_slug", None)
        if slug and getattr(fn, "_action", False) is not False:
            slugs.append(slug)
    return sorted(set(slugs))


@pytest.mark.asyncio
async def test_content_editor_gets_403_on_every_restricted_admin_view_and_action(client, db):
    await _user_with_role(client, db, "editor@x.com", "content_editor")
    await _panel_login(client, "editor@x.com")
    some_id = str(uuid.uuid4())
    swept_views, swept_actions, failures = 0, 0, []
    for view in _model_views():
        ident = view.identity
        swept_views += 1
        urls = [
            ("GET", f"/admin/{ident}/list"),
            ("GET", f"/admin/{ident}/details/{some_id}"),
            ("GET", f"/admin/{ident}/create"),
            ("POST", f"/admin/{ident}/create"),
            ("GET", f"/admin/{ident}/edit/{some_id}"),
            ("POST", f"/admin/{ident}/edit/{some_id}"),
            ("DELETE", f"/admin/{ident}/delete?pks={some_id}"),
            ("GET", f"/admin/{ident}/export/csv"),
        ]
        for slug in _action_slugs(view):
            swept_actions += 1
            urls.append(("GET", f"/admin/{ident}/action/{slug}?pks={some_id}"))
        for method, url in urls:
            r = await client.request(method, url, follow_redirects=False)
            if r.status_code != 403:
                failures.append((method, url, r.status_code))
    # custom admin-only pages
    for method, url in (
        ("GET", "/admin/upload-document"),
        ("POST", "/admin/upload-document"),
        ("GET", f"/admin/role-application-doc?req={some_id}"),
    ):
        r = await client.request(method, url, follow_redirects=False)
        if r.status_code != 403:
            failures.append((method, url, r.status_code))
    assert not failures, failures
    assert swept_views >= 40 and swept_actions >= 8, (swept_views, swept_actions)
    # the sidebar shows nothing but Listings
    home = await client.get("/admin/")
    assert home.status_code == 200
    for word in ("Withdrawals", "Wallets", "KYC", "Users", "Platform Settings", "Transactions"):
        assert word not in home.text, f"menu leaks {word!r}"
    assert "Listings" in home.text


@pytest.mark.asyncio
async def test_content_editor_can_use_the_listing_editor_only(client, db):
    await _user_with_role(client, db, "editor2@x.com", "content_editor")
    await _panel_login(client, "editor2@x.com")
    pid = _seed_property(db)
    assert (await client.get("/admin/listing/")).status_code == 200
    assert (await client.get("/admin/listing/new")).status_code == 200
    page = await client.get(f"/admin/listing/{pid}")
    assert page.status_code == 200
    assert "Raw fields" not in page.text  # technical link hidden from the editor role
    r = await client.post(f"/admin/listing/{pid}", data={"action": "save_facts", "bedrooms": "3"})
    assert r.status_code == 200 and "Key facts saved" in r.text
    r = await client.post(f"/admin/listing/{pid}", data={"action": "publish"})
    assert r.status_code == 200 and "Published" in r.text
    assert db("SELECT status FROM properties WHERE id=:i", i=pid)[0][0] == "active"
    acts = {a[0] for a in db("SELECT action FROM audit_log WHERE entity_id=:i", i=pid)}
    assert {"property.content.update", "property.approve"} <= acts


@pytest.mark.asyncio
async def test_content_editor_has_no_admin_api_and_cannot_be_self_requested(client, db):
    _uid, tok = await _user_with_role(client, db, "editor3@x.com", "content_editor")
    h = {"Authorization": f"Bearer {tok}"}
    swept, failures = 0, []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/admin"):
            continue
        for method in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
            swept += 1
            url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)  # any id will do: 403 first
            r = await client.request(method, url, headers=h, json={})
            if r.status_code != 403:
                failures.append((method, path, r.status_code))
    assert swept >= 5 and not failures, failures
    # an investor cannot request the role for themselves (admin-granted only)
    _uid2, tok2 = await _user_with_role(client, db, "inv@x.com", "investor")
    r = await client.post(
        "/api/v1/auth/roles/request",
        json={"role": "content_editor"},
        headers={"Authorization": f"Bearer {tok2}"},
    )
    assert r.status_code in (400, 422), r.text
    assert "content_editor" not in {
        x[0] for x in db("SELECT role FROM user_roles WHERE user_id=:u", u=_uid2)
    }


@pytest.mark.asyncio
async def test_full_admin_still_sees_everything(client, db):
    await _user_with_role(client, db, "boss@x.com", "admin")
    await _panel_login(client, "boss@x.com")
    assert (await client.get("/admin/withdrawal/list")).status_code == 200
    assert (await client.get("/admin/upload-document")).status_code == 200
    pid = _seed_property(db, slug="boss-tower")
    assert "Raw fields" in (await client.get(f"/admin/listing/{pid}")).text
