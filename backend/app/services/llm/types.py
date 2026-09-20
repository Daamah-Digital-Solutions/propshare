"""Provider-neutral types the assistant speaks (plan §2).

The agent loop only ever sees these dataclasses. A provider adapter (OpenAI today, anything
else later) translates them to and from its own wire format, so switching providers is a
new adapter plus a setting, never a change to the agent, the tools or the guards.

Streams are modelled as a flat sequence of events: text arrives as deltas, tool calls are
announced, streamed and closed, and every stream ends with exactly one ``Completed`` or
``Failed`` event.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# --------------------------------------------------------------------------- #
# Conversation items (what we send)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class AssistantMessage:
    text: str


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation the model requested on an earlier turn (replayed as history)."""

    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True)
class ToolResult:
    """What we answered to a tool call. ``output`` is already JSON text."""

    call_id: str
    output: str
    is_error: bool = False


@dataclass(frozen=True)
class ProviderOpaque:
    """A provider-specific item replayed verbatim (e.g. encrypted reasoning). Never inspected."""

    raw: dict[str, Any]


LLMItem = UserMessage | AssistantMessage | ToolCall | ToolResult | ProviderOpaque


@dataclass(frozen=True)
class LLMTool:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    strict: bool = True


@dataclass(frozen=True)
class LLMRequest:
    """One model call. ``instructions`` + ``tools`` are the cacheable prefix and must be
    byte-stable across turns; per-user data belongs only in the last user item."""

    instructions: str
    tools: tuple[LLMTool, ...]
    items: tuple[LLMItem, ...]
    model: str
    effort: str = "low"
    max_output_tokens: int = 2048
    cache_key: str = ""  # routes the request to one cache shard; never user data
    user_key: str = ""  # opaque safety identifier (HMAC of the user id), never the id


# --------------------------------------------------------------------------- #
# Stream events (what we get back)
# --------------------------------------------------------------------------- #

StopReason = Literal["end", "tool_calls", "max_tokens", "incomplete", "refusal", "error"]


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int | None = None

    def add(self, other: LLMUsage) -> LLMUsage:
        reasoning = (
            None
            if self.reasoning_tokens is None and other.reasoning_tokens is None
            else (self.reasoning_tokens or 0) + (other.reasoning_tokens or 0)
        )
        return LLMUsage(
            self.input_tokens + other.input_tokens,
            self.cached_input_tokens + other.cached_input_tokens,
            self.output_tokens + other.output_tokens,
            reasoning,
        )


@dataclass(frozen=True)
class Started:
    response_id: str = ""


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCallStarted:
    call_id: str
    name: str


@dataclass(frozen=True)
class ToolCallDelta:
    call_id: str
    arguments_delta: str


@dataclass(frozen=True)
class ToolCallDone:
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True)
class Completed:
    usage: LLMUsage
    stop: StopReason
    # provider items that must be replayed next turn (e.g. encrypted reasoning)
    opaque_items: tuple[ProviderOpaque, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Failed:
    code: str
    message: str


LLMStreamEvent = (
    Started | TextDelta | ToolCallStarted | ToolCallDelta | ToolCallDone | Completed | Failed
)


@runtime_checkable
class LLMClient(Protocol):
    provider: str

    def stream(self, req: LLMRequest) -> AsyncIterator[LLMStreamEvent]: ...


# --------------------------------------------------------------------------- #
# Helper: gather a whole stream (tests, non-streaming callers)
# --------------------------------------------------------------------------- #


@dataclass
class Collected:
    text: str = ""
    tool_calls: list[ToolCallDone] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    stop: StopReason | None = None
    failed: Failed | None = None
    opaque_items: tuple[ProviderOpaque, ...] = ()
    events: list[LLMStreamEvent] = field(default_factory=list)


async def collect(stream: AsyncIterator[LLMStreamEvent]) -> Collected:
    """Consume a stream into one object. Raises if the stream ends without Completed/Failed
    or emits anything after the terminal event: a broken adapter must be loud."""
    out = Collected()
    terminal = False
    async for ev in stream:
        if terminal:
            raise RuntimeError(f"event after terminal event: {ev!r}")
        out.events.append(ev)
        if isinstance(ev, TextDelta):
            out.text += ev.text
        elif isinstance(ev, ToolCallDone):
            out.tool_calls.append(ev)
        elif isinstance(ev, Completed):
            out.usage, out.stop, out.opaque_items = ev.usage, ev.stop, ev.opaque_items
            terminal = True
        elif isinstance(ev, Failed):
            out.failed, out.stop = ev, "error"
            terminal = True
    if not terminal:
        raise RuntimeError("stream ended without a Completed or Failed event")
    return out
