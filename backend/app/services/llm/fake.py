"""Scripted provider for tests: no network, no cost, fully deterministic.

A script is a list of turns; each call to ``stream`` plays the next turn. A turn can emit
text, tool calls, a failure, or an incomplete stop, in any mix, so every branch of the agent
loop (tool round-trips, iteration caps, safe mode) is testable offline. Every request is
recorded so tests can assert what the agent actually sent (instructions stability, history
window, that user data never leaks into the cached prefix, and so on).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.services.llm.types import (
    Completed,
    Failed,
    LLMRequest,
    LLMStreamEvent,
    LLMUsage,
    ProviderOpaque,
    Started,
    StopReason,
    TextDelta,
    ToolCallDelta,
    ToolCallDone,
    ToolCallStarted,
)


@dataclass(frozen=True)
class FakeToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = ""


@dataclass
class FakeTurn:
    text: str = ""
    tool_calls: list[FakeToolCall] = field(default_factory=list)
    stop: StopReason | None = None  # default: tool_calls if any, else end
    fail: tuple[str, str] | None = None  # (code, message) -> Failed instead of Completed
    usage: LLMUsage = field(default_factory=lambda: LLMUsage(100, 0, 20, 5))
    chunk: int = 7  # characters per text delta
    opaque: tuple[ProviderOpaque, ...] = ()


class FakeLLM:
    provider = "fake"

    def __init__(self, script: list[FakeTurn] | None = None) -> None:
        self.script: list[FakeTurn] = list(script or [])
        self.requests: list[LLMRequest] = []
        self._calls = 0

    def queue(self, *turns: FakeTurn) -> FakeLLM:
        self.script.extend(turns)
        return self

    @property
    def calls(self) -> int:
        return self._calls

    async def stream(self, req: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        self.requests.append(req)
        self._calls += 1
        if not self.script:
            yield Started(f"fake-{self._calls}")
            yield Failed("NO_SCRIPT", "FakeLLM has no scripted turn left.")
            return
        turn = self.script.pop(0)
        yield Started(f"fake-{self._calls}")
        if turn.fail:
            yield Failed(*turn.fail)
            return
        for i in range(0, len(turn.text), turn.chunk):
            yield TextDelta(turn.text[i : i + turn.chunk])
        for n, call in enumerate(turn.tool_calls, start=1):
            call_id = call.call_id or f"call-{self._calls}-{n}"
            args = json.dumps(call.arguments, separators=(",", ":"))
            yield ToolCallStarted(call_id, call.name)
            # arguments arrive in two pieces, like a real stream
            mid = max(1, len(args) // 2)
            yield ToolCallDelta(call_id, args[:mid])
            yield ToolCallDelta(call_id, args[mid:])
            yield ToolCallDone(call_id, call.name, args)
        stop: StopReason = turn.stop or ("tool_calls" if turn.tool_calls else "end")
        yield Completed(turn.usage, stop, turn.opaque)
