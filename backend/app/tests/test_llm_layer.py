"""Provider-neutral LLM layer (plan §2): types, offline fake, registry. No DB, no network.

Pins the contract every adapter must honour, using the fake as the reference implementation:
  * a stream ends with exactly one terminal event and nothing after it;
  * tool calls are announced, streamed, then closed with the full arguments;
  * the fake records every request, so agent tests can assert what was sent;
  * the registry resolves by name and refuses unknown providers with a clear error.
"""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.services.llm import registry
from app.services.llm.fake import FakeLLM, FakeToolCall, FakeTurn
from app.services.llm.types import (
    Completed,
    Failed,
    LLMClient,
    LLMRequest,
    LLMTool,
    LLMUsage,
    ProviderOpaque,
    Started,
    TextDelta,
    ToolCallDelta,
    ToolCallDone,
    ToolCallStarted,
    ToolResult,
    UserMessage,
    collect,
)


def _req(**over) -> LLMRequest:
    base = dict(
        instructions="You are the Capimax assistant.",
        tools=(LLMTool("get_my_wallet", "Wallet balance", {"type": "object", "properties": {}}),),
        items=(UserMessage("what is my balance?"),),
        model="test-model",
    )
    base.update(over)
    return LLMRequest(**base)


@pytest.mark.asyncio
async def test_text_turn_streams_deltas_and_completes():
    fake = FakeLLM([FakeTurn(text="Your balance is shown in the wallet card.", chunk=10)])
    got = await collect(fake.stream(_req()))
    assert got.text == "Your balance is shown in the wallet card."
    assert got.stop == "end" and got.failed is None and got.tool_calls == []
    assert got.usage == LLMUsage(100, 0, 20, 5)
    kinds = [type(e).__name__ for e in got.events]
    assert kinds[0] == "Started" and kinds[-1] == "Completed"
    assert kinds.count("TextDelta") == 5  # 42 chars in chunks of 10
    assert fake.calls == 1 and fake.requests[0].items[-1] == UserMessage("what is my balance?")


@pytest.mark.asyncio
async def test_tool_call_turn_is_announced_streamed_and_closed():
    fake = FakeLLM(
        [FakeTurn(tool_calls=[FakeToolCall("get_my_wallet", {"currency": "USD"}, call_id="c1")])]
    )
    got = await collect(fake.stream(_req()))
    assert got.stop == "tool_calls" and got.text == ""
    assert got.tool_calls == [ToolCallDone("c1", "get_my_wallet", '{"currency":"USD"}')]
    seq = [e for e in got.events if not isinstance(e, Started | Completed)]
    assert isinstance(seq[0], ToolCallStarted) and seq[0].name == "get_my_wallet"
    deltas = [e for e in seq if isinstance(e, ToolCallDelta)]
    assert "".join(d.arguments_delta for d in deltas) == '{"currency":"USD"}'
    assert isinstance(seq[-1], ToolCallDone)


@pytest.mark.asyncio
async def test_script_plays_in_order_and_runs_out_loudly():
    fake = FakeLLM().queue(FakeTurn(text="one"), FakeTurn(text="two"))
    assert (await collect(fake.stream(_req()))).text == "one"
    assert (await collect(fake.stream(_req()))).text == "two"
    got = await collect(fake.stream(_req()))
    assert got.failed == Failed("NO_SCRIPT", "FakeLLM has no scripted turn left.")
    assert got.stop == "error"
    assert fake.calls == 3 and len(fake.requests) == 3


@pytest.mark.asyncio
async def test_failure_incomplete_and_opaque_items_are_carried():
    opaque = ProviderOpaque({"type": "reasoning", "encrypted_content": "abc"})
    fake = FakeLLM(
        [
            FakeTurn(fail=("RATE_LIMIT", "slow down")),
            FakeTurn(text="cut off", stop="incomplete", opaque=(opaque,)),
        ]
    )
    failed = await collect(fake.stream(_req()))
    assert failed.failed == Failed("RATE_LIMIT", "slow down") and failed.text == ""
    partial = await collect(fake.stream(_req()))
    assert partial.stop == "incomplete" and partial.opaque_items == (opaque,)
    # the next turn replays the opaque item untouched
    nxt = _req(items=(UserMessage("hi"), *partial.opaque_items, ToolResult("c1", "{}")))
    assert nxt.items[1] is opaque


@pytest.mark.asyncio
async def test_collect_rejects_streams_that_break_the_contract():
    async def no_terminal():
        yield Started()
        yield TextDelta("half")

    async def after_terminal():
        yield Completed(LLMUsage(), "end")
        yield TextDelta("late")

    with pytest.raises(RuntimeError, match="without a Completed"):
        await collect(no_terminal())
    with pytest.raises(RuntimeError, match="after terminal"):
        await collect(after_terminal())


def test_usage_adds_and_keeps_reasoning_unknown_when_neither_side_reports_it():
    a, b = LLMUsage(10, 5, 3), LLMUsage(1, 1, 1)
    assert a.add(b) == LLMUsage(11, 6, 4, None)
    assert LLMUsage(1, 0, 0, 2).add(LLMUsage(1, 0, 0, None)) == LLMUsage(2, 0, 0, 2)


def test_registry_resolves_known_providers_and_refuses_unknown_ones():
    assert "openai" in registry.providers()
    registry.register("fake", FakeLLM)
    client = registry.get_client("fake")
    assert isinstance(client, LLMClient) and client.provider == "fake"
    with pytest.raises(AppError) as exc:
        registry.get_client("gemini")
    assert exc.value.code == "ASSISTANT_PROVIDER_UNKNOWN" and exc.value.status_code == 503
    assert "fake" in exc.value.message and "openai" in exc.value.message


def test_request_is_immutable_and_prefix_fields_are_plain_strings():
    req = _req()
    with pytest.raises(Exception):  # noqa: B017 — frozen dataclass: any mutation must fail
        req.model = "other"
    assert isinstance(req.instructions, str) and isinstance(req.tools, tuple)
    assert req.cache_key == "" and req.user_key == ""  # never populated with user data by default
