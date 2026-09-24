"""Tool registry. Importing this package registers every Phase-1 tool (sorted by name so the
tool list sent to the provider is byte-stable across turns)."""

from __future__ import annotations

from app.services.assistant.tools import (  # noqa: F401
    account,
    actions,
    documents,
    platform,
    portfolio,
    roles,
    staff,
    wallet,
)
from app.services.assistant.tools.base import REGISTRY, ToolSpec, get_spec, llm_tools

__all__ = ["REGISTRY", "ToolSpec", "get_spec", "llm_tools"]
