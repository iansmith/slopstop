"""
Phase 0 red tests for BILL-134 — add --inline mode to :pr and :plan to fix
sub-agent deadlock in fleet agents.

When a slopstop skill that spawns-and-awaits sub-agents runs inside a delegated
worktree agent, it deadlocks: the harness routes child completion to the top-level
loop, not back to the spawning context.  The fix: an --inline flag that routes
each spawn-and-await step through an inline fallback (no Agent/Skill spawns).

Expected behaviors after implementation:
1.  :pr SKILL.md documents --inline in Arguments
2.  :pr Step 1 dispatches to inline simplify when --inline
3.  :pr Step 2d dispatches to inline slop detection when --inline
4.  :pr Step 6-claude dispatches to inline code review when --inline
5.  pr-simplify.md has an inline section that captures $INLINE_DIFF for slop reuse
6.  pr-slop-detection.md inline section uses $INLINE_DIFF (with --no-simplify fallback)
7.  pr-claude-review.md has an inline code review section
8.  :plan SKILL.md documents --inline in Arguments
9.  :plan Step 0f dispatches to inline fallback when --inline
10. :plan Step 1c: --inline and Explore-unavailable collapsed into one condition
11. :plan Step 3 forces serial when --inline
12. design/slopstop-agent-process.md documents :pr --inline and :plan --inline for fleet agents
13. plan-agent-prompt.md has a scope note distinguishing fleet vs within-ticket agents

These tests FAIL on current code and turn GREEN once the implementation is complete.

Test command:
    python3 -m pytest tests/test_bill134_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
DESIGN_DIR = REPO_ROOT / "design"


def _skill_text(name):
    """Concatenate SKILL.md + all references/*.md for a skill."""
    base = SKILLS_DIR / name
    texts = []
    skill_md = base / "SKILL.md"
    if skill_md.exists():
        texts.append(skill_md.read_text())
    refs = base / "references"
    if refs.is_dir():
        for f in sorted(refs.glob("*.md")):
            texts.append(f.read_text())
    return "\n".join(texts)


def _spine(name):
    return (SKILLS_DIR / name / "SKILL.md").read_text()


def _ref(skill, filename):
    return (SKILLS_DIR / skill / "references" / filename).read_text()


# ---------------------------------------------------------------------------
# Edge / boundary tests — cases most commonly missed
# ---------------------------------------------------------------------------

def test_pr_inline_does_not_imply_no_poll():
    """--inline flag description must state it has no effect on CodeRabbit polling.

    The inline flag only affects spawn-and-await steps (simplify, slop, claude
    review).  CodeRabbit polling is a shell loop — it doesn't spawn agents and
    must continue to work normally when --inline is active.  The flag description
    in the Arguments section must state it has no effect on Step 6-cr or polling.
    """
    spine = _spine("pr")
    # The --inline flag must be in the Arguments section (before Pre-flight)
    args_section = spine.split("## Pre-flight")[0]
    assert "--inline" in args_section, (
        ":pr SKILL.md must document --inline in the Arguments section; "
        "currently no --inline flag exists so this test will be RED"
    )
    # Within the --inline flag description, it must call out CodeRabbit is unaffected
    inline_line = next(
        (line for line in args_section.splitlines() if "--inline" in line), ""
    )
    assert "6-cr" in inline_line or "poll" in inline_line.lower() or "coderabbit" in inline_line.lower() or "no effect" in inline_line.lower(), (
        ":pr SKILL.md --inline flag description must state it has no effect on "
        "CodeRabbit polling (Step 6-cr)"
    )


def test_pr_slop_inline_handles_no_simplify_fallback():
    """Inline slop detection must handle the case where --no-simplify was passed.

    When --inline and --no-simplify are combined, simplify (Step 1) is skipped,
    so $INLINE_DIFF was never captured.  The inline slop section must fall back
    to running git diff HEAD rather than assuming $INLINE_DIFF exists.
    """
    text = _ref("pr", "pr-slop-detection.md")
    assert "--no-simplify" in text or "no-simplify" in text, (
        "pr-slop-detection.md inline section must handle the --no-simplify case "
        "(where $INLINE_DIFF is not available and git diff HEAD must be re-run)"
    )


def test_pr_inline_simplify_single_diff_command():
    """Inline simplify must use a single git diff HEAD rather than N+1 calls.

    The original agent path ran git diff --name-only (to enumerate files) then
    git diff -- <file> per file (N+1 invocations).  The inline path must use a
    single git diff HEAD which delivers all hunks in one shot.
    """
    text = _ref("pr", "pr-simplify.md")
    # Must have a single-command diff capture, not the two-step enumerate+per-file pattern
    assert "git diff HEAD" in text, (
        "pr-simplify.md inline section must capture the diff with a single "
        "'git diff HEAD' rather than the N+1 name-only + per-file pattern"
    )
    assert "git diff --name-only" not in text or "Inline" not in text.split("git diff --name-only")[0].split("\n")[-1], (
        "pr-simplify.md inline section must not use 'git diff --name-only' "
        "(N+1 invocation pattern); use a single 'git diff HEAD' instead"
    )


def test_plan_inline_does_not_affect_no_adversary():
    """--inline and --no-adversary must be independent flags in :plan.

    --no-adversary already skips Step 0f entirely; --inline changes HOW 0f runs
    (inline vs agent) but not WHETHER it runs.  The Arguments section must
    describe them as independent options.
    """
    spine = _spine("plan")
    # Both flags must appear in the Arguments section
    args_section = spine.split("## Step 0")[0]
    assert "--no-adversary" in args_section, (
        ":plan SKILL.md must document --no-adversary in Arguments"
    )
    assert "--inline" in args_section, (
        ":plan SKILL.md must document --inline in Arguments"
    )


# ---------------------------------------------------------------------------
# Error / rejection tests
# ---------------------------------------------------------------------------

def test_pr_inline_simplify_no_agent_spawn():
    """Inline simplify must explicitly say it skips the Agent spawn.

    The inline path must not invoke Agent(subagent_type: 'code-simplifier').
    The reference file must make this explicit so a model following the
    instructions does not accidentally spawn one.
    """
    text = _ref("pr", "pr-simplify.md")
    inline_section = text.split("## Snapshot")[0] if "## Snapshot" in text else text
    assert "inline" in inline_section.lower(), (
        "pr-simplify.md must have an inline section before the Snapshot commands"
    )
    # The inline section must say to skip the agent spawn, not invoke it
    assert "skip" in inline_section.lower() or "no agent" in inline_section.lower() or "without" in inline_section.lower(), (
        "pr-simplify.md inline section must explicitly say the Agent spawn is skipped"
    )


def test_pr_inline_slop_no_agent_spawn():
    """Inline slop detection must explicitly say it skips the Agent spawn."""
    text = _ref("pr", "pr-slop-detection.md")
    inline_section = text.split("## Slop-detection agent prompt")[0] if "## Slop-detection agent prompt" in text else text
    assert "inline" in inline_section.lower(), (
        "pr-slop-detection.md must have an inline section before the agent prompt"
    )
    assert "skip" in inline_section.lower() or "no agent" in inline_section.lower() or "without" in inline_section.lower(), (
        "pr-slop-detection.md inline section must explicitly say the Agent spawn is skipped"
    )


def test_pr_inline_review_no_skill_spawn():
    """Inline code review must explicitly say it skips the Skill invocation."""
    text = _ref("pr", "pr-claude-review.md")
    inline_section = text.split("## Build args")[0] if "## Build args" in text else text
    assert "inline" in inline_section.lower(), (
        "pr-claude-review.md must have an inline section before Build args"
    )
    assert "skip" in inline_section.lower() or "no skill" in inline_section.lower() or "without" in inline_section.lower(), (
        "pr-claude-review.md inline section must explicitly say the Skill invocation is skipped"
    )


def test_plan_inline_step3_serial_not_fanout():
    """When --inline is passed, :plan Step 3 must always take the serial path.

    Sub-worktree fanout from inside a worktree agent is not supported.  Step 3
    must explicitly prevent the parallel path when --inline is active, so a
    model following the instructions never attempts to launch nested worktree agents.
    """
    spine = _spine("plan")
    step3_section = spine.split("## Step 3")[1].split("## Step")[0] if "## Step 3" in spine else ""
    assert "--inline" in step3_section, (
        ":plan SKILL.md Step 3 must reference --inline and force serial execution"
    )
    assert "serial" in step3_section.lower(), (
        ":plan SKILL.md Step 3 must say 'serial' in the --inline branch"
    )


# ---------------------------------------------------------------------------
# Cross-feature interaction tests
# ---------------------------------------------------------------------------

def test_pr_simplify_inline_diff_variable_for_slop():
    """Inline simplify must capture the diff as a named variable for slop reuse.

    Running git diff HEAD twice (once for simplify, once for slop detection) is
    wasteful when both run in the same context.  The inline simplify section must
    capture the result as $INLINE_DIFF so the slop step can reuse it.
    """
    text = _ref("pr", "pr-simplify.md")
    assert "INLINE_DIFF" in text, (
        "pr-simplify.md inline section must capture the diff as $INLINE_DIFF "
        "so pr-slop-detection.md can reuse it without re-running git diff HEAD"
    )


def test_pr_slop_inline_reuses_inline_diff():
    """Inline slop detection must reference $INLINE_DIFF from the simplify step.

    Both simplify and slop detection need the working-tree diff.  When both run
    inline in the same context, slop detection must reuse $INLINE_DIFF rather
    than re-running git diff HEAD.
    """
    text = _ref("pr", "pr-slop-detection.md")
    assert "INLINE_DIFF" in text, (
        "pr-slop-detection.md inline section must reference $INLINE_DIFF "
        "captured by the inline simplify step, not re-run git diff HEAD"
    )


def test_plan_inline_step1c_collapses_explore_unavailable():
    """When --inline, :plan Step 1c must use the same inline path as 'Explore unavailable'.

    Before this ticket, Step 1c had two separate conditions that resolved identically:
    (a) --inline passed → inline Grep/Glob/Read
    (b) Explore unavailable → inline Grep/Glob/Read (fallback)
    They must be collapsed into one combined condition, e.g.
    'If --inline was passed or Explore is unavailable: use inline Grep/Glob/Read'.
    """
    spine = _spine("plan")
    step1c_section = ""
    if "### 1c." in spine:
        step1c_section = spine.split("### 1c.")[1].split("###")[0]
    # The combined condition must have --inline and "unavailable" on the same line/sentence
    assert "--inline" in step1c_section, (
        ":plan SKILL.md Step 1c must reference --inline for the inline path; "
        "currently no --inline flag exists in Step 1c so this test is RED"
    )
    # After collapsing, "unavailable" and "--inline" should appear in the same condition
    # (same line or closely adjacent), not in two separate blocks
    lines = step1c_section.splitlines()
    combined = any("--inline" in line and ("unavailable" in line or "fall back" in line.lower()) for line in lines)
    assert combined, (
        ":plan SKILL.md Step 1c must collapse --inline and Explore-unavailable "
        "into a single combined condition (e.g. 'If --inline was passed or Explore is unavailable')"
    )


def test_design_doc_fleet_agents_use_inline():
    """design/slopstop-agent-process.md must document that fleet agents use --inline.

    The design doc governs the orchestrator fleet.  It must be updated to specify
    that agents run ':pr --inline' and ':plan --inline' to avoid the deadlock.
    Without this, the orchestrator's agent brief will omit --inline and the fleet
    will deadlock on the first :pr Step 2d.
    """
    design_doc = DESIGN_DIR / "slopstop-agent-process.md"
    assert design_doc.exists(), (
        "design/slopstop-agent-process.md must exist — "
        "it governs the multi-ticket orchestrator fleet"
    )
    text = design_doc.read_text()
    assert ":pr --inline" in text or "pr --inline" in text, (
        "design/slopstop-agent-process.md must specify that fleet agents "
        "run ':pr --inline', not bare ':pr'"
    )
    assert ":plan --inline" in text or "plan --inline" in text, (
        "design/slopstop-agent-process.md must specify that fleet agents "
        "run ':plan --inline', not bare ':plan'"
    )


def test_plan_agent_prompt_scope_note_distinguishes_fleet():
    """plan-agent-prompt.md must have a scope note distinguishing it from fleet agents.

    The per-agent prompt template is for :plan's within-ticket parallel fanout.
    Fleet agents (one per ticket in the orchestrator flow) follow a different
    contract: they use :pr --inline.  Without a scope note, maintainers may
    incorrectly apply this template to fleet agents and omit --inline.
    The scope note must be explicit: mention 'fleet' OR ('within-ticket' AND '--inline').
    """
    text = _ref("plan", "plan-agent-prompt.md")
    assert "fleet" in text.lower(), (
        "plan-agent-prompt.md must have a scope note that explicitly mentions 'fleet' "
        "agents (the multi-ticket orchestrator flow) to distinguish this template from "
        "the fleet-agent contract in design/slopstop-agent-process.md"
    )


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def test_pr_inline_flag_documented_in_arguments():
    """`:pr` SKILL.md Arguments section must document --inline."""
    spine = _spine("pr")
    args_section = spine.split("## Pre-flight")[0]
    assert "--inline" in args_section, (
        ":pr SKILL.md must document --inline in the Arguments section"
    )


def test_pr_step1_dispatches_inline():
    """:pr Step 1 must dispatch to inline simplify when --inline is passed."""
    spine = _spine("pr")
    step1_section = spine.split("## Step 1")[1].split("## Step")[0] if "## Step 1" in spine else ""
    assert "--inline" in step1_section or "inline" in step1_section.lower(), (
        ":pr SKILL.md Step 1 must reference --inline and dispatch to the inline simplify procedure"
    )


def test_pr_step2d_dispatches_inline():
    """:pr Step 2d must dispatch to inline slop detection when --inline is passed."""
    spine = _spine("pr")
    step2d_section = spine.split("## Step 2d")[1].split("## Step")[0] if "## Step 2d" in spine else ""
    assert "--inline" in step2d_section or "inline" in step2d_section.lower(), (
        ":pr SKILL.md Step 2d must reference --inline and dispatch to inline slop detection"
    )


def test_pr_step6_claude_dispatches_inline():
    """:pr Step 6-claude must dispatch to inline code review when --inline is passed."""
    spine = _spine("pr")
    step6_section = spine.split("## Step 6-claude")[1].split("## Step")[0] if "## Step 6-claude" in spine else ""
    assert "--inline" in step6_section or "inline" in step6_section.lower(), (
        ":pr SKILL.md Step 6-claude must reference --inline and dispatch to the inline review"
    )


def test_plan_inline_flag_documented_in_arguments():
    """:plan SKILL.md Arguments section must document --inline."""
    spine = _spine("plan")
    args_section = spine.split("## Pre-flight")[0]
    assert "--inline" in args_section, (
        ":plan SKILL.md must document --inline in the Arguments section"
    )


def test_plan_step0f_dispatches_inline():
    """:plan Step 0f must dispatch to inline adversary fallback when --inline is passed."""
    spine = _spine("plan")
    step0f_section = spine.split("### Step 0f")[1].split("##")[0] if "### Step 0f" in spine else ""
    assert "--inline" in step0f_section or "inline" in step0f_section.lower(), (
        ":plan SKILL.md Step 0f must reference --inline and use the inline adversary fallback"
    )


def test_pr_simplify_has_inline_section():
    """pr-simplify.md must have an inline simplify section."""
    text = _ref("pr", "pr-simplify.md")
    assert "## Inline" in text or "inline" in text.lower().split("## snapshot")[0], (
        "pr-simplify.md must have a dedicated inline simplify section "
        "before the Snapshot commands section"
    )


def test_pr_slop_detection_has_inline_section():
    """pr-slop-detection.md must have an inline slop detection section."""
    text = _ref("pr", "pr-slop-detection.md")
    assert "## Inline" in text or "inline slop" in text.lower(), (
        "pr-slop-detection.md must have a dedicated inline slop detection section"
    )


def test_pr_claude_review_has_inline_section():
    """pr-claude-review.md must have an inline code review section."""
    text = _ref("pr", "pr-claude-review.md")
    assert "## Inline" in text or "inline code review" in text.lower(), (
        "pr-claude-review.md must have a dedicated inline code review section"
    )


# ---------------------------------------------------------------------------
# Adversary gap tests (Phase 0f) — added after initial red suite
# ---------------------------------------------------------------------------

def test_pr_inline_simplify_section_does_not_contain_name_only():
    """Inline simplify section must not use the N+1 git diff --name-only pattern.

    Gaps covered:
    - The existing test_pr_inline_simplify_single_diff_command has a vacuous second
      assertion that is always True in practice (the line before --name-only is never
      "Inline").
    - The real constraint is: the inline section must NOT use --name-only at all.
      The N+1 pattern (enumerate files then diff each) defeats the purpose of a
      single-invocation inline simplify.
    """
    text = _ref("pr", "pr-simplify.md")
    assert "## Inline" in text, (
        "pr-simplify.md must have an ## Inline section "
        "(this test requires it before checking --name-only absence)"
    )
    inline_section = text.split("## Inline")[1].split("\n## ")[0]
    assert "git diff --name-only" not in inline_section, (
        "pr-simplify.md inline section must not use 'git diff --name-only' "
        "(the N+1 per-file enumeration pattern); capture everything in one call"
    )


def test_pr_step1_inline_dispatch_is_conditional():
    """Step 1 --inline dispatch must use an affirmative conditional, not a bare mention.

    'inline' appearing in the step description as a negative mention (e.g. 'skip the
    inline path') would satisfy the existing test.  This test requires a proper
    conditional dispatch phrase.
    """
    spine = _spine("pr")
    step1_section = spine.split("## Step 1")[1].split("## Step")[0] if "## Step 1" in spine else ""
    affirmative = (
        "`--inline`" in step1_section
        or "if --inline" in step1_section.lower()
        or "when --inline" in step1_section.lower()
        or "--inline was passed" in step1_section.lower()
    )
    assert affirmative, (
        ":pr SKILL.md Step 1 must contain an affirmative conditional dispatch "
        "('`--inline`:', 'if --inline', 'when --inline') not just a bare word occurrence"
    )


def test_pr_step2d_inline_dispatch_is_conditional():
    """Step 2d --inline dispatch must use an affirmative conditional, not a bare mention."""
    spine = _spine("pr")
    step2d_section = spine.split("## Step 2d")[1].split("## Step")[0] if "## Step 2d" in spine else ""
    affirmative = (
        "`--inline`" in step2d_section
        or "if --inline" in step2d_section.lower()
        or "when --inline" in step2d_section.lower()
        or "--inline was passed" in step2d_section.lower()
    )
    assert affirmative, (
        ":pr SKILL.md Step 2d must contain an affirmative conditional dispatch "
        "('`--inline`:', 'if --inline') not just a bare word occurrence"
    )


def test_pr_step6_inline_dispatch_is_conditional():
    """Step 6-claude --inline dispatch must use an affirmative conditional, not a bare mention."""
    spine = _spine("pr")
    step6_section = spine.split("## Step 6-claude")[1].split("## Step")[0] if "## Step 6-claude" in spine else ""
    affirmative = (
        "`--inline`" in step6_section
        or "if --inline" in step6_section.lower()
        or "when --inline" in step6_section.lower()
        or "--inline was passed" in step6_section.lower()
    )
    assert affirmative, (
        ":pr SKILL.md Step 6-claude must contain an affirmative conditional dispatch "
        "('`--inline`:', 'if --inline') not just a bare word occurrence"
    )


def test_plan_step0f_inline_dispatch_is_conditional():
    """Step 0f --inline dispatch must use an affirmative conditional, not a bare mention."""
    spine = _spine("plan")
    step0f_section = spine.split("### Step 0f")[1].split("##")[0] if "### Step 0f" in spine else ""
    affirmative = (
        "`--inline`" in step0f_section
        or "if --inline" in step0f_section.lower()
        or "when --inline" in step0f_section.lower()
        or "--inline was passed" in step0f_section.lower()
    )
    assert affirmative, (
        ":plan SKILL.md Step 0f must contain an affirmative conditional dispatch "
        "('`--inline`:', 'if --inline') not just a bare word occurrence"
    )


def test_plan_inline_step3_inline_and_serial_same_branch():
    """--inline in Step 3 must be co-located with the serial path instruction.

    Both '--inline' and 'serial' already exist independently in Step 3 (the step
    describes serial vs parallel paths; 'serial' appears in the existing branch).
    Simply checking both words exist passes even without the feature.  This test
    requires --inline to appear within 5 lines of 'serial', confirming they describe
    the same branch rather than separate sections.
    """
    spine = _spine("plan")
    step3_section = spine.split("## Step 3")[1].split("## Step")[0] if "## Step 3" in spine else ""
    lines = step3_section.splitlines()
    inline_linenos = [i for i, l in enumerate(lines) if "--inline" in l]
    serial_linenos = [i for i, l in enumerate(lines) if "serial" in l.lower()]
    assert inline_linenos, ":plan SKILL.md Step 3 must reference --inline"
    assert serial_linenos, ":plan SKILL.md Step 3 must reference serial path"
    co_located = any(
        abs(il - sl) <= 5
        for il in inline_linenos
        for sl in serial_linenos
    )
    assert co_located, (
        ":plan SKILL.md Step 3: '--inline' and 'serial' must appear within 5 lines "
        "of each other — they must describe the same branch, not separate sections"
    )


def test_plan_agent_prompt_scope_note_affirmative_fleet_mention():
    """plan-agent-prompt.md scope note must affirmatively link fleet agents to --inline.

    Gap: test_plan_agent_prompt_scope_note_distinguishes_fleet only checks 'fleet' in
    text — passes on 'This is NOT for fleet agents'.  This test requires the scope note
    to affirmatively describe fleet agents using --inline (e.g. 'fleet agents use
    :pr --inline').
    """
    text = _ref("plan", "plan-agent-prompt.md")
    assert "fleet" in text.lower(), (
        "plan-agent-prompt.md must mention 'fleet' agents in the scope note"
    )
    assert ":pr --inline" in text or "pr --inline" in text or ":plan --inline" in text, (
        "plan-agent-prompt.md scope note must affirmatively link fleet agents to "
        "--inline usage (e.g. 'fleet agents use :pr --inline'), not just mention fleet"
    )


def test_pr_step2d_inline_respects_no_test_skip():
    """Step 2d --inline dispatch must acknowledge that --no-test still skips the step.

    When both --inline and --no-test are passed, --no-test must take precedence.
    The inline routing must not re-enable Step 2d when --no-test was passed.
    Both flags must appear in Step 2d for the interaction to be explicit.
    """
    spine = _spine("pr")
    step2d_section = spine.split("## Step 2d")[1].split("## Step")[0] if "## Step 2d" in spine else ""
    assert "--inline" in step2d_section and "--no-test" in step2d_section, (
        ":pr SKILL.md Step 2d must reference both --inline (dispatch) and --no-test "
        "(skip takes precedence) so the interaction is explicit"
    )


def test_plan_inline_without_no_adversary_step0f_still_runs():
    """--inline alone must route Step 0f to inline fallback, not skip it.

    test_plan_inline_does_not_affect_no_adversary only checks both flags are in the
    Arguments section.  This test verifies that when --inline is present but
    --no-adversary is NOT, Step 0f still runs (via inline fallback, not skipped).
    The Step 0f text must reference --inline as an inline trigger, and must not
    say --inline causes a skip.
    """
    spine = _spine("plan")
    step0f_section = spine.split("### Step 0f")[1].split("##")[0] if "### Step 0f" in spine else ""
    assert "--inline" in step0f_section, (
        ":plan SKILL.md Step 0f must reference --inline to route to inline fallback"
    )
    lines_with_inline = [l for l in step0f_section.splitlines() if "--inline" in l]
    skip_on_inline = any("skip" in l.lower() for l in lines_with_inline)
    assert not skip_on_inline, (
        ":plan SKILL.md Step 0f must not skip when --inline is passed; "
        "--inline uses inline fallback. Only --no-adversary skips Step 0f."
    )


def test_pr_slop_inline_no_simplify_fallback_reruns_diff():
    """When --no-simplify, inline slop must explicitly re-run git diff HEAD.

    Gap: test_pr_slop_inline_handles_no_simplify_fallback only checks '--no-simplify'
    appears in the text.  An implementation that says 'if --no-simplify: skip slop
    detection' would pass that test while violating the spec.  This test verifies
    the fallback explicitly includes a git diff call.
    """
    text = _ref("pr", "pr-slop-detection.md")
    assert "## Inline" in text, (
        "pr-slop-detection.md must have an ## Inline section"
    )
    inline_section = text.split("## Inline")[1].split("\n## ")[0]
    assert "--no-simplify" in inline_section, (
        "pr-slop-detection.md inline section must address the --no-simplify case"
    )
    assert "git diff" in inline_section, (
        "pr-slop-detection.md inline section must include 'git diff' for the "
        "--no-simplify fallback (re-run diff when $INLINE_DIFF is unavailable)"
    )


def test_pr_inline_review_section_specifies_review_dimensions():
    """Inline code review must specify which dimensions it covers.

    Three tests already verify the inline section exists and skips the Skill spawn.
    None verify the inline section describes WHAT review checks are performed.
    A minimal 'read the diff and comment' section passes all three but provides
    no coverage guidance for the model executing the inline path.
    """
    text = _ref("pr", "pr-claude-review.md")
    assert "## Inline" in text, (
        "pr-claude-review.md must have an ## Inline section"
    )
    inline_section = text.split("## Inline")[1].split("\n## ")[0]
    dimension_words = ["dimension", "correctness", "security", "performance", "readability", "check", "review"]
    assert any(word in inline_section.lower() for word in dimension_words), (
        "pr-claude-review.md inline section must specify review dimensions "
        "(e.g. correctness, security, performance) not just 'read the diff'"
    )


def test_pr_cr_polling_has_no_inline_modification():
    """pr-cr-polling.md must not contain an --inline conditional branch.

    The --inline flag must NOT affect CodeRabbit polling (Step 6-cr).  This test
    guards against an implementation that adds an --inline branch to pr-cr-polling.md,
    which would change CR behaviour and violate the spec ('CR runs unchanged').
    This test passes on current code and must continue to pass post-implementation.
    """
    text = _ref("pr", "pr-cr-polling.md")
    assert "--inline" not in text, (
        "pr-cr-polling.md must not contain '--inline' — CodeRabbit polling is "
        "unaffected by --inline and must not have an inline-conditional branch"
    )
