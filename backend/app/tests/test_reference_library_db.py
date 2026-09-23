"""The company reference library (client documents about PropShare, the Capimax ecosystem,
partners and operating entities) the assistant is trained on.

What each test protects:
  * the four source documents are split into passages that each fit a tool result on their
    own (a table cut in two repeats its header row); the Contents index is dropped;
  * the seed is idempotent, goes through draft -> approve like the KB, and retires passages
    that disappeared from the sources;
  * reference passages NEVER enter the prompt's knowledge-base block (they carry figures the
    live settings may not match) and never leak into search_kb;
  * search_reference finds the right passage for English and Arabic questions, stays inside
    the tool-result size cap untruncated, and is open to visitors (public company info).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.services import kb_service, reference_library
from app.services.assistant import guard
from app.services.assistant.context import AgentContext
from app.services.assistant.tools import REGISTRY
from app.services.assistant.tools.base import call_tool, parse_args

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
PW = "Passw0rd!23"
VISITOR = AgentContext(None, "visitor-1", (), None, "none", False, None)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


async def _admin(client, db) -> str:
    email = "ref-admin@x.io"
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Admin"}
    )
    assert r.status_code == 201
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    return email


def test_documents_split_into_self_contained_passages():
    chunks = reference_library.load_chunks()
    sources = {c.slug.split("-")[1] for c in chunks}
    assert sources == {"kb", "ecosystem", "partners", "entities"}
    assert len({c.slug for c in chunks}) == len(chunks)
    for c in chunks:
        assert len(c.body) <= reference_library.CHUNK_CHARS, c.slug
        assert len(guard.wrap_untrusted(c.body)["untrusted_text"]) == len(c.body)  # no cut
    titles = [c.title for c in chunks]
    assert not any(t.lower().startswith("contents") for t in titles)
    # a sub-section carries its parent heading
    assert "1. Platform Identity and Purpose — Platform mission" in titles
    # a table split across passages repeats its header row in the second part
    faq_or_links = [c for c in chunks if c.title.startswith("31. Official Links Directory")]
    assert len(faq_or_links) == 2
    assert faq_or_links[1].body.startswith("| **Entity** | **Official link** | **Function** |")
    ecosystem = [c for c in chunks if c.slug.startswith("ref-ecosystem-")]
    assert ecosystem and all(c.lang == "ar" for c in ecosystem)


@pytest.mark.asyncio
async def test_seed_is_idempotent_approved_and_kept_out_of_the_prompt(client, db, asession):
    seed = _load("seed_reference")
    assert await seed._seed(None) == 0
    n = len(reference_library.load_chunks())
    rows = db("SELECT DISTINCT audience, status FROM kb_articles")
    assert rows == [("reference", "draft")]
    assert db("SELECT count(*) FROM kb_articles")[0][0] == n
    assert await seed._seed(None) == 0  # unchanged sources -> nothing new
    assert db("SELECT count(*) FROM kb_articles")[0][0] == n

    email = await _admin(client, db)
    assert await seed._seed(email) == 0
    assert db("SELECT count(*) FROM kb_articles WHERE status='approved'")[0][0] == n
    assert db("SELECT count(*) FROM audit_log WHERE action='kb.approved'")[0][0] == n

    # approved reference passages are NOT part of the prompt block
    bundle = await kb_service.render_bundle(asession)
    assert "CIM Global Financial provides feasibility" not in bundle
    assert bundle == "(no approved articles yet)"


@pytest.mark.asyncio
async def test_passages_removed_from_the_sources_are_retired(client, db, monkeypatch):
    seed = _load("seed_reference")
    email = await _admin(client, db)
    assert await seed._seed(email) == 0
    full = reference_library.load_chunks()
    monkeypatch.setattr(reference_library, "load_chunks", lambda: full[:-1])
    assert await seed._seed(email) == 0
    gone = full[-1]
    assert db("SELECT status FROM kb_articles WHERE slug=:s", s=gone.slug) == [("retired",)]
    assert db("SELECT count(*) FROM kb_articles WHERE status='approved'")[0][0] == len(full) - 1


@pytest.mark.parametrize(
    ("query", "expected_slug_prefix", "must_contain"),
    [
        ("Who performs legal due diligence?", "ref-", "LexCrest"),
        ("insurance partners", "ref-", "CoverTech"),
        ("What does Crown Facilities do", "ref-", "Crown Facilities"),
        ("ما هي علاقة بروبشير بنوفا ديجيتال فاينانس؟", "ref-ecosystem-04", "نوفا"),
        ("Pronova PRN", "ref-", "PRN"),
    ],
)
@pytest.mark.asyncio
async def test_search_reference_finds_the_right_passage(
    client, db, asession, query, expected_slug_prefix, must_contain
):
    seed = _load("seed_reference")
    assert await seed._seed(await _admin(client, db)) == 0
    spec = REGISTRY["search_reference"]
    guard.authorize(spec, VISITOR)  # public company information: visitors may ask
    out = await call_tool(spec, asession, VISITOR, parse_args(spec, json.dumps({"query": query})))
    assert out["items"], query
    top = out["items"][0]
    assert must_contain in top["text"]["untrusted_text"], (query, top["section"])
    hits = await reference_library.search(asession, query)
    assert hits[0].slug.startswith(expected_slug_prefix)
    # the whole result reaches the model untruncated
    text = guard.sanitize_result("search_reference", out)
    assert '"truncated"' not in text and len(text.encode()) <= guard.MAX_RESULT_BYTES
    assert "live tools apply" in out["note"]


@pytest.mark.asyncio
async def test_search_kb_never_returns_reference_passages(client, db, asession):
    seed = _load("seed_reference")
    assert await seed._seed(await _admin(client, db)) == 0
    spec = REGISTRY["search_kb"]
    out = await call_tool(
        spec, asession, VISITOR, parse_args(spec, json.dumps({"query": "LexCrest legal"}))
    )
    assert out["items"] == []
    assert await reference_library.search(asession, "the of and") == []  # stopwords only
