"""
Phase 0 red tests for BILL-153 — [autonomous] enabled is repo-scoped —
interactive :merge loses confirm prompt.

Bug: `[autonomous] enabled = true` in .project-conf.toml causes :merge Step 3 to
unconditionally skip the confirm prompt for all invocations — including interactive
human sessions. There is no invocation-scoped override to re-arm the prompt.

Fix: Make autonomy an invocation property:
- Add `--autonomous` flag to :merge so orchestrators pass it explicitly.
- Autonomous-mode prompt skip requires the --autonomous flag, not just the config key.
- `merge-autonomous.md` documents the invocation-scoped override.

Expected behaviors after fix:
1. merge/SKILL.md Arguments section documents the `--autonomous` flag.
2. merge/SKILL.md's "Autonomous mode" header conditions on the --autonomous flag,
   not solely on `[autonomous] enabled = true`.
3. merge-autonomous.md "Confirmation skip" section references the `--autonomous` flag
   (not just the config key) as what triggers the skip.
4. merge-autonomous.md contains an invocation-scoped override section documenting
   when --autonomous is (and is not) required.
5. merge-autonomous.md [workflow] skip_confirm note updated to say the confirm skip
   is also superseded by the --autonomous flag (not [autonomous] enabled = true alone).

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill153_behaviors.py -v
"""

from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).parent.parent
MERGE_SKILL = REPO_ROOT / "skills" / "merge" / "SKILL.md"
MERGE_AUTONOMOUS = REPO_ROOT / "skills" / "merge" / "references" / "merge-autonomous.md"


@pytest.fixture(scope="module")
def skill_text():
    return MERGE_SKILL.read_text()


@pytest.fixture(scope="module")
def autonomous_text():
    return MERGE_AUTONOMOUS.read_text()


def test_autonomous_flag_in_arguments(skill_text):
    """merge/SKILL.md Arguments section must document --autonomous flag."""
    args_start = skill_text.find("## Arguments")
    assert args_start != -1, "merge/SKILL.md must have an ## Arguments section"
    next_section = skill_text.find("\n## ", args_start + 1)
    args_section = skill_text[args_start:next_section] if next_section != -1 else skill_text[args_start:]
    assert "--autonomous" in args_section, (
        "merge/SKILL.md ## Arguments must document the --autonomous flag so orchestrators "
        "can pass it explicitly. Currently the flag does not exist."
    )


def test_autonomous_mode_conditioned_on_flag(skill_text):
    """merge/SKILL.md's Autonomous mode line must reference the --autonomous flag."""
    # Find the one-line "Autonomous mode" note near the top of the skill
    # (the line that currently says "If `[autonomous] enabled = true`: prompts skipped...")
    assert "--autonomous" in skill_text, (
        "merge/SKILL.md must reference the --autonomous flag when describing autonomous mode. "
        "Currently autonomous mode is driven solely by [autonomous] enabled = true in config, "
        "which means interactive sessions lose the confirm prompt when the config key is set."
    )


def test_confirm_skip_requires_flag(autonomous_text):
    """merge-autonomous.md Autonomous behavior section must be scoped to the --autonomous flag."""
    # The ## Autonomous behavior parent section must declare that --autonomous is the trigger.
    # All subsections (Confirmation skip, Strategy selection, etc.) inherit that scope.
    behavior_start = autonomous_text.find("## Autonomous behavior")
    assert behavior_start != -1, "merge-autonomous.md must have a '## Autonomous behavior' section"
    next_h2 = autonomous_text.find("\n## ", behavior_start + 1)
    behavior_section = autonomous_text[behavior_start:next_h2] if next_h2 != -1 else autonomous_text[behavior_start:]

    assert "--autonomous" in behavior_section, (
        "merge-autonomous.md ## Autonomous behavior section must state that autonomous mode "
        "is triggered by the --autonomous flag, not by [autonomous] enabled = true in config. "
        "The section header scopes all subsections including Confirmation skip."
    )


def test_invocation_override_documented(autonomous_text):
    """merge-autonomous.md must document the invocation-scoped --autonomous flag."""
    # The fix must add a section specifically explaining that autonomous mode is
    # triggered by the --autonomous flag, not by [autonomous] enabled = true alone.
    assert "--autonomous" in autonomous_text, (
        "merge-autonomous.md must document the --autonomous flag as the invocation-scoped "
        "override that activates autonomous mode. Currently no such flag exists in the docs, "
        "so interactive sessions cannot opt in or out of autonomous mode per-invocation."
    )


def test_skip_confirm_note_references_flag(autonomous_text):
    """merge-autonomous.md [workflow] skip_confirm table note must reference --autonomous flag."""
    # The existing note says "Has no effect when `[autonomous] enabled = true`"
    # After the fix it should say the confirm skip is superseded by --autonomous flag
    workflow_start = autonomous_text.find("## [workflow] section")
    assert workflow_start != -1, "merge-autonomous.md must have a '## [workflow] section' heading"
    workflow_section = autonomous_text[workflow_start:]

    # The note should reference --autonomous (or the flag) rather than the config key alone
    assert "--autonomous" in workflow_section or "flag" in workflow_section.lower(), (
        "merge-autonomous.md [workflow] section must update the skip_confirm note to reference "
        "the --autonomous flag (not [autonomous] enabled = true) as what supersedes skip_confirm. "
        "Currently the note says 'Has no effect when [autonomous] enabled = true' which describes "
        "the old (broken) behavior."
    )
