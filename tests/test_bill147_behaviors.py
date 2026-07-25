"""
Phase 0 red tests for BILL-147 — Step 5c "skip trigger" misread as "skip poll".

Bug: Step 5c correctly gates the @coderabbitai trigger on $BASE != $DEFAULT_BRANCH,
but agents misread this as "master-base PR → skip the whole polling flow (Step 6-cr)".

Fix: Add a clarifying sentence to Step 5c AND a mirror bullet in the Step 6-cr preamble,
both making clear that skipping the trigger ≠ skipping Step 6-cr.

Expected behaviors after fix:
1. The Step 5c section in skills/pr/SKILL.md contains clarification that skipping
   the trigger does NOT mean skipping the poll — Step 6-cr runs regardless.
2. The Step 6-cr preamble in skills/pr/SKILL.md contains a mirror bullet with the
   same clarification (unconditional run; auto-review is not self-verifying).

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill147_behaviors.py -v
"""

from pathlib import Path
import pytest

from conftest import section

REPO_ROOT = Path(__file__).parent.parent
PR_SKILL = REPO_ROOT / "skills" / "pr" / "SKILL.md"


@pytest.fixture(scope="module")
def pr_skill_text():
    return PR_SKILL.read_text()


def _section(text, header, limit=None):
    """Lowercased section text. Scoping delegated to conftest.section() (BILL-322).

    Kept as a thin shim because both call sites lowercase before matching and one
    passes `limit`. The shared helper is fence-aware and depth-aware; this one was
    neither, so it could not scope a `###` under a `##` and would end a section at
    the first heading inside a fenced template.
    """
    result = section(text, header)
    if not result:
        return None
    if limit is not None:
        result = result[:limit]
    return result.lower()


def test_step_5c_clarifies_trigger_skip_does_not_skip_poll(pr_skill_text):
    """Step 5c must clarify that skipping the @coderabbitai trigger != skipping Step 6-cr."""
    sec = _section(pr_skill_text, "### 5c.")
    assert sec is not None, "Step '### 5c.' not found in skills/pr/SKILL.md"
    has_clarification = (
        "6-cr" in sec
        or "regardless" in sec
        or "self-verifying" in sec
        or "not the same" in sec
    )
    assert has_clarification, (
        "Step 5c must clarify that skipping the @coderabbitai trigger (for auto-review repos) "
        "is NOT the same as skipping Step 6-cr. The poll must run regardless."
    )


def test_step_6cr_preamble_states_it_runs_unconditionally(pr_skill_text):
    """Step 6-cr preamble must state it runs regardless of whether the trigger was posted."""
    sec = _section(pr_skill_text, "## Step 6-cr", limit=600)
    assert sec is not None, "Section '## Step 6-cr' not found in skills/pr/SKILL.md"
    has_unconditional = (
        "regardless" in sec
        or "unconditional" in sec
        or "self-verifying" in sec
    )
    assert has_unconditional, (
        "Step 6-cr preamble must state it runs unconditionally — "
        "regardless of whether the @coderabbitai trigger was posted in Step 5c. "
        "Auto-review is not self-verifying."
    )
