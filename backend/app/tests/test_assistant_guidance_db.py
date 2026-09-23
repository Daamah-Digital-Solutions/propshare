"""The assistant guides, it does not only answer; and the first message is not slow.

What each test protects:
  * a page the model links as [label](path) becomes a button with no extra model round trip
    (the old flow needed a prepare_deep_link call: ~5 s more per answer), and the prompt
    lists the pages it may link, generated from the allow-list;
  * a visitor told to sign in ALWAYS gets Sign in + Create account buttons, even when the
    model forgot them (owner's report, 2026-09-23); a signed-in user never gets them, and
    "holder register" in an answer is not mistaken for an account prompt;
  * the cache warm-up sends the byte-identical prefix of a real turn, runs once per interval
    across workers (the claim), and stays off when the assistant or the interval is off.
"""

from __future__ import annotations

import base64
import datetime as dt
import os

import pytest

from app.core import crypto
from app.core.config import get_settings
from app.services import kb_service
from app.services.assistant import agent, cache_warm, prompts
from app.services.assistant.agent import AssistantSettings, run_turn
from app.services.assistant.context import AgentContext, load_context
from app.services.assistant.tools import llm_tools
from app.services.llm.fake import FakeLLM, FakeTurn

PW = "Passw0rd!23"
SETTINGS = AssistantSettings(
    enabled=True,
    visitor_enabled=True,
    provider="fake",
    model="fake-model",
    effort="low",
    max_output_tokens=512,
    disabled_tools=frozenset(),
    daily_message_cap=200,
    daily_token_budget=10**9,
    retention_days=180,
    rollout="all",
    pricing={},
)
VISITOR = AgentContext(None, "vis-guide", (), None, "none", False, None)


@pytest.fixture
def keys(monkeypatch, tmp_path):
    s = get_settings()
    path = tmp_path / "assistant.keys"
    path.write_text("k1:" + base64.b64encode(os.urandom(32)).decode(), encoding="utf-8")
    monkeypatch.setattr(s, "assistant_encryption_keys_file", str(path), raising=False)
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)
    monkeypatch.setattr(s, "assistant_hmac_secret", "test-hmac", raising=False)
    crypto.reset_cache()
    yield
    crypto.reset_cache()


async def _visitor(asession) -> AgentContext:
    conv = await agent.start_conversation(asession, VISITOR)
    await asession.commit()
    return AgentContext(**{**VISITOR.__dict__, "conversation_id": conv.id})


async def _member(client, db, asession) -> AgentContext:
    r = await client.post(
        "/api/v1/auth/register", json={"email": "m@guide.io", "password": PW, "full_name": "M"}
    )
    assert r.status_code == 201
    uid = db("SELECT id FROM users WHERE email='m@guide.io'")[0][0]
    ctx = await load_context(asession, user_id=uid)
    conv = await agent.start_conversation(asession, ctx)
    await asession.commit()
    return AgentContext(**{**ctx.__dict__, "conversation_id": conv.id})


async def _cards(asession, ctx, answer: str) -> tuple[list[dict], FakeLLM]:
    llm = FakeLLM([FakeTurn(text=answer)])
    events = [ev async for ev in run_turn(asession, ctx, "hi", llm, settings=SETTINGS)]
    return [e["data"] for e in events if e["event"] == "card"], llm


def test_prompt_lists_the_linkable_pages():
    core = prompts.CORE_SYSTEM
    assert "{PAGES}" not in core
    for path in ("/auth", "/auth?tab=register", "/dashboard?tab=wallet", "/kyc", "/support"):
        assert path in core
    assert "prepare_deep_link returns" not in core  # links no longer need a tool round trip


@pytest.mark.asyncio
async def test_markdown_links_become_buttons_in_one_model_call(client, db, asession, keys):
    ctx = await _member(client, db, asession)
    cards, llm = await _cards(
        asession, ctx, "Add funds from your wallet: [Open wallet](/dashboard?tab=wallet)."
    )
    assert cards == [{"kind": "link", "path": "/dashboard?tab=wallet", "label": "Open wallet"}]
    assert len(llm.requests) == 1


@pytest.mark.asyncio
async def test_buttons_speak_the_reply_language_and_are_not_repeated_as_text(asession, keys):
    ctx = await _visitor(asession)
    answer = (
        "للبدء أنشئ حسابًا ثم أكمل التحقق.\n\nابدأ من هنا:\n\n"
        "[إنشاء حساب مجاني](/auth?tab=register)\n- [تصفح العقارات](/marketplace)"
    )
    llm = FakeLLM([FakeTurn(text=answer)])
    events = [ev async for ev in run_turn(asession, ctx, "ابدأ منين؟", llm, settings=SETTINGS)]
    cards = [e["data"] for e in events if e["event"] == "card"]
    shown = ""  # what the client ends up showing: deltas after the last reset
    for e in events:
        if e["event"] == "reset":
            shown = ""
        elif e["event"] == "delta":
            shown += e["data"]["text"]
    assert shown.startswith("للبدء")
    assert "تصفح العقارات" not in shown and "إنشاء حساب" not in shown  # buttons, not text
    assert [(c["path"], c["label"]) for c in cards] == [
        ("/auth?tab=register", "إنشاء حساب مجاني"),
        ("/marketplace", "تصفح العقارات"),
        ("/auth", "تسجيل الدخول"),  # automatic, in Arabic because the reply is Arabic
    ]


@pytest.mark.parametrize(
    "answer",
    [
        "For account-specific information, please sign in first.",
        "You need to log in to see that.",
        "من فضلك سجّل الدخول أولاً عشان أقدر أشوف حسابك.",
    ],
)
@pytest.mark.asyncio
async def test_visitor_told_to_sign_in_always_gets_the_buttons(asession, keys, answer):
    ctx = await _visitor(asession)
    cards, _ = await _cards(asession, ctx, answer)
    assert [c["path"] for c in cards] == ["/auth", "/auth?tab=register"]
    arabic = any("؀" <= ch <= "ۿ" for ch in answer)
    expected = (
        ["تسجيل الدخول", "إنشاء حساب مجاني"] if arabic else ["Sign in", "Create a free account"]
    )
    assert [c["label"] for c in cards] == expected


@pytest.mark.asyncio
async def test_no_duplicate_when_the_model_already_linked_sign_in(asession, keys):
    ctx = await _visitor(asession)
    cards, _ = await _cards(asession, ctx, "Please [Sign in](/auth) to see your balance.")
    assert [c["path"] for c in cards] == ["/auth", "/auth?tab=register"]


@pytest.mark.asyncio
async def test_no_sign_in_buttons_when_not_needed(client, db, asession, keys):
    ctx = await _visitor(asession)
    cards, _ = await _cards(
        asession, ctx, "Ownership is recorded in the holder register of each SPV."
    )
    assert cards == []
    member = await _member(client, db, asession)
    cards, _ = await _cards(asession, member, "Please sign in again on your other device.")
    assert cards == []


# --------------------------------------------------------------------------- #
# cache warm-up
# --------------------------------------------------------------------------- #
@pytest.fixture
def assistant_on(db, monkeypatch, keys):
    s = get_settings()
    monkeypatch.setattr(s, "openai_api_key", "sk-test", raising=False)
    monkeypatch.setattr(s, "assistant_enabled", True, raising=False)
    for key, value in (("assistant_enabled", "true"), ("assistant_model", "fake-model")):
        db(
            "INSERT INTO platform_settings (key, value) VALUES (:k,:v) "
            "ON CONFLICT (key) DO UPDATE SET value=:v",
            k=key,
            v=value,
        )


@pytest.mark.asyncio
async def test_warm_up_sends_the_real_prefix_once_per_interval(asession, assistant_on):
    llm = FakeLLM([FakeTurn(text="OK"), FakeTurn(text="OK")])
    t0 = dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.UTC)

    out = await cache_warm.warm_once(asession, llm_factory=lambda _p: llm, now=t0)
    assert out.startswith("warmed")
    req = llm.requests[0]
    assert req.instructions == prompts.build_instructions(await kb_service.render_bundle(asession))
    assert req.tools == tuple(llm_tools(exclude=set()))
    assert req.cache_key == agent.CACHE_KEY and req.max_output_tokens == 16

    # a second worker in the same interval does nothing
    later = t0 + dt.timedelta(minutes=5)
    assert await cache_warm.warm_once(asession, llm_factory=lambda _p: llm, now=later) == "not_due"
    assert len(llm.requests) == 1
    # after the interval, warm again
    due = t0 + dt.timedelta(minutes=21)
    assert (await cache_warm.warm_once(asession, llm_factory=lambda _p: llm, now=due)).startswith(
        "warmed"
    )
    assert len(llm.requests) == 2


@pytest.mark.asyncio
async def test_warm_up_is_off_when_disabled(db, asession, assistant_on):
    llm = FakeLLM([FakeTurn(text="OK")])
    db(
        "INSERT INTO platform_settings (key, value) VALUES ('assistant_cache_warm_minutes','0') "
        "ON CONFLICT (key) DO UPDATE SET value='0'"
    )
    assert await cache_warm.warm_once(asession, llm_factory=lambda _p: llm) == "off"
    db("UPDATE platform_settings SET value='20' WHERE key='assistant_cache_warm_minutes'")
    db("UPDATE platform_settings SET value='false' WHERE key='assistant_enabled'")
    assert await cache_warm.warm_once(asession, llm_factory=lambda _p: llm) == "off"
    assert llm.requests == []
