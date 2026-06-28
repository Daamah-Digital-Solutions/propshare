"""Phase 15b — DB-backed tests for property milestones.

Acceptance bar: owner-scoped CRUD (another owner -> 403 on create/update/delete/
reorder); progress/title validation -> 422; status->completed sets completed_at,
leaving it clears it; reorder assigns sort_index (foreign/incomplete id set -> 422);
the public GET /properties/{id} embeds the ordered milestones for active properties;
construction_progress = current-milestone rule (in_progress %, else 0); the pure
content.timeline -> rows converter (relative-date offsets, status map, value_index,
sort_index). Plus auth 401 / non-owner-role 403.
"""

from __future__ import annotations

import datetime as dt
import uuid

PW = "Passw0rd!23"


# --- auth / seeding helpers ------------------------------------------------- #
async def _owner(client, db, email: str) -> tuple[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Owner"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'owner')", i=uid)
    db("UPDATE users SET active_role='owner' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"], str(uid)


async def _investor_token(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Inv"}
    )
    return r.json()["access_token"]


def _seed_property(db, owner_id: str | None, *, status: str = "active") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,owner_id,title,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,:o,'Prop','Dubai','residential','installment',:st,1000000,100,100,100,100)",
        id=pid,
        o=owner_id,
        st=status,
    )
    return pid


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create(client, token, pid, **body):
    return await client.post(
        f"/api/v1/owner/properties/{pid}/milestones", json=body, headers=_h(token)
    )


async def _list(client, token, pid):
    return await client.get(f"/api/v1/owner/properties/{pid}/milestones", headers=_h(token))


# --- CRUD + ordering -------------------------------------------------------- #
async def test_create_and_list_ordered(client, db):
    tok, oid = await _owner(client, db, "ms-owner1@x.com")
    pid = _seed_property(db, oid)
    for t in ("Foundation", "Structure", "Handover"):
        r = await _create(client, tok, pid, title=t, status="planned")
        assert r.status_code == 201, r.text

    body = (await _list(client, tok, pid)).json()
    assert [m["title"] for m in body] == ["Foundation", "Structure", "Handover"]
    assert [m["sort_index"] for m in body] == [0, 1, 2]


async def test_non_owner_cannot_crud(client, db):
    tok_a, oid_a = await _owner(client, db, "ms-a@x.com")
    tok_b, _oid_b = await _owner(client, db, "ms-b@x.com")
    pid = _seed_property(db, oid_a)
    created = (await _create(client, tok_a, pid, title="Foundation")).json()
    mid = created["id"]

    # Owner B cannot touch owner A's property milestones.
    c = await _create(client, tok_b, pid, title="Sneaky")
    assert c.status_code == 403 and c.json()["error"]["code"] == "NOT_PROPERTY_OWNER"
    u = await client.patch(
        f"/api/v1/owner/properties/{pid}/milestones/{mid}",
        json={"title": "Hijack"},
        headers=_h(tok_b),
    )
    assert u.status_code == 403
    d = await client.delete(f"/api/v1/owner/properties/{pid}/milestones/{mid}", headers=_h(tok_b))
    assert d.status_code == 403
    ro = await client.post(
        f"/api/v1/owner/properties/{pid}/milestones/reorder",
        json={"ordered_ids": [mid]},
        headers=_h(tok_b),
    )
    assert ro.status_code == 403


async def test_progress_and_title_validation(client, db):
    tok, oid = await _owner(client, db, "ms-val@x.com")
    pid = _seed_property(db, oid)
    assert (await _create(client, tok, pid, title="x", progress_pct=150)).status_code == 422
    assert (await _create(client, tok, pid, title="x", progress_pct=-5)).status_code == 422
    assert (await _create(client, tok, pid, title="")).status_code == 422
    # update with an out-of-range progress is rejected too
    ok = (await _create(client, tok, pid, title="ok")).json()
    bad = await client.patch(
        f"/api/v1/owner/properties/{pid}/milestones/{ok['id']}",
        json={"progress_pct": 101},
        headers=_h(tok),
    )
    assert bad.status_code == 422


async def test_status_completed_sets_and_clears_completed_at(client, db):
    tok, oid = await _owner(client, db, "ms-status@x.com")
    pid = _seed_property(db, oid)
    m = (await _create(client, tok, pid, title="Foundation", status="planned")).json()
    assert m["completed_at"] is None

    done = (
        await client.patch(
            f"/api/v1/owner/properties/{pid}/milestones/{m['id']}",
            json={"status": "completed"},
            headers=_h(tok),
        )
    ).json()
    assert done["status"] == "completed" and done["completed_at"] is not None

    reopened = (
        await client.patch(
            f"/api/v1/owner/properties/{pid}/milestones/{m['id']}",
            json={"status": "in_progress"},
            headers=_h(tok),
        )
    ).json()
    assert reopened["status"] == "in_progress" and reopened["completed_at"] is None

    # creating directly as completed also stamps completed_at
    born_done = (await _create(client, tok, pid, title="Done", status="completed")).json()
    assert born_done["completed_at"] is not None


async def test_reorder_assigns_sort_index(client, db):
    tok, oid = await _owner(client, db, "ms-reorder@x.com")
    pid = _seed_property(db, oid)
    a = (await _create(client, tok, pid, title="A")).json()["id"]
    b = (await _create(client, tok, pid, title="B")).json()["id"]
    c = (await _create(client, tok, pid, title="C")).json()["id"]

    r = await client.post(
        f"/api/v1/owner/properties/{pid}/milestones/reorder",
        json={"ordered_ids": [c, a, b]},
        headers=_h(tok),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [m["id"] for m in body] == [c, a, b]
    assert [m["sort_index"] for m in body] == [0, 1, 2]

    # incomplete set -> 422
    bad1 = await client.post(
        f"/api/v1/owner/properties/{pid}/milestones/reorder",
        json={"ordered_ids": [a, b]},
        headers=_h(tok),
    )
    assert bad1.status_code == 422
    # foreign id in the set -> 422
    bad2 = await client.post(
        f"/api/v1/owner/properties/{pid}/milestones/reorder",
        json={"ordered_ids": [a, b, str(uuid.uuid4())]},
        headers=_h(tok),
    )
    assert bad2.status_code == 422


async def test_delete_removes(client, db):
    tok, oid = await _owner(client, db, "ms-del@x.com")
    pid = _seed_property(db, oid)
    a = (await _create(client, tok, pid, title="A")).json()["id"]
    (await _create(client, tok, pid, title="B")).json()
    d = await client.delete(f"/api/v1/owner/properties/{pid}/milestones/{a}", headers=_h(tok))
    assert d.status_code == 204
    body = (await _list(client, tok, pid)).json()
    assert [m["title"] for m in body] == ["B"]


# --- public read + construction_progress ------------------------------------ #
async def test_public_read_embeds_ordered_milestones(client, db):
    tok, oid = await _owner(client, db, "ms-pub@x.com")
    pid = _seed_property(db, oid, status="active")
    await _create(client, tok, pid, title="Foundation", status="completed", progress_pct=100)
    await _create(client, tok, pid, title="Structure", status="in_progress", progress_pct=40)

    pub = await client.get(f"/api/v1/properties/{pid}")  # public, no auth
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert [m["title"] for m in body["milestones"]] == ["Foundation", "Structure"]
    assert [m["sort_index"] for m in body["milestones"]] == [0, 1]


async def test_construction_progress_current_milestone_rule(client, db):
    tok, oid = await _owner(client, db, "ms-cp@x.com")
    # in_progress milestone drives the %
    p1 = _seed_property(db, oid, status="active")
    await _create(client, tok, p1, title="Down Payment", status="completed", progress_pct=100)
    await _create(client, tok, p1, title="Foundation", status="in_progress", progress_pct=25)
    b1 = (await client.get(f"/api/v1/properties/{p1}")).json()
    assert b1["construction_progress"] == 25  # not the admin-step 100

    # no in_progress milestone -> 0 (even with a completed one)
    p2 = _seed_property(db, oid, status="active")
    await _create(client, tok, p2, title="Down Payment", status="completed", progress_pct=100)
    await _create(client, tok, p2, title="Foundation", status="planned", progress_pct=0)
    b2 = (await client.get(f"/api/v1/properties/{p2}")).json()
    assert b2["construction_progress"] == 0


# --- auth ------------------------------------------------------------------- #
async def test_milestones_require_auth_and_owner_role(client, db):
    tok, oid = await _owner(client, db, "ms-auth-owner@x.com")
    pid = _seed_property(db, oid)
    # unauthenticated
    assert (await client.get(f"/api/v1/owner/properties/{pid}/milestones")).status_code == 401
    assert (
        await client.post(f"/api/v1/owner/properties/{pid}/milestones", json={"title": "x"})
    ).status_code == 401
    # plain investor role -> 403
    inv = await _investor_token(client, db, "ms-plain-inv@x.com")
    assert (await _list(client, inv, pid)).status_code == 403
    assert (await _create(client, inv, pid, title="x")).status_code == 403


# --- pure converter (no DB) ------------------------------------------------- #
def test_timeline_to_milestone_rows_conversion():
    from app.services.milestone_service import timeline_to_milestone_rows

    anchor = dt.date(2026, 1, 15)
    timeline = [
        {"label": "Listed", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
        {"label": "Funding", "date": "+30d", "progress": 62, "valueIndex": 100, "status": "active"},
        {"label": "Dist", "date": "+12m", "progress": 0, "valueIndex": 105, "status": "upcoming"},
    ]
    rows = timeline_to_milestone_rows(timeline, anchor=anchor, created_by=None)
    assert [r["status"] for r in rows] == ["completed", "in_progress", "planned"]
    assert [r["sort_index"] for r in rows] == [0, 1, 2]
    assert [r["value_index"] for r in rows] == [100, 100, 105]
    assert [r["title"] for r in rows] == ["Listed", "Funding", "Dist"]
    assert rows[0]["target_date"] == dt.date(2026, 1, 15)  # Today
    assert rows[1]["target_date"] == dt.date(2026, 2, 14)  # +30 days
    assert rows[2]["target_date"] == dt.date(2027, 1, 15)  # +12 months
    assert rows[0]["completed_at"] is not None  # done -> stamped
    assert rows[1]["completed_at"] is None
