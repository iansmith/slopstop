"""
Phase 0 red tests for BILL-172 — /slopstop:design, the Stage 1 skill.

Stage 1 of the slopstop process (design/slopstop-process.md §5): the big-tier
session grills the user to shared understanding, then writes the PRD and
feature charter into the run dir, and stops at gate G1.

Expected behaviors:
1. skills/design/SKILL.md exists (frontmatter: description +
   disable-model-invocation: true) and stays within the 350-line spine limit.
2. Tier gate: compare the session model against [tiers].big and hard-stop on
   mismatch, naming the required model.
3. Run-id minted; run state seeded at scratch/runs/<run-id>/.
4. Router integration: [fleet.router] enabled + healthy -> run-id carried on
   router-bound requests (passive; no registration call); disabled/down ->
   proceed with the "cost tracking disabled/unavailable" line in the G1 report.
5. The grill is the vendored /slopstop:grill; PRD + charter carry provenance
   headers; the skill ends at G1 ("go ahead with ticket breakdown?") and stops.
6. Installer SKILLS array includes design; plugin.json description lists
   :design.

Test command:
    python3 -m pytest tests/test_bill172_behaviors.py -v
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "skills" / "design" / "SKILL.md"
INSTALL = REPO_ROOT / "install-for-claude-desktop.sh"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"


@pytest.fixture(scope="module")
def spine():
    assert SKILL.exists(), "skills/design/SKILL.md must exist (BILL-172)"
    return SKILL.read_text()


def test_frontmatter_and_line_limit(spine):
    """Explicit slash command, within the 350-line spine limit."""
    frontmatter = spine.split("---", 2)[1]
    assert "description:" in frontmatter
    assert "disable-model-invocation: true" in frontmatter
    assert len(spine.splitlines()) <= 350


def test_tier_gate(spine):
    """Hard stop on session-model mismatch against [tiers].big."""
    assert "[tiers]" in spine
    assert "hard stop" in spine.lower() or "hard-stop" in spine.lower()
    assert "big" in spine


def test_run_id_and_scratch_seeding(spine):
    """Run-id minted; run state at scratch/runs/<run-id>/."""
    assert "run-id" in spine.lower()
    assert "scratch/runs/" in spine


def test_router_degradation(spine):
    """Router health check with the passive run-id carry and degraded mode."""
    assert "[fleet.router]" in spine
    assert "cost tracking" in spine.lower()
    assert "registration" in spine.lower() or "passive" in spine.lower(), (
        "the Phase-1 router is passive — the skill must not invent a "
        "registration call"
    )


def test_grill_and_provenance_and_g1(spine):
    """Vendored grill invoked; provenance headers; G1 stop."""
    assert "/slopstop:grill" in spine or ":grill" in spine
    assert "provenance" in spine.lower()
    assert "G1" in spine
    assert "charter" in spine.lower()


def test_installer_and_manifests_list_design():
    """Installer SKILLS array + both manifest descriptions include design."""
    script = INSTALL.read_text()
    skills_line = next(
        ln for ln in script.splitlines() if ln.startswith("SKILLS=(")
    )
    assert " design" in skills_line or "(design" in skills_line
    plugin = json.loads(PLUGIN_JSON.read_text())
    assert ":design" in plugin["description"]
    marketplace = json.loads(MARKETPLACE_JSON.read_text())
    entry = next(p for p in marketplace["plugins"] if p["name"] == "slopstop")
    assert entry["description"] == plugin["description"], (
        "manifest parity (pinned since BILL-170)"
    )
