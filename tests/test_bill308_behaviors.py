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

REPO_ROOT = Path(__file__).parent.parent
PR_SPINE = REPO_ROOT / "skills" / "pr" / "SKILL.md"
RUN_SPINE = REPO_ROOT / "skills" / "run" / "SKILL.md"
AGENT_BRIEF = REPO_ROOT / "skills" / "run" / "references" / "run-agent-brief.md"
CONFIG_DOC = REPO_ROOT / "CONFIG.md"


@pytest.fixture(scope="module")
def pr_spine():
    return PR_SPINE.read_text()


@pytest.fixture(scope="module")
def step6(pr_spine):
    """Step 6's dispatch block only — where the backend is selected."""
    m = re.search(r"## Step 6 — Review pass(.+?)\n---", pr_spine, re.S)
    assert m, "skills/pr/SKILL.md must still carry a Step 6 dispatch section"
    return m.group(1)


@pytest.fixture(scope="module")
def inline_description(pr_spine):
    """The `--inline` bullet in the Arguments section."""
    m = re.search(r"Optional `--inline`(.+?)\n\n", pr_spine, re.S)
    assert m, "skills/pr/SKILL.md must still describe --inline in Arguments"
    return m.group(1)


def test_step6_dispatch_is_overridden_by_inline(step6):
    """Behavior 1 — with --inline, Step 6 ignores $PR_BACKEND and takes 6-claude."""
    assert "--inline" in step6, (
        "Step 6's dispatch must mention --inline; today it dispatches purely on "
        "$PR_BACKEND, so a fleet agent under backend='greptile' walks into a ~20min "
        "bot poll inside a `claude -p` one-shot"
    )
    low = step6.lower()
    assert "interactive-only" in low or "interactive only" in low, (
        "Step 6 must say the bot backends are interactive-only — that is the reason "
        "the override exists, and without it the override reads as arbitrary"
    )


def test_inline_override_is_logged(step6):
    """Behavior 1 — a one-line log notes the override when the config said otherwise.

    Silently ignoring a configured backend is how an operator ends up believing
    Greptile reviewed a fleet agent's PR when nothing did.
    """
    assert "[--inline]" in step6, (
        "Step 6 must specify the log line noting the override (e.g. "
        "\"[--inline] backend 'greptile' is interactive-only — using Claude review\")"
    )


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
    for backend, step in (
        ("coderabbit", "Step 6-cr"),
        ("greptile", "Step 6-greptile"),
        ("claude", "Step 6-claude"),
    ):
        assert f'`"{backend}"`' in step6, (
            f"Step 6's dispatch must still route the {backend} backend"
        )
        assert step in step6, f"Step 6 must still reach {step} on the interactive path"


def test_bot_trigger_is_skipped_under_inline(pr_spine):
    """Step 5c must not post a bot trigger for a review that will never be polled.

    Not in the ticket's behavior list, but it follows directly: 5c skips only on
    `$PR_BACKEND == "claude"` or `--no-poll`. Leave it alone and `:pr --inline` under
    greptile posts "@greptile review" onto the PR, then takes 6-claude and never polls
    — an unanswered bot request sitting on the PR implying a review is pending.
    """
    m = re.search(r"### 5c\. Trigger review bot(.+?)\n## Step 6", pr_spine, re.S)
    assert m, "skills/pr/SKILL.md must still carry Step 5c"
    assert "--inline" in m.group(1), (
        "Step 5c must also skip when --inline was passed — otherwise it posts a bot "
        "trigger for a poll that the --inline override guarantees will never run"
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
