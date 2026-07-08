"""
Phase 0 red tests for BILL-148 — polling numeric comparisons unguarded against
transient gh api errors.

Bug: the poll script captures counts from `gh api ... --jq "... | length"`.
When gh api returns a transient error object instead of an array, jq produces
empty or non-integer output. That flows into `[ "$head_reviewed" -gt 0 ]`,
which errors on non-integer input. Currently fails-safe by accident; a different
transient error shape could false-positive the completion gate.

Fix: add `case` guards to normalize each captured variable to an integer
immediately after assignment. Also add a comment that transient errors are
expected and must not be treated as completion signals.

Expected behaviors after fix:
1. case guard present for $head_reviewed
2. case guard present for $inline_count
3. case guard present for $all_cr_inline
4. case guard present for $review_count
5. A comment documents that transient gh api errors must not be treated as
   a completion signal.

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill148_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
POLLING_DOC = REPO_ROOT / "skills" / "pr" / "references" / "pr-cr-polling.md"

_CASE_GUARD_TEMPLATE = "''|*[!0-9]*)"


@pytest.fixture(scope="module")
def polling_text():
    return POLLING_DOC.read_text()


def _has_case_guard_for(text, var_name):
    """Return True if a case guard normalizing var_name to 0 is present."""
    return (
        _CASE_GUARD_TEMPLATE in text
        and f'case "${var_name}"' in text
        and f'{var_name}=0' in text
    )


def test_case_guard_head_reviewed(polling_text):
    """case guard for $head_reviewed must be present in pr-cr-polling.md."""
    assert _has_case_guard_for(polling_text, "head_reviewed"), (
        "Missing case guard for $head_reviewed. "
        "Add: case \"$head_reviewed\" in ''|*[!0-9]*) head_reviewed=0 ;; esac"
    )


def test_case_guard_inline_count(polling_text):
    """case guard for $inline_count must be present in pr-cr-polling.md."""
    assert _has_case_guard_for(polling_text, "inline_count"), (
        "Missing case guard for $inline_count. "
        "Add: case \"$inline_count\" in ''|*[!0-9]*) inline_count=0 ;; esac"
    )


def test_case_guard_all_cr_inline(polling_text):
    """case guard for $all_cr_inline must be present in pr-cr-polling.md."""
    assert _has_case_guard_for(polling_text, "all_cr_inline"), (
        "Missing case guard for $all_cr_inline. "
        "Add: case \"$all_cr_inline\" in ''|*[!0-9]*) all_cr_inline=0 ;; esac"
    )


def test_case_guard_review_count(polling_text):
    """case guard for $review_count must be present in pr-cr-polling.md."""
    assert _has_case_guard_for(polling_text, "review_count"), (
        "Missing case guard for $review_count. "
        "Add: case \"$review_count\" in ''|*[!0-9]*) review_count=0 ;; esac"
    )


def test_transient_error_comment(polling_text):
    """A comment must state that transient gh api errors must not be treated as
    a completion signal."""
    assert "not be treated as a completion signal" in polling_text.lower(), (
        "pr-cr-polling.md must contain a comment documenting that transient "
        "gh api errors are expected and must not be treated as a completion signal."
    )
