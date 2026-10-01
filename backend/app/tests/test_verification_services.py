"""Verification partners: the page, the assistant and the link guard agree.

The client named five services that verify Capimax records (2026-10-01): Capimax documents and
investment certificates and valuation / financial documents at CIM Global Financial, insurance
at CoverTech, legal documents at LexCrest Global, blockchain records at Proof Anchor. Before,
the assistant only ever sent people "to the Verification Center". What each test protects:
  * the SPA's list (src/lib/verificationPartners.ts) and the backend's are the same five, in
    the same order, with the same providers and links;
  * the assistant's tool gives every service with what to enter and its link, to visitors
    too, untruncated;
  * a holder's certificate reference from get_my_holdings is the one printed on the PDF;
  * a reply may carry a partner's exact link, which becomes a button; a look-alike host, a
    longer path, a query string or plain http is still removed;
  * a sentence naming Proof Anchor is not flagged as blockchain wording about PropShare, the
    same words about PropShare still are;
  * the knowledge-base article and the system prompt route verification questions to them.
"""

# ruff: noqa: E501
from __future__ import annotations

import pathlib
import re
import uuid

import pytest

from app.services import certificate_service, verification_partners
from app.services.assistant import guard, prompts
from app.services.assistant.tools import REGISTRY
from app.services.assistant.tools.base import call_tool, parse_args
from app.services.llm.fake import FakeLLM, FakeToolCall, FakeTurn
from app.services.llm.types import ToolResult
from app.tests.test_assistant_agent_db import _conv, _text, _turn, keys  # noqa: F401 (fixture)
from app.tests.test_assistant_eval_tools_db import _load
from app.tests.test_assistant_tools_db import VISITOR, _ctx, _prop, _user

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPA_LIST = ROOT / "src" / "lib" / "verificationPartners.ts"
CIM = "https://www.cimglobalfinancial.com/capimax-verify"
COVERTECH = "https://www.covertechinsurance.com/capimax-ecosystem"
LEXCREST = "https://lexcrestlegal.xyz/document-center"
PROOF_ANCHOR = "https://www.proofanchor.io/verify"


def test_the_page_and_the_assistant_list_the_same_services():
    source = SPA_LIST.read_text(encoding="utf-8")
    body = source.split("VERIFICATION_PARTNERS", 1)[1]
    spa = list(
        zip(
            re.findall(r'\bkey: "([^"]+)"', body),
            re.findall(r'\btitle: "([^"]+)"', body),
            re.findall(r'\bprovider: "([^"]+)"', body),
            re.findall(r'\burl: "([^"]+)"', body),
            strict=True,
        )
    )
    backend = [(s.key, s.title, s.provider, s.url) for s in verification_partners.SERVICES]
    assert spa == backend
    assert verification_partners.URLS == {CIM, COVERTECH, LEXCREST, PROOF_ANCHOR}


@pytest.mark.asyncio
async def test_the_tool_gives_every_service_to_anyone(asession):
    spec = REGISTRY["get_verification_services"]
    assert spec.tier == "informational"
    guard.authorize(spec, VISITOR)  # visitors may ask too
    out = await call_tool(spec, asession, VISITOR, parse_args(spec, "{}"))
    assert [s["key"] for s in out["services"]] == [
        "capimax_documents",
        "valuation_financial",
        "insurance",
        "legal",
        "blockchain",
    ]
    by_key = {s["key"]: s for s in out["services"]}
    assert by_key["capimax_documents"]["url"] == CIM
    assert "Certificate Number" in by_key["capimax_documents"]["how_to_verify"]
    assert by_key["insurance"]["provider"] == "CoverTech Insurance"
    assert "Document Number" in by_key["legal"]["how_to_verify"]
    assert "Contract Address" in by_key["blockchain"]["how_to_verify"]
    assert "exactly" in out["note"] and "get_my_holdings" in out["note"]
    text = guard.sanitize_result(spec.name, out)
    assert '"truncated"' not in text and len(text.encode()) <= guard.MAX_RESULT_BYTES


@pytest.mark.asyncio
async def test_a_holders_reference_is_the_one_printed_on_the_certificate(client, db, asession):
    uid = await _user(client, db, f"verify-{uuid.uuid4().hex[:6]}@capimaxtrial.com")
    pid = _prop(db, slug=f"verify-tower-{uuid.uuid4().hex[:6]}")
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) "
        "VALUES (:u,:p,4,100,'purchase')",
        u=uid,
        p=pid,
    )
    spec = REGISTRY["get_my_holdings"]
    out = await call_tool(spec, asession, await _ctx(asession, uid), parse_args(spec, "{}"))
    ref = out["items"][0]["certificate_reference"]
    assert ref == ("CMX-" + str(pid)[:4] + str(uid)[:4]).upper()
    _name, pdf = await certificate_service.build_for_holding(
        asession, user_id=uid, property_id=uuid.UUID(str(pid))
    )
    assert ref.encode() in pdf


@pytest.mark.asyncio
@pytest.mark.usefixtures("keys")
async def test_a_verification_question_ends_with_the_partners_button(client, db, asession):
    uid = await _user(client, db, f"verify-{uuid.uuid4().hex[:6]}@capimaxtrial.com")
    ctx = await _conv(asession, uid)
    answer = (
        "Insurance certificates are verified by CoverTech Insurance: it confirms the "
        "certificate's authenticity, coverage and current status.\n"
        f"[Verify Insurance Certificate]({COVERTECH})"
    )
    llm = FakeLLM(
        [
            FakeTurn(tool_calls=[FakeToolCall("get_verification_services", {})]),
            FakeTurn(text=answer),
        ]
    )
    events = await _turn(asession, ctx, "How do I check an insurance certificate?", llm)
    seen = [i for i in llm.requests[1].items if isinstance(i, ToolResult)][0].output
    assert COVERTECH in seen and PROOF_ANCHOR in seen  # the model had every service in hand
    cards = [e["data"] for e in events if e["event"] == "card"]
    assert cards == [{"kind": "link", "path": COVERTECH, "label": "Verify Insurance Certificate"}]
    assert _text(events).endswith("coverage and current status.")  # the button replaces the line
    assert events[-1]["data"]["flags"] == []


def test_a_partners_exact_link_becomes_a_button(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "app_base_url", "https://capimaxpropshare.com", raising=False
    )
    text, flags, links = guard.postprocess_output(
        f"Open [Verify Document / Certificate]({CIM}) and enter CMX-1234ABCD.\n"
        f"Insurance certificates: {COVERTECH}.\n"
        f"- [LexCrest Document Center]({LEXCREST})\n"
        f"Proof Anchor, in capitals: {PROOF_ANCHOR.upper()}"
    )
    assert flags == []
    assert "Open Verify Document / Certificate and enter CMX-1234ABCD." in text
    assert f"{COVERTECH}." in text  # a link written out stays readable, the dot stays a dot
    assert (
        "LexCrest Document Center" not in text
    )  # the line was only a link: the button replaces it
    assert [(link["route_id"], link["path"], link["label"]) for link in links] == [
        (guard.PARTNER_ROUTE, LEXCREST, "LexCrest Document Center"),
        (guard.PARTNER_ROUTE, CIM, "Verify Document / Certificate"),
        (guard.PARTNER_ROUTE, COVERTECH, "Verify with CoverTech Insurance"),
        (guard.PARTNER_ROUTE, PROOF_ANCHOR, "Verify with Proof Anchor"),
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.cimglobalfinancial.com.evil.example/capimax-verify",
        "https://www.cimglobalfinancial.com/capimax-verify/../../login",
        "https://www.proofanchor.io/verify?next=https://evil.example",
        "http://www.proofanchor.io/verify",
        "https://www.proofanchor.io/verify-now",
        "https://lexcrestglobal.xyz/document-center",
    ],
)
def test_anything_like_a_partner_link_is_still_removed(url):
    text, flags, links = guard.postprocess_output(f"Verify it at [this page]({url}) or {url}")
    assert "evil.example" not in text and links == []
    assert "external_link_removed" in flags and "[link removed]" in text


def test_naming_proof_anchor_is_not_blockchain_wording_about_propshare():
    clean = (
        "Records of Capimax BRX are verified by Proof Anchor: search by contract or token "
        f"address at {PROOF_ANCHOR}.\n"
        "| Blockchain, Smart Contract & Digital Asset Verification | Proof Anchor |\n"
        "5. Blockchain, Smart Contract & Digital Asset Verification"
    )
    assert guard.postprocess_output(clean)[1] == []
    _text, flags, _links = guard.postprocess_output(
        "Proof Anchor checks other platforms. Your PropShare units are tokens on the blockchain."
    )
    assert len([f for f in flags if f.startswith("forbidden_term")]) == 2


def test_the_assistant_is_told_to_send_people_to_the_right_partner():
    seed = _load("seed_kb")
    articles = {
        lang: next(
            body for slug, *_rest, body in rows if slug == "developers-and-verification-center"
        )
        for lang, rows in (("en", seed.ARTICLES), ("ar", seed.ARTICLES_AR))
    }
    for body in articles.values():
        for url in (CIM, COVERTECH, LEXCREST, PROOF_ANCHOR):
            assert url in body
        for provider in (
            "CIM Global Financial",
            "CoverTech Insurance",
            "LexCrest Global",
            "Proof Anchor",
        ):
            assert provider in body
    prompt = prompts.CORE_SYSTEM
    assert "get_verification_services" in prompt and "copied exactly" in prompt
    assert "a verification question gets /kyc" not in prompt
    assert guard.make_link("verification_services")["path"] == "/verification-center"
