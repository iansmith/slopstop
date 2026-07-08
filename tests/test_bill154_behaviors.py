"""
Phase 0 red tests for BILL-154 — Autonomous :merge applies ticket transition
without validating computed target state.

Bug: Step 3's interactive confirm prompt is the only validation of the computed
$NEXT_STATE. Autonomous mode replaces the prompt with a post-hoc log — the
transition is applied before any human or guard checks the direction. A backward
or negative-outcome transition (e.g. "Failed Test" on a "To Do" ticket) fires
silently.

Fix: Add a forward-only guard in merge-execute-transition.md that runs BEFORE
the per-system dispatch in Step 5. Guard is autonomous-mode-only. Per-system rules:
- JIRA: target statusCategory.key must advance (new → indeterminate → done).
- Linear: target state position must be > current state position.
- GitHub: refuse if $NEXT_GH_ACTION would close with state_reason="not_planned".
Guard hard-stops (does not apply) and logs the reason. merge-autonomous.md
documents the guard for orchestrators.

Expected behaviors after fix:
1. merge-execute-transition.md has an autonomous forward-only guard section before
   the per-system dispatch (JIRA / Linear / GitHub).
2. The JIRA guard checks statusCategory ordering — refuses a target whose category
   key is not a forward step from the current category.
3. The Linear guard checks state position — refuses a target whose position is not
   greater than the current state's position.
4. The GitHub guard refuses a not_planned close as a backward/negative outcome.
5. The guard hard-stops on violation (not just logs a warning and proceeds).
6. merge-autonomous.md documents the forward-only guard so orchestrators know to
   expect it.

Tests FAIL on current code; turn GREEN once the fix is applied.

Test command: python3 -m pytest tests/test_bill154_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
EXECUTE_TRANSITION = REPO_ROOT / "skills" / "merge" / "references" / "merge-execute-transition.md"
MERGE_AUTONOMOUS = REPO_ROOT / "skills" / "merge" / "references" / "merge-autonomous.md"


@pytest.fixture(scope="module")
def execute_text():
    return EXECUTE_TRANSITION.read_text()


@pytest.fixture(scope="module")
def autonomous_text():
    return MERGE_AUTONOMOUS.read_text()


def test_execute_transition_has_autonomous_forward_guard(execute_text):
    """merge-execute-transition.md must have an autonomous forward-only guard section."""
    has_guard = (
        "## Autonomous" in execute_text
        or "autonomous forward" in execute_text.lower()
        or "forward-only guard" in execute_text.lower()
    )
    assert has_guard, (
        "merge-execute-transition.md must contain an autonomous forward-only guard section "
        "that validates the computed transition direction before the per-system dispatch. "
        "Currently the file has no autonomous-mode guard and applies any non-null transition "
        "unconditionally."
    )


def test_jira_autonomous_guard_checks_status_category(execute_text):
    """JIRA guard must verify statusCategory ordering before applying the transition."""
    assert "statusCategory" in execute_text, (
        "merge-execute-transition.md must check the target JIRA transition's statusCategory.key "
        "against the current state's statusCategory.key to confirm forward direction "
        "(new → indeterminate → done). Currently no statusCategory check exists — JIRA "
        "transitions are applied blindly regardless of direction."
    )


def test_linear_autonomous_guard_checks_position(execute_text):
    """Linear guard must verify target state position is greater than current."""
    assert "position" in execute_text, (
        "merge-execute-transition.md must check that the target Linear state's position is "
        "greater than the current state's position before applying the transition in autonomous "
        "mode. Currently no position check exists — Linear transitions are applied blindly."
    )


def test_github_autonomous_guard_refuses_not_planned(execute_text):
    """GitHub guard must refuse a not_planned close as a negative-outcome transition."""
    assert "not_planned" in execute_text, (
        "merge-execute-transition.md must guard against not_planned closes in autonomous mode. "
        "Closing an issue with state_reason='not_planned' marks it as 'won't fix' — a negative "
        "outcome that must never fire silently. Currently no such guard exists."
    )


def test_forward_guard_hard_stops_not_warns(execute_text):
    """The forward-only guard must hard-stop (refuse) on a backward/lateral transition."""
    stop_signals = ["hard-stop", "hard stop", "refuse", "stop with", "do not apply"]
    found = any(signal in execute_text.lower() for signal in stop_signals)
    assert found, (
        "merge-execute-transition.md's forward-only guard must hard-stop and refuse to apply the "
        "transition when a backward or lateral move is detected. Logging a warning and proceeding "
        "is insufficient — the ticket must not be transitioned. Currently there is no guard at all."
    )


def test_autonomous_md_documents_forward_guard(autonomous_text):
    """merge-autonomous.md must document the forward-only transition guard."""
    assert "forward-only" in autonomous_text.lower() or "forward guard" in autonomous_text.lower(), (
        "merge-autonomous.md must document that autonomous mode applies a forward-only guard "
        "before executing ticket transitions. Orchestrators need to know that backward/lateral "
        "transitions are hard-stopped with a logged reason so they can diagnose failures. "
        "Currently merge-autonomous.md has no forward-direction guard documentation."
    )
