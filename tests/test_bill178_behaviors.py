"""
Phase 0 red tests for BILL-178 — :run failure handling
(design/slopstop-process.md §7e).

Budgets, the 2-failure diagnosis fork, rewrites with mandatory huge-tier delta
checks, single tier escalation, and the G4 human gate with a non-blocking
fleet.

Expected behaviors:
1. skills/run/SKILL.md Step 7 is real (stub replaced), delegating to
   references/run-failure-handling.md (manifest updated).
2. Budgets config-bound to [fleet.budget]; after 2 failed attempts the
   diagnosis fork: ticket-defect -> rewrite, capability-gap -> escalation.
3. Rewrite: cites the specific code/instruction that failed, (V2)/(V3) title,
   fresh huge-tier delta check before ANY relaunch (specificity added vs scope
   subtracted), fresh agent + fresh attempts in the same preserved worktree
   (reset-to-fork allowed only as a recorded diagnosis).
4. Escalation: [fleet.agents].escalation_model, max once, autonomous.
   TICKET UNDERSPECIFIED routes to rewrite without consuming attempts.
5. G4: failure ledger + per-ticket spend line (or degraded-mode note) + the
   four-option menu (more attempts / another rewrite / salvage — human-only /
   abandon); the fleet keeps running independent tickets while G4 pends.

Test command:
    python3 -m pytest tests/test_bill178_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SPINE = REPO_ROOT / "skills" / "run" / "SKILL.md"
REF = REPO_ROOT / "skills" / "run" / "references" / "run-failure-handling.md"
MANIFEST = REPO_ROOT / "skills" / "run" / "references" / "manifest.txt"


@pytest.fixture(scope="module")
def spine():
    return SPINE.read_text()


@pytest.fixture(scope="module")
def ref():
    assert REF.exists(), "references/run-failure-handling.md must exist"
    return REF.read_text()


def test_stub_replaced(spine):
    step7 = spine[spine.find("## Step 7"):spine.find("## Step 8")]
    assert "Docks here" not in step7
    assert "run-failure-handling.md" in step7


def test_manifest_updated():
    listed = {ln.strip() for ln in MANIFEST.read_text().splitlines() if ln.strip()}
    assert "run-failure-handling.md" in listed


def test_budgets_config_bound(ref):
    for key in ("max_attempts_per_version", "max_ticket_versions",
                "max_tier_escalations"):
        assert key in ref


def test_diagnosis_fork_after_two(ref):
    lowered = ref.lower()
    assert "2" in ref and "diagnos" in lowered
    assert "ticket" in lowered and "capability" in lowered


def test_rewrite_semantics(ref):
    assert "(V2)" in ref and "(V3)" in ref
    lowered = ref.lower()
    assert "delta check" in lowered or "delta-check" in lowered
    assert "specific" in lowered
    assert "preserved worktree" in lowered
    assert "reset" in lowered and "recorded" in lowered


def test_delta_check_is_huge_tier_and_mandatory(ref):
    lowered = ref.lower()
    assert "huge" in lowered
    assert "before" in lowered and "relaunch" in lowered
    assert "scope" in lowered and ("subtract" in lowered or "shrink" in lowered)


def test_escalation_once_autonomous(ref):
    assert "escalation_model" in ref
    lowered = ref.lower()
    assert "once" in lowered or "max_tier_escalations" in ref
    assert "autonomous" in lowered


def test_underspecified_no_attempt(ref):
    assert "TICKET UNDERSPECIFIED" in ref
    assert "no attempt" in ref.lower() or "without consuming" in ref.lower()


def test_g4_menu_and_nonblocking_fleet(ref):
    lowered = ref.lower()
    for option in ("more attempts", "rewrite", "salvage", "abandon"):
        assert option in lowered, f"G4 menu must include {option}"
    assert "spend" in lowered
    assert "independent" in lowered  # fleet keeps running independent tickets
    assert "human" in lowered
