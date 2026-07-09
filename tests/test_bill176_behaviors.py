"""
Phase 0 red tests for BILL-176 — :run monitoring: poll loop and autonomous
kill authority (design/slopstop-process.md §7c).

Expected behaviors:
1. skills/run/SKILL.md Step 5 is the real monitoring loop (no longer a
   BILL-176 docking stub) delegating detail to references/run-monitoring.md
   (manifest updated).
2. All four triggers are config-bound to their [fleet.monitoring] keys:
   quiet_investigate_min (investigate, don't kill), silence_kill_min (no
   comments AND no worktree activity), loop_kill_reports, filemap_violation
   (instant + mechanical, with the "warn" logging mode).
3. Kills are autonomous (no human interrupt), consume an attempt, are
   recorded in fleet-state with the reason, and the relaunch brief cites it.

Test command:
    python3 -m pytest tests/test_bill176_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SPINE = REPO_ROOT / "skills" / "run" / "SKILL.md"
REF = REPO_ROOT / "skills" / "run" / "references" / "run-monitoring.md"
MANIFEST = REPO_ROOT / "skills" / "run" / "references" / "manifest.txt"


@pytest.fixture(scope="module")
def spine():
    return SPINE.read_text()


@pytest.fixture(scope="module")
def ref():
    assert REF.exists(), "references/run-monitoring.md must exist"
    return REF.read_text()


def test_stub_replaced(spine):
    """Step 5 must no longer be a docking stub."""
    assert "run-monitoring.md" in spine
    step5 = spine[spine.find("## Step 5"):spine.find("## Step 6")]
    assert "Docks here" not in step5
    assert "poll_interval_min" in step5


def test_manifest_updated():
    listed = {ln.strip() for ln in MANIFEST.read_text().splitlines() if ln.strip()}
    assert "run-monitoring.md" in listed


def test_triggers_config_bound(ref):
    for key in ("poll_interval_min", "quiet_investigate_min",
                "silence_kill_min", "loop_kill_reports", "filemap_violation"):
        assert key in ref, f"trigger must be bound to [fleet.monitoring].{key}"


def test_quiet_investigates_not_kills(ref):
    assert "investigate" in ref.lower()
    assert "git status" in ref or "mtime" in ref.lower()


def test_silence_requires_both_signals(ref):
    """Silence kill needs no comments AND no worktree activity."""
    lowered = ref.lower()
    assert "and" in lowered and "silence" in lowered
    assert "no comments" in lowered or "no new ticket comment" in lowered


def test_filemap_kill_mechanical_with_warn_mode(ref):
    lowered = ref.lower()
    assert "instant" in lowered or "immediately" in lowered
    assert '"warn"' in ref
    assert "changed-files" in lowered or "changed files" in lowered


def test_kills_consume_attempt_no_human(ref):
    lowered = ref.lower()
    assert "consume" in lowered and "attempt" in lowered
    assert "no human" in lowered or "never interrupt" in lowered or "not a human" in lowered
    assert "fleet-state" in lowered
    assert "relaunch" in lowered
