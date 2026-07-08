"""
Phase 0 red tests for BILL-149 — /simplify flags house-style error wraps without
checking sibling conventions.

Bug: pr-simplify.md instructs the simplifier to flag redundant error-wraps and
boilerplate. When every sibling function in the same file uses the same pattern,
that pattern is the established local convention — removal breaks consistency.
The current instructions have no guard for this case.

Fix: add a sibling-check guard to pr-simplify.md instructing the simplifier to
grep 2–3 sibling functions before flagging an error-wrap, docstring, or boilerplate
construct as redundant. If the pattern is an established local convention, do NOT
flag it — consistency with neighbors outranks local terseness.

Expected behaviors after fix:
1. The sibling-check guard is present in pr-simplify.md (basic existence).
2. "Convention" or "established" appears — the guard explains WHY to skip.
3. Error-wrap and/or boilerplate constructs are explicitly named as subjects of the guard.
4. A "do not flag" directive is present — the guard has a clear action.
5. The guard applies to both the inline simplify path AND the agent invocation path.

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill149_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SIMPLIFY_REF = REPO_ROOT / "skills" / "pr" / "references" / "pr-simplify.md"

_INLINE_HEADER = "## Inline simplify"
_AGENT_HEADER = "## Agent invocation"


@pytest.fixture(scope="module")
def simplify_text():
    return SIMPLIFY_REF.read_text()


def _section(text, header):
    """Return the text from `header` to the next ## heading (or EOF)."""
    start = text.find(f"\n{header}")
    if start == -1:
        return ""
    start += 1  # skip leading newline
    end = text.find("\n## ", start + len(header))
    return text[start:] if end == -1 else text[start:end]


def test_sibling_check_present(simplify_text):
    """pr-simplify.md must contain a sibling-check guard."""
    assert "sibling" in simplify_text.lower(), (
        "pr-simplify.md is missing a sibling-check guard. "
        "Add an instruction to grep sibling functions before flagging a pattern as redundant."
    )


def test_convention_explanation_present(simplify_text):
    """The guard must explain that an established local convention must not be flagged."""
    text = simplify_text.lower()
    assert "convention" in text or "established" in text, (
        "pr-simplify.md must state that when a pattern is the established local convention "
        "it must not be flagged as redundant."
    )


def test_error_wrap_scope_covered(simplify_text):
    """The guard must explicitly name error-wrap or boilerplate as subjects."""
    text = simplify_text.lower()
    assert "error-wrap" in text or "error wrap" in text or "boilerplate" in text, (
        "pr-simplify.md must explicitly name error-wrap, error wrap, or boilerplate "
        "as a subject of the sibling-check guard."
    )


def test_do_not_flag_directive_present(simplify_text):
    """The guard must contain a 'do not flag' directive."""
    text = simplify_text.lower()
    assert "do not flag" in text or "must not flag" in text or "do not flag it" in text, (
        "pr-simplify.md must contain a clear 'do not flag' directive for patterns that "
        "match the established local convention."
    )


def test_guard_covers_inline_path(simplify_text):
    """The sibling-check guard must be present in (or upstream of) the inline simplify section."""
    inline_section = _section(simplify_text, _INLINE_HEADER)
    # Also accept if the guard appears BEFORE the first section heading (file-level preamble)
    preamble = simplify_text[: simplify_text.find(f"\n{_INLINE_HEADER}")]
    covered = "sibling" in inline_section.lower() or "sibling" in preamble.lower()
    assert covered, (
        "The sibling-check guard must appear in the inline simplify section of pr-simplify.md "
        "(or in a preamble that applies to all paths). Currently the inline path has no guard."
    )


def test_guard_covers_agent_prompt(simplify_text):
    """The sibling-check guard must be present in (or upstream of) the agent invocation section."""
    agent_section = _section(simplify_text, _AGENT_HEADER)
    preamble = simplify_text[: simplify_text.find(f"\n{_AGENT_HEADER}")]
    covered = "sibling" in agent_section.lower() or "sibling" in preamble.lower()
    assert covered, (
        "The sibling-check guard must appear in the agent invocation section of pr-simplify.md "
        "(or in a preamble that applies to all paths). Currently the agent prompt has no guard."
    )
