"""The invented-numbers rule for the model eval gate (plan §5, ``criteria_v1``).

Every number in an answer must be traceable to the turn's tool results, the knowledge base,
the platform context or the user's own message — or be a harmless list marker / small
count / arithmetic derived from allowed values. Anything else is a violation and fails the
eval case. The rule is deliberately conservative and fails CLOSED when the allowed set gets
too large to check exhaustively.

Pure functions, no I/O: unit-tested in ``test_eval_number_rule.py``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import itertools
import re
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_ALLOWED = 400  # |A| above this -> fail closed ("too_many_numbers")
MAX_GROUP_FOR_SUMS = 16  # rows per unit-context group considered for subset sums
TOLERANCE = Decimal("0.01")

_ARABIC_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_PERSIAN_DIGITS = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_SEPARATORS = {ord("٫"): ".", ord("٬"): ",", ord("٪"): "%"}
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_CANDIDATE_RE = re.compile(r"-?\d+(?:\.\d+)?%?")
_LIST_MARKER_RE = re.compile(r"(?m)^\s*(?:[-*•]\s*)?(\d{1,2})[.)\-:]\s")
_UNIT_WORDS = re.compile(
    r"%|\$|USD|AED|SAR|EUR|GBP|دولار|درهم|ريال|units?|وحد(ة|ات)|months?|شه(ر|ور)|days?|(أ|ا)يام|يوم|"
    r"years?|سن(ة|وات)|tokens?|hours?|ساع(ة|ات)|weeks?|(أ|ا)سابيع|أسبوع",
    re.I,
)
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_MONTHS = (
    "January February March April May June July August September October November December"
).split()


def normalise(text: str) -> str:
    """Arabic-Indic / Persian digits -> ASCII; Arabic separators -> ASCII; thousands
    separators removed; ``%`` kept attached."""
    text = text.translate(_ARABIC_DIGITS).translate(_PERSIAN_DIGITS).translate(_SEPARATORS)
    return _THOUSANDS_RE.sub("", text)


@dataclasses.dataclass(frozen=True)
class Candidate:
    raw: str
    value: Decimal
    percent: bool
    start: int
    end: int
    context: str  # 12 chars left + token + 12 chars right


@dataclasses.dataclass(frozen=True)
class Violation:
    number: str
    context: str
    reason: str


@dataclasses.dataclass
class Result:
    violations: list[Violation]
    flags: list[str]
    allowed_count: int

    @property
    def ok(self) -> bool:
        return not self.violations and not self.flags


def extract_candidates(text: str) -> list[Candidate]:
    out = []
    for m in _CANDIDATE_RE.finditer(text):
        raw = m.group(0)
        percent = raw.endswith("%")
        try:
            value = Decimal(raw.rstrip("%"))
        except InvalidOperation:
            continue
        out.append(
            Candidate(
                raw=raw,
                value=value,
                percent=percent,
                start=m.start(),
                end=m.end(),
                context=text[max(0, m.start() - 12) : m.end() + 12],
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Allowed set
# --------------------------------------------------------------------------- #
def _to_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        s = normalise(value.strip()).rstrip("%")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
            return Decimal(s)
    return None


def _date_parts(value: str) -> set[Decimal]:
    m = _ISO_DATE_RE.match(value.strip())
    if not m:
        return set()
    y, mo, d = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return {Decimal(y), Decimal(mo), Decimal(d)}


def _date_words(value: str) -> set[str]:
    m = _ISO_DATE_RE.match(value.strip())
    if not m:
        return set()
    y, mo, d = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    try:
        dt.date(y, mo, d)
    except ValueError:
        return set()
    return {
        f"{d:02d}/{mo:02d}/{y}",
        f"{d}/{mo}/{y}",
        f"{_MONTHS[mo - 1]} {d}, {y}",
        f"{d} {_MONTHS[mo - 1]} {y}",
    }


@dataclasses.dataclass
class Allowed:
    values: set[Decimal] = dataclasses.field(default_factory=set)
    groups: dict[str, list[Decimal]] = dataclasses.field(default_factory=dict)
    strings: set[str] = dataclasses.field(default_factory=set)  # ids, ticket numbers, dates

    def add_value(self, v: Decimal, group: str | None = None) -> None:
        for form in (
            v,
            v.quantize(Decimal(1)),
            v.quantize(Decimal("0.1")),
            v.quantize(Decimal("0.01")),
        ):
            self.values.add(form.normalize() if form == form.to_integral_value() else form)
            self.values.add(form)
        if group is not None:
            self.groups.setdefault(group, []).append(v)


def _walk(node: Any, path: str, allowed: Allowed) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            _walk(v, f"{path}.{k}" if path else str(k), allowed)
    elif isinstance(node, list):
        for v in node:
            _walk(v, f"{path}[]", allowed)
    elif isinstance(node, str):
        allowed.strings.add(node)
        d = _to_decimal(node)
        if d is not None:
            allowed.add_value(d, path)
            return
        for part in _date_parts(node):
            allowed.add_value(part)
        for word in _date_words(node):
            allowed.strings.add(word)
        for n in extract_candidates(normalise(node)):  # numbers inside free text
            allowed.add_value(n.value)
    else:
        d = _to_decimal(node)
        if d is not None:
            allowed.add_value(d, path)


def build_allowed(
    *,
    tool_results: list[Any],
    kb_text: str = "",
    platform_context: str = "",
    user_text: str = "",
) -> Allowed:
    allowed = Allowed()
    for i, result in enumerate(tool_results):
        _walk(result, f"tool{i}", allowed)
    for text in (kb_text, platform_context, user_text):
        if text:
            for n in extract_candidates(normalise(text)):
                allowed.add_value(n.value)
            allowed.strings.update(text.split())
    return allowed


# --------------------------------------------------------------------------- #
# Derived arithmetic
# --------------------------------------------------------------------------- #
def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= TOLERANCE


def _derived(value: Decimal, allowed: Allowed) -> bool:
    base = sorted({v for v in allowed.values})
    hundred = Decimal(100)
    for a, b in itertools.product(base, repeat=2):
        candidates = [
            a + b,
            a - b,
            a * b,
            a * b / hundred,
            a * (1 + b / hundred),
            a * (1 - b / hundred),
        ]
        if b != 0:
            candidates.append(a / b)
        if any(_close(value, c) for c in candidates):
            return True
    for group in allowed.groups.values():
        rows = group[:MAX_GROUP_FOR_SUMS]
        for size in range(2, min(6, len(rows)) + 1):
            for combo in itertools.combinations(rows, size):
                if _close(value, sum(combo, Decimal(0))):
                    return True
    return False


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #
def _token_around(text: str, start: int, end: int) -> str:
    left = start
    while left > 0 and not text[left - 1].isspace():
        left -= 1
    right = end
    while right < len(text) and not text[right].isspace():
        right += 1
    return text[left:right].strip(".,;:!?()[]\"'")


def check_numbers(
    answer: str,
    *,
    tool_results: list[Any],
    kb_text: str = "",
    platform_context: str = "",
    user_text: str = "",
) -> Result:
    text = normalise(answer)
    allowed = build_allowed(
        tool_results=tool_results,
        kb_text=kb_text,
        platform_context=platform_context,
        user_text=user_text,
    )
    flags: list[str] = []
    if len(allowed.values) > MAX_ALLOWED:
        flags.append("too_many_numbers")
        return Result([], flags, len(allowed.values))
    markers = {m.start(1) for m in _LIST_MARKER_RE.finditer(text)}
    violations: list[Violation] = []
    for c in extract_candidates(text):
        if c.value in allowed.values or any(_close(c.value, v) for v in allowed.values):
            continue
        if c.start in markers:
            continue  # (a) list / step marker
        token = _token_around(text, c.start, c.end)
        if token and any(token in s for s in allowed.strings):
            continue  # (f) ticket numbers, ids, dates written the tool's way
        near = text[max(0, c.start - 12) : c.end + 12]
        if (
            not c.percent
            and c.value == c.value.to_integral_value()
            and 0 <= c.value <= 12
            and not _UNIT_WORDS.search(near)
        ):
            continue  # (b) standalone small integer with no unit / currency / percent nearby
        if _derived(c.value, allowed):
            continue  # (d) arithmetic over allowed values
        violations.append(
            Violation(c.raw, c.context, "not in tool results, KB, context or user text")
        )
    return Result(violations, flags, len(allowed.values))
