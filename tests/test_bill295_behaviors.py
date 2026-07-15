"""
Phase 0 red tests for BILL-295 — :focus lightweight mid-session re-tag command.

Expected behaviors after fix:
1. New file skills/focus/SKILL.md exists
2. skills/focus/SKILL.md has required frontmatter with disable-model-invocation: true
3. skills/focus/SKILL.md stays within the line budget (350 lines max)
4. YAML frontmatter in skills/focus/SKILL.md is valid (no parsing errors)

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill295_behaviors.py -v
"""

from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).parent.parent
FOCUS_SKILL = REPO_ROOT / "skills" / "focus" / "SKILL.md"
LINE_LIMIT = 350


@pytest.fixture(scope="module")
def focus_skill_text():
    return FOCUS_SKILL.read_text()


@pytest.fixture(scope="module")
def focus_skill_lines():
    return FOCUS_SKILL.read_text().split("\n")


def test_focus_skill_file_exists():
    """The skills/focus/SKILL.md file must exist."""
    assert FOCUS_SKILL.exists(), (
        "skills/focus/SKILL.md must exist — "
        "this is the new :focus command definition."
    )


def test_focus_skill_is_file():
    """The skill must be a file, not a directory."""
    assert FOCUS_SKILL.is_file(), (
        "skills/focus/SKILL.md must be a file."
    )


def test_focus_skill_yaml_frontmatter_valid(focus_skill_lines):
    """YAML frontmatter must be valid (starts with ---, ends with ---)."""
    assert focus_skill_lines[0] == "---", (
        "skills/focus/SKILL.md must start with --- for YAML frontmatter."
    )

    # Find closing ---
    closing_index = None
    for i in range(1, min(50, len(focus_skill_lines))):
        if focus_skill_lines[i] == "---":
            closing_index = i
            break

    assert closing_index is not None, (
        "skills/focus/SKILL.md must have closing --- for YAML frontmatter."
    )


def test_focus_skill_has_disable_model_invocation(focus_skill_text):
    """skills/focus/SKILL.md must have disable-model-invocation: true in frontmatter."""
    assert "disable-model-invocation: true" in focus_skill_text, (
        "skills/focus/SKILL.md must have 'disable-model-invocation: true' "
        "in the YAML frontmatter (this is an explicit slash command)."
    )


def test_focus_skill_within_line_budget(focus_skill_text):
    """skills/focus/SKILL.md should stay within the line budget (350 lines max)."""
    line_count = len(focus_skill_text.split("\n"))
    assert line_count <= LINE_LIMIT, (
        f"skills/focus/SKILL.md has {line_count} lines, exceeds the {LINE_LIMIT}-line limit. "
        "Keep the skill definition concise."
    )


def test_focus_skill_mentions_focus_command(focus_skill_text):
    """skills/focus/SKILL.md must reference the /slopstop:focus command."""
    assert "/slopstop:focus" in focus_skill_text or ":focus" in focus_skill_text, (
        "skills/focus/SKILL.md must describe the /slopstop:focus command."
    )


def test_focus_skill_mentions_router(focus_skill_text):
    """skills/focus/SKILL.md must mention the router."""
    assert "router" in focus_skill_text.lower(), (
        "skills/focus/SKILL.md must describe router interaction — "
        "the command POSTs to the router's /tag endpoint."
    )


def test_focus_skill_mentions_shared_recipe(focus_skill_text):
    """skills/focus/SKILL.md must reference the shared router-tag-post recipe."""
    assert "router-tag-post" in focus_skill_text, (
        "skills/focus/SKILL.md must reference the router-tag-post.md recipe — "
        "this is the shared POST logic from BILL-293."
    )


def test_focus_skill_uses_installed_path_for_recipe(focus_skill_text):
    """skills/focus/SKILL.md must reference the recipe using the installed path."""
    assert "~/.claude/commands/slopstop-start-refs/router-tag-post.md" in focus_skill_text, (
        "skills/focus/SKILL.md must reference the recipe at ~/.claude/commands/slopstop-start-refs/router-tag-post.md, "
        "not as a repo-relative path (for headless agent compatibility)."
    )
