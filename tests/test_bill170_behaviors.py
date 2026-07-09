"""
Behavior tests for BILL-170 — Vendor grill-me as /slopstop:grill.

slopstop's Stage 1 (:design) opens with a grill session; vendoring the external
grill-me skill removes the dependency on the user having it installed. The
structural conformance tests (test_skill_structure.py) enumerate fixed skill
lists, so the vendored skill is pinned here instead.

Expected behaviors:
1. skills/grill/SKILL.md exists with description frontmatter,
   disable-model-invocation: true, and a provenance note.
2. The skill stays within the 350-line spine limit.
3. install-for-claude-desktop.sh's SKILLS array includes grill.
4. .claude-plugin/plugin.json's description lists :grill.

Test command:
    python3 -m pytest tests/test_bill170_behaviors.py -v
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
GRILL_SKILL = REPO_ROOT / "skills" / "grill" / "SKILL.md"
INSTALL_SCRIPT = REPO_ROOT / "install-for-claude-desktop.sh"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"


@pytest.fixture(scope="module")
def skill_text():
    return GRILL_SKILL.read_text()


def test_grill_skill_exists(skill_text):
    """skills/grill/SKILL.md must exist and be non-empty."""
    assert skill_text.strip()


def test_grill_frontmatter(skill_text):
    """Frontmatter must carry a description and disable-model-invocation: true."""
    assert skill_text.startswith("---"), "SKILL.md must open with YAML frontmatter"
    frontmatter = skill_text.split("---", 2)[1]
    assert "description:" in frontmatter
    assert "disable-model-invocation: true" in frontmatter, (
        "grill is an explicit slash command, not model-invocable"
    )


def test_grill_has_provenance_note(skill_text):
    """The skill must record where it was adapted from (the external grill-me skill)."""
    assert "grill-me" in skill_text and "Provenance" in skill_text


def test_grill_within_line_limit(skill_text):
    """The vendored skill must respect the 350-line spine limit."""
    assert len(skill_text.splitlines()) <= 350


def test_installer_includes_grill():
    """install-for-claude-desktop.sh SKILLS array must include grill."""
    script = INSTALL_SCRIPT.read_text()
    skills_line = next(
        line for line in script.splitlines() if line.startswith("SKILLS=(")
    )
    assert " grill" in skills_line or "(grill" in skills_line, (
        "grill missing from the installer's SKILLS array"
    )


def test_plugin_description_lists_grill():
    """.claude-plugin/plugin.json description must enumerate :grill."""
    manifest = json.loads(PLUGIN_JSON.read_text())
    assert ":grill" in manifest["description"]


def test_manifests_descriptions_in_parity():
    """plugin.json and marketplace.json must carry the same plugin description.

    BILL-170's review caught marketplace.json still advertising eleven commands
    after plugin.json moved to twelve — this pins the two manifests together so
    a future skill addition can't update only one.
    """
    plugin = json.loads(PLUGIN_JSON.read_text())
    marketplace = json.loads(MARKETPLACE_JSON.read_text())
    marketplace_entry = next(
        p for p in marketplace["plugins"] if p["name"] == "slopstop"
    )
    assert marketplace_entry["description"] == plugin["description"], (
        "plugin.json and marketplace.json descriptions have diverged — "
        "update both when the command list changes"
    )
