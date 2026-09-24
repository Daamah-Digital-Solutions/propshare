"""Tool plumbing (plan §4): every tool is a ``ToolSpec`` with a pydantic INPUT model (turned
into a strict JSON schema for the provider) and a pydantic OUTPUT model that acts as an
allow-list: a handler returns a plain dict and the base layer validates it through the
output model with ``extra="forbid"``, so a field the model was never meant to see cannot leak
even if a service returns more.

Tiers:
  informational   public data, visitors allowed
  read_own        the signed-in user's own data
  prepare_only    computes something for the user (a quote) but changes nothing
  confirmed_action creates a PROPOSAL only; execution is a separate authenticated call
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.assistant.context import AgentContext
from app.services.llm.types import LLMTool

Tier = str
TIERS: tuple[Tier, ...] = ("informational", "read_own", "prepare_only", "confirmed_action")


class ToolOutput(BaseModel):
    """Base for every output model: unknown keys are an error, never silently passed on."""

    model_config = ConfigDict(extra="forbid")


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


Handler = Callable[[AsyncSession, AgentContext, BaseModel], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[ToolOutput]
    tier: Tier
    handler: Handler
    # roles that may call it (empty = any signed-in user for read_own; visitors never)
    roles: tuple[str, ...] = ()

    def llm_tool(self) -> LLMTool:
        return LLMTool(self.name, self.description, to_strict_schema(self.input_model), True)


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.tier not in TIERS:
        raise ValueError(f"{spec.name}: unknown tier {spec.tier!r}")
    if not issubclass(spec.output_model, ToolOutput):
        raise TypeError(f"{spec.name}: output model must extend ToolOutput")
    if spec.name in REGISTRY:
        raise ValueError(f"tool {spec.name!r} registered twice")
    REGISTRY[spec.name] = spec
    return spec


def get_spec(name: str) -> ToolSpec | None:
    return REGISTRY.get(name)


def llm_tools(exclude: set[str] | None = None) -> tuple[LLMTool, ...]:
    """Sorted by name: the tool list is part of the cached prefix and must not reorder."""
    return tuple(
        spec.llm_tool() for name, spec in sorted(REGISTRY.items()) if name not in (exclude or set())
    )


# --------------------------------------------------------------------------- #
# Strict JSON schema (provider requirement for strict function tools)
# --------------------------------------------------------------------------- #
def to_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic schema -> strict tool schema: every object has additionalProperties=false and
    lists ALL its properties as required; optional fields become nullable instead."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            ref = node["$ref"].split("/")[-1]
            return walk(defs[ref])
        # "properties" maps field names to schemas; the map itself is not a schema (a field
        # may even be called "properties")
        node = {
            k: {name: walk(sub) for name, sub in v.items()} if k == "properties" else walk(v)
            for k, v in node.items()
            if k not in ("default", "title")
        }
        if node.get("type") == "object" or "properties" in node:
            props = node.get("properties", {})
            required = set(node.get("required", []))
            for key, prop in list(props.items()):
                if key not in required:
                    props[key] = _nullable(prop)
            node["properties"] = props
            node["required"] = list(props.keys())
            node["additionalProperties"] = False
        return node

    return walk(schema)


def _nullable(prop: dict[str, Any]) -> dict[str, Any]:
    if "anyOf" in prop:
        if not any(p.get("type") == "null" for p in prop["anyOf"]):
            prop["anyOf"] = [*prop["anyOf"], {"type": "null"}]
        return prop
    t = prop.get("type")
    if t is None:
        return {"anyOf": [prop, {"type": "null"}]}
    if isinstance(t, list):
        if "null" not in t:
            prop["type"] = [*t, "null"]
    elif t != "null":
        prop["type"] = [t, "null"]
    return prop


# --------------------------------------------------------------------------- #
# Running a tool: parse args -> handler -> allow-list -> JSON
# --------------------------------------------------------------------------- #
def parse_args(spec: ToolSpec, arguments_json: str) -> BaseModel:
    raw = json.loads(arguments_json or "{}")
    if not isinstance(raw, dict):
        raise ValueError("arguments must be a JSON object")
    return spec.input_model.model_validate(raw)


async def call_tool(
    spec: ToolSpec, session: AsyncSession, ctx: AgentContext, args: BaseModel
) -> dict[str, Any]:
    """Run the handler and pass its result through the output allow-list."""
    result = await spec.handler(session, ctx, args)
    return spec.output_model.model_validate(result).model_dump(mode="json")
