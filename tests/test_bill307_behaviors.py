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
def step4(spine):
    """Step 4's worktree-creation bullet — where <TYPE> is substituted."""
    m = re.search(r"## Step 4 — Brief and launch(.+?)\n## Step 5", spine, re.S)
    assert m, "skills/run/SKILL.md must still carry a Step 4 section"
    return m.group(1)


def test_precondition_does_not_require_branch_type(precondition):
    """Behavior 1 — `[autonomous] enabled = true` alone is a sufficient fleet config."""
    assert "branch_type" not in precondition, (
        "the Fleet precondition still requires branch_type; per start-autonomous.md "
        "unset is the common case, and :run must accept it"
    )


def test_precondition_error_message_does_not_demand_branch_type(spine):
    """Behavior 1 — the operator-facing stop message must not ask for a key that is optional.

    The message is the whole user-visible surface of this bug: it is what told the
    operator to set a key `:start` never wanted. Four of ten consuming projects leave
    branch_type unset and were hard-stopped out of `:run` entirely by it.
    """
    assert "Fleet agents require [autonomous] enabled = true and\nbranch_type" not in spine, (
        "the precondition's stop message still demands branch_type"
    )
    assert "headless agents cannot answer interactive" in spine, (
        "the precondition must keep explaining *why* autonomous mode is required at all "
        "— that reason (interactive prompts stall a headless agent) is still valid"
    )


def test_step4_computes_the_heuristic_when_branch_type_is_unset(step4):
    """Behavior 2 — Step 4 runs the same heuristic, per ticket."""
    low = step4.lower()
    assert "heuristic" in low, (
        "Step 4 must say it computes the label/title heuristic when branch_type is unset "
        "— otherwise :run has nothing to substitute into `-b <TYPE>/<TICKET>`"
    )
    assert "start-branch-type-heuristics" in step4, (
        "Step 4 must point at skills/start/references/start-branch-type-heuristics.md as "
        "the single definition of the heuristic, not restate the label/title table"
    )


def test_step4_still_honors_an_explicit_branch_type(step4):
    """Behavior 4 — set branch_type keeps working as a blanket value, no heuristic."""
    assert "branch_type" in step4, (
        "Step 4 must still document [autonomous].branch_type as the value that wins "
        "when it is set"
    )


def test_no_signal_stops_only_that_leaf(step4):
    """Behavior 3 — a no-signal ticket must not abort the whole fleet.

    The distinction is the ticket's, and it matters operationally: one unlabeled leaf
    among twenty should cost one leaf, not the run. The exception is a no-signal leaf
    that blocks everything downstream, where stopping the leaf stops the fleet anyway.
    """
    low = step4.lower()
    assert "label" in low, (
        "the no-signal message must tell the operator to add a type-indicating label "
        "— an actionable instruction, not just a failure"
    )
    assert "leaf" in low, (
        "Step 4 must scope the no-signal stop to that leaf's launch rather than the fleet"
    )
    assert "downstream" in low or "blocks everything" in low, (
        "Step 4 must name the exception: a no-signal leaf that blocks everything "
        "downstream does stop the fleet"
    )


def test_heuristic_reference_exists_and_is_the_one_definition():
    """The referenced file must exist, and :run must not fork a second copy of the table."""
    assert HEURISTICS_REF.is_file(), f"{HEURISTICS_REF} must exist for Step 4 to point at"
    spine = RUN_SPINE.read_text()
    assert "regression" not in spine.lower(), (
        "skills/run/SKILL.md must not restate the label->type table (its 'regression' row "
        "is a marker for that table having been copied) — one definition per value"
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
