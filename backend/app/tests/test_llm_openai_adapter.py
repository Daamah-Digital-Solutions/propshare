"""OpenAI Responses adapter, tested WITHOUT network: a dummy SDK client records the params
and replays scripted provider events.

Pins what the plan requires of the wire call: store=False, encrypted reasoning included and
replayed, the HMAC safety identifier and constant cache key passed through, strict function
tools, and every provider failure surfacing as a Failed event rather than an exception.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from app.services.llm.openai_responses import OpenAIResponsesAdapter, build_params
from app.services.llm.types import (
    AssistantMessage,
    Completed,
    Failed,
    LLMRequest,
    LLMTool,
    LLMUsage,
    ProviderOpaque,
    ToolCall,
    ToolCallDone,
    ToolResult,
    UserMessage,
    collect,
)


class DummyClient:
    """Looks like AsyncOpenAI: ``responses.create(**params)`` returns an async event iterator."""

    def __init__(self, events=None, raise_on_create: Exception | None = None):
        self.params = None
        self._events = events or []
        self._raise = raise_on_create
        self.responses = self

    async def create(self, **params):
        self.params = params
        if self._raise:
            raise self._raise
        events = self._events

        async def gen():
            for e in events:
                yield e

        return gen()


def _usage(inp=120, cached=100, out=30, reasoning=8):
    return NS(
        input_tokens=inp,
        input_tokens_details=NS(cached_tokens=cached),
        output_tokens=out,
        output_tokens_details=NS(reasoning_tokens=reasoning),
    )


REQ = LLMRequest(
    instructions="CORE SYSTEM + KB",
    tools=(
        LLMTool(
            "get_my_wallet",
            "Wallet balance",
            {"type": "object", "properties": {}, "additionalProperties": False, "required": []},
        ),
    ),
    items=(
        UserMessage("hi"),
        AssistantMessage("hello"),
        ToolCall("c0", "get_my_wallet", "{}"),
        ToolResult("c0", '{"balance":"10.00"}'),
        ProviderOpaque({"type": "reasoning", "id": "rs_1", "encrypted_content": "enc"}),
        UserMessage("<platform_context>...</platform_context>\nbalance?"),
    ),
    model="gpt-test",
    effort="low",
    max_output_tokens=512,
    cache_key="capimax-assistant-v1",
    user_key="hmac-of-user",
)


def test_build_params_matches_the_plan():
    p = build_params(REQ)
    assert p["model"] == "gpt-test" and p["instructions"] == "CORE SYSTEM + KB"
    assert p["store"] is False and p["include"] == ["reasoning.encrypted_content"]
    assert p["stream"] is True and p["parallel_tool_calls"] is True
    assert p["reasoning"] == {"effort": "low"} and p["max_output_tokens"] == 512
    assert p["prompt_cache_key"] == "capimax-assistant-v1"
    assert p["safety_identifier"] == "hmac-of-user"
    assert p["tools"] == [
        {
            "type": "function",
            "name": "get_my_wallet",
            "description": "Wallet balance",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
                "required": [],
            },
            "strict": True,
        }
    ]
    assert p["input"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"type": "function_call", "call_id": "c0", "name": "get_my_wallet", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c0", "output": '{"balance":"10.00"}'},
        {"type": "reasoning", "id": "rs_1", "encrypted_content": "enc"},  # replayed verbatim
        {"role": "user", "content": "<platform_context>...</platform_context>\nbalance?"},
    ]
    # no user data anywhere except the last input item
    assert "hmac-of-user" not in p["instructions"] and "balance?" not in p["instructions"]
    # empty keys are simply not sent
    bare = build_params(LLMRequest("i", (), (UserMessage("x"),), "m"))
    assert "prompt_cache_key" not in bare and "safety_identifier" not in bare


@pytest.mark.asyncio
async def test_text_and_tool_call_stream_maps_to_neutral_events():
    events = [
        NS(type="response.created", response=NS(id="resp_1")),
        NS(type="response.in_progress"),
        NS(type="response.output_text.delta", delta="Let me "),
        NS(type="response.output_text.delta", delta="check."),
        NS(
            type="response.output_item.added",
            item=NS(type="function_call", id="fc_1", call_id="call_1", name="get_my_wallet"),
        ),
        NS(type="response.function_call_arguments.delta", item_id="fc_1", delta='{"cur'),
        NS(type="response.function_call_arguments.delta", item_id="fc_1", delta='rency":"USD"}'),
        NS(
            type="response.function_call_arguments.done",
            item_id="fc_1",
            arguments='{"currency":"USD"}',
        ),
        NS(
            type="response.output_item.done",
            item=NS(
                type="function_call",
                id="fc_1",
                call_id="call_1",
                name="get_my_wallet",
                arguments='{"currency":"USD"}',
            ),
        ),
        NS(
            type="response.output_item.done",
            item=NS(
                type="reasoning",
                id="rs_9",
                encrypted_content="ENC9",
                summary=[],
                model_dump=lambda exclude_none: {
                    "type": "reasoning",
                    "id": "rs_9",
                    "encrypted_content": "ENC9",
                },
            ),
        ),
        NS(type="response.completed", response=NS(id="resp_1", usage=_usage())),
        NS(type="response.output_text.delta", delta="NEVER SEEN"),  # after terminal: ignored
    ]
    client = DummyClient(events)
    got = await collect(OpenAIResponsesAdapter(client=client).stream(REQ))
    assert got.text == "Let me check."
    assert got.tool_calls == [ToolCallDone("call_1", "get_my_wallet", '{"currency":"USD"}')]
    assert got.stop == "tool_calls"
    assert got.usage == LLMUsage(120, 100, 30, 8)
    assert got.opaque_items == (
        ProviderOpaque({"type": "reasoning", "id": "rs_9", "encrypted_content": "ENC9"}),
    )
    assert client.params["store"] is False  # the dummy saw exactly the built params
    deltas = [e for e in got.events if type(e).__name__ == "ToolCallDelta"]
    assert all(d.call_id == "call_1" for d in deltas)  # item id -> call id mapping


@pytest.mark.asyncio
async def test_incomplete_refusal_and_failed_responses():
    inc = [
        NS(type="response.created", response=NS(id="r")),
        NS(type="response.output_text.delta", delta="partial"),
        NS(
            type="response.incomplete",
            response=NS(usage=_usage(), incomplete_details=NS(reason="max_output_tokens")),
        ),
    ]
    got = await collect(OpenAIResponsesAdapter(client=DummyClient(inc)).stream(REQ))
    assert got.text == "partial" and got.stop == "max_tokens"

    ref = [
        NS(type="response.created", response=NS(id="r")),
        NS(type="response.refusal.delta", delta="I can't"),
        NS(type="response.refusal.done", refusal="I can't help with that"),
        NS(type="response.completed", response=NS(usage=_usage())),
    ]
    got = await collect(OpenAIResponsesAdapter(client=DummyClient(ref)).stream(REQ))
    assert got.stop == "refusal" and got.text == ""

    failed = [
        NS(type="response.created", response=NS(id="r")),
        NS(type="response.failed", response=NS(error=NS(code="server_error", message="boom"))),
    ]
    got = await collect(OpenAIResponsesAdapter(client=DummyClient(failed)).stream(REQ))
    assert got.failed == Failed("server_error", "boom")

    err = [NS(type="error", code="rate_limit_exceeded", message="slow down")]
    got = await collect(OpenAIResponsesAdapter(client=DummyClient(err)).stream(REQ))
    assert got.failed == Failed("rate_limit_exceeded", "slow down")

    truncated = [NS(type="response.created", response=NS(id="r"))]
    got = await collect(OpenAIResponsesAdapter(client=DummyClient(truncated)).stream(REQ))
    assert got.failed is not None and got.failed.code == "STREAM_ENDED"


@pytest.mark.asyncio
async def test_sdk_exceptions_become_failed_events_not_exceptions():
    import openai

    class Conn(openai.APIConnectionError):
        def __init__(self):  # bypass the SDK constructor: only the type matters here
            Exception.__init__(self, "network down")

    got = await collect(
        OpenAIResponsesAdapter(client=DummyClient(raise_on_create=Conn())).stream(REQ)
    )
    assert got.failed is not None and got.failed.code == "CONNECTION"
    assert got.stop == "error" and isinstance(got.events[-1], Failed)

    got = await collect(
        OpenAIResponsesAdapter(client=DummyClient(raise_on_create=RuntimeError("weird"))).stream(
            REQ
        )
    )
    assert got.failed == Failed("PROVIDER_ERROR", "weird")

    # a failure mid-stream is also an event
    class Exploding:
        def __init__(self):
            self.responses = self

        async def create(self, **params):
            async def gen():
                yield NS(type="response.created", response=NS(id="r"))
                yield NS(type="response.output_text.delta", delta="ok ")
                raise RuntimeError("socket closed")

            return gen()

    got = await collect(OpenAIResponsesAdapter(client=Exploding()).stream(REQ))
    assert got.text == "ok " and got.failed == Failed("PROVIDER_ERROR", "socket closed")


def test_usage_tolerates_missing_details():
    from app.services.llm.openai_responses import _usage_of

    assert _usage_of(NS(usage=None)) == LLMUsage()
    assert _usage_of(NS(usage=NS(input_tokens=5, output_tokens=2))) == LLMUsage(5, 0, 2, None)
    assert isinstance(Completed(LLMUsage(), "end"), Completed)
