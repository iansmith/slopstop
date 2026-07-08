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


# --- Adversary gap tests (BILL-154 Phase 0f) ---


def test_forward_guard_precedes_per_system_dispatch(execute_text):
    """The forward-only guard section must appear BEFORE the ## JIRA dispatch, not after."""
    lower = execute_text.lower()
    guard_markers = ["autonomous forward", "forward-only guard", "## autonomous"]
    guard_pos = next(
        (lower.find(m) for m in guard_markers if lower.find(m) != -1),
        -1,
    )
    jira_pos = execute_text.find("## JIRA")
    assert guard_pos != -1, (
        "No forward-only guard section found in merge-execute-transition.md — "
        "cannot verify placement relative to per-system dispatch."
    )
    assert jira_pos != -1, "## JIRA section missing from merge-execute-transition.md."
    assert guard_pos < jira_pos, (
        f"Forward-only guard (at char {guard_pos}) must appear BEFORE the ## JIRA dispatch "
        f"section (at char {jira_pos}). A guard placed after the dispatch intercepts nothing — "
        "all three systems will have already applied their transitions by the time the guard runs."
    )


def test_forward_guard_scoped_to_autonomous_mode_only(execute_text):
    """The guard must be conditional on --autonomous; non-autonomous Step 5 must be unchanged."""
    lower = execute_text.lower()
    autonomous_scope = (
        "--autonomous" in execute_text
        or "when autonomous" in lower
        or "autonomous mode only" in lower
        or "only in autonomous" in lower
        or "autonomous-mode-only" in lower
        or "if autonomous" in lower
    )
    assert autonomous_scope, (
        "merge-execute-transition.md must explicitly state the forward-only guard fires only "
        "when --autonomous is passed on the command line. A guard that fires in interactive "
        "sessions too would prevent users from applying any non-forward transition even after "
        "manually reviewing and confirming it in Step 3."
    )


def test_forward_guard_permits_valid_forward_transitions(execute_text):
    """Guard must have an explicit pass-through for valid forward transitions."""
    lower = execute_text.lower()
    has_pass_condition = (
        "proceed" in lower
        or "apply the transition" in lower
        or "passes the guard" in lower
        or "if the check passes" in lower
        or "direction is forward" in lower
    )
    assert has_pass_condition, (
        "merge-execute-transition.md's forward-only guard must document that valid forward "
        "transitions pass through and are applied normally. Without an explicit pass condition, "
        "a 'refuse all autonomous transitions' implementation satisfies all other tests while "
        "breaking the feature entirely."
    )


def test_forward_guard_refuses_lateral_same_position_transitions(execute_text):
    """Lateral transitions (same statusCategory / same position) must also be refused."""
    lower = execute_text.lower()
    has_strict_advance = (
        "lateral" in lower
        or "same position" in lower
        or "same category" in lower
        or ("greater than" in lower and "position" in lower)
        or ("strictly" in lower and ("position" in lower or "category" in lower))
        or "must be greater" in lower
        or "not greater" in lower
    )
    assert has_strict_advance, (
        "merge-execute-transition.md's guard must explicitly refuse lateral transitions — where "
        "the target has the same statusCategory (JIRA) or same position (Linear) as the current "
        "state. 'Forward' means strictly advances. A guard that only refuses clear backward moves "
        "permits In Progress → Code Review (both indeterminate) or position 3 → 3 silently."
    )


def test_forward_guard_logs_reason_on_refusal(execute_text):
    """The guard must emit a log line with the refusal reason, not silently hard-stop."""
    lower = execute_text.lower()
    has_log = (
        "[autonomous]" in execute_text
        or "reason" in lower
        or "refused" in lower
        or "skipping transition" in lower
    )
    assert has_log, (
        "merge-execute-transition.md's forward-only guard must log the refusal reason when "
        "it hard-stops a backward/lateral transition. Silent hard-stops are undiagnosable in "
        "automated pipelines — orchestrators must distinguish 'guard refused' from 'transition "
        "errored'. The log should follow the [autonomous] prefix convention."
    )


def test_github_autonomous_guard_covers_negative_outcome_labels(execute_text):
    """GitHub guard must cover negative-outcome label transitions, not only not_planned closes."""
    lower = execute_text.lower()
    has_label_guard = (
        "negative" in lower
        or "negative-outcome" in lower
        or "negative label" in lower
        or "wont-fix" in lower
        or "wont fix" in lower
        or ("label" in lower and ("refuse" in lower or "reject" in lower or "guard" in lower))
    )
    assert has_label_guard, (
        "merge-execute-transition.md's GitHub guard must cover negative-outcome label transitions "
        "in addition to not_planned closes. The spec says 'refuse if $NEXT_GH_ACTION would close "
        "with state_reason=\"not_planned\" OR negative-outcome label'. A guard limited to "
        "state_reason would silently apply a swap-labels action adding a 'wont-fix' or 'invalid' "
        "label in autonomous mode."
    )
