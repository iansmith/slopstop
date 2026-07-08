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

REPO_ROOT = Path(__file__).parent.parent
PR_SKILL = REPO_ROOT / "skills" / "pr" / "SKILL.md"


@pytest.fixture(scope="module")
def pr_skill_text():
    return PR_SKILL.read_text()


def test_step_5c_clarifies_trigger_skip_does_not_skip_poll(pr_skill_text):
    """Step 5c must clarify that skipping the @coderabbitai trigger != skipping Step 6-cr."""
    lower = pr_skill_text.lower()
    idx_5c = lower.find("### 5c.")
    assert idx_5c != -1, "Step '### 5c.' not found in skills/pr/SKILL.md"
    idx_next_section = lower.find("\n## ", idx_5c)
    if idx_next_section == -1:
        idx_next_section = len(lower)
    step_5c_text = lower[idx_5c:idx_next_section]
    has_clarification = (
        "6-cr" in step_5c_text
        or "regardless" in step_5c_text
        or "self-verifying" in step_5c_text
        or "not the same" in step_5c_text
    )
    assert has_clarification, (
        "Step 5c must clarify that skipping the @coderabbitai trigger (for auto-review repos) "
        "is NOT the same as skipping Step 6-cr. The poll must run regardless."
    )


def test_step_6cr_preamble_states_it_runs_unconditionally(pr_skill_text):
    """Step 6-cr preamble must state it runs regardless of whether the trigger was posted."""
    lower = pr_skill_text.lower()
    idx_6cr = lower.find("## step 6-cr")
    assert idx_6cr != -1, "Section '## Step 6-cr' not found in skills/pr/SKILL.md"
    # Scope to the 6-cr section preamble (before the first sub-heading or next ##)
    idx_next = lower.find("\n## ", idx_6cr + 1)
    if idx_next == -1:
        idx_next = len(lower)
    preamble = lower[idx_6cr:min(idx_6cr + 600, idx_next)]
    has_unconditional = (
        "regardless" in preamble
        or "unconditional" in preamble
        or "self-verifying" in preamble
        or ("auto-review" in preamble and ("not" in preamble or "skip" in preamble))
        or ("trigger" in preamble and ("5c" in preamble or "poll" in preamble))
    )
    assert has_unconditional, (
        "Step 6-cr preamble must state it runs unconditionally — "
        "regardless of whether the @coderabbitai trigger was posted in Step 5c. "
        "Auto-review is not self-verifying."
    )
