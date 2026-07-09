"""
Phase 0 red tests for BILL-168 — the five-section leaf-ticket standard.

Stage 2 (:tickets) writes leaf tickets whose consumer is a haiku-class model:
what isn't in the ticket doesn't exist for the implementer. This ticket ships
the standard as a reference doc with a copyable template, the mechanical
structural check adversaries run first, and the (V2)/(V3) title convention.

Placement: design/ticket-standard.md for now (per the ticket's conditional —
the :tickets skill hasn't landed; BILL-173 moves it into that skill's
references/).

Expected behaviors:
1. design/ticket-standard.md exists, defines all five sections with authoring
   guidance, and carries a copyable template.
2. The structural adversary check (five sections present and non-empty,
   behaviors count 2-5) is specified as a mechanical precondition before
   content review.
3. The ticket-title version convention (V2)/(V3) is specified here.
4. design/slopstop-process.md section 6 cross-links the standard.

Test command:
    python3 -m pytest tests/test_bill168_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
STANDARD = REPO_ROOT / "design" / "ticket-standard.md"
SPEC = REPO_ROOT / "design" / "slopstop-process.md"


@pytest.fixture(scope="module")
def text():
    assert STANDARD.exists(), "design/ticket-standard.md must exist (BILL-168)"
    return STANDARD.read_text()


def test_defines_all_five_sections(text):
    """All five mandatory section names must be defined."""
    for section in ("Observable behaviors", "File map", "Definition of done",
                    "Out of scope", "Test expectations"):
        assert section in text, f"standard must define the '{section}' section"


def test_names_the_consumer(text):
    """The standard must state that the consumer is a small (haiku-class) model."""
    assert "haiku-class" in text or "small model" in text.lower()


def test_has_copyable_template(text):
    """A copyable template block must be present (fenced, with all five headings)."""
    assert "```" in text, "template must be a fenced block"
    fenced = text.split("```")[1::2]
    assert any(
        all(h in block for h in ("Observable behaviors", "File map",
                                 "Definition of done", "Out of scope",
                                 "Test expectations"))
        for block in fenced
    ), "one fenced block must contain all five template headings"


def test_specifies_structural_check(text):
    """The mechanical structural check must be specified for adversaries."""
    assert "structural" in text.lower()
    assert "non-empty" in text.lower() or "not empty" in text.lower()
    assert "between **2 and 5**" in text, (
        "the behaviors count bound must be stated in the checklist itself "
        "(bare digits match dates and headings — vacuous)"
    )


def test_specifies_version_convention(text):
    """(V2)/(V3) title convention for failure-driven rewrites must be here."""
    assert "(V2)" in text and "(V3)" in text


def test_spec_cross_links_standard():
    """design/slopstop-process.md Stage-2 section must link ticket-standard.md."""
    assert "ticket-standard.md" in SPEC.read_text()
