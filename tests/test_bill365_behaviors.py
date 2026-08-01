"""
Phase 0 red tests for BILL-365 — the tamper-gate docs describe the wrong file set.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/365). Transcription, not authorship:
every assertion below is pinned by the ticket, and per the fleet brief's hard
constraint 9 the implementer may not renegotiate them. If one is wrong, the
sanctioned exit is the TICKET UNDERSPECIFIED halt (TD-4a), not an edit to this
file.

Both tamper gates derive their frozen set from the WHOLE Phase 0 commit --
`FROZEN=$(git show --name-only --format= "$RED")` in pr-slop-detection.md and
run-verification.md -- but two documents tell the agent it diffs "test files".
Today those name the same set, because the Phase 0 commit is test-only by
invariant, so the error is inert. It is still a wrong description of a mechanical
gate, in the two documents an agent reads to decide what is safe.

This ticket is documentation-only; every check here reads file content.

Test command:
    python3 -m pytest tests/test_bill365_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
AGENT_BRIEF = REPO_ROOT / "skills" / "run" / "references" / "run-agent-brief.md"
PR_SPINE = REPO_ROOT / "skills" / "pr" / "SKILL.md"

# The correction the ticket mandates. Stated in the ticket, not invented here.
CORRECT_PHRASE = "every file in the Phase 0 commit"
DERIVATION = "git show --name-only"


def _text(path):
    if not path.is_file():
        pytest.fail(f"{path} does not exist")
    return path.read_text()


class TestAgentBriefDescribesTheFrozenSetCorrectly:
    """run-agent-brief.md hard constraint 9 — the one doc a fleet agent reads."""

    def test_agent_brief_drops_the_test_files_description(self):
        assert "diffs your test files" not in _text(AGENT_BRIEF), (
            "run-agent-brief.md hard constraint 9 still says handoff verification "
            "'diffs your test files'. It diffs every file in the Phase 0 commit — "
            "FROZEN comes from `git show --name-only` against the red-test commit "
            "(run-verification.md), deliberately, so inline tests inside source "
            "files are covered by the same mechanism."
        )

    def test_agent_brief_states_the_real_file_set(self):
        assert CORRECT_PHRASE in _text(AGENT_BRIEF), (
            f"run-agent-brief.md must state the gate covers {CORRECT_PHRASE!r}"
        )


class TestPrSpineDescribesTheFrozenSetCorrectly:
    """skills/pr/SKILL.md Step 2d — the solo path's copy of the same claim."""

    def test_pr_spine_drops_the_test_files_description(self):
        assert "Diff the test files" not in _text(PR_SPINE), (
            "pr/SKILL.md Step 2d still says 'Diff the test files across the range'. "
            "Step 2d's frozen set is every file in the Phase 0 commit "
            "(pr-slop-detection.md's FROZEN derivation), not a test-file glob."
        )

    def test_pr_spine_states_the_real_file_set(self):
        assert CORRECT_PHRASE in _text(PR_SPINE), (
            f"pr/SKILL.md Step 2d must state the gate covers {CORRECT_PHRASE!r}"
        )


class TestDerivationIsCheckableFromTheDocsAnAgentReads:
    def test_at_least_one_doc_names_the_derivation(self):
        # The ticket asks for the derivation to be named in at least one of the two,
        # so a reader can verify the claim instead of trusting it.
        named_in = [
            p.name for p in (AGENT_BRIEF, PR_SPINE) if DERIVATION in _text(p)
        ]
        assert named_in, (
            f"neither run-agent-brief.md nor pr/SKILL.md names the {DERIVATION!r} "
            "derivation — an agent has no way to check the corrected claim against "
            "the script that implements it"
        )
