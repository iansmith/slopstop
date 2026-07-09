"""
Phase 0 red tests for BILL-179 — :run integration + final report + final
big-tier adversary (design/slopstop-process.md §7f-§7g, §8).

Expected behaviors:
1. skills/run/SKILL.md Step 8 is real (stub replaced), delegating to
   references/run-final-report.md (manifest updated).
2. Integration: serial, dependency order, :merge <TICKET> from the root
   checkout (declined-PR reopen), conflicts resolved + suite re-run, and the
   PASS@<sha> blessing re-checked at the tip before integrating (BILL-177's
   forward contract).
3. Umbrella completion: umbrella report to the run dir + fresh big-tier drift
   check vs PRD + charter; failures -> reconcile or G4.
4. Final report per PRD §10 (outcome table, deviation ledger, verification
   state, spend, archive confirmation) with a provenance header; PRD + charter
   attached to the umbrella ticket.
5. Final adversary: fresh big-tier, charter "prove wrong or INCOMPLETE",
   works from ground truth and re-runs the test suite itself; <=3 rounds ->
   human. G-final stop; scratch cleaned only after human acceptance.

Test command:
    python3 -m pytest tests/test_bill179_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SPINE = REPO_ROOT / "skills" / "run" / "SKILL.md"
REF = REPO_ROOT / "skills" / "run" / "references" / "run-final-report.md"
MANIFEST = REPO_ROOT / "skills" / "run" / "references" / "manifest.txt"


@pytest.fixture(scope="module")
def spine():
    return SPINE.read_text()


@pytest.fixture(scope="module")
def ref():
    assert REF.exists(), "references/run-final-report.md must exist"
    return REF.read_text()


def test_stub_replaced(spine):
    step8 = spine[spine.find("## Step 8"):spine.find("## Rules")]
    assert "Docks here" not in step8
    assert "run-final-report.md" in step8


def test_manifest_updated():
    listed = {ln.strip() for ln in MANIFEST.read_text().splitlines() if ln.strip()}
    assert "run-final-report.md" in listed


def test_serial_merge_from_root(ref):
    lowered = ref.lower()
    assert ":merge" in ref
    assert "root" in lowered
    assert "serial" in lowered or "one at a time" in lowered
    assert "reopen" in lowered or "declined" in lowered


def test_blessing_recheck_honored(ref):
    """BILL-177's PASS@<sha> forward contract."""
    assert "PASS@" in ref
    lowered = ref.lower()
    assert "void" in lowered or "re-run" in lowered


def test_umbrella_drift_check(ref):
    lowered = ref.lower()
    assert "umbrella report" in lowered
    assert "drift" in lowered
    assert "charter" in lowered


def test_final_report_sections(ref):
    lowered = ref.lower()
    for section in ("outcome table", "deviation ledger", "verification state",
                    "spend", "archive confirmation"):
        assert section in lowered, f"final report must carry: {section}"
    assert "provenance" in lowered


def test_prd_charter_archived_to_umbrella(ref):
    lowered = ref.lower()
    assert "attach" in lowered
    assert "prd" in lowered and "charter" in lowered


def test_final_adversary(ref):
    lowered = ref.lower()
    assert "incomplete" in lowered
    assert "ground truth" in lowered
    assert "re-run" in lowered and ("suite" in lowered or "test" in lowered)
    assert "3" in ref and "round" in lowered
    assert "omission" in lowered


def test_gfinal_stop_and_scratch_cleanup(ref):
    assert "G-final" in ref
    lowered = ref.lower()
    assert "accept" in lowered
    assert "scratch" in lowered and ("only after" in lowered or "never before" in lowered)
