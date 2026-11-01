"""The language a document is issued in: the one the person has the site in (client, 2026-11-01,
as on Capimax BRX).

The site asks for a document with ``?lang=ar|fr``; the route wraps the work in
``with doc_language(lang):``. Inside it ``tr`` gives the text in that language from
``doc_strings.TEXT``, dates name their month in it, and ``DocCanvas`` draws every string: Arabic
is joined, put in display order and set in the bundled font, and an Arabic document mirrors right
to left. English is the default and goes through untouched, so an English document is the same
file it always was.

Only what a string says is mirrored by the canvas. A shape drawn at one side of the page goes
through ``mx`` / ``mbox`` at the place it is drawn.
"""

from __future__ import annotations

import datetime as dt
import functools
import pathlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.services.doc_strings import MONTHS, TEXT

_W = 595.0  # A4 points: the one page size the documents use
_COLUMN = {"ar": 0, "fr": 1}
_LANG: ContextVar[str] = ContextVar("doc_lang", default="en")

_RLM = "\u200f"  # keeps a Latin run from swallowing the separator after it; never drawn
_ARABIC = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"
_SANS, _SANS_BOLD = "PropShare-Sans", "PropShare-Sans-Bold"
_SANS_SCALE = 0.92  # the bundled font runs larger than the Times and Helvetica it sits beside


# --- the language ---------------------------------------------------------------------------- #
def current() -> str:
    return _LANG.get()


def is_rtl() -> bool:
    return _LANG.get() == "ar"


@contextmanager
def doc_language(code: str | None) -> Iterator[None]:
    """Everything rendered inside the block is in this language (unknown code: English)."""
    token = _LANG.set(code if code in _COLUMN else "en")
    try:
        yield
    finally:
        _LANG.reset(token)


# --- the text -------------------------------------------------------------------------------- #
def _normal(text: str) -> str:
    return " ".join(text.split())


def _compile() -> tuple[dict[str, tuple[str, str]], list[tuple[re.Pattern[str], tuple[str, str]]]]:
    exact: dict[str, tuple[str, str]] = {}
    templates: list[tuple[re.Pattern[str], tuple[str, str]]] = []
    for en, pair in TEXT.items():
        key = _normal(en)
        if re.search(r"\{\d+\}", key):
            pattern = re.sub(r"\\\{(\d+)\\\}", r"(?P<v\1>.+?)", re.escape(key))
            templates.append((re.compile(pattern, re.IGNORECASE), pair))
        else:
            exact[key.casefold()] = pair
    templates.sort(key=lambda t: -len(t[0].pattern))  # the more specific first
    return exact, templates


_EXACT, _TEMPLATES = _compile()


def _in_case_of(original: str, found: str) -> str:
    """A label written in capitals comes out in capitals, one in lower case in lower case."""
    if original.isupper():
        return found.upper()
    if original.islower():
        return found.lower()
    return found


@functools.lru_cache(maxsize=8192)
def _lookup(text: str, lang: str) -> str | None:
    key = _normal(text)
    column = _COLUMN[lang]
    pair = _EXACT.get(key.casefold())
    if pair is not None:
        return _in_case_of(key, pair[column])
    for pattern, pair in _TEMPLATES:
        match = pattern.fullmatch(key)
        if match:
            values = {name[1:]: _value(text, lang) for name, text in match.groupdict().items()}
            return re.sub(r"\{(\d+)\}", lambda v, vs=values: vs[v.group(1)], pair[column])
    return None


def _value(text: str, lang: str) -> str:
    found = _lookup(text, lang)
    return text if found is None else found


def tr(text: str) -> str:
    """``text`` in the document's language; the text itself when English or unknown. Never for
    a name someone entered: a property called "Status" is still called that."""
    lang = _LANG.get()
    if lang == "en" or not text:
        return text
    return _value(text, lang)


def status_text(status: str) -> str:
    """A status as stored or capitalised ("Pending_payment"), in the document's language."""
    return status if _LANG.get() == "en" else tr(status.replace("_", " "))


def date_range(start: str, end: str) -> str:
    """Two dates as a period, for a spreadsheet cell."""
    lang = _LANG.get()
    if lang == "ar":
        return f"من {start} إلى {end}"
    return f"du {start} au {end}" if lang == "fr" else f"{start} to {end}"


def long_date(d: dt.date | dt.datetime, english: str = "%d %b %Y") -> str:
    """A date with its month in words, in the document's language; ``english`` is the format of
    the document it appears in."""
    names = MONTHS.get(_LANG.get())
    return f"{d.day:02d} {names[d.month - 1]} {d.year}" if names else d.strftime(english)


def table_date(d: dt.date | dt.datetime) -> str:
    """A date for a narrow table column: an Arabic month name would run into the next one."""
    return d.strftime("%d/%m/%Y") if is_rtl() else long_date(d)


def list_text(items: list[str]) -> str:
    return ("، " if is_rtl() else ", ").join(items)


def sheet_direction(*sheets) -> None:
    """An Arabic workbook reads from the right."""
    if is_rtl():
        for sheet in sheets:
            sheet.sheet_view.rightToLeft = True


# --- drawing it ------------------------------------------------------------------------------ #
def mx(x: float) -> float:
    """An x position in the document's direction (mirrored in Arabic)."""
    return _W - x if is_rtl() else x


def mbox(x: float, width: float) -> float:
    """The left edge of a box at ``x``, ``width`` wide, in the document's direction."""
    return _W - x - width if is_rtl() else x


def has_arabic(text: str) -> bool:
    return bool(_ARABIC.search(text))


@functools.lru_cache(maxsize=1)
def _register_fonts() -> None:
    pdfmetrics.registerFont(TTFont(_SANS, str(_ASSETS / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(_SANS_BOLD, str(_ASSETS / "DejaVuSans-Bold.ttf")))


@functools.lru_cache(maxsize=8192)
def _displayed(text: str, rtl: bool) -> str:
    """Arabic letters joined and in display order. The two libraries are loaded only when an
    Arabic string is drawn: nothing else needs them."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    # An Arabic document reads from the right even where a line starts with a Latin name.
    drawn = get_display(arabic_reshaper.reshape(text), base_dir="R" if rtl else "L")
    return drawn.replace(_RLM, "")


def visual(text: str, font: str) -> tuple[str, str]:
    """(what to draw, the font to draw it in) for ``text`` asked for in ``font``."""
    if not has_arabic(text):
        return text, font
    _register_fonts()
    return _displayed(text, is_rtl()), _SANS_BOLD if "Bold" in font else _SANS


def text_width(text: str, font: str, size: float) -> float:
    """The width ``text`` takes when drawn, for fitting and wrapping."""
    drawn, real = visual(text, font)
    return pdfmetrics.stringWidth(drawn, real, size if real == font else size * _SANS_SCALE)


class DocCanvas(canvas.Canvas):
    """A canvas that draws every string in the document's language and direction."""

    def _say(self, draw, x: float, y: float, text: str) -> None:
        asked, size = self._fontname, self._fontsize
        drawn, font = visual(str(text), asked)
        if font != asked:
            canvas.Canvas.setFont(self, font, size * _SANS_SCALE)
        draw(self, x, y, drawn)
        if font != asked:
            canvas.Canvas.setFont(self, asked, size)

    def drawString(self, x, y, text, *args, **kwargs):  # noqa: N802
        if args or kwargs or not (is_rtl() or has_arabic(str(text))):
            return super().drawString(x, y, text, *args, **kwargs)
        if is_rtl():
            return self._say(canvas.Canvas.drawRightString, _W - x, y, text)
        return self._say(canvas.Canvas.drawString, x, y, text)

    def drawRightString(self, x, y, text, *args, **kwargs):  # noqa: N802
        if args or kwargs or not (is_rtl() or has_arabic(str(text))):
            return super().drawRightString(x, y, text, *args, **kwargs)
        if is_rtl():
            return self._say(canvas.Canvas.drawString, _W - x, y, text)
        return self._say(canvas.Canvas.drawRightString, x, y, text)

    def drawCentredString(self, x, y, text, *args, **kwargs):  # noqa: N802
        if args or kwargs or not (is_rtl() or has_arabic(str(text))):
            return super().drawCentredString(x, y, text, *args, **kwargs)
        return self._say(canvas.Canvas.drawCentredString, mx(x), y, text)
