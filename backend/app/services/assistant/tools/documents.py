"""Document search tool (Batch D): passages from a property's PUBLIC documents.

Informational tier (visitors allowed — the documents are public on the property page).
Passages are wrapped as untrusted text: a contract can contain anything, and the model
must quote it, not obey it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import document_index_service
from app.services.assistant import guard
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.base import ToolOutput, ToolSpec, register


class SearchDocsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id_or_slug: str = Field(description="Property id or slug")
    query: str = Field(min_length=2, max_length=200, description="Words to look for")


class Passage(ToolOutput):
    untrusted_text: str


class DocHit(ToolOutput):
    title: str
    type: str
    pages: int
    passages: list[Passage]


class Unsearchable(ToolOutput):
    title: str
    type: str
    reason: str


class SearchDocsOut(ToolOutput):
    property_title: str
    slug: str | None
    documents_total: int
    hits: list[DocHit]
    unsearchable: list[Unsearchable]


async def _search_property_documents(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: SearchDocsIn = args
    out = await document_index_service.search(
        session, property_id_or_slug=a.property_id_or_slug, query=a.query
    )
    return {
        "property_title": out["property_title"],
        "slug": out["slug"],
        "documents_total": out["documents_total"],
        "hits": [
            {
                "title": h["title"],
                "type": h["type"],
                "pages": h["pages"],
                "passages": [guard.wrap_untrusted(p) for p in h["passages"]],
            }
            for h in out["hits"]
        ],
        "unsearchable": out["unsearchable"],
    }


register(
    ToolSpec(
        "search_property_documents",
        "Search inside a property's public documents (SPV papers, valuation, agreements, "
        "insurance) for the given words and get the matching passages to quote. Says which "
        "documents could not be searched (scanned or not indexed yet).",
        SearchDocsIn,
        SearchDocsOut,
        "informational",
        _search_property_documents,
    )
)
