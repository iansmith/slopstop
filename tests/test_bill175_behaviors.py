"""
Phase 0 red tests for BILL-175 — /slopstop:run skeleton: launch order, agent
contract, briefs, fleet state.

Stage 3's orchestrator (design/slopstop-process.md §7a-§7b): reads the
G2-approved tree, computes the dependency-first launch order, launches one
hermetically-sealed worktree agent per leaf with the §7a brief, externalizes
fleet state to disk. Monitoring (#176), verification (#177), failure handling
(#178), and integration/report (#179) dock into this spine later.

Expected behaviors:
1. skills/run/SKILL.md exists (frontmatter, ≤350 lines), tier gate vs
   [tiers].medium, reads the run dir by run-id.
2. Launch ordering: file-affinity + explicit relations, detailed in
   references/run-launch-order.md.
3. Agent brief in references/run-agent-brief.md: :plan --ticket-driven
   --inline, :pr --inline, decline the PR, never :merge, $TRACKING_DIR
   carve-out, reporting protocol, same-size adversary at adversary_effort,
   stuck exit, TICKET UNDERSPECIFIED marker awareness.
4. Router: healthy -> ANTHROPIC_BASE_URL injection + run-id per request;
   disabled/down -> direct with the degradation note. Health check happens at
   EACH agent launch.
5. Fleet state at scratch/runs/<run-id>/fleet-state.md — the source of truth,
   updated on every event.
6. Installer + manifests include run (parity).

Test command:
    python3 -m pytest tests/test_bill175_behaviors.py -v
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "skills" / "run" / "SKILL.md"
REFS = REPO_ROOT / "skills" / "run" / "references"
INSTALL = REPO_ROOT / "install-for-claude-desktop.sh"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"


@pytest.fixture(scope="module")
def spine():
    assert SKILL.exists(), "skills/run/SKILL.md must exist (BILL-175)"
    return SKILL.read_text()


@pytest.fixture(scope="module")
def brief():
    path = REFS / "run-agent-brief.md"
    assert path.exists(), "references/run-agent-brief.md must exist"
    return path.read_text()


@pytest.fixture(scope="module")
def launch_order():
    path = REFS / "run-launch-order.md"
    assert path.exists(), "references/run-launch-order.md must exist"
    return path.read_text()


def test_frontmatter_line_limit_tier_gate(spine):
    frontmatter = spine.split("---", 2)[1]
    assert "description:" in frontmatter
    assert "disable-model-invocation: true" in frontmatter
    assert len(spine.splitlines()) <= 350
    assert "[tiers]" in spine and "medium" in spine
    assert "hard stop" in spine.lower() or "hard-stop" in spine.lower()


def test_reads_run_dir(spine):
    assert "scratch/runs/" in spine
    assert "run-id" in spine.lower() or "$RUN_ID" in spine


def test_launch_order_reference(spine, launch_order):
    assert "run-launch-order.md" in spine
    assert "file" in launch_order.lower() and "affinity" in launch_order.lower()
    assert "disjoint" in launch_order.lower()
    assert "blocked" in launch_order.lower() or "explicit" in launch_order.lower()


def test_brief_contract(brief):
    """The brief carries every §7a hard constraint."""
    assert ":plan --ticket-driven --inline" in brief
    assert ":pr --inline" in brief
    assert "DECLINE" in brief or "decline" in brief
    assert "slopstop:merge" in brief  # the do-NOT-run instruction names it
    assert "$TRACKING_DIR" in brief
    assert "adversary_effort" in brief
    assert "TICKET UNDERSPECIFIED" in brief
    assert "stuck" in brief.lower()
    assert "rebase" in brief.lower()  # git-behavior constraint


def test_router_injection_per_launch(spine):
    assert "[fleet.router]" in spine
    assert "ANTHROPIC_BASE_URL" in spine
    assert "each agent launch" in spine.lower() or "every agent launch" in spine.lower()
    assert "cost tracking" in spine.lower()


def test_fleet_state_externalized(spine):
    assert "fleet-state.md" in spine
    assert "source of truth" in spine.lower()


def test_agents_config_consumed(spine):
    """Model/effort come from [fleet.agents]."""
    assert "[fleet.agents]" in spine


def test_installer_and_manifests():
    script = INSTALL.read_text()
    skills_line = next(ln for ln in script.splitlines() if ln.startswith("SKILLS=("))
    assert " run" in skills_line or "(run" in skills_line
    plugin = json.loads(PLUGIN_JSON.read_text())
    assert ":run" in plugin["description"]
