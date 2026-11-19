"""The certificate's share sentence (client, 2026-11-18): the units are a share of the SPV that
owns the property, so the sentence names the SPV, never "of the property", and fits the page."""

import pytest

from app.services import certificate_service as cs
from app.services.doc_lang import doc_language, tr

ATHENS = "Capimax Aethera Skyline Athens SPV Ltd"


def _sentence(spv: str) -> str:
    return tr(f"representing 0.0221% of the total issued interests in {spv},")


def test_a_sentence_too_long_for_one_line_puts_the_spv_name_whole_on_the_second():
    with doc_language("en"):
        size, lines = cs._share_lines(_sentence(ATHENS), ATHENS)
    assert size == 12.0
    assert lines == ["representing 0.0221% of the total issued interests in", f"{ATHENS},"]


def test_a_short_sentence_stays_on_one_line():
    with doc_language("en"):
        size, lines = cs._share_lines(_sentence("Lumen SPV"), "Lumen SPV")
    assert (size, lines) == (
        12.0,
        ["representing 0.0221% of the total issued interests in Lumen SPV,"],
    )


def test_a_very_long_name_wraps_and_shrinks_but_never_leaves_the_frame():
    name = (
        "Capimax Aethera Skyline Athens Business and Diplomatic District Holdings Special "
        "Purpose Vehicle Societe Anonyme"
    )
    with doc_language("en"):
        size, lines = cs._share_lines(_sentence(name), name)
        widths = [cs._drawn_width(ln, "Times-Roman", size) for ln in lines]
    assert len(lines) == 2 and 9.5 <= size < 12
    assert all(w <= cs._SHARE_WIDTH for w in widths)


@pytest.mark.parametrize(
    ("lang", "named", "unnamed"),
    [
        ("ar", "من إجمالي الحصص المصدرة في " + ATHENS, "في الشركة ذات الغرض الخاص المصدرة"),
        ("fr", "de l'ensemble des parts émises par " + ATHENS, "par la SPV émettrice"),
    ],
)
def test_the_sentence_is_translated_with_the_spv_name_kept_as_registered(lang, named, unnamed):
    with doc_language(lang):
        assert named in _sentence(ATHENS)
        assert unnamed in tr(
            "representing 0.0221% of the total issued interests in the issuing SPV,"
        )
        size, lines = cs._share_lines(_sentence(ATHENS), ATHENS)
    assert lines[-1].startswith(ATHENS) and size == 12.0
