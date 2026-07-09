"""
Phase 0 red tests for BILL-169 — :plan --ticket-driven profile.

Fleet agents run :plan against five-section tickets (skills/tickets/references/ticket-standard.md)
where the ticket IS the investigation. The profile turns :plan from open-ended
reasoning into checklist execution, with a distinct halt when the ticket turns
out to be wrong — routed back to Stage 2 without burning attempts.

Expected behaviors:
1. skills/plan/SKILL.md documents --ticket-driven in Arguments and the
   auto-select rule (ticket body carries the five sections).
2. The spine delegates the profile detail to references/plan-ticket-driven.md
   via a "→ Read" pointer (context economy: loaded only when the profile
   activates), and the manifest lists the new file.
3. The reference specifies: file map is the territory (no free investigation),
   red tests transcribed from the ticket's Test expectations and shown failing
   before implementation, and the "ticket underspecified" stop — commit
   nothing, post the mismatch as a ticket comment, halt with the distinct
   marker line the orchestrator recognizes.
4. The spine stays within the 350-line limit (checked by the existing
   structural test).

Test command:
    python3 -m pytest tests/test_bill169_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SPINE = REPO_ROOT / "skills" / "plan" / "SKILL.md"
REF = REPO_ROOT / "skills" / "plan" / "references" / "plan-ticket-driven.md"
MANIFEST = REPO_ROOT / "skills" / "plan" / "references" / "manifest.txt"


@pytest.fixture(scope="module")
def spine():
    return SPINE.read_text()


@pytest.fixture(scope="module")
def ref():
    assert REF.exists(), "skills/plan/references/plan-ticket-driven.md must exist"
    return REF.read_text()


def test_arguments_document_ticket_driven(spine):
    """The Arguments section must document the --ticket-driven flag."""
    args_start = spine.find("## Arguments")
    next_section = spine.find("\n## ", args_start + 1)
    args = spine[args_start:next_section]
    assert "--ticket-driven" in args


def test_spine_has_auto_select_rule(spine):
    """The profile must auto-select when the ticket body has the five sections."""
    assert "five sections" in spine, (
        "spine must state the auto-select rule keyed on the five-section standard"
    )


def test_spine_delegates_to_reference(spine):
    """Profile detail loads on demand via a → Read pointer."""
    assert "plan-ticket-driven.md" in spine
    idx = spine.find("plan-ticket-driven.md")
    assert "→ Read" in spine[max(0, idx - 200):idx], (
        "the reference must be loaded via the house '→ Read' pointer style"
    )


def test_manifest_lists_reference():
    """references/manifest.txt must list the new file (install completeness)."""
    listed = {ln.strip() for ln in MANIFEST.read_text().splitlines() if ln.strip()}
    assert "plan-ticket-driven.md" in listed


def test_ref_file_map_is_territory(ref):
    """No free investigation — the file map bounds the work."""
    assert "file map" in ref.lower()
    assert "no free investigation" in ref.lower() or "territory" in ref.lower()


def test_ref_red_tests_transcribed(ref):
    """Red tests come from the ticket's Test expectations, shown failing first."""
    assert "Test expectations" in ref
    assert "transcrib" in ref.lower()
    assert "fail" in ref.lower()


def test_ref_underspecified_stop(ref):
    """The stop: commit nothing, ticket comment with the mismatch, marker line."""
    assert "ticket underspecified" in ref.lower()
    assert "commit nothing" in ref.lower() or "commits nothing" in ref.lower()
    assert "TICKET UNDERSPECIFIED" in ref, (
        "the reference must define the exact marker line the orchestrator "
        "greps for (an all-caps literal)"
    )


def test_ref_stop_routes_to_stage2_not_attempts(ref):
    """The stop must state it routes to a rewrite without consuming attempts."""
    assert "attempt" in ref.lower()
    assert "rewrite" in ref.lower() or "stage 2" in ref.lower()
