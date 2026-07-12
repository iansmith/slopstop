"""
Phase 0 red tests for BILL-173 — /slopstop:tickets, the Stage 2 skill.

Stage 2 (design/slopstop-process.md §6): the medium tier reads the PRD +
charter from the run dir (artifacts only), cuts the umbrella/leaf tree per the
five-section standard, drives the huge-tier adversary loop over it, and stops
at gate G2.

Expected behaviors:
1. skills/tickets/SKILL.md exists (frontmatter, ≤350 lines); tier gate against
   [tiers].medium; reads scratch/runs/<run-id>/ artifacts (run-id argument).
2. Five-section standard enforced; ticket-standard.md relocates into this
   skill's references/ (from its BILL-168 interim home in design/), with the
   spec's §6 link updated and a manifest listing every reference.
3. Huge-tier adversary loop: fresh subagent at [tiers].huge, fed only PRD +
   charter + drafted tickets, specific findings, ≤3 rounds, exhaustion goes to
   the human.
4. G2 report with tree summary + adversary verdict + spend line, provenance
   headers on the report and every created ticket, then stop — no fleet
   launch, no rewrite handling (Stage 3 owns those).
5. Installer SKILLS array + manifest descriptions include tickets (parity).

Test command:
    python3 -m pytest tests/test_bill173_behaviors.py -v
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "skills" / "tickets" / "SKILL.md"
REFS = REPO_ROOT / "skills" / "tickets" / "references"
SPEC = REPO_ROOT / "design" / "slopstop-process.md"
INSTALL = REPO_ROOT / "install-for-claude-desktop.sh"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"


@pytest.fixture(scope="module")
def spine():
    assert SKILL.exists(), "skills/tickets/SKILL.md must exist (BILL-173)"
    return SKILL.read_text()


def test_frontmatter_and_line_limit(spine):
    frontmatter = spine.split("---", 2)[1]
    assert "description:" in frontmatter
    assert "disable-model-invocation: true" in frontmatter
    assert len(spine.splitlines()) <= 350


def test_tier_gate_medium(spine):
    assert "[tiers]" in spine
    assert "medium" in spine
    assert "hard stop" in spine.lower() or "hard-stop" in spine.lower()


def test_reads_run_artifacts_only(spine):
    """Stage boundary is artifact-only: PRD + charter from the run dir."""
    assert "scratch/runs/" in spine
    assert "prd.md" in spine and "charter.md" in spine


def test_standard_relocated_into_references():
    """ticket-standard.md moves from design/ into this skill's references/."""
    assert (REFS / "ticket-standard.md").exists()
    assert not (REPO_ROOT / "design" / "ticket-standard.md").exists(), (
        "the interim design/ copy must be removed by the move (BILL-168 note)"
    )
    manifest = (REFS / "manifest.txt").read_text().splitlines()
    listed = {ln.strip() for ln in manifest if ln.strip()}
    on_disk = {f.name for f in REFS.glob("*.md")}
    assert listed == on_disk, "manifest must exactly match references/*.md"


def test_spec_link_updated():
    """The spec's §6 pointer must follow the standard to its new home.

    Guard against the vacuous form: after removing every occurrence of the
    NEW path, no reference to ticket-standard.md may remain (this fails on
    master, whose spec used the old relative link).
    """
    spec = SPEC.read_text()
    residue = spec.replace("skills/tickets/references/ticket-standard.md", "")
    assert "ticket-standard.md" not in residue, (
        "spec still references ticket-standard.md at a path other than "
        "skills/tickets/references/"
    )
    assert "skills/tickets/references/ticket-standard.md" in spec


def test_huge_adversary_loop(spine):
    """Fresh huge-tier adversary, artifact-fed, ≤3 rounds, human on exhaustion."""
    assert "[tiers].huge" in spine or "huge tier" in spine.lower()
    assert "3" in spine and ("round" in spine.lower())
    assert "fresh" in spine.lower()
    assert "human" in spine.lower()


def test_g2_stop_and_provenance(spine):
    assert "G2" in spine
    assert "provenance" in spine.lower()
    assert "launch the fleet" in spine.lower()
    assert "stop" in spine.lower()


def test_installer_and_manifests():
    script = INSTALL.read_text()
    skills_line = next(ln for ln in script.splitlines() if ln.startswith("SKILLS=("))
    assert " tickets" in skills_line or "(tickets" in skills_line
    plugin = json.loads(PLUGIN_JSON.read_text())
    assert ":tickets" in plugin["description"]
