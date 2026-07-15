"""
Phase 0 red tests for BILL-293 — :start posts /tag and shared /tag-post recipe.

Expected behaviors after fix:
1. New file skills/start/references/router-tag-post.md exists with the shared recipe
2. skills/start/SKILL.md references router-tag-post.md by filename
3. skills/start/SKILL.md adds a new step (between Step 3 transition and Step 4 branch)
   that gates on [fleet.router] enabled and extracts run-id from ANTHROPIC_CUSTOM_HEADERS
4. skills/start/SKILL.md stays within its line budget (started at 243 lines, should stay reasonable)
5. YAML frontmatter in skills/start/SKILL.md remains valid (no parsing errors)

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill293_behaviors.py -v
"""

from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).parent.parent
START_SKILL = REPO_ROOT / "skills" / "start" / "SKILL.md"
ROUTER_TAG_POST_RECIPE = REPO_ROOT / "skills" / "start" / "references" / "router-tag-post.md"


@pytest.fixture(scope="module")
def start_skill_text():
    return START_SKILL.read_text()


@pytest.fixture(scope="module")
def start_skill_lines():
    return START_SKILL.read_text().split("\n")


def test_router_tag_post_recipe_exists():
    """The shared router-tag-post.md recipe file must exist."""
    assert ROUTER_TAG_POST_RECIPE.exists(), (
        "skills/start/references/router-tag-post.md must exist — "
        "this is the shared recipe for the /tag POST logic."
    )


def test_router_tag_post_recipe_is_file():
    """The recipe must be a file, not a directory."""
    assert ROUTER_TAG_POST_RECIPE.is_file(), (
        "skills/start/references/router-tag-post.md must be a file."
    )


def test_start_skill_references_router_tag_post(start_skill_text):
    """skills/start/SKILL.md must reference the router-tag-post.md recipe."""
    assert "router-tag-post" in start_skill_text, (
        "skills/start/SKILL.md must reference router-tag-post.md — "
        "the shared recipe is the new Step 3.5."
    )


def test_start_skill_mentions_fleet_router_enabled(start_skill_text):
    """skills/start/SKILL.md must gate on [fleet.router] enabled."""
    assert "[fleet.router]" in start_skill_text or "fleet.router" in start_skill_text, (
        "skills/start/SKILL.md must reference [fleet.router] enabled — "
        "the new step gates the POST on router config."
    )


def test_start_skill_mentions_anthropic_custom_headers(start_skill_text):
    """skills/start/SKILL.md must mention ANTHROPIC_CUSTOM_HEADERS for run-id extraction."""
    assert "ANTHROPIC_CUSTOM_HEADERS" in start_skill_text, (
        "skills/start/SKILL.md must reference ANTHROPIC_CUSTOM_HEADERS — "
        "the run-id is extracted from the X-Slopstop-Run header."
    )


def test_start_skill_mentions_tag_endpoint(start_skill_text):
    """skills/start/SKILL.md must reference the /tag endpoint."""
    assert "/tag" in start_skill_text, (
        "skills/start/SKILL.md must reference the /tag endpoint — "
        "the new step POSTs to this endpoint."
    )


def test_start_skill_yaml_frontmatter_valid(start_skill_lines):
    """YAML frontmatter must be valid (starts with ---, ends with ---)."""
    assert start_skill_lines[0] == "---", (
        "skills/start/SKILL.md must start with --- for YAML frontmatter."
    )

    # Find closing ---
    closing_index = None
    for i in range(1, min(50, len(start_skill_lines))):
        if start_skill_lines[i] == "---":
            closing_index = i
            break

    assert closing_index is not None, (
        "skills/start/SKILL.md must have closing --- for YAML frontmatter."
    )


def test_start_skill_within_line_budget(start_skill_text):
    """skills/start/SKILL.md should stay within reasonable line budget (started at 243)."""
    line_count = len(start_skill_text.split("\n"))
    # Allow up to 350 lines for the added step + references + guidance
    assert line_count <= 350, (
        f"skills/start/SKILL.md has {line_count} lines, should stay under 350. "
        "The added step should be concise, referencing the recipe file."
    )


def test_start_skill_line_count_increased():
    """skills/start/SKILL.md must have grown from the original 244 lines (243 + 1 blank)."""
    line_count = len(START_SKILL.read_text().split("\n"))
    # Original was 244 lines; with new step referencing recipe, should have grown to ~250
    assert line_count > 248, (
        f"skills/start/SKILL.md has {line_count} lines, but should have grown from 244 "
        "to accommodate the new step and references."
    )


def test_router_tag_post_recipe_has_extract_logic(start_skill_text):
    """The new step must mention extracting run-id from headers."""
    # Looking for language about extracting/reading from ANTHROPIC_CUSTOM_HEADERS
    assert ("extract" in start_skill_text.lower() or "read" in start_skill_text.lower()), (
        "skills/start/SKILL.md must describe extracting the run-id from headers."
    )


def test_router_tag_post_recipe_has_content():
    """The router-tag-post.md recipe must not be empty."""
    content = ROUTER_TAG_POST_RECIPE.read_text()
    assert len(content.strip()) > 50, (
        "skills/start/references/router-tag-post.md must have substantial content, "
        "not just a stub."
    )
