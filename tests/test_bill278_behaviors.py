"""Behavior tests for BILL-278 — freeze the red tests, enforce it mechanically.

Provenance note (honest record): these tests were written AFTER the BILL-278
implementation, not before it. No Phase 0 red state was established for BILL-278 —
the change was committed straight from a design session without :start/:plan. The
:pr Step 2d tamper gate correctly flagged that, and the override was taken and
recorded rather than hidden. These tests are green on arrival; their value is
forward-looking (they pin the behavior against regression), not evidentiary.

That is exactly the SOP-110 pattern this ticket exists to prevent, and it is
documented here rather than papered over.

Test command:
    python3 -m pytest tests/test_bill278_behaviors.py -v
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKILLS = REPO_ROOT / "skills"


def _read(rel: str) -> str:
    return (SKILLS / rel).read_text()


# ---------------------------------------------------------------------------
# The rule is stated where the tests are frozen
# ---------------------------------------------------------------------------

def test_plan_step_0e_freezes_the_tests():
    """:plan Step 0e must declare the Phase 0 commit a freeze, not just a commit."""
    spine = _read("plan/SKILL.md")
    assert "freezes the tests" in spine, (
        "skills/plan/SKILL.md Step 0e does not state that the Phase 0 commit FREEZES "
        "the tests. Without that, 'commit the red tests' reads as bookkeeping."
    )
    assert "amend" in spine and "rebase" in spine, (
        "Step 0e must forbid amending AND rebasing the Phase 0 commit — otherwise the "
        "frozen baseline can be rewritten out from under the tamper gate."
    )


def test_step_0e_refuses_to_freeze_a_green_test():
    """The gate's whole premise is that the baseline was RED. Nothing verified that.

    `on_phase0_tests_pass = "continue"` (the sample value; "ask" stalls headless) let an
    agent commit tests that PASSED at 0d as the Phase 0 baseline. Every downstream diff is
    then clean by construction — so the cheapest evasion of the freeze was never changing
    an assertion, but never writing a falsifying one. That is the SOP-110 shape.
    """
    spine = _read("plan/SKILL.md")
    assert "Only tests observed FAILING at 0d may enter this commit" in spine, (
        "Step 0e must refuse to stage a test that passed at 0d. A green test frozen as "
        "the baseline makes the tamper gate and Gate 0 vacuous."
    )
    assert "on_phase0_tests_pass" in spine, (
        "Step 0e must explicitly deny on_phase0_tests_pass the authority to freeze a "
        "green test — redness is a property of the baseline, not a knob."
    )


def test_pr_tamper_gate_is_not_skippable_by_any_flag():
    """The policed agent composes its own :pr invocation, so a flag-keyed skip is a
    switch the cheater controls. --no-test nominally means 'don't run the suite' — but
    the tamper gate runs no tests at all (git log + git diff)."""
    section = _step_section(_read("pr/SKILL.md"), "2d")
    assert "No flag skips this gate" in section, (
        "Step 2d must not be skippable by --no-test (or any other argument). The fleet "
        "agent composes its own :pr call, so an agent could disable its own tamper gate."
    )
    assert "task_plan.md" in section, (
        "Step 2d's skip condition must key on a RECORDED FACT (does task_plan.md record "
        "a Phase 0 baseline?), not on an agent-supplied argument."
    )


def test_plan_step_0e_points_at_the_halt_not_a_self_fix():
    """A wrong expected value routes to TICKET UNDERSPECIFIED, never a test edit."""
    spine = _read("plan/SKILL.md")
    assert "TICKET UNDERSPECIFIED" in spine and "TD-4a" in spine, (
        "Step 0e must route a genuinely-wrong expected value to the TICKET "
        "UNDERSPECIFIED halt (TD-4a), not invite the agent to fix the test itself."
    )


def test_td4a_covers_the_post_phase0_discovery_case():
    """TD-4's halt assumed plan-time discovery; TD-4a covers mid-implementation."""
    ref = _read("plan/references/plan-ticket-driven.md")
    assert "TD-4a" in ref, (
        "plan-ticket-driven.md has no TD-4a. TD-4 says 'Commit nothing' — which is "
        "wrong once the red tests are already committed. The mid-implementation case "
        "needs its own halt variant ('commit nothing FURTHER')."
    )
    assert "commit nothing *further*" in ref.lower() or "commit nothing further" in ref.lower(), (
        "TD-4a must say commit nothing FURTHER — the Phase 0 commit stays as it is."
    )


# ---------------------------------------------------------------------------
# The rule reaches the fleet agent
# ---------------------------------------------------------------------------

def test_agent_brief_has_frozen_red_tests_section():
    brief = _read("run/references/run-agent-brief.md")
    assert "The red tests are the contract" in brief, (
        "run-agent-brief.md is missing the frozen-red-tests section. The fleet agent "
        "is the party being policed; the rule must be in its brief."
    )
    assert "made the test agree" in brief, (
        "The brief must draw the distinction that matters: 'made the test pass' and "
        "'made the test agree with my code' are different acts."
    )


def test_agent_brief_hard_constraint_9_exists():
    brief = _read("run/references/run-agent-brief.md")
    assert "9. Red tests are frozen" in brief, (
        "The frozen-tests rule must appear as a numbered hard constraint, not only as "
        "prose — the constraint list is what a small-tier agent actually follows."
    )


def test_run_spine_passes_the_brief_through_whole():
    spine = _read("run/SKILL.md")
    # "whole" alone is near-vacuous: run/SKILL.md already says "the whole run" elsewhere.
    # Assert the actual rule, not a word that happens to appear.
    assert "verbatim, never summarized" in spine, (
        "run/SKILL.md Step 4 must instruct the orchestrator to pass the brief through "
        "WHOLE and verbatim — an orchestrator that summarizes the brief can summarize "
        "away the frozen-red-tests rule itself."
    )
    assert "Gate 0" in spine, "Step 4 must name Gate 0 as the enforcement."


# ---------------------------------------------------------------------------
# The ticket can actually state a contract to enforce
# ---------------------------------------------------------------------------

def test_ticket_standard_requires_expected_values():
    ref = _read("tickets/references/ticket-standard.md")
    assert "State the expected values" in ref, (
        "ticket-standard.md must require tickets to state expected VALUES, not just "
        "test names. You cannot diff against a vetted value that was never written down."
    )
    assert "oracle" in ref, (
        "When the value is not knowable at cut time, the ticket must name the ORACLE "
        "that supplies it — otherwise the expectation is left to the implementer."
    )


# ---------------------------------------------------------------------------
# Gate 0 — the :run backstop — and its three shell defects
# ---------------------------------------------------------------------------

def test_gate0_exists_and_runs_before_the_subagents():
    ref = _read("run/references/run-verification.md")
    assert "Gate 0" in ref, "run-verification.md has no Gate 0."
    assert "Run only if Gate 0 passed" in ref, (
        "Gate 0 must gate the subagents — a FAIL should end verification before any "
        "subagent tokens are spent."
    )


def test_gate0_missing_baseline_is_a_fail_not_a_pass():
    """The highest-value line: a missing Phase 0 commit is the STRONGEST failure."""
    ref = _read("run/references/run-verification.md")
    assert "No Phase 0 red-test commit found → FAIL" in ref, (
        "A missing baseline must FAIL. A tamper diff that only runs WHEN a baseline "
        "exists actively rewards skipping the baseline — it becomes the cheaper "
        "evasion, not the absence of one (observed live on SOP-110)."
    )


def test_gate0_guards_the_empty_baseline_before_diffing():
    """`git diff $RED..tip` with RED empty resolves to HEAD..tip — an empty, CLEAN diff."""
    ref = _read("run/references/run-verification.md")
    assert 'if [ -z "$RED" ]' in ref, (
        "Gate 0 must GUARD the empty-baseline case with an explicit `if [ -z \"$RED\" ]`. "
        "`[ -n \"$RED\" ] || echo FAIL` does not stop execution: the next line becomes "
        "`git diff ..<tip>`, which git resolves as HEAD..<tip> — an empty diff that "
        "reads as CLEAN, silently passing the exact case the gate exists to catch."
    )


def test_gate0_takes_the_earliest_red_commit_not_the_newest():
    """git log is reverse-chronological: grep -m1 takes the NEWEST match.

    Scoped to the actual RED= assignment, not the whole file — the prose above it
    legitimately contains the string "grep -m1" while explaining why it must not be
    used, and a whole-file check would flag that explanation as the defect.
    """
    ref = _read("run/references/run-verification.md")
    red_cmds = [ln for ln in ref.splitlines() if ln.strip().startswith("RED=")]
    assert red_cmds, "Gate 0 has no RED= baseline assignment."
    for cmd in red_cmds:
        assert "grep -m1" not in cmd, (
            f"Gate 0's baseline command uses `grep -m1`: {cmd!r}. git log is "
            "reverse-chronological, so -m1 takes the NEWEST 'Phase 0: red tests' "
            "commit — letting an agent slide the baseline past its own tamper by "
            "titling a later commit that way. Take the earliest match (tail -1)."
        )
        assert "tail -1" in cmd, (
            f"Gate 0's baseline command must select the EARLIEST Phase 0 commit "
            f"via `tail -1`: {cmd!r}"
        )


def test_gate0_derives_frozen_files_from_the_commit_not_a_glob():
    """Step 0e stages red tests by path, so the RED commit IS the manifest."""
    ref = _read("run/references/run-verification.md")
    assert "git show --name-only" in ref, (
        "Gate 0 must derive the frozen file set from the RED commit itself "
        "(`git show --name-only`), not a hardcoded glob. A glob silently covers nothing "
        "in a repo whose tests don't match it, over-scopes testdata/ fixtures, and "
        "misses Rust/Go inline #[cfg(test)] tests that live in source files — the one "
        "place a tamper would be invisible."
    )


# ---------------------------------------------------------------------------
# :pr Step 2d — the solo-path gate, and the config hole that made it dead code
# ---------------------------------------------------------------------------

def test_pr_has_a_mechanical_tamper_gate():
    ref = _read("pr/references/pr-slop-detection.md")
    assert "Red-test tamper diff" in ref, (
        "pr-slop-detection.md must carry the mechanical tamper diff. The slop catalog "
        "ALREADY listed expectation inversion and test deletion as 🔴 — the gate missed "
        "SOP-111 anyway because it only scanned uncommitted changes and was skipped on "
        "a clean tree, which is exactly what a tampering agent presents."
    )


def _step_section(text: str, step: str) -> str:
    """Return the body of '## Step <step>' up to the next '## Step' heading."""
    marker = f"## Step {step}"
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].split("## Step", 1)[0]


def test_pr_tamper_gate_is_not_governed_by_on_slop_findings():
    """The defect this test exists to prevent: a fleet config silently kills the gate.

    `on_slop_findings = "skip"` means "skip slop detection ENTIRELY". A fleet-capable
    config is effectively pinned to it, because "ask" stalls a headless agent. Nesting
    the mechanical tamper gate under that key means it never runs for exactly the
    agents it exists to police.

    Asserted behaviorally (the gate's section disclaims both levers), not by matching
    an exact sentence — the wording must stay free to change.
    """
    section = _step_section(_read("pr/SKILL.md"), "2d")
    assert section, ":pr SKILL.md has no '## Step 2d' section."
    # Bind to the NEW gate specifically. Master's OLD Step 2d was the slop gate and also
    # mentioned on_slop_findings + --no-adversary, so those alone don't distinguish the
    # fix from the bug it replaced. Require the tamper gate's own identity first.
    assert "tamper" in section.lower() and "on_redtest_tamper" in section, (
        "Step 2d must BE the mechanical red-test tamper gate (its own on_redtest_tamper "
        "knob), not the slop gate. If this fails, 2d is still the old slop step."
    )
    assert "on_slop_findings" in section and "--no-adversary" in section, (
        "Step 2d must name both levers it is NOT governed by (on_slop_findings and "
        "--no-adversary) — silence there is how the gate got disabled in the first place."
    )
    assert "not" in section.lower(), (
        "Step 2d must NEGATE those levers, not merely mention them. A mechanical "
        "anti-tampering check must not be disableable by a knob meant for a fuzzy one."
    )


def test_pr_tamper_gate_has_its_own_knob_with_no_skip_and_a_strict_default():
    ref = _read("pr/references/pr-autonomous.md")
    assert "on_redtest_tamper" in ref, (
        "The tamper gate needs its own autonomous knob (on_redtest_tamper), separate "
        "from on_slop_findings."
    )
    # The knob's value table must offer hard-stop and warn — and must NOT offer skip.
    tamper_section = ref.split("on_redtest_tamper", 1)[1].split("## ", 1)[0]
    assert "hard-stop" in tamper_section and "warn" in tamper_section, (
        "on_redtest_tamper must document its hard-stop and warn values."
    )
    assert "| `skip`" not in tamper_section, (
        "on_redtest_tamper must NOT offer a `skip` value — that is the whole point of "
        "separating it from on_slop_findings, which is pinned to skip in fleet configs."
    )
    assert "default" in tamper_section.lower() and "hard-stop" in tamper_section, (
        "The default must be the STRICT value. A gate you must opt into is a gate that "
        "does not run."
    )


def test_pr_slop_detection_ref_scopes_on_slop_findings_to_step_2e():
    """The reference file must not re-open the hole it was split to close.

    pr-slop-detection.md carries BOTH gates. Its autonomous-path section originally said
    'consult on_slop_findings' with no scoping — so an agent reading the file end-to-end
    would apply `skip` to the tamper gate, exactly the failure the split prevents.
    """
    ref = _read("pr/references/pr-slop-detection.md")
    auto = ref.split("## Autonomous path", 1)
    assert len(auto) > 1, "pr-slop-detection.md has no Autonomous path section."
    heading_line = auto[1].splitlines()[0]
    assert "2e" in heading_line, (
        "The Autonomous path section in pr-slop-detection.md must be scoped to Step 2e. "
        "Unscoped, it tells the agent to apply on_slop_findings — whose `skip` value is "
        "pinned in fleet configs — to the mechanical tamper gate as well."
    )
    assert "on_redtest_tamper" in ref, (
        "pr-slop-detection.md carries the tamper gate, so it must name the knob that "
        "actually governs it."
    )
