"""The assistant never presents the client's target platform as today's platform.

The reference library is the client's description of the complete platform; asked "do you do
KYB?", the model answered "Yes" and listed the checks (live check, 2026-09-24). What is not
built is now carried next to the passages search_reference returns.

What each test protects:
  * the lines a question names come first, then those the passages touch, capped;
  * everyday words do not trigger a line ("forward-looking", "a quote");
  * the reference tool returns the lines for a KYB question, and the result still fits the
    8 KB tool cap without truncating the passages.
"""

from __future__ import annotations

import json

import pytest

from app.services.assistant import guard, platform_gaps
from app.services.assistant.context import AgentContext
from app.services.assistant.tools import REGISTRY
from app.services.assistant.tools.base import call_tool, parse_args
from app.tests.test_reference_library_db import _admin, _load

VISITOR = AgentContext(None, "vis-gaps", (), None, "none", False, None)


def test_question_first_then_passages_and_capped():
    notes = platform_gaps.notes_for(
        "Do you verify companies with KYB?",
        ["Supported online payments use Stripe and PayPal.", "Refunds follow the agreement."],
    )
    assert notes[0].startswith("Company (KYB) verification")
    assert any(n.startswith("PayPal, Mercury") for n in notes)
    assert any(n.startswith("Refunds cannot") for n in notes)
    many = " ".join(["KYB", "PayPal", "refund", "SMS", "waterfall", "e-signature", "phased"])
    assert len(platform_gaps.notes_for(many, [])) == platform_gaps.MAX_NOTES


def test_everyday_words_do_not_trigger_a_line():
    text = (
        "A projection is a forward-looking estimate based on disclosed assumptions. "
        "Ask for a quote of the fees before you commit."
    )
    assert platform_gaps.notes_for("What is a projection?", [text]) == []


@pytest.mark.asyncio
async def test_search_reference_carries_what_is_not_built(client, db, asession):
    seed = _load("seed_reference")
    assert await seed._seed(await _admin(client, db)) == 0
    spec = REGISTRY["search_reference"]
    for query in (
        "Do you verify companies with KYB and their beneficial owners?",
        "Can I pay with PayPal or Wise?",
        "How do I verify my certificate reference?",
    ):
        out = await call_tool(
            spec, asession, VISITOR, parse_args(spec, json.dumps({"query": query}))
        )
        assert out["not_on_platform_yet"], query
        assert "not available today" in out["note"]
        text = guard.sanitize_result("search_reference", out)
        assert '"truncated"' not in text and len(text.encode()) <= guard.MAX_RESULT_BYTES
    kyb = await call_tool(
        spec, asession, VISITOR, parse_args(spec, json.dumps({"query": "KYB for companies"}))
    )
    assert kyb["not_on_platform_yet"][0].startswith("Company (KYB) verification")
