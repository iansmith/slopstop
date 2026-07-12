"""
Phase 0 red tests for BILL-164 — design/slopstop-process.md, the four-tier
process spec; retire the old fleet doc.

The v3 restructure (PRD: docs/prd-slopstop-v3-agent-process.md, umbrella #162)
elevates the multi-agent pipeline to be THE slopstop process. This ticket writes
the spec that the stage-skill tickets implement and deletes the superseded
design/slopstop-agent-process.md (live references updated).

Expected behaviors:
1. design/slopstop-process.md exists and encodes the PRD's core decisions:
   gates ledger (G1/G2/G-final/G4), tier table + same-size adversary rule +
   provenance headers, scratch/ artifact layout, agent contract, monitoring/kill
   policy, 3x3x1 budgets, rewrite delta check, context economy, router
   degradation, final report + final adversary.
2. A "which tier runs which commands" mapping is present.
3. The old fleet doc is gone and no tracked file references it.

Test command:
    python3 -m pytest tests/test_bill164_behaviors.py -v
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SPEC = REPO_ROOT / "design" / "slopstop-process.md"
OLD_FLEET_DOC = REPO_ROOT / "design" / "slopstop-agent-process.md"


@pytest.fixture(scope="module")
def spec_text():
    assert SPEC.exists(), "design/slopstop-process.md must exist (BILL-164)"
    return SPEC.read_text()


def test_spec_exists_and_old_doc_deleted():
    """The new spec replaces the old fleet doc — both halves must hold."""
    assert SPEC.exists()
    assert not OLD_FLEET_DOC.exists()


def test_no_live_references_to_old_doc():
    """git grep for the old filename outside tests/ must return zero hits.

    tests/ and CHANGELOG.md are excluded: historical docstrings and changelog
    entries legitimately name the retired file when recording what BILL-164
    changed. Everywhere else — design/, skills/, README, manifests — a
    reference is a live pointer to a file that no longer exists. (The
    untracked PRD in docs/ is invisible to git grep, which only sees tracked
    files.)
    """
    result = subprocess.run(
        ["git", "grep", "-l", "slopstop-agent-process", "--",
         ":!tests/", ":!CHANGELOG.md"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    # git grep exits 1 when there are no matches.
    assert result.returncode == 1, (
        f"tracked files still reference slopstop-agent-process:\n{result.stdout}"
    )


def test_spec_has_gate_ledger(spec_text):
    """All four gates must be specified."""
    for gate in ("G1", "G2", "G-final", "G4"):
        assert gate in spec_text, f"spec must define gate {gate}"


def test_spec_has_tier_rules(spec_text):
    """Tier table, same-size adversary rule, and provenance headers must appear."""
    assert "[tiers]" in spec_text
    assert "same-size" in spec_text or "own tier" in spec_text, (
        "spec must state the same-size adversary rule"
    )
    assert "provenance" in spec_text.lower(), (
        "spec must require provenance headers on produced artifacts"
    )


def test_spec_has_command_tier_map(spec_text):
    """A which-tier-runs-which-commands mapping must cover the stage commands."""
    for cmd in (":design", ":tickets", ":run"):
        assert cmd in spec_text, f"spec must map {cmd} to its tier"


def test_spec_has_agent_contract(spec_text):
    """Fleet agent contract: ticket-driven plan, inline pr, decline, no merge."""
    assert "--ticket-driven" in spec_text
    assert ":pr --inline" in spec_text or "pr --inline" in spec_text
    assert "decline" in spec_text.lower()
    assert "ticket underspecified" in spec_text.lower()


def test_spec_has_budgets_and_delta_check(spec_text):
    """3x3x1 budgets and the rewrite delta check must be specified."""
    assert "[fleet.budget]" in spec_text
    assert "delta check" in spec_text.lower() or "delta-check" in spec_text.lower(), (
        "spec must require a huge-tier delta check on every ticket rewrite"
    )


def test_spec_has_monitoring_policy(spec_text):
    """Kill triggers must be config-bound, including the file-map violation kill."""
    assert "[fleet.monitoring]" in spec_text
    assert "filemap_violation" in spec_text or "file-map violation" in spec_text.lower()


def test_spec_has_scratch_layout(spec_text):
    """scratch/ interchange layout and ticket archival of PRD + charter."""
    assert "scratch/" in spec_text
    assert "charter" in spec_text.lower()


def test_spec_has_router_degradation(spec_text):
    """Router integration must specify graceful degradation and the disabled default."""
    assert "[fleet.router]" in spec_text
    assert "cost tracking" in spec_text.lower(), (
        "spec must define the degraded-mode report line when the router is off/down"
    )


def test_spec_has_final_report_adversary(spec_text):
    """The final report must be adversaried by a fresh huge-tier pass."""
    assert "final report" in spec_text.lower()
    assert "incomplete" in spec_text.lower(), (
        "the final-report adversary's charter is 'prove wrong or INCOMPLETE'"
    )


def test_spec_links_base_process_not_restates(spec_text):
    """The spec must link to base-process.md rather than restating the inner loop."""
    assert "base-process.md" in spec_text
