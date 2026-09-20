"""Knowledge base (plan §7): drafts are invisible to the model, approval is versioned and
audited, and the rendered bundle is deterministic (same rows -> same bytes) so the provider
prompt cache keeps hitting."""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import AppError
from app.services import kb_service

PW = "Passw0rd!23"


async def _admin(client, db) -> uuid.UUID:
    r = await client.post(
        "/api/v1/auth/register", json={"email": "kb@test.io", "password": PW, "full_name": "KB"}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email='kb@test.io'")[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    return uid


@pytest.mark.asyncio
async def test_drafts_are_invisible_until_approved_and_versions_rotate(client, db, asession):
    admin = await _admin(client, db)
    v1 = await kb_service.upsert_draft(
        asession, slug="fees", lang="en", title="Fees", body_md="Fees are shown before you pay."
    )
    assert v1.version == 1 and v1.status == "draft"
    assert await kb_service.render_bundle(asession) == "(no approved articles yet)"

    await kb_service.approve(asession, article_id=v1.id, actor_id=admin)
    bundle_a = await kb_service.render_bundle(asession)
    assert bundle_a == "## [en] Fees  (kb:fees v1)\nFees are shown before you pay."
    assert await kb_service.render_bundle(asession) == bundle_a  # deterministic

    v2 = await kb_service.upsert_draft(
        asession,
        slug="fees",
        lang="en",
        title="Fees",
        body_md="Fees are shown before you pay. Always.",
    )
    assert v2.version == 2
    assert await kb_service.render_bundle(asession) == bundle_a  # v2 still a draft
    await kb_service.approve(asession, article_id=v2.id, actor_id=admin)
    await asession.commit()
    assert "v2" in await kb_service.render_bundle(asession)
    assert db("SELECT status FROM kb_articles WHERE id=:i", i=v1.id)[0][0] == "retired"
    assert db("SELECT count(*) FROM audit_log WHERE action='kb.approved'")[0][0] == 2

    await kb_service.retire(asession, article_id=v2.id, actor_id=admin)
    await asession.commit()
    assert await kb_service.render_bundle(asession) == "(no approved articles yet)"
    assert db("SELECT count(*) FROM audit_log WHERE action='kb.retired'")[0][0] == 1


@pytest.mark.asyncio
async def test_bundle_orders_by_priority_then_slug_and_caps_size(client, db, asession):
    admin = await _admin(client, db)
    b = await kb_service.upsert_draft(
        asession, slug="b-exit", lang="en", title="Exit", body_md="x", priority=50
    )
    a = await kb_service.upsert_draft(
        asession, slug="a-kyc", lang="ar", title="التحقق", body_md="y", priority=50
    )
    z = await kb_service.upsert_draft(
        asession, slug="z-first", lang="en", title="First", body_md="z", priority=1
    )
    for row in (b, a, z):
        await kb_service.approve(asession, article_id=row.id, actor_id=admin)
    bundle = await kb_service.render_bundle(asession)
    assert [line for line in bundle.splitlines() if line.startswith("## ")] == [
        "## [en] First  (kb:z-first v1)",
        "## [ar] التحقق  (kb:a-kyc v1)",
        "## [en] Exit  (kb:b-exit v1)",
    ]
    huge = await kb_service.upsert_draft(
        asession,
        slug="huge",
        lang="en",
        title="Huge",
        body_md="h" * (kb_service.MAX_BUNDLE_CHARS + 1),
    )
    await kb_service.approve(asession, article_id=huge.id, actor_id=admin)
    with pytest.raises(AppError) as exc:
        await kb_service.render_bundle(asession)
    assert exc.value.code == "KB_TOO_LARGE"
