"""
Phase 0 red tests for BILL-308 — fleet agents always use Claude code review.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/308). Structural assertions over
skill and doc text, matching the test_skill_structure.py convention.

Policy (Ian, 2026-07-25): agents launched headlessly by `:run` (`claude -p`)
always use Claude's own code review. Greptile/CodeRabbit reviews are
interactive-only.

`--inline` already existed but changed only *how* Step 6-claude executes, never
*which* backend was selected — the flag's own description said it "has no effect
on CodeRabbit polling". So a fleet agent running `:pr --inline` under
`backend = "greptile"` entered a 60s x 20 background poll inside a `claude -p`
one-shot. Whether that process survives ~20 minutes is unverified; if it dies the
agent reports a false timeout and no review happens, silently.

The interactive path must be untouched — that is a hard constraint of the ticket,
and one test below pins each of the three interactive dispatches.

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill308_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

from conftest import ref, section

REPO_ROOT = Path(__file__).parent.parent
PR_SPINE = REPO_ROOT / "skills" / "pr" / "SKILL.md"
RUN_SPINE = REPO_ROOT / "skills" / "run" / "SKILL.md"
AGENT_BRIEF = REPO_ROOT / "skills" / "run" / "references" / "run-agent-brief.md"
CONFIG_DOC = REPO_ROOT / "CONFIG.md"


@pytest.fixture(scope="module")
def pr_spine():
    return PR_SPINE.read_text()


@pytest.fixture(scope="module")
def backend_resolution(pr_spine):
    """The `$PR_BACKEND` Pre-flight bullet — where the effective backend is decided.

    Originally scoped to Step 6's dispatch, because that is where the ticket implies
    the override lives. Resolution moved to Pre-flight during `/simplify`: deciding it
    once at the point `$PR_BACKEND` is first read means the variable denotes one value
    for the whole run, so Steps 5c/6/7f/8 need no override branch and cannot disagree
    about which backend actually reviewed. It also fixes a real hole in the Step 6
    placement — under `--no-poll`, Step 6 is skipped entirely, so an override living
    there never ran and left `$PR_BACKEND` stale for Steps 7f and 8.

    The asserted behavior is unchanged; only its location moved.

    Re-scoped again by BILL-325, which restructured Pre-flight's bullets when it cut
    the spine to <=150 lines. Now scoped to the whole Pre-flight section rather than a
    single bullet's exact punctuation — Pre-flight is where resolution lives, and
    pinning a bullet's leading dashes to a regex made this fixture break on a pure
    reflow. It still excludes Step 6, which is the point of scoping at all.
    """
    sec = section(pr_spine, "## Pre-flight")
    assert sec, "skills/pr/SKILL.md must still carry a Pre-flight section"
    assert "$PR_BACKEND" in sec, "Pre-flight must still resolve $PR_BACKEND"
    return sec


@pytest.fixture(scope="module")
def step6(pr_spine):
    """Step 6's dispatch block — consumes the already-resolved backend."""
    sec = section(pr_spine, "## Step 6 — Review pass")
    assert sec, "skills/pr/SKILL.md must still carry a Step 6 dispatch section"
    return sec


@pytest.fixture(scope="module")
def inline_description(pr_spine):
    """The `--inline` bullet in the Arguments section."""
    args = section(pr_spine, "## Arguments")
    assert args, "skills/pr/SKILL.md must still carry an Arguments section"
    line = next((l for l in args.splitlines() if "`--inline`" in l), "")
    assert line, "skills/pr/SKILL.md must still describe --inline in Arguments"
    return line


def test_inline_forces_the_claude_backend(backend_resolution):
    """Behavior 1 — --inline overrides $PR_BACKEND, and the reason is stated.

    Without the stated reason the override reads as arbitrary and invites removal.
    """
    low = backend_resolution.lower()
    assert "--inline" in backend_resolution, (
        "$PR_BACKEND resolution must account for --inline; unfixed, :pr dispatches "
        "purely on the configured value, so a fleet agent under backend='greptile' "
        "walks into a ~20min bot poll inside a `claude -p` one-shot"
    )
    assert "interactive-only" in low or "interactive only" in low, (
        "the resolution must say the bot backends are interactive-only"
    )


def test_inline_override_is_logged(backend_resolution):
    """Behavior 1 — a one-line log notes the override when the config said otherwise.

    Silently ignoring a configured backend is how an operator ends up believing
    Greptile reviewed a fleet agent's PR when nothing did.
    """
    assert "[--inline]" in backend_resolution, (
        "the resolution must specify the log line noting the override (e.g. "
        "\"[--inline] backend 'greptile' is interactive-only — using Claude review\")"
    )


def test_step6_dispatch_needs_no_inline_branch(step6):
    """Resolving once in Pre-flight means the dispatch stays a plain three-way switch.

    A second `--inline` check inside Step 6 would be the drift risk this placement
    exists to remove: two sites keying on one condition.
    """
    assert "$PR_BACKEND" in step6, "Step 6 must still dispatch on the resolved backend"


def test_inline_description_no_longer_claims_no_effect_on_polling(inline_description):
    """Behavior 1 — the flag's own description was the clearest statement of the bug."""
    low = inline_description.lower()
    assert "no effect on coderabbit polling" not in low, (
        "the --inline description still says it has no effect on CodeRabbit polling; "
        "--inline must now force the claude backend, which is precisely an effect on it"
    )
    assert "forces" in low or "always" in low, (
        "the --inline description must state that it *forces* the Claude review backend, "
        "not merely that it can run Claude review inline (which it already said)"
    )


def test_interactive_dispatch_is_unchanged(step6):
    """Behavior 3 — interactive `:pr` keeps honoring the config, all three backends.

    The ticket's hard constraint. A fix that made 6-cr/6-greptile unreachable, or
    dropped a backend from the dispatch, would satisfy every other test here.
    """
    # Assert the PAIRING, not the two strings independently. BILL-325 widened the
    # `step6` fixture from a regex ending at `---` to conftest.section(), which now
    # swallows the `### Step 6-cr / 6-greptile / 6-claude` SUBSECTIONS — so a bare
    # `step in step6` was satisfied by each subsection's own heading rather than by
    # the dispatch bullet. Mutation-proven: routing `"coderabbit"` to Step 6-greptile
    # passed. That ships a `[pr_review] backend = "greptile"` project into the
    # CodeRabbit poller, which waits 20 minutes for a `coderabbitai[bot]` comment that
    # will never arrive and then reports "no review". Same widened-fixture bug BILL-324
    # hit; catching it twice is why the assertion is now on the edge, not the nodes.
    for backend, step in (
        ("coderabbit", "Step 6-cr"),
        ("greptile", "Step 6-greptile"),
        ("claude", "Step 6-claude"),
    ):
        assert re.search(rf'`"{backend}"`\*\*\s*→\s*{re.escape(step)}(?![0-9A-Za-z-])', step6), (
            f"Step 6's dispatch must route {backend!r} to {step} specifically — the "
            "backend and the step must appear as one dispatch edge, not merely both "
            "somewhere in the section"
        )


def test_bot_trigger_is_skipped_under_inline(pr_spine):
    """Step 5c must not post a bot trigger for a review that will never be polled.

    Not in the ticket's behavior list, but it follows directly: 5c skips only on
    `$PR_BACKEND == "claude"` or `--no-poll`. Leave it alone and `:pr --inline` under
    greptile posts "@greptile review" onto the PR, then takes 6-claude and never polls
    — an unanswered bot request sitting on the PR implying a review is pending.
    """
    sec = section(ref("pr", "pr-push-and-create.md"), "## 5c.")
    assert sec, "pr-push-and-create.md must carry Step 5c (relocated there by BILL-325)"
    assert "--inline" in sec, (
        "Step 5c must account for --inline — otherwise it posts a bot trigger for a "
        "poll that the override guarantees will never run. With Pre-flight resolution "
        "its existing `$PR_BACKEND == \"claude\"` check already covers it, so what 5c "
        "needs is to say so rather than to re-derive the condition"
    )


def test_run_docs_state_fleet_agents_always_use_claude_review():
    """Behavior 2 — :run's docs say the fleet ignores [pr_review] backend."""
    combined = RUN_SPINE.read_text() + AGENT_BRIEF.read_text()
    low = combined.lower()
    assert "pr_review" in low, (
        "skills/run/SKILL.md or run-agent-brief.md must name [pr_review] backend and "
        "state that fleet agents ignore it — an operator reading only :run's docs "
        "currently has no way to know the configured backend does not apply"
    )
    assert "interactive" in low, (
        ":run's docs must say [pr_review] backend applies to interactive sessions only"
    )


def test_config_doc_records_the_fleet_exception():
    """Behavior 4 — CONFIG.md's backend row gains the fleet-agent exception."""
    text = CONFIG_DOC.read_text()
    row = next((l for l in text.splitlines() if l.startswith("| `backend`")), None)
    assert row is not None, "CONFIG.md must document [pr_review] backend"
    assert "fleet" in row.lower(), (
        "CONFIG.md's backend row must note the fleet-agent exception — a reader "
        "setting backend='greptile' needs to know it does not apply to :run's agents"
    )
