"""The company reference library: the client's own documents about PropShare, the Capimax
ecosystem, partners and operating entities, kept verbatim and searchable by the assistant.

Why not the knowledge base prompt block: the approved KB is short, figure-free wording that
rides in every request (cached prefix). The reference documents are ~80k characters of
company material — too big for every request, and they carry figures (fee card, plan terms)
that the live platform settings may not match. So they live beside the KB:

  * stored as ``kb_articles`` rows with ``audience='reference'`` (same draft -> approve flow,
    same admin screen, same audit), split into small chunks by heading;
  * never rendered into the prompt block (``kb_service.approved_articles`` excludes them);
  * reached through the ``search_reference`` tool, which returns the best-matching chunks
    within the tool-result size budget.

The source files live in ``app/knowledge/reference``; ``scripts/seed_reference.py`` loads them.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KbArticle

REFERENCE_AUDIENCE = "reference"
REFERENCE_DIR = pathlib.Path(__file__).resolve().parents[1] / "knowledge" / "reference"
CHUNK_CHARS = 1700  # stays under wrap_untrusted's 2000-char cap with the heading prefix
RESULT_BUDGET_BYTES = 6800  # leaves room in the 8 KB tool-result cap for the JSON envelope


@dataclasses.dataclass(frozen=True)
class Source:
    key: str
    filename: str
    lang: str
    title: str


SOURCES: tuple[Source, ...] = (
    Source(
        "kb",
        "platform_knowledge_base_2026.md",
        "en",
        "PropShare complete platform & AI customer-service knowledge base (Sept 2026)",
    ),
    Source(
        "ecosystem",
        "ecosystem_role_2026.ar.md",
        "ar",
        "علاقة كابي مكس بروبشير بمنظومة كابي مكس (2026)",
    ),
    Source(
        "partners", "partners_register_2026.md", "en", "PropShare partners page register (2026)"
    ),
    Source(
        "entities",
        "operating_entities_2026.md",
        "en",
        "Entities associated with platform operations (2026)",
    ),
)


@dataclasses.dataclass(frozen=True)
class Chunk:
    slug: str
    lang: str
    title: str
    body: str
    source_ref: str


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #
_HEADING_RE = re.compile(r"^(#{1,2})\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\|\s*:?-{3,}")


def _clean_heading(text: str) -> str:
    text = text.replace("\\.", ".").replace("**", "").strip()
    return re.sub(r"\s+", " ", text)


def _fix_blank_table_headers(lines: list[str]) -> list[str]:
    """The source tables were exported with an EMPTY header row and the real column names
    as the first body row. Promote that row, so a table (or a chunk repeating its header)
    says what its columns are."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            line.startswith("|")
            and not line.replace("|", "").strip()
            and i + 2 < len(lines)
            and _TABLE_SEP_RE.match(lines[i + 1])
            and lines[i + 2].startswith("|")
        ):
            out.extend([lines[i + 2], lines[i + 1]])
            i += 3
            continue
        out.append(line)
        i += 1
    return out


def _clean_body(text: str) -> str:
    text = "\n".join(_fix_blank_table_headers(text.splitlines()))
    text = text.replace("<br>", "; ").replace("\\.", ".").replace("\\", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    # empty table cells (logo column) carry nothing
    text = re.sub(r"\|\s{2,}\|", "| |", text)
    return text.strip()


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """(heading, body) per ``#``/``##`` heading; text before the first heading is kept as an
    'Overview' section. The Contents table of the long reference is dropped (it is an index
    of the sections that follow, and it would win every keyword search)."""
    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    parent = ""  # a ``##`` section is titled "<# heading> — <## heading>" so it reads alone
    for line in markdown.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            heading = _clean_heading(m.group(2))
            if m.group(1) == "#":
                parent = heading
            elif parent:
                heading = f"{parent} — {heading}"
            sections.append((heading, []))
        else:
            sections[-1][1].append(line)
    out = []
    for heading, lines in sections:
        if heading.lower() == "contents":
            continue
        body = _clean_body("\n".join(lines))
        if body:
            out.append((heading, body))
    return out


def chunk_body(body: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Split on line boundaries into pieces of at most ``limit`` characters. A piece that
    starts inside a table repeats the table's header row, so every chunk reads on its own."""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    header: list[str] = []  # header row + separator of the table we are in
    lines = body.splitlines()
    for i, line in enumerate(lines):
        is_row = line.startswith("|")
        if is_row and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            header = [line, lines[i + 1]]
        elif not is_row:
            header = []
        if current and size + len(line) + 1 > limit:
            chunks.append("\n".join(current).strip())
            current = list(header) if is_row and header and line not in header else []
            size = sum(len(x) + 1 for x in current)
        while len(line) > limit:  # a single overlong line (rare): hard-wrap it
            current.append(line[:limit])
            chunks.append("\n".join(current).strip())
            current, size, line = [], 0, line[limit:]
        current.append(line)
        size += len(line) + 1
    if "\n".join(current).strip():
        chunks.append("\n".join(current).strip())
    return [c for c in chunks if c]


def load_chunks(directory: pathlib.Path = REFERENCE_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for source in SOURCES:
        text = (directory / source.filename).read_text(encoding="utf-8")
        for s_idx, (heading, body) in enumerate(split_sections(text)):
            parts = chunk_body(body)
            for p_idx, part in enumerate(parts):
                suffix = f" (part {p_idx + 1}/{len(parts)})" if len(parts) > 1 else ""
                chunks.append(
                    Chunk(
                        slug=f"ref-{source.key}-{s_idx:02d}-{p_idx + 1}",
                        lang=source.lang,
                        title=f"{heading}{suffix}",
                        body=part,
                        source_ref=f"{source.filename} | {source.title}",
                    )
                )
    return chunks


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
_AR_DIACRITICS = re.compile("[\\u064b-\\u0652\\u0640]")  # tashkeel + tatweel
_WORD_RE = re.compile(r"\w+", re.U)
_STOP = frozenset(
    "the and for with what who how does are is was can you your our about from that this "
    "which when where why into platform propshare capimax "
    "ما من في على عن هل هي هو التي الذي مع او أو كيف لماذا متى اين أين ماهي ماهو".split()
)
# Arabic query words -> the English words the (mostly English) documents use.
# Keys are in normalize()d form.
_ALIASES = {
    "نوفا": "nova",
    "برونوفا": "pronova",
    "بروبشير": "propshare",
    "سمسب": "sumsub",
    "سترايب": "stripe",
    "تامين": "insurance",
    "شركاء": "partner",
    "شريك": "partner",
    "مطور": "developer",
    "مطورين": "developer",
    "تمويل": "financing",
    "رسوم": "fee",
    "تقييم": "valuation",
    "قانوني": "legal",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _AR_DIACRITICS.sub("", text)
    return text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"}))


def _stem(word: str) -> str:
    if len(word) > 4 and word.startswith("ال"):
        word = word[2:]
    elif len(word) > 5 and word[:3] in ("وال", "بال", "لال"):
        word = word[3:]
    if word.isascii() and len(word) > 4 and word.endswith("s"):
        word = word[:-1]
    return word


def query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for raw in _WORD_RE.findall(normalize(query)):
        if raw in _STOP or len(raw) < 3:
            continue
        stem = _stem(raw)
        for term in (stem, _ALIASES.get(raw, ""), _ALIASES.get(stem, "")):
            if term and term not in _STOP and term not in terms:
                terms.append(term)
    return terms[:12]


def _words(text: str) -> set[str]:
    return {_stem(w) for w in _WORD_RE.findall(normalize(text))}


def score(terms: list[str], title: str, body: str) -> int:
    title_words, body_words = _words(title), _words(body)
    total = 0
    for term in terms:
        in_title = term in title_words or any(w.startswith(term) for w in title_words)
        in_body = term in body_words or (
            len(term) >= 4 and any(w.startswith(term) for w in body_words)
        )
        total += (3 if in_title else 0) + (2 if in_body else 0)
    return total


async def approved_reference(session: AsyncSession) -> list[KbArticle]:
    stmt = (
        select(KbArticle)
        .where(KbArticle.status == "approved", KbArticle.audience == REFERENCE_AUDIENCE)
        .order_by(KbArticle.slug)
    )
    return list((await session.execute(stmt)).scalars().all())


async def search(session: AsyncSession, query: str, limit: int = 3) -> list[KbArticle]:
    """Best-matching approved chunks, most relevant first, within the result byte budget."""
    terms = query_terms(query)
    if not terms:
        return []
    ranked = sorted(
        ((score(terms, r.title, r.body_md), r) for r in await approved_reference(session)),
        key=lambda pair: (-pair[0], pair[1].slug),
    )
    picked: list[KbArticle] = []
    used = 0
    for points, row in ranked:
        if points <= 0 or len(picked) >= limit:
            break
        size = len((row.title + row.body_md).encode("utf-8")) + 200
        if picked and used + size > RESULT_BUDGET_BYTES:
            continue
        picked.append(row)
        used += size
    return picked
