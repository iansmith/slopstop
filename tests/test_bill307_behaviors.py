"""
Phase 0 red tests for BILL-307 — :run must not require [autonomous].branch_type.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/307). Structural assertions over
skill and doc text, matching the test_skill_structure.py convention.

Two sides of one config key disagreed. `start-autonomous.md` calls unset
`branch_type` "the common case" and falls back to the per-ticket label/title
heuristic; `:run`'s Fleet precondition hard-stopped unless it was set. `:start`
is the correct side, so `:run` moves.

The substantive part is not the precondition but Step 4: `:run` creates the
worktree branch with `git worktree add -b <TYPE>/<TICKET>` *before* the agent
starts, so `:run` and the agent's own `:start` must compute the identical string
or the agent invents a second branch — breaking the skill's own promise that the
agent "finds the branch already checked out."

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill307_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
RUN_SPINE = REPO_ROOT / "skills" / "run" / "SKILL.md"
CONFIG_DOC = REPO_ROOT / "CONFIG.md"
HEURISTICS_REF = (
    REPO_ROOT / "skills" / "start" / "references" / "start-branch-type-heuristics.md"
)


@pytest.fixture(scope="module")
def spine():
    return RUN_SPINE.read_text()


@pytest.fixture(scope="module")
def precondition(spine):
    """The Fleet precondition paragraph only — scoped so Step 4's prose can't satisfy it."""
    m = re.search(r"\*\*Fleet precondition:\*\*(.+?)\n\n", spine, re.S)
    assert m, "skills/run/SKILL.md must still carry a **Fleet precondition:** paragraph"
    return m.group(1)


@pytest.fixture(scope="module")
def resolution(spine):
    """Steps 3-4: where `<TYPE>` is resolved and then substituted into the branch.

    Deliberately spans both. Resolution belongs wherever the dependency graph is in
    hand — that is Step 3, the only step that holds it, and it is where a no-signal
    leaf can be judged against what it blocks. Step 4 consumes the result. Scoping to
    the pair still excludes the Fleet precondition, which is the point of scoping at
    all: otherwise this prose would satisfy the precondition assertions above and they
    would pass without the precondition having changed.
    """
    m = re.search(r"## Step 3 — Launch order(.+?)\n## Step 5", spine, re.S)
    assert m, "skills/run/SKILL.md must still carry Step 3 and Step 4 sections"
    return m.group(1)


def test_precondition_does_not_require_branch_type(precondition):
    """Behavior 1 — `[autonomous] enabled = true` alone is a sufficient fleet config."""
    assert "branch_type" not in precondition, (
        "the Fleet precondition still requires branch_type; per start-autonomous.md "
        "unset is the common case, and :run must accept it"
    )


def test_precondition_keeps_the_headless_reason(precondition):
    """Behavior 1 — dropping the branch_type requirement must not drop *why* autonomous is required.

    The reason (interactive prompts stall a headless agent until monitoring kills it) is
    still valid and is the only thing justifying the remaining requirement. A fix that
    deletes the whole paragraph would pass the test above and lose it.
    """
    assert "headless agents cannot answer interactive" in precondition, (
        "the precondition must keep explaining why [autonomous] enabled = true is required"
    )


def test_heuristic_is_computed_when_branch_type_is_unset(resolution):
    """Behavior 2 — :run runs the same heuristic, per leaf."""
    low = resolution.lower()
    assert "heuristic" in low, (
        "the launch path must say it computes the label/title heuristic when branch_type "
        "is unset — otherwise :run has nothing to substitute into `-b <TYPE>/<TICKET>`"
    )
    assert "start-branch-type-heuristics" in resolution, (
        "it must point at skills/start/references/start-branch-type-heuristics.md as the "
        "single definition of the heuristic, not restate the label/title table"
    )


def test_an_explicit_branch_type_is_still_honored(resolution):
    """Behavior 4 — set branch_type keeps working as a blanket value, no heuristic."""
    assert "branch_type" in resolution, (
        "the launch path must still document [autonomous].branch_type as the value that "
        "wins when it is set"
    )


def test_no_signal_stops_only_that_leaf(resolution):
    """Behavior 3 — a no-signal ticket must not abort the whole fleet.

    The distinction is the ticket's, and it matters operationally: one unlabeled leaf
    among twenty should cost one leaf, not the run. The exception is a no-signal leaf
    that blocks everything downstream, where stopping the leaf stops the fleet anyway.
    """
    low = resolution.lower()
    assert "label" in low, (
        "the no-signal message must tell the operator to add a type-indicating label "
        "— an actionable instruction, not just a failure"
    )
    assert "leaf" in low, (
        "the no-signal stop must be scoped to that leaf's launch rather than the fleet"
    )
    assert "downstream" in low or "blocks every" in low, (
        "it must name the exception: a no-signal leaf that blocks everything downstream "
        "does stop the fleet"
    )


def test_unrun_leaf_is_representable_in_the_ledger(spine):
    """A skip that the ledger cannot express is a skip a later poll cannot see.

    fleet-state.md is "the source of truth for the whole run" and every wake-up
    re-reads it. Behavior 3 creates a leaf that never launches; if `status` has no
    vocabulary for it, a poll cannot tell it from `queued` and waits forever for an
    agent that was never started.
    """
    assert "unrun" in spine.lower(), (
        "skills/run/SKILL.md must define an `unrun` ledger status — a leaf dropped for "
        "having no branch-type signal consumed no attempt and is not a kill"
    )


def test_final_report_can_carry_an_unrun_leaf():
    """The omission adversary hunts "quietly dropped tickets" — a legitimate skip looks like one.

    Step 3 tells the orchestrator to carry the skip into the final report, so the report
    template needs somewhere to put it and its adversary needs to not false-FAIL on it.
    """
    report = (
        REPO_ROOT / "skills" / "run" / "references" / "run-final-report.md"
    ).read_text()
    assert "unrun" in report.lower(), (
        "run-final-report.md's outcome table must give unrun leaves their own rows, and "
        "its adversary prompt must treat a disclosed unrun leaf as disclosed rather than "
        "as a quietly dropped ticket"
    )


def test_heuristic_reference_exists_and_is_the_one_definition(spine):
    """The referenced file must exist, and :run must not fork a second copy of the table.

    The copy check keys on the table's own header row, not on a word from one of its
    rows: `regression` (the obvious marker) appears in plenty of legitimate prose about
    regression tests, so it would fail the suite with a message about a copied table
    that isn't there.
    """
    assert HEURISTICS_REF.is_file(), f"{HEURISTICS_REF} must exist for :run to point at"
    assert "| Label signal |" not in spine, (
        "skills/run/SKILL.md must reference the label->type table, not restate it "
        "— one definition per value (CLAUDE.md §5)"
    )


def test_config_doc_records_that_run_consumes_branch_type():
    """CONFIG.md's key reference lists branch_type as :start-only; :run reads it too."""
    text = CONFIG_DOC.read_text()
    row = next(
        (l for l in text.splitlines() if l.startswith("| `branch_type`")),
        None,
    )
    assert row is not None, "CONFIG.md must document branch_type in the [autonomous] table"
    assert ":run" in row, (
        "CONFIG.md's branch_type row still names only `:start` as the consuming skill; "
        ":run substitutes it into the worktree branch, so a reader configuring a fleet "
        "needs to know it applies there too"
    )
