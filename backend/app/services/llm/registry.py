"""Provider registry: the ``assistant_provider`` setting names the adapter to use.

Adding a second provider later is a new adapter class registered here; nothing else in the
assistant changes.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.errors import AppError
from app.services.llm.types import LLMClient

_FACTORIES: dict[str, Callable[[], LLMClient]] = {}


def register(name: str, factory: Callable[[], LLMClient]) -> None:
    _FACTORIES[name] = factory


def providers() -> tuple[str, ...]:
    return tuple(sorted(_FACTORIES))


def get_client(provider: str) -> LLMClient:
    try:
        factory = _FACTORIES[provider]
    except KeyError as exc:
        raise AppError(
            "ASSISTANT_PROVIDER_UNKNOWN",
            f"Unknown assistant provider {provider!r}. Known: {', '.join(providers())}.",
            status_code=503,
        ) from exc
    return factory()


def _openai_factory() -> LLMClient:
    # imported lazily so the SDK is only loaded when the provider is actually used
    from app.services.llm.openai_responses import OpenAIResponsesAdapter

    return OpenAIResponsesAdapter()


register("openai", _openai_factory)
