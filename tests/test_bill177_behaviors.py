"""
Phase 0 red tests for BILL-177 — :run handoff verification
(design/slopstop-process.md §7d).

When an agent reports done, the orchestrator trusts nothing: two fresh
medium-tier subagents read the actual worktree/diff and return verdict-only
structured results; failures relaunch the agent in the same preserved worktree
with the findings cited.

Expected behaviors:
1. skills/run/SKILL.md Step 6 is the real verification step (stub replaced),
   delegating to references/run-verification.md (manifest updated).
2. Two subagents: requirements adversary (vs the ticket's DoD/behaviors —
   vacuous tests, scope violations, criteria met on paper) and code reviewer;
   both medium-tier, both fresh, both reading artifacts not claims.
3. Verdict-only returns (pass/fail + file:line findings); the orchestrator
   context never ingests diffs.
4. Either verdict fails -> relaunch in the same preserved worktree, findings
   in the brief, consuming an attempt.

Test command:
    python3 -m pytest tests/test_bill177_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SPINE = REPO_ROOT / "skills" / "run" / "SKILL.md"
REF = REPO_ROOT / "skills" / "run" / "references" / "run-verification.md"
MANIFEST = REPO_ROOT / "skills" / "run" / "references" / "manifest.txt"


@pytest.fixture(scope="module")
def spine():
    return SPINE.read_text()


@pytest.fixture(scope="module")
def ref():
    assert REF.exists(), "references/run-verification.md must exist"
    return REF.read_text()


def test_stub_replaced(spine):
    step6 = spine[spine.find("## Step 6"):spine.find("## Step 7")]
    assert "Docks here" not in step6
    assert "run-verification.md" in step6


def test_manifest_updated():
    listed = {ln.strip() for ln in MANIFEST.read_text().splitlines() if ln.strip()}
    assert "run-verification.md" in listed


def test_two_subagents_medium_fresh(ref):
    lowered = ref.lower()
    assert "adversary" in lowered and "reviewer" in lowered
    assert "medium" in lowered
    assert "fresh" in lowered


def test_adversary_hunts_conformance(ref):
    lowered = ref.lower()
    assert "definition of done" in lowered or "dod" in lowered
    assert "vacuous" in lowered
    assert "scope" in lowered


def test_reads_artifacts_not_claims(ref):
    lowered = ref.lower()
    assert "worktree" in lowered
    assert "claim" in lowered  # "never the agent's claims"


def test_verdict_only_no_diffs_in_context(ref):
    lowered = ref.lower()
    assert "verdict" in lowered
    assert "file:line" in lowered or "file : line" in lowered
    assert "never" in lowered and "diff" in lowered


def test_failure_relaunches_same_worktree(ref):
    lowered = ref.lower()
    assert "same" in lowered and "worktree" in lowered
    assert "attempt" in lowered
    assert "finding" in lowered
